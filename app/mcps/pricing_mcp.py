'''MCP surface for cost of goods sold and delivery pricing.'''

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from ..domain.budget import BudgetLedger
from ..domain.economy import EconomicContext, EconomicDataUnavailable
from ..domain.money import menu_rounding
from ..domain.pantry import PantryRepository
from ..domain.units import UnitConverter, UnknownUnitError
from .base import BaseMCP


class RecipeLine(BaseModel):
    '''One ingredient line of a recipe, for a single portion.'''

    ingredient: Annotated[str, Field(description='Ingredient name as the recipe writes it.')]
    quantity: Annotated[float, Field(gt=0, description='Amount for ONE portion.')]
    unit: Annotated[str, Field(description='Recipe unit: kg, g, L, ml or un.')]


class PurchasedItem(BaseModel):
    """A price researched for something the pantry does not have.

    The package is the point. She cannot buy 40 g of condensed milk: she buys a
    can. So the shopping list has to carry whole packages, and the CMV has to
    carry only the part the recipe eats. Two different numbers from one price,
    and doing that split in prose is how a batch once got charged three entire
    packages and a profit appeared that no tool had calculated.
    """

    ingredient: Annotated[str, Field(description='Name as the recipe writes it.')]
    package_price: Annotated[float, Field(gt=0, description='R$ for ONE package, as researched.')]
    package_quantity: Annotated[float, Field(gt=0, description='How much comes in one package, e.g. 395 for a 395g can.')]
    package_unit: Annotated[str, Field(description='Unit of the package: kg, g, L, ml or un.')]


class MarketReference(BaseModel):
    '''The observed price band, straight from market_research_dish_prices.'''

    min: Annotated[float, Field(gt=0, description="reference.min from the market tool.")]
    median: Annotated[float, Field(gt=0, description='reference.median from the market tool.')]
    max: Annotated[float, Field(gt=0, description='reference.max from the market tool.')]
    sample_size: Annotated[int, Field(ge=0, description='How many prices were observed.')]
    confidence: Annotated[str, Field(description="'none', 'low', 'medium' or 'good'.")]


