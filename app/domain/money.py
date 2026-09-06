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


def launch_projection(
    lines: list[dict], cash_to_spend: float = 0.0
) -> dict:
    '''What a whole batch is worth, in the only terms she thinks in.

    A menu with a cost, a price and a per-portion profit answers "how much do I
    make on one". It does not answer the question she actually asks, which is
    whether the day was worth doing. That needs the quantity, and the quantity
    is hers: how many marmitas come out of the pan.

    Two costs, kept apart on purpose, because collapsing them is the mistake
    this function exists to avoid:

    ``production_cost`` is what the food costs, ingredients she already owned
    included. ``cash_to_spend`` is what still has to leave her pocket to buy
    what the pantry does not have. The return is measured over production cost,
    which is the number that stays honest as her stock changes.
    '''
    rows = []
    for line in lines:
        portions = int(line.get('portions') or 0)
        cmv = float(line.get('cmv') or 0.0)
        price = float(line.get('price') or 0.0)
        receives = float(line.get('she_receives') or 0.0)
        per_portion = float(line.get('profit') or 0.0)
        revenue = round(price * portions, 2)
        received = round(receives * portions, 2)
        rows.append({
            'dish': line.get('dish', ''),
            'portions': portions,
            'production_cost': round(cmv * portions, 2),
            'revenue': revenue,
            'after_platform_fee': received,
            # The platform's cut for THIS dish. It was only ever returned as a
            # total, and the closing message reads dish by dish - so the agent
            # subtracted per dish in prose, and the figure audit caught two
            # numbers no tool had produced. They were right, and being right is
            # not the standard: arithmetic in a message is arithmetic nobody
            # can check.
            'platform_fee_paid': round(revenue - received, 2),
            'profit': round(per_portion * portions, 2),
            'profit_per_portion': round(per_portion, 2),
        })

    cost = round(sum(r['production_cost'] for r in rows), 2)
    revenue = round(sum(r['revenue'] for r in rows), 2)
    received = round(sum(r['after_platform_fee'] for r in rows), 2)
    gain = round(sum(r['profit'] for r in rows), 2)
    portions = sum(r['portions'] for r in rows)

    cash = round(cash_to_spend, 2)
    return {
        'dishes': rows,
        'portions_total': portions,
        'production_cost': cost,
        'cash_to_spend': cash,
        'revenue': revenue,
        'after_platform_fee': received,
        'profit': gain,
        'platform_fee_paid': round(revenue - received, 2),
        # Three ways to say "was it worth it", because one of them alone lies.
        #
        # Margin on sales is the honest headline: it cannot exceed 100, so it
        # stays believable and comparable between dishes.
        #
        # Return over production cost is what a brigadeiro does to a spoonful of
        # condensed milk, and it reads as 1556% because the base is the fraction
        # the batch ate, not what she paid at the till. True, and useless as a
        # headline.
        #
        # Return over cash is measured against what actually leaves her pocket
        # now. It flatters later batches, since most of a can is still on the
        # shelf, so it is reported next to the other two rather than instead.
        #
        # None rather than zero when a base is missing: a percentage over
        # nothing is not infinity, it is a question about missing data.
        'margin_on_sales_percent': round(gain / revenue * 100, 1) if revenue else None,
        'return_on_cost_percent': round(gain / cost * 100, 1) if cost else None,
        'return_on_cash_percent': round(gain / cash * 100, 1) if cash else None,
    }
