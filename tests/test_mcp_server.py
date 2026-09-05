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
