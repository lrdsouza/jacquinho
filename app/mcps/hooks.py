'''HTTP routes the agent runtime calls, not the model.

Everything else in this server is reached by the model deciding to reach it,
which is exactly the weakness two failures kept exploiting.

The first: a confirmed answer is a claim about something Dona Maria said, and
the only record of what she said was the transcript the model itself wrote. It
once recorded that she owned an oven nobody had asked about and priced a whole
lasagna on it. A quote checked against a transcript the quoter authored is not a
check.

The second: the server decides a dish is dead, hands over the sentence, refuses
every tool that means moving on - and still never sees the message that
actually reaches her. It could guarantee the sentence was written. Not that it
was sent.

Hermes fires shell hooks around each turn. ``pre_llm_call`` carries her raw
message before the model sees it; ``post_llm_call`` carries the reply after the
tool loop ends. Two scripts curl them here. Her words land in Redis marked as
captured, and the verdict debt is settled by the text she actually received -
not by the agent's promise to send it.

A shell hook cannot rewrite the outgoing message; only a Python plugin can. So
this does not stop a bad turn from being sent. What it does is refuse to
forget: the debt stays open, and the next turn cannot move on either.
'''

from __future__ import annotations

import json
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..domain.audit import MessageAudit
from ..domain.claims import ClaimPipeline
from ..domain.memory import ConversationStore
from ..domain.pacing import check as pacing_check
from ..domain.verdict import VerdictAnnouncement

logger = logging.getLogger('jacquinho.hooks')

# One bucket for what the runtime captured, so it is never confused with what
# the agent chose to write down.
CAPTURED_SESSION = 'real'

# Not every 'user' turn is a user. Hermes runs a background-review pass that
# speaks to the agent in her seat - 'Review the conversation above and update
# the skill library'. Captured verbatim, it becomes something the server would
# accept as words Dona Maria said, which is the exact hole this file exists to
# close. Hermes filters these by the same prefixes internally.
HARNESS_PREFIXES = (
    'review the conversation above and update the skill library',
    'review the conversation above and consider saving to memory',
)


