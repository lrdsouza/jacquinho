"""The arithmetic the challenge specifies."""

import math

import pytest

from app.domain.money import break_even, menu_rounding, net_share, profit

FEE = 0.10
NET = net_share(FEE)


def test_break_even_is_cmv_over_net_share():
    assert break_even(8.68, FEE) == pytest.approx(9.6444, abs=0.001)


def test_at_break_even_she_makes_exactly_nothing():
    cmv = 8.68
    assert profit(break_even(cmv, FEE), cmv, FEE) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize('price', [14.90, 19.90, 24.90])
def test_she_receives_ninety_percent(price):
    assert price * NET == pytest.approx(price * 0.9)


@pytest.mark.parametrize('price, cmv', [(19.90, 8.68), (14.90, 6.40)])
def test_profit_is_what_she_receives_minus_cost(price, cmv):
    assert profit(price, cmv, FEE) == pytest.approx(0.9 * price - cmv)


def test_a_price_below_break_even_loses_money():
    cmv = 8.68
    assert profit(break_even(cmv, FEE) - 1, cmv, FEE) < 0


@pytest.mark.parametrize('value', [14.17, 18.89, 23.61, 14.95, 9.64])
def test_menu_rounding_lands_on_ninety_and_never_below(value):
    rounded = menu_rounding(value)
    assert math.isclose(rounded % 1, 0.90, abs_tol=1e-9)
    assert rounded >= value


# --- something the pantry does not have -------------------------------------

def test_a_purchase_is_split_between_the_package_and_the_spoonful():
    """She cannot buy 40 g of condensed milk: she buys a can. The batch eats a
    fraction of it. Charging the batch for the whole can overstated the cost of
    a brigadeiro by an order of magnitude, and the split was being done in prose."""
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP, PurchasedItem, RecipeLine

    to_buy = []
    entry, cost = PricingMCP._cost_a_purchase(
        RecipeLine(ingredient='leite condensado', quantity=15, unit='g'),
        PurchasedItem(ingredient='leite condensado', package_price=7.89,
                      package_quantity=395, package_unit='g'),
        portions=25, to_buy=to_buy,
    )
    # 7,89 for 395 g is about 0,02 per gram; 15 g per brigadeiro is about 30 centavos.
    assert entry is not None
    assert 0.29 <= cost <= 0.31
    # And the shopping list buys one whole can, not 400 g of nothing.
    assert to_buy[0]['estimated_cost'] == 7.89
    assert to_buy[0]['buy'].startswith('1 x 395')
    assert to_buy[0]['left_over'].endswith('kg')


def test_one_gram_over_the_package_buys_a_second_package():
    """375 g fits in one can; 400 g does not, and the shopping list has to say
    two even though the second is almost untouched."""
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP, PurchasedItem, RecipeLine

    to_buy = []
    PricingMCP._cost_a_purchase(
        RecipeLine(ingredient='leite condensado', quantity=16, unit='g'),
        PurchasedItem(ingredient='leite condensado', package_price=7.89,
                      package_quantity=395, package_unit='g'),
        portions=25, to_buy=to_buy,
    )
    assert to_buy[0]['buy'].startswith('2 x 395')
    assert to_buy[0]['estimated_cost'] == round(2 * 7.89, 2)
    assert to_buy[0]['left_over'] == '0.39 kg'


def test_a_batch_bigger_than_the_package_buys_more_packages():
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP, PurchasedItem, RecipeLine

    to_buy = []
    PricingMCP._cost_a_purchase(
        RecipeLine(ingredient='leite condensado', quantity=100, unit='g'),
        PurchasedItem(ingredient='leite condensado', package_price=7.89,
                      package_quantity=395, package_unit='g'),
        portions=10, to_buy=to_buy,
    )
    # 1000 g needed, 395 g per can: three cans.
    assert to_buy[0]['buy'].startswith('3 x 395')
    assert to_buy[0]['estimated_cost'] == round(3 * 7.89, 2)


def test_a_package_measured_in_another_dimension_asks_instead_of_guessing():
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP, PurchasedItem, RecipeLine

    to_buy = []
    entry, question = PricingMCP._cost_a_purchase(
        RecipeLine(ingredient='granulado', quantity=2, unit='un'),
        PurchasedItem(ingredient='granulado', package_price=4.99,
                      package_quantity=150, package_unit='g'),
        portions=25, to_buy=to_buy,
    )
    assert entry is None
    assert 'rende uma embalagem' in question['question']
    assert to_buy == []


