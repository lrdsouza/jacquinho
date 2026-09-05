'''MCP surface for the chat transcript, stored in Redis.'''

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..domain.memory import ConversationStore, MemoryUnavailable, RedisBackend
from .base import BaseMCP


class ConversationMCP(BaseMCP):
    '''Keeps the conversation so nothing she said once is asked twice.'''

    name = 'chat'
    instructions = (
        'Persist the conversation as it happens. Save every turn with save_turn. '
        'Hold context with get_context, which returns the last twenty turns plus '
        'one running summary of everything before them. When it says '
        'needs_new_summary, write the summary yourself from '
        'turns_awaiting_summary and post it with save_summary. Before asking her '
        'anything, search_history first: repeating a question she already '
        'answered is the fastest way to lose her.'
    )

    def __init__(self, settings):
        self.backend = RedisBackend(settings.redis_url)
        self.store = ConversationStore(self.backend)
        super().__init__(settings)

    def register(self) -> None:
        @self.mcp.tool
        def save_turn(
            session: Annotated[str, Field(description='Conversation id, stable across the chat.')],
            role: Annotated[Literal['dona_maria', 'agent'], Field(description='Who spoke.')],
            content: Annotated[str, Field(description='What was said, in her own words when it is hers.')],
            tags: Annotated[list[str], Field(description="Topics, e.g. ['forno', 'orcamento', 'parmegiana'].")] = [],
        ) -> dict:
            '''Record one turn of the conversation.

            Save her answers verbatim. A paraphrase loses the detail that later
            turns out to matter, like 'o forno acende mas nao esquenta direito'.
            '''
            try:
                return self.store.save_turn(session, role, content, tags)
            except MemoryUnavailable as error:
                return {'saved': False, 'error': str(error)}

        @self.mcp.tool
        def recent_history(
            session: Annotated[str, Field(description='Conversation id.')],
            limit: Annotated[int, Field(ge=1, le=200, description='How many turns back.')] = 20,
        ) -> dict:
            '''Read the last turns of a conversation.'''
            try:
                turns = self.store.history(session, limit)
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {'available': True, 'session': session, 'turns': turns}

        @self.mcp.tool
        def search_history(
            session: Annotated[str, Field(description='Conversation id.')],
            term: Annotated[str, Field(description="What to look for, e.g. 'forno' or 'geladeira'.")],
            limit: Annotated[int, Field(ge=1, le=50, description='Maximum matches.')] = 10,
        ) -> dict:
            '''Find what she already said about something, accent-insensitive.'''
            try:
                matches = self.store.search(session, term, limit)
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {
                'available': True,
                'term': term,
                'match_count': len(matches),
                'matches': matches,
                'hint': (
                    'Nothing found does not mean she never said it: it may predate '
                    'this session. Check kitchen_read_kitchen_profile too.'
                )
                if not matches
                else None,
            }

        @self.mcp.tool
        def list_sessions() -> dict:
            '''List every stored conversation.'''
            try:
                return {'available': True, 'sessions': self.store.sessions()}
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}

        @self.mcp.tool
        def get_context(
            session: Annotated[str, Field(description='Conversation id.')],
        ) -> dict:
            """The context to hold: the last twenty turns plus one summary.

            Everything older is represented by a single running summary rather
            than replayed. When ``needs_new_summary`` is true, twenty turns have
            piled up since the summary was last written and it is time to rewrite
            it with turns_awaiting_summary and save_summary.
            """
            try:
                context = self.store.context(session)
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {
                'available': True,
                **context,
                'next_step': (
                    'Call turns_awaiting_summary, write one paragraph covering it '
                    'in her own terms, and post it with save_summary.'
                    if context['needs_new_summary']
                    else 'Context is current. Carry on.'
                ),
            }

        @self.mcp.tool
        def turns_awaiting_summary(
            session: Annotated[str, Field(description='Conversation id.')],
        ) -> dict:
            """The turns a new summary has to absorb.

            Everything the current summary does not yet cover. Summarise these
            keeping what a later turn would need: what she owns, what she ruled
            out and why, what she chose, what is still open. Drop the pleasantries.
            """
            try:
                turns = self.store.turns_to_summarise(session)
                context = self.store.context(session)
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {
                'available': True,
                'session': session,
                'turn_count': len(turns),
                'previous_summary': context['summary'],
                'turns': turns,
                'covers_up_to_turn': context['total_turns'],
                'instruction': (
                    'Fold the previous summary and these turns into ONE paragraph. '
                    'Keep decisions, capabilities and rejections with their reasons; '
                    'drop small talk. Then call save_summary with covers_turns set '
                    'to covers_up_to_turn.'
                ),
            }

        @self.mcp.tool
        def save_summary(
            session: Annotated[str, Field(description='Conversation id.')],
            summary: Annotated[str, Field(description='The rewritten running summary.')],
            covers_turns: Annotated[int, Field(ge=0, description='covers_up_to_turn from turns_awaiting_summary.')],
        ) -> dict:
            """Replace the running summary with a rewritten one."""
            try:
                entry = self.store.save_summary(session, summary, covers_turns)
            except MemoryUnavailable as error:
                return {'saved': False, 'error': str(error)}
            return {'saved': True, **entry}
