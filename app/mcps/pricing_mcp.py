'''MCP surface for cost of goods sold and delivery pricing.'''

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from ..domain.budget import BudgetLedger
from ..domain.costing import RecipeLock
from ..domain.economy import EconomicContext, EconomicDataUnavailable
from ..domain.memory import ConversationStore, RedisBackend
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
        'call calculate_cmv then price_scenarios. The first complete costing '
        'settles that dish\'s ingredient list; pass the same list afterwards and '
        'you get the same number. It only reopens through reopen_recipe, which '
        'needs her words, because a recipe changes when SHE changes it. An ingredient the pantry does '
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
    def _in_her_words(amount: str, ingredient: str, cost: float) -> str:
        """One line of the cost, as she would say it out loud.

        A total on its own is a number she has to take on faith. "100 g de carne
        moída: R$ 2,80" is a number she can check against her own shopping, and
        checking is the whole point of showing it.

        Grams and litres are for recipes; people say "meio quilo" and "um copo
        de leite". This keeps the unit but scales it to what reads naturally.
        """
        try:
            value, unit = amount.split(' ', 1)
            quantity = float(value)
        except ValueError:
            return f'{amount} de {ingredient}: R$ {cost:.2f}'.replace('.', ',')

        if unit == 'kg' and quantity < 1:
            written = f'{quantity * 1000:g} g'
        elif unit == 'l' and quantity < 1:
            written = f'{quantity * 1000:g} ml'
        elif unit == 'un':
            written = f'{quantity:g}' + (' unidade' if quantity == 1 else ' unidades')
        else:
            written = f'{quantity:g} {unit}'
        return f'{written} de {ingredient}: R$ {cost:.2f}'.replace('.', ',')

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

    def __init__(self, settings, repository: PantryRepository, db, observer=None):
        self.repository = repository
        self.db = db
        self.observer = observer
        self.lock = RecipeLock(db)
        self.chat = ConversationStore(RedisBackend(settings.redis_url))
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
            lines: Annotated[list[RecipeLine], Field(description='Ingredients as the recipe writes them. Per portion by default; if the recipe gives totals, pass recipe_yields and these are the totals.')],
            portions: Annotated[int, Field(ge=1, description='Portions she will produce per batch.')] = 1,
            recipe_yields: Annotated[int, Field(ge=0, description='How many portions the recipe itself yields. Pass it when `lines` are the recipe totals, and the division is done here instead of in your head.')] = 0,
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
            # The recipe of a dish is settled once. Passing a different list
            # for the same dish is how the cost wandered from R$ 9,90 to
            # R$ 8,18 to R$ 7,15 in one consultation, each figure arithmetically
            # right and none of them the dish.
            settled = self.lock.locked(dish) if dish else None
            if settled and RecipeLock.signature(lines) != settled['lines']:
                return {
                    'ok': False,
                    'recipe_is_settled': settled,
                    'what_you_passed_differs_by': RecipeLock.differs(
                        settled['lines'], lines
                    ),
                    'cmv_per_portion': settled['cmv_per_portion'],
                    'calculation_complete': True,
                    'next_step': (
                        f'A receita de {dish!r} já está fechada, e o custo dela é '
                        f'R$ {settled["cmv_per_portion"]:.2f} por porção. Use esse '
                        'número. Se ela pediu para trocar um ingrediente, ou '
                        'desistiu deste prato, chame pricing_reopen_recipe com as '
                        'palavras dela e refaça: receita, portão, custo e preço. '
                        'Se for outro prato, use o nome do outro prato.'
                    ),
                }

            # A recipe found on the web says "1 kg de carne, serve 6". Dividing
            # that by six is arithmetic, and arithmetic done in the model's head
            # is exactly what this server exists to prevent. Pass the yield and
            # the division happens here, where it can be shown.
            if recipe_yields > 1:
                lines = [
                    line.model_copy(
                        update={'quantity': line.quantity / recipe_yields}
                    )
                    for line in lines
                ]

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
            # The itemised cost, ready to read to her. Biggest first, because
            # the first two lines usually explain most of the number and the
            # centavos at the end are noise.
            breakdown = [
                self._in_her_words(entry['amount'], entry['ingredient'], entry['cost'])
                for entry in sorted(used, key=lambda e: -e['cost'])
            ]
            # A cost she has already heard is a promise. Recalculating is fine;
            # changing the number in silence leaves her with two prices in her
            # head. It happened in the flagship transcript of this repository:
            # R$ 8,51 in one turn, R$ 7,80 in the next, no word about it.
            changed = None
            if complete and self.observer is not None:
                from .middleware import ConfidenceMiddleware

                before = self.observer.previous_cmv(
                    ConfidenceMiddleware.SESSION_FALLBACK, dish
                )
                if before is not None and abs(before - cmv) > 0.005:
                    direction = 'caiu' if cmv < before else 'subiu'
                    was = self.observer.previous_cmv_lines(
                        ConfidenceMiddleware.SESSION_FALLBACK, dish
                    )
                    now = {e['ingredient']: e['amount'] for e in used}
                    saiu = sorted(set(was) - set(now))
                    entrou = sorted(set(now) - set(was))
                    mudou = sorted(
                        k for k in set(was) & set(now) if was[k] != now[k]
                    )
                    porque = []
                    if saiu:
                        porque.append(f'saiu {", ".join(saiu)}')
                    if entrou:
                        porque.append(f'entrou {", ".join(entrou)}')
                    if mudou:
                        porque.append(f'mudou a quantidade de {", ".join(mudou)}')
                    changed = {
                        'told_her_before': round(before, 2),
                        'now': round(cmv, 2),
                        'what_moved': {
                            'left_the_recipe': saiu,
                            'joined_the_recipe': entrou,
                            'changed_amount': mudou,
                        },
                        'say_now': (
                            f'Você disse a ela que este prato custava '
                            f'R$ {before:.2f} por porção, e agora deu '
                            f'R$ {cmv:.2f}. Diga que {direction}'
                            + (f', porque {"; ".join(porque)}' if porque else '')
                            + '. Ela não pode ficar com dois preços na cabeça sem '
                            'saber qual vale, nem sem saber o que mudou.'
                        ),
                    }
            # Ask the ledger, not the constant: earlier dishes may already have
            # eaten into the budget.
            budget_check = (
                self._ledger().check(shopping_cost)
                if shopping_cost > 0
                else {'verdict': 'nothing_to_buy', 'fits': True}
            )

            if complete and dish:
                self.lock.lock(dish, lines, portions, round(cmv, 2),
                               shopping=to_buy, shopping_cost=shopping_cost)

            return {
                'dish': dish,
                'cmv_changed_since_you_told_her': changed,
                'recipe_now_settled': bool(complete and dish),
                'portions_per_batch': portions,
                'cmv_per_portion': round(cmv, 2) if complete else None,
                # The same number, named the way she names it. 'CMV' is
                # consultancy vocabulary and she never asked for a consultant.
                'cost_per_portion_for_her': (
                    f'custo por porção: R$ {cmv:.2f}'.replace('.', ',')
                    if complete else None
                ),
                'breakdown_for_her': breakdown if complete else [],
                'calculation_complete': complete,
                'ingredients': used,
                'must_buy': to_buy,
                'shopping_cost': round(shopping_cost, 2),
                'budget': budget_check,
                'not_found': unknown,
                'open_questions': questions,
                'next_step': (
                    'Show her `breakdown_for_her` before the total: a cost she can '
                    'check against her own shopping is worth more than a number she '
                    'has to believe. Never say "CMV" to her. Then run '
                    'market_research_dish_prices for this dish, and price_scenarios '
                    'with the cost and that reference band. Reserve the shopping with '
                    'budget_reserve_purchase only after she says she will buy it: '
                    'you are not buying anything, she is.'
                    if complete
                    else 'Do NOT price yet. Take open_questions back to the conversation.'
                ),
            }

        @self.mcp.tool
        def reopen_recipe(
            dish: Annotated[str, Field(description='Dish whose recipe is settled.')],
            her_words: Annotated[str, Field(description='What SHE said that changes the dish, copied from her message.')],
            what_changed: Annotated[str, Field(description="In one line: 'trocou o presunto por frango', 'desistiu deste prato'.")] = '',
        ) -> dict:
            """Unsettle a recipe, because the dish changed in the conversation.

            The only way back into `calculate_cmv` with a different ingredient
            list. It exists so that a recipe changes when **she** changes it, and
            not because the model composed the list differently on the second
            call.

            After this, redo the work that hung off the old recipe: search the
            recipe again if it is really another dish, run the gate, cost it, and
            price it. The old numbers are not about this recipe any more.
            """
            if len(her_words.split()) < 2:
                return {
                    'reopened': False,
                    'error': 'Reabrir a receita é uma decisão dela, e precisa das '
                             'palavras dela.',
                    'next_step': (
                        'Se ela pediu para trocar alguma coisa ou desistiu do '
                        'prato, copie a frase dela. Se não pediu, a receita '
                        'continua como está e o custo é o que já foi calculado.'
                    ),
                }
            try:
                spoken = self.chat.she_said(her_words)
            except Exception:
                spoken = {'said': False, 'turns_on_record': 0, 'unavailable': True}
            if not spoken['said'] and not spoken.get('unavailable'):
                return {
                    'reopened': False,
                    'error': f'Ela não disse isso. Procurei {her_words!r} nas '
                             f"{spoken['turns_on_record']} falas dela e não achei.",
                    'next_step': (
                        'Não mude a receita dela por conta própria. A receita '
                        'fechada continua valendo.'
                    ),
                }
            because = f'{what_changed} | ela: “{her_words}”'.strip(' |')
            done = self.lock.reopen(dish, because)
            return {
                'reopened': done,
                'dish': dish,
                'note': None if done else 'Não havia receita fechada para este prato.',
                'next_step': (
                    'Refaça tudo que dependia da receita antiga: se for outro prato, '
                    'busque a receita; rode o portão de novo com o que a nova versão '
                    'exige; recalcule o CMV; e só então volte a falar de preço. Os '
                    'números antigos não são mais deste prato.'
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
