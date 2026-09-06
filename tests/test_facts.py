"""The map from MCP output fields to claim kinds."""

from app.domain.claims import ClaimKind
from app.domain.facts import FACT_MAP, facts_from, output_values


def test_the_cost_of_a_dish_comes_from_the_field_that_computes_it():
    facts = facts_from('pricing_calculate_cmv', {
        'cmv_per_portion': 4.15, 'shopping_cost': 6.95,
        'must_buy': [{'estimated_cost': 6.95}],
    }, 'lasanha')
    kinds = {(f.kind, f.value, f.binds) for f in facts}
    assert (ClaimKind.COST, 4.15, True) in kinds
    assert (ClaimKind.BUDGET, 6.95, True) in kinds
    assert all(f.source.startswith('pricing_calculate_cmv.') for f in facts)


def test_scenarios_are_grounded_but_do_not_bind():
    facts = facts_from('pricing_price_scenarios', {
        'break_even_price': 4.61,
        'scenarios': [{'selling_price': 15.90, 'profit_per_portion': 10.16},
                      {'selling_price': 17.90, 'profit_per_portion': 11.96}],
    }, 'lasanha')
    assert {f.value for f in facts} == {4.61, 15.90, 10.16, 17.90, 11.96}
    assert not any(f.binds for f in facts)


def test_the_menu_is_where_a_price_stops_being_a_candidate():
    facts = facts_from('menu_add_dish', {
        'price': 16.90, 'she_receives': 15.21, 'profit': 11.06, 'cmv': 4.15,
    }, 'lasanha')
    assert all(f.binds for f in facts)
    assert {f.kind for f in facts} == {
        ClaimKind.PRICE, ClaimKind.RECEIPT, ClaimKind.PROFIT, ClaimKind.COST}


def test_a_wrapped_result_is_unwrapped():
    facts = facts_from('budget_get_status',
                       {'result': {'remaining': 63.91}}, 'lasanha')
    assert [f.value for f in facts] == [63.91]


def test_an_unmapped_tool_produces_no_facts():
    assert facts_from('chat_save_turn', {'saved': True, 'turns': 3}, 'x') == []


def test_an_echoed_argument_is_not_evidence():
    """budget_reserve_purchase was handed the amount by the model and returned
    it, so the figure audit accepted it as evidence that the amount was right."""
    payload = {'reserved': True, 'amount': 12.0, 'remaining': 68.0}
    assert output_values('budget_reserve_purchase', payload, {'amount': 12.0}) == {68.0}


def test_without_arguments_everything_produced_counts():
    assert output_values('budget_get_status', {'remaining': 68.0}, None) == {68.0}


def test_every_mapped_tool_name_looks_like_a_real_tool():
    for tool in FACT_MAP:
        assert '_' in tool and tool.islower()


def test_every_mapped_field_exists_in_the_tool_that_produces_it():
    """A map pointing at a field that does not exist is worse than no map: it
    fails silently and every claim it should have grounded looks unsupported."""
    import pytest

    pytest.importorskip('fastmcp')
    import inspect

    from app.domain import budget, catalogue, market, money, pantry  # noqa: F401
    import app.mcps.budget_mcp as bm
    import app.mcps.market_mcp as km
    import app.mcps.menu_mcp as mm
    import app.mcps.pantry_mcp as am
    import app.mcps.pricing_mcp as pm

    sources = '\n'.join(inspect.getsource(mod) for mod in (
        bm, km, mm, am, pm, budget, catalogue, market, money, pantry,
    ))

    missing = []
    for tool, spec in FACT_MAP.items():
        for path, _, _ in spec:
            leaf = path.split('.')[-1].replace('[]', '')
            if f"'{leaf}'" not in sources and f'"{leaf}"' not in sources:
                missing.append(f'{tool}.{path}')
    assert not missing, f'campos que nenhum servidor produz: {missing}'
