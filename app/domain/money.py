'''Money arithmetic: the delivery fee, the floor, and how a menu rounds.

Small enough to look like it belongs wherever it is used, which is how it ended
up inside the pricing MCP - where it could not be tested without starting a
server. It is domain logic and lives here.
'''

from __future__ import annotations

import math


def net_share(platform_fee: float) -> float:
    '''What is left of a sale after the platform takes its cut.'''
    return 1 - platform_fee


def break_even(cmv: float, platform_fee: float) -> float:
    '''The price below which she loses money: P = CMV / (1 - fee).'''
    return cmv / net_share(platform_fee)


def profit(price: float, cmv: float, platform_fee: float) -> float:
    '''What she keeps: (1 - fee) x P - CMV.'''
    return price * net_share(platform_fee) - cmv


def menu_rounding(value: float) -> float:
    '''Round UP to a .90 ending, the way a menu prices things.

    Always upwards: rounding a price down can put it under the break-even floor
    the caller just computed.
    '''
    return math.floor(value) + 0.90 if value % 1 <= 0.90 else math.ceil(value) + 0.90
