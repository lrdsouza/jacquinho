"""The server itself: does it start, mount and answer without breaking.

These need fastmcp, so they run inside the container - `jacquinho test`.
"""

import pytest

pytest.importorskip('fastmcp')

from fastmcp import Client  # noqa: E402

from app.config import Settings  # noqa: E402
from app.mcps.server import MCPServer  # noqa: E402


@pytest.fixture(scope='module')
def server():
    return MCPServer(Settings.from_env()).root


@pytest.mark.asyncio
async def test_every_server_is_mounted(server):
    async with Client(server) as client:
        names = {tool.name for tool in await client.list_tools()}
    prefixes = {name.split('_')[0] for name in names}
    assert {'pantry', 'dishes', 'recipes', 'kitchen', 'market',
            'economy', 'budget', 'pricing', 'confidence', 'menu', 'chat'} <= prefixes


@pytest.mark.asyncio
async def test_no_tool_name_collides(server):
    async with Client(server) as client:
        names = [tool.name for tool in await client.list_tools()]
    assert len(names) == len(set(names))


@pytest.mark.asyncio
async def test_every_tool_describes_itself(server):
    """A tool without a description is a tool the agent will misuse."""
    async with Client(server) as client:
        tools = await client.list_tools()
    undocumented = [t.name for t in tools if not (t.description or '').strip()]
    assert undocumented == []


@pytest.mark.asyncio
async def test_prompts_are_registered(server):
    async with Client(server) as client:
        names = {p.name for p in await client.list_prompts()}
    assert {'open_conversation', 'check_specific_dish',
            'suggest_from_pantry', 'evaluate_dish'} <= names


@pytest.mark.asyncio
async def test_the_spreadsheet_seeds_the_database_on_startup(server):
    """The application reads rows, not the file; the file only seeds them."""
    async with Client(server) as client:
        result = await client.call_tool('pantry_list_ingredients', {})
    assert result.data['total_ingredients'] == 37


@pytest.mark.asyncio
async def test_seeding_twice_changes_nothing(server):
    async with Client(server) as client:
        again = await client.call_tool('pantry_reseed_from_spreadsheet', {})
    assert again.data['seeded'] is False
    assert again.data['reason'] == 'already seeded' 


@pytest.mark.asyncio
async def test_a_bad_argument_is_refused_not_guessed(server):
    from fastmcp.exceptions import ToolError

    async with Client(server) as client:
        with pytest.raises(ToolError):
            await client.call_tool('pricing_price_scenarios', {'cmv_per_portion': -5})


@pytest.mark.asyncio
async def test_unknown_ingredient_returns_suggestions_not_an_error(server):
    async with Client(server) as client:
        result = await client.call_tool(
            'pantry_find_ingredient', {'name': 'farinha de rosca'}
        )
    assert result.data['found'] is False
    assert result.data['suggestions']


@pytest.mark.asyncio
async def test_a_store_that_answers_reports_available(server):
    async with Client(server) as client:
        result = await client.call_tool('chat_recent_history', {'session': 'x'})
    assert result.data['available'] is True


@pytest.mark.asyncio
async def test_money_tools_are_refused_until_the_gate_passes(server):
    """Advice can be corrected in the next turn; these cost money."""
    from fastmcp.exceptions import ToolError

    async with Client(server) as client:
        with pytest.raises(ToolError, match='gate'):
            await client.call_tool(
                'pricing_price_scenarios', {'cmv_per_portion': 8.68}
            )


@pytest.mark.asyncio
async def test_the_gate_takes_a_dish_so_approval_does_not_leak(server):
    """Without a dish the approval landed on a nameless trail, and the dish it
    was meant for was then refused entry to the menu."""
    async with Client(server) as client:
        tools = {t.name: t for t in await client.list_tools()}
    for name in ('kitchen_check_feasibility', 'kitchen_elicitation_gaps'):
        assert 'dish' in tools[name].inputSchema['properties']


@pytest.mark.asyncio
async def test_assessment_fills_gaps_from_what_was_observed(server):
    """The agent assembles the evidence bundle by hand and leaves things out.

    A real run produced a badge saying 'sem preço de mercado' minutes after the
    market had been researched, because the bundle omitted it.
    """
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': 'Teste', 'equipment_needed': [], 'techniques_needed': []},
        )
        await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': 'Teste',
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'}]},
        )
        # The bundle below mentions neither the gate nor the CMV.
        report = await client.call_tool(
            'confidence_assess_answer',
            {'dish': 'Teste', 'draft_answer': 'x', 'claim': 'cost',
             'mode': 'deterministic', 'evidence': {}},
        )
    signals = {s['signal']: s['score'] for s in report.data['deterministic']['signals']}
    assert signals['feasibility'] == 1.0
    assert signals['cost'] > 0


