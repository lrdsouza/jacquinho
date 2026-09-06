'''Which MCP output field establishes which kind of claim.

The claim layer only means something if it is checked against what the servers
actually produced. It was not, really: it read two fields out of two tools and
compared everything else against a flat bag of every number that had passed
through, arguments included. That bag is how a shopping total the model chose
counted as evidence for itself.

So the map is declared here, field by field, and two distinctions do the work.

**Output, never argument.** A tool is evidence for what it *computes*. What it
receives is the model talking to itself, and counting that closes a circle with
nothing inside it.

**Grounding is not committing.** `price_scenarios` returns three prices; they
are candidates, and none of them is the price of the dish. Only the one that
went on the menu binds her to anything. Marking every produced number as a
commitment would turn "here are three options" into three contradictions on the
next turn.
'''

from __future__ import annotations

from .claims import ClaimKind, ToolFact

# tool -> ((path, kind, binds), ...)
#
# Paths are dotted, with `[]` for "every element of this list". Only fields a
# tool derives appear here: nothing that arrives as an argument.
FACT_MAP: dict[str, tuple[tuple[str, ClaimKind, bool], ...]] = {
    'pantry_list_ingredients': (
        ('ingredients[].unit_cost', ClaimKind.PANTRY, False),
        ('ingredients[].price_paid', ClaimKind.PANTRY, False),
    ),
    'pantry_find_ingredient': (
        ('item.unit_cost', ClaimKind.PANTRY, False),
        ('item.price_paid', ClaimKind.PANTRY, False),
    ),
    'pricing_calculate_cmv': (
        # The cost of the dish, and the only cost that binds.
        ('cmv_per_portion', ClaimKind.COST, True),
        ('shopping_cost', ClaimKind.BUDGET, True),
        ('must_buy[].estimated_cost', ClaimKind.BUDGET, False),
        # Every line of the breakdown she is read out loud.
        ('ingredients[].cost', ClaimKind.COST, False),
        ('budget.remaining_after', ClaimKind.BUDGET, False),
        # Her stock is finite, so what is left of it and how much she still has
        # to buy are facts of the pantry, not rhetoric. Amounts, not money.
        ('ingredients[].stock_left_quantity', ClaimKind.PANTRY, False),
        ('ingredients[].already_used_quantity', ClaimKind.PANTRY, False),
        ('must_buy[].buy_quantity', ClaimKind.PANTRY, False),
    ),
    'pricing_price_scenarios': (
        # Candidates. She has not chosen yet, so none of these binds.
        ('break_even_price', ClaimKind.PRICE, False),
        ('cmv_per_portion', ClaimKind.COST, False),
        ('scenarios[].selling_price', ClaimKind.PRICE, False),
        ('scenarios[].she_receives', ClaimKind.RECEIPT, False),
        ('scenarios[].profit_per_portion', ClaimKind.PROFIT, False),
        ('scenarios[].real_terms.profit_in_12_months_at_same_price',
         ClaimKind.PROFIT, False),
        ('scenarios[].real_terms.price_to_hold_this_profit', ClaimKind.PRICE, False),
    ),
    'market_research_dish_prices': (
        ('reference.min', ClaimKind.MARKET, False),
        ('reference.median', ClaimKind.MARKET, False),
        ('reference.max', ClaimKind.MARKET, False),
        ('observed[].price', ClaimKind.MARKET, False),
    ),
    'budget_get_status': (
        ('total_budget', ClaimKind.BUDGET, False),
        ('remaining', ClaimKind.BUDGET, False),
        ('reserved_for_her_to_buy', ClaimKind.BUDGET, False),
    ),
    'budget_check_purchase': (
        ('remaining_before', ClaimKind.BUDGET, False),
        ('remaining_after', ClaimKind.BUDGET, False),
        ('shortfall', ClaimKind.BUDGET, False),
    ),
    'budget_reserve_purchase': (
        ('remaining', ClaimKind.BUDGET, False),
        ('reserved_for_her_to_buy', ClaimKind.BUDGET, False),
    ),
    'menu_add_dish': (
        # This is where a price stops being a candidate.
        ('cmv', ClaimKind.COST, True),
        ('price', ClaimKind.PRICE, True),
        ('she_receives', ClaimKind.RECEIPT, True),
        ('profit', ClaimKind.PROFIT, True),
    ),
    'pantry_what_is_left': (
        ('ingredients[].stock', ClaimKind.PANTRY, True),
        ('ingredients[].already_committed', ClaimKind.PANTRY, True),
        ('ingredients[].stock_before_any_dish', ClaimKind.PANTRY, True),
    ),
    'menu_expected_return': (
        ('revenue', ClaimKind.PRICE, False),
        ('after_platform_fee', ClaimKind.RECEIPT, False),
        ('platform_fee_paid', ClaimKind.BUDGET, False),
        ('production_cost', ClaimKind.COST, False),
        ('cash_to_spend', ClaimKind.BUDGET, False),
        ('profit', ClaimKind.PROFIT, False),
        ('dishes[].profit', ClaimKind.PROFIT, False),
        ('dishes[].revenue', ClaimKind.PRICE, False),
        # The closing message reads dish by dish, so every line of it needs a
        # field behind it. Without these three the agent subtracted the fee in
        # prose - correctly, and uncheckably.
        ('dishes[].platform_fee_paid', ClaimKind.BUDGET, False),
        ('dishes[].after_platform_fee', ClaimKind.RECEIPT, False),
        ('dishes[].production_cost', ClaimKind.COST, False),
    ),
    'menu_build_launch_menu': (
        ('items[].cmv', ClaimKind.COST, True),
        ('items[].price', ClaimKind.PRICE, True),
        ('items[].profit', ClaimKind.PROFIT, True),
    ),
}


def _walk(node, path: list[str]):
    '''Every value at a dotted path, following `[]` into lists.'''
    if not path:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            yield float(node)
        return
    head, rest = path[0], path[1:]
    if head.endswith('[]'):
        branch = (node or {}).get(head[:-2]) if isinstance(node, dict) else None
        for item in branch or []:
            yield from _walk(item, rest)
        return
    if isinstance(node, dict):
        yield from _walk(node.get(head), rest)


def facts_from(tool: str, payload: dict | None, subject: str) -> list[ToolFact]:
    '''The typed facts one tool result establishes.'''
    spec = FACT_MAP.get(tool)
    if not spec or not isinstance(payload, dict):
        return []
    # FastMCP wraps a bare return under 'result'.
    inner = payload.get('result')
    body = inner if isinstance(inner, dict) else payload

    out: list[ToolFact] = []
    for path, kind, binds in spec:
        for value in _walk(body, path.split('.')):
            out.append(ToolFact(subject=subject, kind=kind, value=round(value, 2),
                                source=f'{tool}.{path}', binds=binds))
    return out


def output_values(tool: str, payload: dict | None, arguments: dict | None) -> set[float]:
    '''Every number a tool produced, minus every number it was handed.

    The subtraction is the point. `budget_reserve_purchase` was echoing the
    amount the model chose, and the figure audit accepted it as evidence that
    the amount was right.
    '''
    from .audit import MessageAudit

    if not isinstance(payload, dict):
        return set()
    produced = MessageAudit.known_values(payload)
    given = MessageAudit.known_values(arguments) if isinstance(arguments, dict) else set()
    return produced - given
