'''Redis: what is hot, rewritten constantly, and worthless once superseded.

Only two things live here. The conversation window, which is appended to on
every turn and read on every turn, and judging tickets, which exist for the
length of one exchange. Everything that is a record about Dona Maria - what she
owns, what she ruled out, what she committed to buy, what went on the menu -
lives in Postgres instead, because those must survive eviction and be asked
relational questions.
'''

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import redis

from .units import UnitConverter


class MemoryUnavailable(RuntimeError):
    '''Raised when Redis cannot be reached.'''


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class RedisBackend:
    '''Thin connection holder that fails loudly instead of silently dropping data.'''

    def __init__(self, url: str, timeout: float = 5.0):
        self.url = url
        self.timeout = timeout
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                self.url,
                decode_responses=True,
                socket_connect_timeout=self.timeout,
                socket_timeout=self.timeout,
            )
        return self._client

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except redis.RedisError as error:
            raise MemoryUnavailable(f'redis unreachable at {self.url}: {error}') from error

    def guard(self, action, *args, **kwargs):
        try:
            return action(*args, **kwargs)
        except redis.RedisError as error:
            raise MemoryUnavailable(f'redis error: {error}') from error


class ConversationStore:
    '''The chat, as a bounded window plus one running summary.

    The context handed back is the last WINDOW turns and a single summary
    message standing in for everything before them. Once WINDOW new turns have
    accumulated since the last summary, the summary is rewritten to absorb
    them. Older turns stay in Redis: the trimming is of what the agent is
    handed, not of what is kept.
    '''

    SESSIONS_KEY = 'chat:sessions'
    MAX_TURNS = 2000
    # 20 turns of context: roughly ten from her and ten from the agent.
    WINDOW = 20

    def __init__(self, backend: RedisBackend):
        self.backend = backend

    @staticmethod
    def _turns_key(session: str) -> str:
        return f'chat:{session}:turns'

    @staticmethod
    def _summary_key(session: str) -> str:
        return f'chat:{session}:summary'

    # A turn the agent typed into a tool, versus one captured from the wire
    # before the model saw it. The difference matters exactly once, and it is
    # the difference that stops the agent inventing her answers.
    AUTHORED = 'agent'
    CAPTURED = 'hook'

    def save_turn(
        self, session: str, role: str, content: str, tags: list[str],
        source: str = AUTHORED,
    ) -> dict:
        entry = {
            'role': role,
            'content': content,
            'tags': tags,
            'source': source,
            'at': _now(),
        }
        key = self._turns_key(session)

        def write():
            pipe = self.backend.client.pipeline()
            pipe.rpush(key, json.dumps(entry, ensure_ascii=False))
            pipe.ltrim(key, -self.MAX_TURNS, -1)
            pipe.sadd(self.SESSIONS_KEY, session)
            pipe.execute()
            return self.backend.client.llen(key)

        total = self.backend.guard(write)
        return {'saved': True, 'session': session, 'turns_in_session': total, **entry}

    def history(self, session: str, limit: int) -> list[dict]:
        raw = self.backend.guard(
            self.backend.client.lrange, self._turns_key(session), -limit, -1
        )
        return [json.loads(item) for item in raw]

    def search(self, session: str, term: str, limit: int) -> list[dict]:
        needle = UnitConverter.normalise_text(term)
        found = [
            turn
            for turn in self.history(session, self.MAX_TURNS)
            if needle in UnitConverter.normalise_text(turn['content'])
        ]
        return found[-limit:]

    def sessions(self) -> list[str]:
        return sorted(self.backend.guard(self.backend.client.smembers, self.SESSIONS_KEY))

    def she_said(self, quote: str) -> dict:
        '''Did Dona Maria actually say this, anywhere in the conversation?

        The agent once recorded that she owned an oven she had never been asked
        about, and priced a whole lasagna on top of it. Nothing in the server
        could contradict that, because the only record of what she said lived
        in the model's context. It lives here now, so a claim about her words
        can be checked against her words.

        Searched across sessions on purpose: the session id the agent uses for
        the chat is its own choice, and a quote in the wrong bucket is still
        something she said.
        '''
        needle = UnitConverter.normalise_text(quote)
        if not needle:
            return {'said': False, 'turns_on_record': 0, 'match': None,
                    'checked_against': 'nada'}

        hers = [
            turn
            for session in self.sessions()
            for turn in self.history(session, self.MAX_TURNS)
            if turn.get('role') == 'dona_maria'
        ]
        # If anything was captured from the wire, only that counts. Otherwise
        # the agent could write her answer into the transcript and then quote
        # itself, which is the same fabrication wearing a receipt.
        captured = [t for t in hers if t.get('source') == self.CAPTURED]
        pool, provenance = (
            (captured, 'falas capturadas antes do modelo ver')
            if captured
            else (hers, 'falas salvas pelo agente')
        )
        for turn in pool:
            if needle in UnitConverter.normalise_text(turn['content']):
                return {'said': True, 'turns_on_record': len(pool), 'match': turn,
                        'checked_against': provenance}
        return {'said': False, 'turns_on_record': len(pool), 'match': None,
                'checked_against': provenance}

    # A batch size, as she says it: "faço 8 marmitas por fornada", "rende 12",
    # "essa fornada eu faço maior, 18 marmitas".
    BATCH_PATTERNS = (
        re.compile(r'(\d{1,3})\s*(?:marmita|porc|porç|por[çc][õo]es|unidade)', re.I),
        re.compile(r'(?:rende|fa[çc]o|fazer|sai[ae]m?)\s*(\d{1,3})\b', re.I),
    )

    def batch_size_she_said(self) -> dict | None:
        """The last batch size she named out loud, if she named one.

        `portions` is her number, not a default. It arrived as `= 1` and the
        agent took the default: her escondidinho was costed for a batch of one
        while she had said "faço 8 marmitas por fornada" in her first message,
        so the pantry lost an eighth of what the fornada actually eats and the
        shopping list came out short. A default that is wrong seven times out of
        eight is worse than a missing argument.

        Read from what the runtime captured, never from what the agent typed,
        for the same reason `she_said` is.
        """
        hers = [
            turn
            for session in self.sessions()
            for turn in self.history(session, self.MAX_TURNS)
            if turn.get('role') == 'dona_maria'
        ]
        captured = [t for t in hers if t.get('source') == self.CAPTURED]
        # Newest first, by the clock and not by which session came back first:
        # she may have said 8 in one breath and 18 in the next, and the answer
        # is the last one she said, not the last one the iteration happened to
        # reach.
        pool = sorted(
            captured or hers, key=lambda turn: turn.get('at') or '', reverse=True
        )
        for turn in pool:
            for pattern in self.BATCH_PATTERNS:
                found = pattern.search(turn.get('content') or '')
                if found:
                    size = int(found.group(1))
                    if 1 < size <= 200:
                        return {'portions': size, 'her_words': turn['content']}
        return None

    # ------------------------------------------------------- summary window

    def _summary(self, session: str) -> dict:
        raw = self.backend.guard(self.backend.client.get, self._summary_key(session))
        return json.loads(raw) if raw else {'text': '', 'covers_turns': 0, 'at': None}

    def total_turns(self, session: str) -> int:
        return int(
            self.backend.guard(self.backend.client.llen, self._turns_key(session)) or 0
        )

    def context(self, session: str) -> dict:
        """What the agent should be holding: the summary plus the last window."""
        summary = self._summary(session)
        total = self.total_turns(session)
        covered = summary['covers_turns']
        window = self.history(session, self.WINDOW)
        unsummarised = max(0, total - covered)

        return {
            'session': session,
            'summary': summary['text'] or None,
            'summary_covers_turns': covered,
            'recent_turns': window,
            'turns_in_window': len(window),
            'total_turns': total,
            'turns_since_summary': unsummarised,
            'needs_new_summary': unsummarised >= self.WINDOW,
        }

    def turns_to_summarise(self, session: str) -> list[dict]:
        """The turns a new summary has to absorb: everything not yet covered."""
        summary = self._summary(session)
        raw = self.backend.guard(
            self.backend.client.lrange,
            self._turns_key(session),
            summary['covers_turns'],
            -1,
        )
        return [json.loads(item) for item in raw]

    def save_summary(self, session: str, text: str, covers_turns: int) -> dict:
        entry = {'text': text, 'covers_turns': covers_turns, 'at': _now()}
        self.backend.guard(
            self.backend.client.set,
            self._summary_key(session),
            json.dumps(entry, ensure_ascii=False),
        )
        return entry
