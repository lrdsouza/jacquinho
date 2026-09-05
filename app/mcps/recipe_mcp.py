'''MCP surface for recipe discovery driven by pantry keywords.'''

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..domain.elicitation import ElicitationCatalogue, ElicitationPlanner
from ..domain.kitchen import KitchenProfile
from ..domain.catalogue import BlockReason, CatalogueUnavailable, RecipeCatalogue
from ..domain.pantry import PantryRepository
from ..domain.search import (
    Freshness,
    RecipeQueryBuilder,
    SearchError,
    SearchProviderFactory,
)
from .base import BaseMCP


class RecipeMCP(BaseMCP):
    '''Turns the pantry into search keywords and finds real recipes on the web.'''

    name = 'recipes'
    instructions = (
        'Recipe discovery and the shortlist. Start from build_search_queries so '
        'the search is driven by what she actually owns, then search_recipes and '
        'check_pantry_coverage. Save every candidate you open with save_candidate, '
        'including the equipment and techniques its recipe demands: that is what '
        'lets a later rejection rule out similar dishes without searching again. '
        'When she turns a dish down, call block_candidate with the reason and, '
        'when a capability is what stopped it, the item that did. A block tied '
        'to a capability lifts itself the day that capability changes. Then call '
        'next_candidate, and only go back to the web when it comes back empty.'
    )

    def __init__(self, settings, repository: PantryRepository, db):
        self.repository = repository
        self.db = db
        self.query_builder = RecipeQueryBuilder(repository)
        self.catalogue = RecipeCatalogue(db)
        super().__init__(settings)

    def _planner(self) -> ElicitationPlanner:
        ElicitationCatalogue.load_custom(self.db)
        return ElicitationPlanner(KitchenProfile(self.db))

    def _provider(self):
        return SearchProviderFactory.create(
            self.settings.search_provider, self.settings.brave_api_key
        )

    def register(self) -> None:
        @self.mcp.tool
        def build_search_queries(
            constraints: Annotated[list[str], Field(description="Operating limits to fold in, e.g. ['sem forno'].")] = [],
            limit: Annotated[int, Field(ge=1, le=20, description='How many queries to return.')] = 8,
        ) -> dict:
            '''Build web-search queries from the pantry ingredients themselves.

            Pairs proteins with sides and skips seasonings, so the queries read
            like something a cook would type. Feed the constraints you already
            learned from her, so results are producible in her kitchen.
            '''
            queries = self.query_builder.build(constraints=constraints, limit=limit)
            buckets = {
                bucket: [item.search_keyword for item in items]
                for bucket, items in self.query_builder.buckets().items()
            }
            return {
                'queries': queries,
                'keywords_by_group': buckets,
                'note': (
                    'Ingredients in the premium group are expensive per kilo. Use '
                    'them as a finishing touch, never as the base of a lunchbox.'
                ),
            }

        @self.mcp.tool
        def search_recipes(
            query: Annotated[str, Field(description='Query from build_search_queries, or a refined one.')],
            limit: Annotated[int, Field(ge=1, le=15, description='Maximum results.')] = 8,
        ) -> dict:
            '''Search the web for real recipes matching the query.

            Uses Brave Search when BRAVE_API_KEY is set, otherwise falls back to
            a keyless DuckDuckGo scrape, which is best effort.
            '''
            provider = self._provider()
            try:
                results = provider.search(query, limit, Freshness.DISHES)
            except SearchError as error:
                return {
                    'query': query,
                    'provider': provider.name,
                    'error': str(error),
                    'next_step': (
                        'Tell Dona Maria the search is unavailable and ask her which '
                        'dishes she already cooks well. Do not invent recipe sources.'
                    ),
                }
            return {
                'query': query,
                'provider': provider.name,
                'result_count': len(results),
                'results': [result.as_dict() for result in results],
                'next_step': (
                    'Open the promising ones, extract the ingredient list, then call '
                    'check_pantry_coverage before showing the dish to her.'
                ),
            }

        @self.mcp.tool
        def check_pantry_coverage(
            ingredients: Annotated[list[str], Field(description="A recipe's ingredient names.")],
        ) -> dict:
            '''Score how much of a recipe the pantry already covers.

            Flags recipes leaning on the expensive pantry items, which look
            attractive but wreck the cost of a lunchbox.
            '''
            return self.query_builder.coverage(ingredients)

        @self.mcp.tool
        def save_candidate(
            dish: Annotated[str, Field(description='Dish name as you would say it to her.')],
            source_url: Annotated[str, Field(description='Where the recipe came from.')],
            source_title: Annotated[str, Field(description='Page title of the source.')],
            ingredients: Annotated[list[str], Field(description="The recipe's ingredient names.")],
            required_equipment: Annotated[list[str], Field(description='Equipment keys from kitchen_analyse_recipe_requirements.')],
            required_techniques: Annotated[list[str], Field(description='Technique keys from the same analysis.')],
            pantry_coverage: Annotated[float, Field(ge=0, le=1, description='coverage_ratio from check_pantry_coverage.')],
            notes: Annotated[str, Field(description='Anything worth remembering about this version.')] = '',
        ) -> dict:
            """Put a recipe in the catalogue, with what it demands of her kitchen.

            Save every recipe you actually open, even ones you do not show her
            yet. The demands are the point: when she says she has no oven, every
            saved recipe needing one is ruled out without another search - and
            the day she gets an oven they all come back.
            """
            try:
                entry = self.catalogue.save(
                    dish, source_url, source_title, ingredients,
                    required_equipment, required_techniques, pantry_coverage, notes,
                )
            except CatalogueUnavailable as error:
                return {'saved': False, 'error': str(error)}
            return {'saved': True, **entry}

        @self.mcp.tool
        def list_candidates(
            only_open: Annotated[bool, Field(description='True hides everything currently blocked.')] = False,
        ) -> dict:
            """The catalogue, with each recipe's demands and any block on it."""
            try:
                recipes = self.catalogue.all(only_open=only_open)
            except CatalogueUnavailable as error:
                return {'available': False, 'error': str(error)}
            entries = [r.as_dict() for r in recipes]
            return {
                'available': True,
                'count': len(entries),
                'candidates': entries,
                'blocked': [
                    {
                        'dish': e['dish'],
                        'blocked_by': [b['blocking_item'] for b in e['active_blocks']],
                        'reasons': [b['reason'] for b in e['active_blocks']],
                        'liftable': any(b['conditional'] for b in e['active_blocks']),
                    }
                    for e in entries
                    if e['blocked']
                ],
            }

        @self.mcp.tool
        def block_candidate(
            dish: Annotated[str, Field(description='Dish she turned down.')],
            reason: Annotated[Literal['disliked', 'impediment', 'missing_equipment', 'missing_technique', 'over_budget', 'too_expensive'], Field(description='Why it is out.')],
            blocking_item: Annotated[str, Field(description="The capability that stopped it, e.g. 'forno'. Required for the block to be liftable later.")] = '',
            note: Annotated[str, Field(description='Her words, so the reason survives the session.')] = '',
        ) -> dict:
            """Take a dish off the table, recording what would bring it back.

            A block naming a capability lifts itself the day that capability
            changes. A block on taste does not: she is allowed to simply not
            want to cook something, and that is not a problem to be solved.
            """
            try:
                entry = self.catalogue.block(dish, reason, blocking_item or None, note)
            except CatalogueUnavailable as error:
                return {'blocked': False, 'error': str(error)}
            if entry is None:
                return {
                    'blocked': False,
                    'error': f'{dish!r} is not in the catalogue',
                    'hint': 'Call save_candidate first, then block it.',
                }
            conditional = BlockReason.is_conditional(reason)
            return {
                'blocked': True,
                'recipe': entry,
                'liftable': conditional,
                'lifts_when': (
                    f'{blocking_item} becomes available'
                    if conditional and blocking_item
                    else 'never on its own; this one is about taste, not capability'
                    if not conditional
                    else 'someone lifts it by hand - no capability was named'
                ),
                'next_step': 'Call next_candidate.',
            }

        @self.mcp.tool
        def revisit_blocks(
            capability: Annotated[str, Field(description="Capability that just changed, e.g. 'forno'.")],
            because: Annotated[str, Field(description="What changed, in her words, e.g. 'comprou fogao de 6 bocas'.")],
        ) -> dict:
            """Bring back every dish that was waiting on this capability.

            Call it whenever a capability flips to confirmed_yes. Dishes ruled
            out weeks ago come back on their own, which is the whole reason the
            block recorded what stopped it.
            """
            try:
                revived = self.catalogue.lift_for_capability(capability, because)
            except CatalogueUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {
                'available': True,
                'capability': capability,
                'revived_count': len(revived),
                'revived': [r['dish'] for r in revived],
                'recipes': revived,
                'next_step': (
                    f"Tell her these are back on the table now that she has "
                    f"{capability}, then call next_candidate."
                    if revived
                    else 'Nothing was waiting on this one. Carry on.'
                ),
            }

        @self.mcp.tool
        def unblock_candidate(
            dish: Annotated[str, Field(description='Dish to put back on the table.')],
            because: Annotated[str, Field(description='Why it is coming back.')],
        ) -> dict:
            """Lift every block on one dish by hand, when she changes her mind."""
            try:
                entry = self.catalogue.lift_block(dish, because)
            except CatalogueUnavailable as error:
                return {'unblocked': False, 'error': str(error)}
            if entry is None:
                return {'unblocked': False, 'error': f'{dish!r} is not in the catalogue'}
            return {'unblocked': True, 'recipe': entry}

        @self.mcp.tool
        def block_history(
            dish: Annotated[str, Field(description='Dish to look up.')],
        ) -> dict:
            """Every block ever placed on a dish, lifted or not.

            Useful when she asks why something was dropped, or whether anything
            has changed since.
            """
            try:
                return {'available': True, 'dish': dish, 'history': self.catalogue.history(dish)}
            except CatalogueUnavailable as error:
                return {'available': False, 'error': str(error)}

        @self.mcp.tool
        def next_candidate() -> dict:
            """The best option she has not turned down, that her kitchen can do.

            Ranks the open catalogue against what she has told you: recipes she
            can make now come first, then those needing the fewest unanswered
            questions, then pantry coverage. Search the web again only when this
            comes back empty.
            """
            try:
                open_recipes = self.catalogue.all(only_open=True)
            except CatalogueUnavailable as error:
                return {'available': False, 'error': str(error)}

            if not open_recipes:
                return {
                    'available': True,
                    'candidate': None,
                    'next_step': (
                        'Nothing is open in the catalogue. Go back to '
                        'dishes_discover_dishes or search_recipes, and tell her you '
                        'are looking for something else rather than going quiet.'
                    ),
                }

            planner = self._planner()
            ranked = []
            for recipe in open_recipes:
                gate = planner.gaps_for_dish(recipe.equipment + recipe.techniques)
                ranked.append(
                    {
                        'dish': recipe.dish,
                        'source_url': recipe.source_url,
                        'pantry_coverage': float(recipe.pantry_coverage or 0),
                        'can_make_now': gate['safe_to_shop'],
                        'blocked_by': [item['item'] for item in gate['known_blockers']],
                        'open_questions': [item['item'] for item in gate['must_ask_before_buying']],
                        'notes': recipe.notes,
                    }
                )

            # A dish her kitchen cannot do is not an option, however good its
            # pantry coverage. Separate the two rather than ranking them
            # together, so a hard blocker never hides behind an open question.
            ruled_out = [entry for entry in ranked if entry['blocked_by']]
            viable = [entry for entry in ranked if not entry['blocked_by']]
            viable.sort(
                key=lambda entry: (
                    not entry['can_make_now'],
                    len(entry['open_questions']),
                    -entry['pantry_coverage'],
                )
            )

            if not viable:
                blockers = sorted({i for e in ruled_out for i in e['blocked_by']})
                return {
                    'available': True,
                    'candidate': None,
                    'ruled_out_by_kitchen': ruled_out,
                    'next_step': (
                        f'Everything open is blocked by her kitchen: {blockers}. '
                        'Block those with the capability named, so they come back if '
                        'that ever changes, then search again folding the blockers '
                        "into the query as constraints, for example 'sem forno'."
                    ),
                }

            best = viable[0]
            return {
                'available': True,
                'candidate': best,
                'others_waiting': viable[1:],
                'ruled_out_by_kitchen': ruled_out,
                'next_step': (
                    f"Offer {best['dish']} by name - no counts, no sources - and ask "
                    'whether she likes cooking it and whether she sees a problem, '
                    'then menu_record_feedback. Its recipe is at source_url; fetch '
                    'that rather than searching again.'
                    if best['can_make_now']
                    else f"{best['dish']} is possible but you still have not asked "
                    f"her about {best['open_questions']}. Ask that first."
                ),
            }