class HookRoutes:
    '''Wires the agent runtime's turn boundaries into the server's state.'''

    def __init__(self, root, store: ConversationStore, observer):
        self.root = root
        self.store = store
        self.observer = observer

    @staticmethod
    async def _body(request: Request) -> dict:
        '''The hook payload, flattened.

        Hermes promotes only a handful of keys to the top level and files the
        rest under ``extra`` - so ``user_message`` and ``assistant_response``,
        the only two fields these routes exist for, arrive nested. Reading the
        top level alone finds nothing, and finds it silently.
        '''
        try:
            raw = await request.body()
            data = json.loads(raw or b'{}')
        except (json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        extra = data.get('extra')
        return {**(extra if isinstance(extra, dict) else {}), **data}

    def _session(self) -> str:
        from .middleware import ConfidenceMiddleware

        return ConfidenceMiddleware.SESSION_FALLBACK

    @staticmethod
    def _is_the_harness(text: str) -> bool:
        return text.strip().lower().startswith(HARNESS_PREFIXES)

    def _save(self, role: str, content: str) -> None:
        if not content.strip() or self._is_the_harness(content):
            return
        try:
            self.store.save_turn(
                CAPTURED_SESSION, role, content, [],
                source=ConversationStore.CAPTURED,
            )
        except Exception as error:
            # Losing a turn costs a verification, not the consultation.
            logger.warning('turn not captured: %s', error)

    def _judge_claims(self, session: str, reply: str) -> None:
        """Decompose the delivered message and check every claim in it.

        This is the only place the whole pipeline can run: it needs the message
        she actually received, the tool facts of the turn, and what she was told
        before. Deterministic, so it runs on every turn without costing a model
        call.
        """
        dish = self.observer.dish_in_play(session)
        judgement = ClaimPipeline.run(
            message=reply,
            subject=dish or '(a consultoria)',
            known_numbers=self.observer.numbers_seen(session),
            facts=self.observer.facts_for(session),
            ledger=self.observer.commitments(session),
        )
        if judgement.verifiable == 0:
            return
        payload = {
            'dish': dish, 'score': judgement.score, 'verdict': judgement.verdict,
            'verifiable': judgement.verifiable, 'grounded': judgement.grounded,
            'contradictions': judgement.contradictions,
        }
        # A count with no example is not actionable: knowing that one figure of
        # thirteen has no tool behind it says nothing about which one to look at.
        loose = [
            {'quoted': c.claim.quoted, 'kind': c.claim.kind.value}
            for c in judgement.claims if c.verdict.value == 'ungrounded'
        ]
        if loose:
            payload['sem_lastro'] = loose
        if judgement.contradictions:
            payload['detail'] = [
                c.note for c in judgement.claims
                if c.verdict.value == 'contradicts_earlier_turn'
            ]
            logger.warning('jacquinho.claims %s',
                           json.dumps(payload, ensure_ascii=False))
        else:
            level = logger.warning if loose else logger.info
            level('jacquinho.claims %s', json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _log_pacing(reply: str) -> None:
        """A wall that went out anyway leaves a line in the log.

        The turn boundary cannot rewrite what she already read - only
        pre_tool_call can block - so this is telemetry, not a gate. The gate is
        `message_pacing` inside `confidence_assess_answer`, which the agent reads
        while the draft is still a draft. This says how often the gate is being
        walked past, which is the only way to know whether it works.
        """
        report = pacing_check(reply)
        if report['one_subject_per_part']:
            return
        logger.warning(
            'jacquinho.pacing %s',
            json.dumps(
                {
                    'words': report['words'],
                    'parts': report['parts'],
                    'subjects': report['subjects'],
                    'questions': len(report['questions']),
                    'why': report['split_because'],
                },
                ensure_ascii=False,
            ),
        )

    def _audit_figures(self, session: str, reply: str) -> None:
        '''Every R$ in the message, against every R$ the tools produced.

        `confidence_audit_figures` does this on demand, and the agent has to
        remember to ask. It did not: a closing message told her the strogonoff
        left R$ 7,26 per marmita when the tool had returned R$ 5,27, because the
        model subtracted cost from price in prose and forgot the platform fee.
        The ledger had the right number the whole time.

        Nothing here can unsend that message. What it can do is stop the error
        from being invisible, which is the difference between a bug and a
        rumour.
        '''
        known = self.observer.numbers_seen(session)
        if not known or not reply.strip():
            return
        report = MessageAudit.check(reply, {'tools': sorted(known)})
        if report['verdict'] == 'clean':
            return
        logger.warning(
            'jacquinho.figures %s',
            json.dumps({'unsupported': report['unsupported'],
                        'stated': report['figures_stated']}, ensure_ascii=False),
        )

    def register(self) -> None:
        @self.root.custom_route('/hooks/her-message', methods=['POST'])
        async def her_message(request: Request) -> JSONResponse:
            '''Her message, straight off the wire, before the model reads it.'''
            payload = await self._body(request)
            text = str(payload.get('user_message') or '')
            self._save('dona_maria', text)
            if self._is_the_harness(text):
                # The curator is not the consultation. Do not nudge it about a
                # verdict owed to someone it is not talking to.
                return JSONResponse({})

            # Free ride: the turn is starting and the hook can hand the model
            # context. If she is owed a verdict, that is the first thing it
            # should know, before it plans anything else.
            owed = self.observer.owed_announcement(self._session())
            if not owed:
                return JSONResponse({})
            return JSONResponse({'context': owed['say_now']})

        @self.root.custom_route('/hooks/final-message', methods=['POST'])
        async def final_message(request: Request) -> JSONResponse:
            '''The reply as she will read it. The only place that is knowable.'''
            payload = await self._body(request)
            reply = str(payload.get('assistant_response') or '')
            if self._is_the_harness(str(payload.get('user_message') or '')):
                return JSONResponse({})
            self._save('agent', reply)

            session = self._session()
            self._audit_figures(session, reply)
            # Only now is a value a promise: it reached her.
            self._judge_claims(session, reply)
            self.observer.mark_costs_told(session, reply)
            self._log_pacing(reply)

            owed = self.observer.owed_announcement(session)
            if not owed:
                return JSONResponse({})

            check = VerdictAnnouncement.check(
                reply, owed.get('dish', ''), owed.get('items', []),
            )
            if check['ok']:
                self.observer.settle_announcement(session)
                logger.info(
                    'jacquinho.verdict %s',
                    json.dumps({'dish': owed.get('dish'), 'delivered': True,
                                'kind': owed.get('kind')}, ensure_ascii=False),
                )
                return JSONResponse({})

            # She did not hear it. Reopen: the next turn starts with every tool
            # that means moving on shut again, drafted sentence or not.
            self.observer.reopen_announcement(session)
            logger.warning(
                'jacquinho.verdict %s',
                json.dumps({'dish': owed.get('dish'), 'delivered': False,
                            'missing': check['missing']}, ensure_ascii=False),
            )
            return JSONResponse({'context': owed['say_now']})