# --- the close: what the day is worth ---------------------------------------

def test_the_projection_keeps_the_two_costs_apart():
    """What the food costs and what she still has to buy are different numbers,
    and adding them together double-counts the pantry she already paid for."""
    from app.domain.money import launch_projection

    p = launch_projection(
        [{'dish': 'Lasanha de panela', 'portions': 8, 'cmv': 10.07,
          'price': 17.90, 'she_receives': 16.11, 'profit': 6.04}],
        cash_to_spend=29.86,
    )
    assert p['production_cost'] == round(10.07 * 8, 2)
    assert p['revenue'] == round(17.90 * 8, 2)
    assert p['after_platform_fee'] == round(16.11 * 8, 2)
    assert p['profit'] == round(6.04 * 8, 2)
    assert p['cash_to_spend'] == 29.86
    # The fee she pays is revenue minus what reaches her, not a fourth number.
    assert p['platform_fee_paid'] == round(p['revenue'] - p['after_platform_fee'], 2)


def test_the_return_is_measured_over_what_the_food_cost():
    from app.domain.money import launch_projection

    p = launch_projection(
        [{'dish': 'X', 'portions': 10, 'cmv': 5.00,
          'price': 12.00, 'she_receives': 10.80, 'profit': 5.80}]
    )
    assert p['production_cost'] == 50.0
    assert p['profit'] == 58.0
    assert p['return_on_cost_percent'] == 116.0


def test_a_return_over_nothing_is_a_question_not_infinity():
    from app.domain.money import launch_projection

    p = launch_projection([{'dish': 'X', 'portions': 4, 'cmv': 0,
                            'price': 10, 'she_receives': 9, 'profit': 9}])
    assert p['return_on_cost_percent'] is None


def test_the_projection_adds_up_across_dishes():
    from app.domain.money import launch_projection

    p = launch_projection([
        {'dish': 'A', 'portions': 6, 'cmv': 5.00, 'price': 15.00,
         'she_receives': 13.50, 'profit': 8.50},
        {'dish': 'B', 'portions': 4, 'cmv': 2.00, 'price': 8.00,
         'she_receives': 7.20, 'profit': 5.20},
    ])
    assert p['portions_total'] == 10
    assert p['production_cost'] == round(6 * 5.00 + 4 * 2.00, 2)
    assert p['profit'] == round(6 * 8.50 + 4 * 5.20, 2)


def test_the_headline_percentage_cannot_exceed_one_hundred():
    """Return over production cost read 1556% for a brigadeiro, because the base
    is the spoonful the batch ate and not what she paid at the till. True, and
    useless as a headline: margin on sales is the number that stays believable."""
    from app.domain.money import launch_projection

    p = launch_projection(
        [{'dish': 'Brigadeiro', 'portions': 25, 'cmv': 0.81,
          'price': 14.90, 'she_receives': 13.41, 'profit': 12.60}],
        cash_to_spend=38.82,
    )
    assert 0 < p['margin_on_sales_percent'] <= 100
    assert p['margin_on_sales_percent'] == 84.6
    # The other two are still reported, and still labelled for what they are.
    assert p['return_on_cost_percent'] > 1000
    assert p['return_on_cash_percent'] == round(315.0 / 38.82 * 100, 1)


def test_a_percentage_over_a_missing_base_is_none():
    from app.domain.money import launch_projection

    p = launch_projection([{'dish': 'X', 'portions': 4, 'cmv': 0,
                            'price': 10, 'she_receives': 9, 'profit': 9}])
    assert p['return_on_cost_percent'] is None
    assert p['return_on_cash_percent'] is None
    assert p['margin_on_sales_percent'] is not None


# --- the cost, in her language ----------------------------------------------

def test_the_breakdown_reads_like_a_person_talking():
    """A total on its own is a number she has to take on faith. '100 g de carne
    moída: R$ 2,80' is one she can check against her own shopping.

    It comes back as a bullet, dash included: six ingredients run into a
    paragraph become something she skims, and the line she would have questioned
    is the one that disappears.
    """
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP

    said = PricingMCP._in_her_words('0.1 kg', 'carne moída', 2.80)
    assert said == '- 100 g de carne moída: R$ 2,80'


