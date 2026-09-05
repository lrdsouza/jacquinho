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
