'''MCP surface over the pantry database.'''

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..domain.pantry import PantryRepository
from .base import BaseMCP


class PantryMCP(BaseMCP):
    '''Reads Dona Maria's pantry: what she has, and what it really cost.'''

    name = 'pantry'
    instructions = (
        'Source of truth for the pantry. Unit costs here are already normalised '
        'from the two spreadsheet sheets, with packaging resolved. Never restate '
        'a cost from memory: read it from these tools.'
    )

    def __init__(self, settings, repository: PantryRepository, db):
        self.repository = repository
        self.db = db
        super().__init__(settings)

    def register(self) -> None:
        @self.mcp.tool
        def list_ingredients() -> dict:
            '''List every pantry ingredient with a normalised unit cost.

            The cost comes from joining the two sheets with packaging resolved:
            a 'balde 2kg' bought for R$ 82.00 becomes R$ 41.00/kg, not
            R$ 82.00 per bucket. ``search_keyword`` is the term to feed into
            recipe search.
            '''
            items = [item.as_dict() for item in self.repository.sorted_items()]
            return {
                'top_up_budget': self.settings.top_up_budget,
                'platform_fee': self.settings.platform_fee,
                'total_ingredients': len(items),
                'ingredients': items,
                'search_keywords': [item['search_keyword'] for item in items],
                'unit_questions_pending': [
                    item['ingredient'] for item in items if 'note' in item
                ],
            }

        @self.mcp.tool
        def find_ingredient(
            name: Annotated[str, Field(description='Ingredient name, accents optional.')],
        ) -> dict:
            '''Look ONE ingredient up, tolerating accents, case and parentheticals.

            For a recipe, use recipes_check_pantry_coverage with the whole
            ingredient list instead: one call, and it tells you what is missing
            in one go. Calling this in a loop is slow and reads, to her, like
            someone who does not know her pantry.
            '''
            item = self.repository.find(name)
            if item is None:
                return {
                    'found': False,
                    'searched_for': name,
                    'suggestions': self.repository.suggest(name),
                    'next_step': (
                        'It is not in the pantry. Do NOT ask her whether she has it - '
                        'you just looked, and asking says you did not. State it '
                        "plainly ('azeitona nao esta na sua lista') and offer a way "
                        'out: swap it for something in suggestions that plays the '
                        'same role, or put it on the shopping list with a price. '
                        'Water, and sometimes salt or sugar, she has at home without '
                        'the spreadsheet knowing - do not treat those as missing.'
                    ),
                }
            return {'found': True, **item.as_dict()}

        @self.mcp.tool
        def record_package_size(
            ingredient: Annotated[str, Field(description='Ingredient name.')],
            quantity: Annotated[float, Field(gt=0, description='e.g. 400 for a 400 g pack.')],
            unit: Annotated[Literal['g', 'kg', 'ml', 'L'], Field(description='Unit of that weight or volume.')],
        ) -> dict:
            '''Record how much a package sold by the piece actually weighs.

            Call this after asking Dona Maria. The chocolate coating cost
            R$ 79.90 per 'un' and the sheet never says the weight, so without
            this there is no way to cost '200 g of coating'.
            '''
            item = self.repository.find(ingredient)
            if item is None:
                return {
                    'error': 'ingredient not found',
                    'suggestions': self.repository.suggest(ingredient),
                }
            self.repository.record_package_size(item.key, quantity, unit)
            updated = self.repository.find(item.name)
            return {
                'ok': True,
                'ingredient': updated.name,
                'new_unit_cost': f'R$ {updated.unit_cost:.2f}/{updated.base_unit}',
                'stock': f'{updated.stock:g} {updated.base_unit}',
            }

        @self.mcp.resource('pantry://ingredients')
        def pantry_resource() -> dict:
            '''Browsable snapshot of the pantry database.'''
            return {
                'ingredients': [item.as_dict() for item in self.repository.sorted_items()]
            }

        @self.mcp.tool
        def reseed_from_spreadsheet(
            force: Annotated[bool, Field(description='True replaces what is stored with the file.')] = False,
        ) -> dict:
            """Reload the pantry from the spreadsheet into the database.

            The application reads Postgres, not the file. Use this when she
            hands over an updated spreadsheet; without ``force`` it does
            nothing if the pantry has already been loaded.
            """
            return self.repository.seed(force=force)