@pytest.mark.asyncio
async def test_discovery_has_a_budget(server):
    """One real turn spent twenty discoveries - about a hundred web searches -
    and ended with no reply at all."""
    from fastmcp.exceptions import ToolError

    async with Client(server) as client:
        for _ in range(5):
            await client.call_tool(
                'dishes_discover_dishes', {'category': 'main_course', 'queries': 2}
            )
        with pytest.raises(ToolError, match='buscas'):
            await client.call_tool(
                'dishes_discover_dishes', {'category': 'dessert', 'queries': 2}
            )


@pytest.mark.asyncio
async def test_the_agent_can_ask_what_it_has_not_asked(server):
    """Not the model deducing it: a query. 'unknown' is a stored state."""
    async with Client(server) as client:
        coverage = await client.call_tool('kitchen_elicitation_coverage', {})
        questions = await client.call_tool('kitchen_next_questions', {'limit': 3})
    assert coverage.data['still_unknown']
    assert coverage.data['ready_to_recommend'] is False
    assert questions.data['questions'][0]['priority'] == 1


@pytest.mark.asyncio
async def test_recording_an_answer_reports_what_is_settled(server):
    """The agent kept re-asking things it had just been told."""
    async with Client(server) as client:
        result = await client.call_tool(
            'kitchen_record_capability',
            {'category': 'equipment', 'item': 'fogao',
             'state': 'confirmed_yes', 'note': '4 bocas'},
        )
    settled = result.data['already_answered']
    unknown = result.data['still_unknown']
    assert 'fogao' in settled
    # Order-independent: other tests share this database, so assert the
    # relationship rather than which specific items happen to be pending.
    assert unknown, 'the checklist is never fully answered by one call'
    assert not set(settled) & set(unknown)


@pytest.mark.asyncio
async def test_cmv_is_arithmetic_and_shows_its_working(server):
    """The model writes no number here."""
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': 'Conta', 'equipment_needed': [], 'techniques_needed': []},
        )
        result = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': 'Conta',
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'}]},
        )
    line = result.data['ingredients'][0]
    assert line['arithmetic'] == '0.2 x 14.00 = 2.80'
    assert result.data['cmv_per_portion'] == pytest.approx(2.80)


@pytest.mark.asyncio
async def test_an_ambiguous_unit_becomes_a_question_not_an_estimate(server):
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': 'Brownie', 'equipment_needed': [], 'techniques_needed': []},
        )
        result = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': 'Brownie',
             'lines': [{'ingredient': 'Cobertura de chocolate',
                        'quantity': 200, 'unit': 'g'}]},
        )
    assert result.data['cmv_per_portion'] is None
    assert result.data['open_questions']


@pytest.mark.asyncio
async def test_acceptance_check_lists_what_is_still_missing(server):
    """The checks lived in five places and nobody consulted all five."""
    async with Client(server) as client:
        result = await client.call_tool(
            'menu_acceptance_check',
            {'dish': 'Prato Novo', 'requirements': ['massa fresca']},
        )
    data = result.data
    assert data['ready_to_accept'] is False
    assert 'viabilidade' in data['blocking']
    assert 'custo' in data['blocking']
    # And it hands over the actual question, not just the gap.
    assert data['questions_she_has_not_been_asked'][0]['question']


@pytest.mark.asyncio
async def test_acceptance_check_clears_once_every_check_passes(server):
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': 'Pronto', 'equipment_needed': [], 'techniques_needed': []},
        )
        await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': 'Pronto',
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 100, 'unit': 'g'}]},
        )
        await client.call_tool(
            'confidence_assess_answer',
            {'dish': 'Pronto', 'draft_answer': 'x', 'claim': 'cost',
             'mode': 'deterministic', 'evidence': {}},
        )
        result = await client.call_tool('menu_acceptance_check', {'dish': 'Pronto'})
    assert result.data['ready_to_accept'] is True
    assert result.data['blocking'] == []


@pytest.mark.asyncio
async def test_market_and_inflation_inform_but_do_not_block_acceptance(server):
    """A dish can go on the menu without a market price; a price cannot be
    quoted without one. Different things."""
    async with Client(server) as client:
        result = await client.call_tool('menu_acceptance_check', {'dish': 'Pronto'})
    optional = {
        c['check'] for c in result.data['checks'] if not c['blocks_acceptance']
    }
    assert optional == {'preço de mercado', 'inflação atual'}
