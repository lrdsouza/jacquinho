'''MCP surface for her opinions on dishes and the launch menu itself.'''

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ..domain.catalogue import BlockReason, CatalogueUnavailable as MemoryUnavailable
from ..domain.catalogue import DishFeedbackStore, LaunchMenuStore, RecipeCatalogue
from .base import BaseMCP


class MenuMCP(BaseMCP):
    '''Carries a dish from her opinion of it to the launch menu.'''

    name = 'menu'
    instructions = (
        'Every candidate dish gets record_feedback before anything else: does she '
        'want to cook it, and does she see a problem with it. A dish she dislikes '
        'is dead however good the numbers look. Only add_dish once the gate '
        'passed, the CMV is complete, the price is market-grounded and she chose '
        'it. Before offering to accept anything, call acceptance_check: it lists '
        'every check still standing between this dish and the menu, including '
        'the questions she has not been asked. build_launch_menu is the '
        'deliverable the whole conversation is for.'
    )

    def __init__(self, settings, db, observer=None):
        self.db = db
        self.observer = observer
        self.feedback = DishFeedbackStore(db)
        self.menu = LaunchMenuStore(db)
        self.catalogue = RecipeCatalogue(db)
        super().__init__(settings)

    def _shelve(self, dish: str, comment: str) -> list[str]:
        '''Take a dish she does not want off the table, here and now.

        The next_step used to say "then call recipes_reject_candidate", and a
        second call the agent has to remember is a second call it skips. It did:
        she said the parmegiana gives her too much work and never turns out
        well, the agent answered "anotado, nem entra na conversa", and nothing
        was written anywhere. Twenty turns later the conversation window has
        rolled and the parmegiana is a fresh idea again.

        A dish she named herself is usually not in the catalogue, so it gets the
        same honest stub a blocked dish gets.
        '''
        try:
            if self.catalogue.get(dish) is None:
                self.catalogue.save(
                    dish=dish, source_url='', source_title='dito por ela na conversa',
                    ingredients=[], equipment=[], techniques=[], pantry_coverage=0.0,
                    notes='Prato que ela recusou; a receita nunca foi buscada.',
                )
            recipe = self.catalogue.get(dish)
            if recipe and any(
                b.get('reason') == BlockReason.DISLIKED for b in recipe.active_blocks
            ):
                return []
            self.catalogue.block(
                dish, BlockReason.DISLIKED, None,
                comment or 'ela não quer cozinhar este prato',
            )
        except Exception:
            return []
        return [dish]

    def register(self) -> None:
        @self.mcp.tool
        def record_feedback(
            dish: Annotated[str, Field(description='Dish you showed her.')],
            likes_cooking: Annotated[bool, Field(description='Does she actually want to cook this?')],
            comment: Annotated[str, Field(description='Her reaction, in her own words.')],
            impediments: Annotated[list[str], Field(description="Anything she flagged, e.g. ['da muito trabalho', 'nao tenho forma'].")] = [],
        ) -> dict:
            '''Record what she thinks of a dish you proposed.

            The brief asks this of every candidate: whether she likes cooking it
            and whether she sees an impediment. Her impediments are leads for
            kitchen_elicitation_gaps, not just notes.
            '''
            try:
                entry = self.feedback.record(dish, likes_cooking, comment, impediments)
            except MemoryUnavailable as error:
                return {'saved': False, 'error': str(error)}
            # Taste is a durable fact about her, not a note in this session.
            shelved = self._shelve(dish, comment) if not likes_cooking else []
            return {
                'saved': True,
                'shelved_for_good': shelved,
                **entry,
                'next_step': (
                    'Já tirei este prato da mesa, com o motivo dela. Vá para '
                    'recipes_next_candidate e ofereça a próxima opção. Não tente '
                    'convencê-la, e não volte a oferecer este.'
                    if not likes_cooking
                    else (
                        'She raised something. Take each impediment to '
                        'kitchen_elicitation_gaps; if it turns out to block the '
                        "dish, call recipes_reject_candidate with reason "
                        "'impediment' and move to recipes_next_candidate."
                        if impediments
                        else 'No impediment raised. Continue with the evaluate_dish '
                        'prompt.'
                    )
                ),
            }

        @self.mcp.tool
        def list_feedback() -> dict:
            '''Everything she has said about dishes so far.'''
            try:
                entries = self.feedback.all()
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {
                'available': True,
                'liked': [e['dish'] for e in entries if e['likes_cooking']],
                'rejected': [e['dish'] for e in entries if not e['likes_cooking']],
                'entries': entries,
            }

        @self.mcp.tool
        def add_dish(
            dish: Annotated[str, Field(description='Dish she accepted.')],
            category: Annotated[str, Field(description='Category id from dishes_list_categories.')],
            cmv: Annotated[float, Field(gt=0, description='CMV per portion from pricing_calculate_cmv.')],
            price: Annotated[float, Field(gt=0, description='The price SHE chose.')],
            confidence_band: Annotated[str, Field(description="Band from confidence_assess_answer: 'high', 'medium' or 'low'.")],
            notes: Annotated[str, Field(description='Anything she should remember about this dish.')] = '',
        ) -> dict:
            '''Put an accepted dish on the launch menu.

            Only after the viability gate passed, the CMV was complete, the price
            was grounded in the market, and she picked it herself.
            '''
            try:
                entry = self.menu.add(
                    dish, category, cmv, price, self.settings.platform_fee,
                    confidence_band, notes,
                )
            except MemoryUnavailable as error:
                return {'added': False, 'error': str(error)}
            return {'added': True, **entry}

        @self.mcp.tool
        def remove_dish(
            dish: Annotated[str, Field(description='Dish to take off the menu.')],
        ) -> dict:
            '''Take a dish off the launch menu.'''
            try:
                return {'removed': self.menu.remove(dish)}
            except MemoryUnavailable as error:
                return {'removed': False, 'error': str(error)}

        @self.mcp.tool
        def build_launch_menu() -> dict:
            '''The launch menu: every accepted dish, with cost, price and profit.

            This is where the consultation is meant to end. It flags any dish
            that got on with weak evidence.
            '''
            try:
                return {'available': True, **self.menu.summary()}
            except MemoryUnavailable as error:
                return {'available': False, 'error': str(error)}

        @self.mcp.tool
        def acceptance_check(
            dish: Annotated[str, Field(description='The dish you are thinking of accepting.')],
            requirements: Annotated[list[str], Field(description="What the dish demands, e.g. ['assar no forno']. Leave empty to check only the flow.")] = [],
        ) -> dict:
            """What still stands between this dish and the menu.

            Every check with its state, plus the questions she has not been
            asked yet. The checks existed in five different places and nobody
            consulted all five; this is the one place that answers the question
            the agent actually has, which is whether it may go ahead.

            ``ready`` false means do not offer to accept. Ask what is listed.
            """
            from ..domain.elicitation import ElicitationCatalogue, ElicitationPlanner
            from ..domain.kitchen import KitchenProfile
            from ..mcps.middleware import ConfidenceMiddleware

            if self.observer is None:
                return {'available': False, 'error': 'observer not wired'}

            session = ConfidenceMiddleware.SESSION_FALLBACK
            checks = self.observer.acceptance_checks(session, dish)

            unanswered: list[dict] = []
            blockers: list[dict] = []
            if requirements:
                ElicitationCatalogue.load_custom(self.db)
                planner = ElicitationPlanner(KitchenProfile(self.db))
                gaps = planner.gaps_for_dish(requirements)
                unanswered = [
                    {'item': entry['item'], 'question': entry['question']}
                    for entry in gaps['must_ask_before_buying']
                ] + [
                    {'item': entry['requirement'], 'question': entry['question']}
                    for entry in gaps['unrecognised_requirements']
                ]
                blockers = gaps['known_blockers']

            missing = [c['check'] for c in checks if c['blocks_acceptance'] and not c['passed']]
            ready = not missing and not unanswered and not blockers

            return {
                'dish': dish,
                'ready_to_accept': ready,
                'checks': checks,
                'blocking': missing,
                'questions_she_has_not_been_asked': unanswered,
                'kitchen_blockers': blockers,
                'next_step': (
                    'Tudo conferido. Mostre os cenários, deixe ELA escolher o preço, '
                    'e só então chame add_dish.'
                    if ready
                    else (
                        'Pergunte primeiro, uma coisa por vez: '
                        + '; '.join(q['question'] for q in unanswered[:3])
                        if unanswered
                        else f'Faltam estas checagens: {missing}. '
                        'Rode-as antes de oferecer o prato como fechado.'
                        if missing
                        else f'A cozinha dela barra este prato: '
                        f'{[b["item"] for b in blockers]}. Ofereça outra versão.'
                    )
                ),
            }
