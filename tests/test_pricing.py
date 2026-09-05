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
