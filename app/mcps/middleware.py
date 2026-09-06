'''FastMCP middleware that keeps the confidence log honest.'''

from __future__ import annotations

import logging

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

from ..domain.observer import ConfidenceObserver

logger = logging.getLogger('jacquinho.confidence')


class ConfidenceMiddleware(Middleware):
    '''Scores the evidence trail after every tool call, without being asked.

    The agent can forget to grade its own answer; the server cannot forget to
    watch. Every evidence-bearing result folds into a running score, and the
    badge is written to the log right after the call that changed it - which is
    where it can be read next to the message it belongs to.
    '''

    # Tools that commit her to something. Advice can be wrong and be corrected;
    # these cost money or go on a menu, so they are refused outright until the
    # viability gate has passed in this session. This is the difference between
    # asking the agent not to skip a step and it not being able to.
    # The key used when no MCP session header reaches the middleware, which is
    # every local run. Named so other code can ask the observer the same thing.
    SESSION_FALLBACK = 'local'

    # Each discovery runs several web searches. A real conversation spent twenty
    # of them in one turn - the first two found dishes, the next eighteen came
    # back empty, and the turn ended with no reply at all. Searching is not free
    # and an empty result is an answer, not an invitation to try again.
    SEARCH_TOOL = 'dishes_discover_dishes'
    SEARCH_BUDGET = 5

    NEEDS_GATE = {
        'pricing_price_scenarios': 'nenhum preço sai antes do gate de viabilidade',
        'menu_add_dish': 'nenhum prato entra no cardápio antes do gate',
        'budget_reserve_purchase': 'nenhum dinheiro é reservado antes do gate',
    }

    # The observer scores the evidence trail; it never sees the sentence. A
    # model that gathers impeccable evidence and then writes a different number
    # still scores well, and only the judge - which reads the draft - catches
    # that. So the one irreversible act, putting a dish on the menu, additionally
    # requires that an assessment happened for that dish. It does not make the
    # observer read the message; it makes the thing that does read it
    # unavoidable at the moment it matters.
    # Cost before price, for the same reason: a price is only meaningful over a
    # cost that was calculated for THIS dish.
    NEEDS_CMV = {
        'pricing_price_scenarios': (
            'nenhum preço sai antes de pricing_calculate_cmv para este prato'
        ),
    }

    # Moving on is the failure. When a dish dies - or comes back - she has to
    # hear it before anything else happens, and three rounds of stronger wording
    # in tool results did not achieve that: the model filed the answer, honoured
    # it from then on, and replied about something else. So these are refused
    # while the session owes her a verdict. Reading is never refused: the profile,
    # the pantry, the history and the gate stay open, because checking the facts
    # before speaking is exactly what it should be doing here.
    MOVING_ON = frozenset({
        'dishes_survey_categories',
        'dishes_discover_dishes',
        'recipes_search_recipes',
        'recipes_save_candidate',
        'recipes_check_pantry_coverage',
        'pricing_calculate_cmv',
        'pricing_price_scenarios',
        'market_research_dish_prices',
        'budget_reserve_purchase',
        'menu_add_dish',
        # Asking her the next question while the last answer is unanswered is
        # the exact shape of the failure, so it counts as moving on too.
        'kitchen_next_questions',
    })

    NEEDS_ASSESSMENT = {
        'menu_add_dish': (
            'nenhum prato entra no cardápio sem passar por '
            'confidence_assess_answer. O observador pontua a evidência, mas quem '
            'lê o que você escreveu é o julgamento.'
        ),
    }

    def __init__(self, observer: ConfidenceObserver, db=None):
        self.observer = observer
        self.db = db

    @staticmethod
    def _payload(result) -> dict | None:
        '''Pull the structured content out of a tool result, if it has any.'''
        data = getattr(result, 'structured_content', None)
        if isinstance(data, dict):
            # FastMCP wraps a bare return value under 'result'.
            inner = data.get('result')
            return inner if isinstance(inner, dict) else data
        return None

    def _attach_state(self, result, session: str, dish: str | None) -> None:
        '''Put where-we-are into the result the agent is about to read.

        A rule stated once in a prompt is a rule the model can drift away from.
        A field in every tool result is one it cannot miss.
        '''
        payload = getattr(result, 'structured_content', None)
        if not isinstance(payload, dict):
            return
        state = self.observer.state_of(session, dish)
        inner = payload.get('result')
        target = inner if isinstance(inner, dict) else payload
        target['conversation_state'] = state

    def _persist(self, tool: str, report: dict) -> None:
        if self.db is None:
            return
        try:
            from psycopg.types.json import Json

            self.db.execute(
                '''INSERT INTO answer_assessments
                       (dish, draft_answer, mode, claim, deterministic_score,
                        final_score, band, badge, blocking_issues, signals)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)''',
                (report.get('dish') or f'(observado após {tool})', '', 'observer',
                 report['claim'],
                 report['score'], report['score'], report['band'], report['badge'],
                 Json(report['blocking_issues']), Json(report['signals'])),
            )
        except Exception:
            # An audit trail that breaks the conversation is worse than no trail.
            pass

    @staticmethod
    def _session(context) -> str:
        '''One trail per client connection, so two conversations do not share one.

        Not ``ctx.session_id``: over HTTP that is a fresh UUID per request, so
        every call would land in its own trail and nothing would accumulate.
        The MCP session header is the connection, which is what a conversation
        actually is.
        '''
        try:
            from fastmcp.server.dependencies import get_http_headers

            headers = get_http_headers() or {}
            value = headers.get('mcp-session-id')
            if isinstance(value, str) and value:
                return value
        except Exception:
            pass
        # In-memory transport, or a client that sends no session header: one
        # conversation at a time, which is what a local run is.
        return ConfidenceMiddleware.SESSION_FALLBACK

    @staticmethod
    def _dish(context) -> str | None:
        '''The dish this call is about, when the call names one.'''
        arguments = getattr(context.message, 'arguments', None) or {}
        value = arguments.get('dish')
        return value if isinstance(value, str) and value.strip() else None

    async def on_call_tool(self, context, call_next):
        name = getattr(context.message, 'name', '') or '?'
        dish = self._dish(context)
        reason = self.NEEDS_GATE.get(name)
        # The gate is checked for THIS dish. Approving the parmegiana and then
        # asking about lasanha used to un-approve the parmegiana.
        session = self._session(context)
        if reason and not self.observer.gate_approved(session, dish):
            raise ToolError(
                f'Recusado: {reason}. Rode kitchen_analyse_recipe_requirements com o '
                'texto da receita, ou kitchen_check_feasibility com o que o prato '
                'exige, e só volte aqui quando o veredito for approved. Ler o perfil '
                'da cozinha não conta: ler não é verificar.'
            )

        owed = self.observer.owed_announcement(session)
        if owed and not owed.get('drafted') and name in self.MOVING_ON:
            raise ToolError(
                f'Recusado: {owed["say_now"]} Enquanto isso não for feito, '
                'ferramentas que seguem a conversa estão fechadas. Escreva a frase '
                'para ela e passe-a em kitchen_announce_verdict.'
            )

        if name == self.SEARCH_TOOL:
            done = self.observer.searches_done(session)
            if done >= self.SEARCH_BUDGET:
                raise ToolError(
                    f'Recusado: já foram {done} buscas nesta conversa. Trabalhe com '
                    'o que você achou - recipes_next_candidate lista o que está '
                    'aberto - ou pergunte a ela o que ela já cozinha bem. Uma '
                    'categoria que voltou vazia não fica cheia na décima tentativa.'
                )
            self.observer.count_search(session)

        needs_cost = self.NEEDS_CMV.get(name)
        if needs_cost and not self.observer.cmv_ready(session, dish):
            raise ToolError(
                f'Recusado: {needs_cost}. Rode pricing_calculate_cmv com as linhas '
                'da receita, nomeando o prato, e volte com o cmv_per_portion que '
                'ele devolver.'
            )

        needs_judgement = self.NEEDS_ASSESSMENT.get(name)
        if needs_judgement and not self.observer.assessed(session, dish):
            raise ToolError(f'Recusado: {needs_judgement}')

        result = await call_next(context)
        try:
            payload = self._payload(result)
            # An explicit assessment declares what the message asserts; that
            # beats guessing it from whichever tool happened to run last.
            if name == 'confidence_assess_answer' and isinstance(payload, dict):
                declared = (payload.get('deterministic') or {}).get('claim')
                if declared:
                    self.observer.declare_claim(session, dish, declared)
            # Every figure, not just the six evidence slots: the numbers she
            # acts on come out of pricing and the menu, which feed no slot.
            arguments = getattr(context.message, 'arguments', None) or {}
            self.observer.remember_numbers(session, name, payload, arguments, dish)
            if name == 'menu_add_dish' and isinstance(payload, dict):
                self.observer.note_menu(session, dish, payload)
            if name == 'pricing_reopen_recipe' and payload and payload.get('reopened'):
                from ..domain.claims import ClaimKind

                ledger = self.observer.commitments(session)
                for kind in (ClaimKind.COST, ClaimKind.PRICE, ClaimKind.PROFIT,
                             ClaimKind.RECEIPT):
                    ledger.authorise_revision(
                        self.observer.key_for(payload.get('dish')) or '', kind
                    )
            report = self.observer.record(session, name, payload, dish)
            # Every call gets a log line, so a watcher never looks dead; only a
            # call that actually changed the picture earns an audit row.
            if report['moved']:
                self._persist(name, report)
        except Exception as error:
            # Observation must never break the call it is observing.
            logger.debug('confidence observer skipped %s: %s', name, error)

        # Deliberately outside the block above. If the state cannot be attached
        # the agent loses the thread of the conversation, and a failure swallowed
        # here is exactly how that goes unnoticed.
        try:
            self._attach_state(result, session, dish)
        except Exception as error:
            logger.warning('conversation state not attached: %s', error)
        return result