def test_small_volumes_become_millilitres():
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP

    # Vírgula decimal, porque é assim que se escreve em português.
    assert PricingMCP._in_her_words('0.0625 l', 'leite', 0.31) == (
        '- 62,5 ml de leite: R$ 0,31')


def test_pieces_are_counted_not_weighed():
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP

    assert PricingMCP._in_her_words('1 un', 'ovo', 0.60).startswith('- 1 unidade de ovo')
    assert PricingMCP._in_her_words('3 un', 'ovo', 1.80).startswith('- 3 unidades de ovo')


def test_a_whole_kilo_stays_a_kilo():
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP

    assert PricingMCP._in_her_words('1,5 kg'.replace(',', '.'), 'farinha', 7.72) == (
        '- 1,5 kg de farinha: R$ 7,72')


def test_the_recipe_yield_is_divided_by_the_tool_not_by_the_model():
    """A recipe found on the web says '1 kg de carne, serve 6'. Dividing that by
    six is arithmetic, and arithmetic in the model's head is what this server
    exists to prevent."""
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import RecipeLine

    line = RecipeLine(ingredient='carne moída', quantity=1.0, unit='kg')
    per_portion = line.model_copy(update={'quantity': line.quantity / 6})
    assert round(per_portion.quantity, 4) == 0.1667


def test_the_tail_of_the_breakdown_becomes_one_line():
    """Eleven bullets ending in 'uma pitada de sal: R$ 0,00' is worse than the
    total alone: she stops reading before the line she would have questioned."""
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP

    used = [
        {'ingredient': 'Carne moída', 'amount': '0.0625 kg', 'cost': 1.75},
        {'ingredient': 'Queijo mussarela', 'amount': '0.025 kg', 'cost': 1.00},
        {'ingredient': 'Batata', 'amount': '0.125 kg', 'cost': 0.75},
        {'ingredient': 'Manteiga', 'amount': '0.00375 kg', 'cost': 0.15},
        {'ingredient': 'Azeite', 'amount': '0.0015 l', 'cost': 0.12},
        {'ingredient': 'Cebola', 'amount': '0.015 kg', 'cost': 0.06},
        {'ingredient': 'Leite', 'amount': '0.0125 l', 'cost': 0.06},
        {'ingredient': 'Alho', 'amount': '0.0005 kg', 'cost': 0.01},
        {'ingredient': 'Sal', 'amount': '0.000625 kg', 'cost': 0.00},
    ]
    lines = PricingMCP._breakdown_lines(used, 3.90)

    assert lines[0].startswith('- 62,5 g de Carne moída')
    # The tail is folded, not dropped: it keeps its ingredients and its cents.
    assert lines[-1].startswith('- e o resto (')
    assert 'sal' in lines[-1] and 'alho' in lines[-1]
    assert len(lines) <= PricingMCP.MOST_LINES + 1


def test_a_short_recipe_keeps_every_line():
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP

    used = [
        {'ingredient': 'Carne moída', 'amount': '0.1 kg', 'cost': 2.80},
        {'ingredient': 'Queijo mussarela', 'amount': '0.05 kg', 'cost': 2.00},
    ]
    lines = PricingMCP._breakdown_lines(used, 4.80)
    assert len(lines) == 2
    assert not any('e o resto' in line for line in lines)


def test_the_folded_line_adds_up_to_the_total():
    """What is folded is still counted. It has to be, or the bullets stop
    explaining the number they sit under."""
    pytest.importorskip('fastmcp')
    from app.mcps.pricing_mcp import PricingMCP

    used = [
        {'ingredient': f'Item {i}', 'amount': f'{i} un', 'cost': round(1.0 / (i + 1), 2)}
        for i in range(12)
    ]
    total = sum(entry['cost'] for entry in used)
    lines = PricingMCP._breakdown_lines(used, total)
    shown = sum(
        float(line.rsplit('R$ ', 1)[1].replace(',', '.')) for line in lines
    )
    assert shown == pytest.approx(total, abs=0.02)
