'''MCP surface for dish discovery: pantry in, cross-verified dishes out.'''

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..domain.consensus import ConsensusEngine
from ..domain.dishes import DishCategoryRegistry, DishPlanner
from ..domain.pantry import PantryRepository
from ..domain.search import Freshness, SearchProviderFactory
from .base import BaseMCP


class DishMCP(BaseMCP):
    '''Works out which dishes the pantry can actually produce, per category.'''

    name = 'dishes'
    instructions = (
        'Dish discovery from the pantry itself. survey_categories shows which '
        'kinds of dish the ingredients can support at all; assess_category shows '
        'ingredient by ingredient why. discover_dishes then searches several '
        'phrasings, keeps only recent pages, and returns a dish ONLY when '
        'independent domains agree on it. Anything with source_count 1 is a lead, '
        'not a finding: never present it to Dona Maria as what people cook.'
    )

    def __init__(self, settings, repository: PantryRepository, db):
        self.repository = repository
        self.db = db
        super().__init__(settings)

    def _registry(self) -> DishCategoryRegistry:
        return DishCategoryRegistry(self.db)

    def _planner(self) -> DishPlanner:
        return DishPlanner(self.repository, self._registry())

    def register(self) -> None:
        @self.mcp.tool
        def list_categories() -> dict:
            '''List every dish category, built in or created in conversation.'''
            registry = self._registry()
            return {
                'categories': [category.as_dict() for category in registry.all()],
                'hint': (
                    'Use create_category to add a kind of dish that is not here, '
                    'for example a vegetarian or a low-cost line.'
                ),
            }

        @self.mcp.tool
        def create_category(
            key: Annotated[str, Field(description="Short id, e.g. 'vegetarian_main'.")],
            label: Annotated[str, Field(description="Name in Portuguese, e.g. 'Prato vegetariano'.")],
            search_terms: Annotated[list[str], Field(description="Search phrasings, e.g. ['prato vegetariano', 'sem carne'].")],
            required_groups: Annotated[list[list[str]], Field(description='AND of ORs: the pantry needs one match in EVERY group.')],
        ) -> dict:
            '''Create a new dish category the pantry can be assessed against.

            Groups are normalised ingredient tokens, not full names: use
            ['feijao', 'ovos', 'queijo'] rather than 'Feijão carioquinha'.
            '''
            try:
                category = self._registry().register(
                    key, label, search_terms, required_groups
                )
            except ValueError as error:
                return {'created': False, 'error': str(error)}
            return {'created': True, 'category': category.as_dict()}

        @self.mcp.tool
        def delete_category(
            key: Annotated[str, Field(description='Category id to remove.')],
        ) -> dict:
            '''Remove a category created earlier. Built-ins cannot be removed.'''
            removed = self._registry().remove(key)
            return {
                'removed': removed,
                'reason': None if removed else 'unknown key, or it is a built-in',
            }

        @self.mcp.tool
        def survey_categories() -> dict:
            '''Check every category against the pantry in one pass.

            Use this early: it tells you which kinds of dish are even on the
            table before you spend a search on them.
            '''
            survey = self._planner().survey()
            survey['next_step'] = (
                'Ask her which of these she feels like cooking, then call '
                'discover_dishes for it. Do not re-offer to search: she already '
                'said yes by getting you here.'
            )
            return survey

        @self.mcp.tool
        def assess_category(
            category: Annotated[str, Field(description='Category id from list_categories.')],
        ) -> dict:
            '''Go through the pantry ingredient by ingredient for one category.

            Shows which ingredient satisfies which requirement, with stock and
            unit cost, and states plainly what is missing when it does not work.
            '''
            planner = self._planner()
            found = planner.registry.get(category)
            if found is None:
                return {
                    'error': f'unknown category {category!r}',
                    'available': [item.key for item in planner.registry.all()],
                }
            return planner.assess(found)

        @self.mcp.tool
        def discover_dishes(
            category: Annotated[str, Field(description='Category id from list_categories.')],
            constraints: Annotated[list[str], Field(description="Kitchen limits to fold in, e.g. ['sem forno'].")] = [],
            min_sources: Annotated[int, Field(ge=1, le=6, description='Distinct domains that must agree. 2 is the sensible floor.')] = 2,
            freshness: Annotated[Literal['month', 'year', 'five_years', 'any'], Field(description='How recent results must be. Dishes default to the last five years.')] = 'five_years',
            queries: Annotated[int, Field(ge=2, le=12, description='How many phrasings to search.')] = 6,
        ) -> dict:
            '''Find dishes for a category that several recent sources agree on.

            Runs multiple query phrasings, filters to recent pages, then keeps
            only dish names appearing on ``min_sources`` independent domains and
            touching at least one pantry ingredient. Results carry their sources
            so every claim can be checked.
            '''
            planner = self._planner()
            found = planner.registry.get(category)
            if found is None:
                return {
                    'error': f'unknown category {category!r}',
                    'available': [item.key for item in planner.registry.all()],
                }

            assessment = planner.assess(found)
            if not assessment['supported']:
                return {
                    'category': found.key,
                    'searched': False,
                    'reason': 'the pantry cannot support this category',
                    'blocked_because': assessment['blocked_because'],
                    'next_step': (
                        'Tell her which ingredient group is missing and ask whether '
                        'it is worth buying, checking budget_check_purchase first.'
                    ),
                }

            provider = SearchProviderFactory.create(
                self.settings.search_provider, self.settings.brave_api_key
            )
            engine = ConsensusEngine(provider, planner.pantry_tokens(), freshness)
            query_list = planner.queries_for(found, constraints, queries)
            gathered = engine.gather(query_list)
            candidates = engine.agree(gathered['results'], min_sources)

            return {
                'category': found.key,
                'label': found.label,
                'searched': True,
                'provider': provider.name,
                'freshness': freshness,
                'queries_run': query_list,
                'pages_kept': len(gathered['results']),
                'stale_results_dropped': gathered['stale_results_dropped'],
                'queries_failed': gathered['queries_failed'],
                'min_sources_required': min_sources,
                'agreed_dishes': [candidate.as_dict() for candidate in candidates],
                'agreement_found': bool(candidates),
                'how_to_read_this': (
                    'INTERNAL - none of this goes to Dona Maria. source_count is the '
                    'number of independent domains whose recent headlines carried '
                    'this phrase. Dish names are extracted with heuristics, so '
                    'agreement proves several sources are talking about it, not that '
                    'the phrase is a well-formed dish. Offer her the dish names in '
                    'your own voice; never quote counts, sources or the word '
                    'consensus at her.'
                ),
                'sources_to_open': {
                    candidate['dish']: [m['url'] for m in candidate['seen_at']]
                    for candidate in [c.as_dict() for c in candidates]
                },
                'next_step': (
                    'Offer her two or three of these by name, in your own voice and '
                    'with no counts. When she picks one, fetch its recipe from the '
                    'URLs already in sources_to_open for that dish - they were '
                    'found and vetted a moment ago, so searching the web again is '
                    'wasted time and a worse source. Then '
                    'kitchen_analyse_recipe_requirements and '
                    'recipes_check_pantry_coverage.'
                    if candidates
                    else 'Nothing came back for this category. Do NOT announce that '
                    'to her, and do NOT search it again - an empty category does not '
                    'fill up on a second attempt. Offer what you found in another '
                    'category, or ask her what she already cooks well.'
                ),
            }