class PricingMCP(BaseMCP):
    '''All the arithmetic of the challenge, kept outside the language model.'''

    name = 'pricing'
    instructions = (
        'Cost and price authority. Never compute CMV or a selling price in prose: '
        'call calculate_cmv then price_scenarios. An ingredient the pantry does '
        'not have still has a cost: look up what one package costs and pass it in '
        'researched_prices, and the tool splits the whole package she must buy '
        'from the fraction the recipe eats. Those are different numbers and doing '
        'that split in prose is how a can of condensed milk becomes the cost of '
        'one brigadeiro. When calculate_cmv returns open_questions, take them back '
        'to the conversation instead of guessing. '
        'price_scenarios only produces sellable prices when it is given a market '
        'reference from market_research_dish_prices: cost tells you the floor, '
        'the market tells you the price.'
    )

    @staticmethod
    def _cost_a_purchase(line, priced, portions: int, to_buy: list) -> tuple:
        """Split a researched package price into a CMV share and a shopping line.

        She buys whole packages and the recipe eats a fraction of one. Charging
        the batch for the whole package overstates the cost of every dish that
        leaves leftovers, which is most of them; charging only the fraction and
        then shopping for the fraction sends her to buy 40 g of condensed milk.
        Both numbers are needed and they are not the same number.
        """
        import math

        try:
            recipe_pack = UnitConverter.parse(line.unit)
            bought_pack = UnitConverter.parse(priced.package_unit)
        except UnknownUnitError:
            return None, {
                'ingredient': line.ingredient,
                'question': (
                    f'Nao entendi a unidade {line.unit!r} ou '
                    f'{priced.package_unit!r}. E em kg, g, L, ml ou un?'
                ),
            }
        if recipe_pack.dimension != bought_pack.dimension:
            return None, {
                'ingredient': line.ingredient,
                'question': (
                    f'A receita pede {line.quantity:g} {line.unit}, e o preço que '
                    f'você achou é de {priced.package_quantity:g} '
                    f'{priced.package_unit}. Quanto rende uma embalagem, na '
                    'unidade da receita?'
                ),
            }

        package_size = priced.package_quantity * bought_pack.factor
        if package_size <= 0:
            return None, {
                'ingredient': line.ingredient,
                'question': f'Qual o tamanho da embalagem de {line.ingredient}?',
            }

        unit_cost = priced.package_price / package_size
        per_portion = line.quantity * recipe_pack.factor
        cost = per_portion * unit_cost

        batch_need = per_portion * portions
        packages = max(1, math.ceil(batch_need / package_size - 1e-9))
        to_buy.append({
            'ingredient': line.ingredient,
            'buy': f'{packages} x {priced.package_quantity:g} {priced.package_unit}',
            'estimated_cost': round(packages * priced.package_price, 2),
            'basis': 'researched package price',
            'used_by_the_batch': f'{batch_need:g} {bought_pack.base_unit}',
            # With the unit: a bare 0.39 next to a 395 g package reads as
            # grams and is kilos.
            'left_over': (
                f'{round(packages * package_size - batch_need, 4):g} '
                f'{bought_pack.base_unit}'
            ),
        })

        return {
            'ingredient': line.ingredient,
            'amount': f'{per_portion:g} {bought_pack.base_unit}',
            'unit_cost': f'R$ {unit_cost:.4f}/{bought_pack.base_unit}',
            'cost': round(cost, 2),
            'arithmetic': (
                f'{priced.package_price:.2f} / {package_size:g} = {unit_cost:.4f} '
                f'por {bought_pack.base_unit}; {per_portion:g} x {unit_cost:.4f} '
                f'= {cost:.2f}'
            ),
            'from': 'compra, não da despensa',
        }, cost

    def __init__(self, settings, repository: PantryRepository, db):
        self.repository = repository
        self.db = db
        self.economy = EconomicContext(settings.ibge_locality)
        super().__init__(settings)

    def _real_terms(self, price: float, cmv: float, net_share: float) -> dict:
        '''Show what inflation does to this profit if the price stays put.

        Margin as a percentage of the sale and annual inflation are different
        quantities, and comparing them says nothing. What inflation actually
        does is push her costs up while a printed menu price stays still, so
        that is what this projects.
        '''
        try:
            reading = self.economy.read()
        except EconomicDataUnavailable as error:
            return {
                'available': False,
                'error': str(error),
                'warning': (
                    'Profit above is nominal only. Say so: it was not checked '
                    'against inflation.'
                ),
            }

        receives = price * net_share
        profit_now = receives - cmv
        cmv_next_year = cmv * (1 + reading.cost_index / 100)
        profit_next_year = receives - cmv_next_year
        price_to_hold = (cmv_next_year + profit_now) / net_share

        return {
            'available': True,
            'locality': reading.locality,
            'ipca_food_at_home_12m_percent': reading.cost_index,
            'ipca_headline_12m_percent': reading.headline_12m,
            'ipca_reference_period': reading.reference_period,
            'cmv_in_12_months': round(cmv_next_year, 2),
            'profit_in_12_months_at_same_price': round(profit_next_year, 2),
            'profit_erosion': round(profit_now - profit_next_year, 2),
            'price_to_hold_this_profit': round(price_to_hold, 2),
            'still_profitable_in_12_months': profit_next_year > 0,
            'meaning': (
                f'If ingredients keep tracking food inflation in {reading.locality} '
                f'({reading.cost_index}% a year) and she keeps charging '
                f'R$ {price:.2f}, this profit falls '
                f'from R$ {profit_now:.2f} to R$ {profit_next_year:.2f}. Holding it '
                f'would mean charging R$ {price_to_hold:.2f}.'
            ),
        }

    def _ledger(self) -> BudgetLedger:
        return BudgetLedger(self.db, self.settings.top_up_budget)

    def register(self) -> None:
        @self.mcp.tool
        def calculate_cmv(
            dish: Annotated[str, Field(description='Dish name.')],
            lines: Annotated[list[RecipeLine], Field(description='Ingredients for ONE portion.')],
            portions: Annotated[int, Field(ge=1, description='Portions produced per batch.')] = 1,
            researched_prices: Annotated[list[PurchasedItem], Field(description='Prices you looked up for ingredients the pantry does not have, one per ingredient, as a package.')] = [],
        ) -> dict:
            '''Cost one portion, splitting what she has from what she must buy.

            Something the pantry does not have still has a cost, and it has two:
            the whole package she has to buy, and the fraction the recipe eats.
            Pass the researched package price and this splits them. Without it
            the ingredient comes back under ``not_found`` and the CMV stays
            incomplete, because a cost computed in prose is exactly the number
            nobody can check.

            Returns ``open_questions`` rather than guessing when a recipe unit
            does not match how the ingredient was bought.
            '''
            used, to_buy, unknown, questions = [], [], [], []
            cmv = 0.0
            bought = {
                UnitConverter.normalise_text(entry.ingredient): entry
                for entry in researched_prices
            }

            for line in lines:
                item = self.repository.find(line.ingredient)
                if item is None:
                    priced = bought.get(UnitConverter.normalise_text(line.ingredient))
                    if priced is None:
                        unknown.append(
                            {
                                'ingredient': line.ingredient,
                                'amount': f'{line.quantity:g} {line.unit}',
                                'pantry_suggestions': self.repository.suggest(line.ingredient),
                                'action': (
                                    'Not in the pantry. Look up what a package costs '
                                    'and pass it in researched_prices, or substitute '
                                    'it. Do not price the dish without this.'
                                ),
                            }
                        )
                        continue
                    entry, cost = self._cost_a_purchase(line, priced, portions, to_buy)
                    if entry is None:
                        questions.append(cost)
                        continue
                    cmv += cost
                    used.append(entry)
                    continue

                try:
                    package = UnitConverter.parse(line.unit)
                except UnknownUnitError:
                    questions.append(
                        {
                            'ingredient': item.name,
                            'question': (
                                f'Nao entendi a unidade {line.unit!r}. '
                                'E em kg, g, L, ml ou un?'
                            ),
                        }
                    )
                    continue

                if package.dimension != item.dimension:
                    questions.append(
                        {
                            'ingredient': item.name,
                            'question': (
                                f'A receita pede {line.quantity:g} {line.unit}, mas '
                                f'{item.name} foi comprado por {item.sheet_unit} '
                                f'(R$ {item.price_paid:.2f}). Quanto pesa ou rende '
                                'uma embalagem?'
                            ),
                            'resolve_with': 'pantry_record_package_size',
                        }
                    )
                    continue

                base_quantity = line.quantity * package.factor
                cost = base_quantity * item.unit_cost
                cmv += cost

                entry = {
                    'ingredient': item.name,
                    'amount': f'{base_quantity:g} {item.base_unit}',
                    'unit_cost': f'R$ {item.unit_cost:.2f}/{item.base_unit}',
                    'cost': round(cost, 2),
                    'arithmetic': (
                        f'{base_quantity:g} x {item.unit_cost:.2f} = {cost:.2f}'
                    ),
                }

                batch_need = base_quantity * portions
                if batch_need > item.stock + 1e-9:
                    shortfall = batch_need - item.stock
                    entry['short_on_stock'] = (
                        f'has {item.stock:g} {item.base_unit}, needs {batch_need:g} '
                        f'for {portions} portions'
                    )
                    to_buy.append(
                        {
                            'ingredient': item.name,
                            'buy': f'{shortfall:g} {item.base_unit}',
                            'estimated_cost': round(shortfall * item.unit_cost, 2),
                            'basis': 'estimated from the price she already paid',
                        }
                    )
                used.append(entry)

            shopping_cost = sum(entry['estimated_cost'] for entry in to_buy)
            complete = not questions and not unknown
            # Ask the ledger, not the constant: earlier dishes may already have
            # eaten into the budget.
            budget_check = (
                self._ledger().check(shopping_cost)
                if shopping_cost > 0
                else {'verdict': 'nothing_to_buy', 'fits': True}
            )

            return {
                'dish': dish,
                'portions_per_batch': portions,
                'cmv_per_portion': round(cmv, 2) if complete else None,
                'calculation_complete': complete,
                'ingredients': used,
                'must_buy': to_buy,
                'shopping_cost': round(shopping_cost, 2),
                'budget': budget_check,
                'not_found': unknown,
                'open_questions': questions,
                'next_step': (
                    'Run market_research_dish_prices for this dish, then call '
                    'price_scenarios with the CMV and that reference band. Commit the '
                    'shopping with budget_reserve_purchase only after she says she '
                    'will buy it. You are not buying anything: she is.'
                    if complete
                    else 'Do NOT price yet. Take open_questions back to the conversation.'
                ),
            }

        @self.mcp.tool
        def price_scenarios(
            cmv_per_portion: Annotated[float, Field(gt=0, description='Portion CMV from calculate_cmv.')],
            market: Annotated[MarketReference | None, Field(description='Reference band from market_research_dish_prices.')] = None,
        ) -> dict:
            '''Build delivery price scenarios anchored to the observed market.

            The break-even floor is pure arithmetic and always returned: she
            keeps 0.90 x P, so P = CMV / 0.90. Sellable scenarios are only
            produced when a market reference is supplied, because a multiplier
            over cost is a guess, not a price.
            '''
            fee = self.settings.platform_fee
            net_share = 1 - fee
            break_even = cmv_per_portion / net_share

            def scenario(price: float, label: str, rationale: str) -> dict:
                receives = price * net_share
                profit = receives - cmv_per_portion
                return {
                    'scenario': label,
                    'rationale': rationale,
                    'selling_price': round(price, 2),
                    'she_receives': round(receives, 2),
                    'profit_per_portion': round(profit, 2),
                    'margin_on_receipts': (
                        f'{(profit / receives * 100) if receives else 0:.0f}%'
                    ),
                    'arithmetic': (
                        f'0.90 x {price:.2f} = {receives:.2f} received; '
                        f'{receives:.2f} - {cmv_per_portion:.2f} CMV = {profit:.2f} profit'
                    ),
                    'above_break_even': profit > 0,
                    'real_terms': self._real_terms(price, cmv_per_portion, net_share),
                }

            floor = {
                'cmv_per_portion': round(cmv_per_portion, 2),
                'platform_fee': f'{fee * 100:.0f}%',
                'break_even_price': round(break_even, 2),
                'formula': 'P >= CMV / 0.90   |   profit = 0.90 x P - CMV',
                'cost_basis_caveat': (
                    'This CMV uses the prices she actually paid, at an unknown date. '
                    'Use economy_restate_cost to see what it becomes at current '
                    'prices before treating the margin as durable.'
                ),
            }

            if market is None or market.sample_size == 0:
                return {
                    **floor,
                    'market_grounded': False,
                    'scenarios': [],
                    'next_step': (
                        'Run market_research_dish_prices for this dish and call this '
                        'tool again with the reference band. You may tell her the '
                        'break-even floor now, but not a selling price.'
                    ),
                }

            anchors = [
                (market.min, 'Entrada', 'no piso do que o mercado cobra, para atrair'),
                (market.median, 'Mercado', 'na mediana do que a concorrencia cobra'),
                (market.max, 'Premium', 'no topo da faixa observada'),
            ]
            scenarios = [
                scenario(menu_rounding(price), label, rationale)
                for price, label, rationale in anchors
                if price >= break_even
            ]

            unviable = [
                label for price, label, _ in anchors if price < break_even
            ]

            return {
                **floor,
                'market_grounded': True,
                'market': {
                    'reference': {
                        'min': market.min,
                        'median': market.median,
                        'max': market.max,
                    },
                    'sample_size': market.sample_size,
                    'confidence': market.confidence,
                },
                'scenarios': scenarios,
                'unviable_anchors': unviable,
                'alert': (
                    f'O mercado cobra abaixo do custo dela nestes pontos: {unviable}. '
                    'Mostre isso: ou o prato muda, ou ela nao compete por preco aqui.'
                )
                if unviable
                else None,
                'confidence_warning': (
                    'Amostra pequena. Diga a ela que a faixa e indicativa.'
                    if market.confidence in ('none', 'low')
                    else None
                ),
                'instruction': (
                    'Show the arithmetic and the sources to Dona Maria, then let HER '
                    'choose. Do not pick the price for her.'
                ),
            }
