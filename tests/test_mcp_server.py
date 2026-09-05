"""The server itself: does it start, mount and answer without breaking.

These need fastmcp, so they run inside the container - `jacquinho test`.
"""

import pytest

pytest.importorskip('fastmcp')

from fastmcp import Client  # noqa: E402

from app.config import Settings  # noqa: E402
from app.mcps.server import MCPServer  # noqa: E402
from conftest import capture_her_message  # noqa: E402


@pytest.fixture(scope='module')
def built():
    return MCPServer(Settings.from_env())


@pytest.fixture(scope='module')
def server(built):
    return built.root


@pytest.fixture(autouse=True)
def one_conversation_per_test(built):
    """A verdict owed to her belongs to the conversation that created it.

    The server is built once for the module because building it is slow, so
    without this a debt raised in one test would close the tools of the next -
    which is correct in a conversation and nonsense across tests.
    """
    yield
    built.observer.pending.clear()
    built.observer.announced.clear()


async def _she_says(built, client, text, **capability):
    """She speaks, and only then is her answer recorded.

    The agent once decided she owned an oven nobody had asked about and priced a
    whole lasagna on it. A confirmed answer is now a claim about her words, and
    the server looks them up in what the runtime captured - so the tests capture
    them the same way, through the turn-boundary route rather than through the
    tool the agent could have typed anything into.
    """
    await capture_her_message(built, text)
    return await client.call_tool(
        'kitchen_record_capability', {'her_words': text, **capability},
    )


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
    # Order-independent: other tests answer items in this shared database, so
    # assert the shape of the answer rather than which items are still pending.
    assert coverage.data['still_unknown']
    assert 0 <= coverage.data['coverage_percent'] < 100
    asked = questions.data['questions']
    assert asked and asked == sorted(asked, key=lambda q: q['priority'])


@pytest.mark.asyncio
async def test_recording_an_answer_reports_what_is_settled(built, server):
    """The agent kept re-asking things it had just been told."""
    async with Client(server) as client:
        result = await _she_says(
            built, client, 'tenho um fogao de 4 bocas aqui em casa',
            category='equipment', item='fogao', state='confirmed_yes',
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
        # A requirement of its own, because this database is shared with every
        # other test and with whatever the last real conversation answered. The
        # assertion is about a question she has not been asked; borrowing one
        # that someone else may have answered tests the neighbours instead.
        await client.call_tool(
            'kitchen_register_requirement',
            {'key': 'prensa_de_teste', 'category': 'equipment',
             'question': 'Você tem prensa?',
             'why_it_matters': 'Sem ela o prato não sai.',
             'priority': 1, 'triggers': ['prensa']},
        )
        result = await client.call_tool(
            'menu_acceptance_check',
            {'dish': 'Prato Novo', 'requirements': ['prensa_de_teste']},
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


@pytest.mark.asyncio
async def test_a_no_tells_the_agent_to_close_the_dish(built, server):
    """She told the agent the thing that rules the dish out and heard nothing
    back about the dish she had asked for."""
    async with Client(server) as client:
        result = await _she_says(
            built, client, 'nao tenho forno nao, so um cooktop',
            category='equipment', item='forno', state='confirmed_no',
        )
    guidance = result.data['next_step']
    assert 'check_feasibility' in guidance
    assert 'version of HER dish' in guidance


@pytest.mark.asyncio
async def test_a_blocking_answer_rules_the_dish_out_on_the_spot(built, server):
    """Telling the agent to go and re-check was not enough: it recorded the
    answer that ruled the dish out and carried on as if nothing had happened."""
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_analyse_recipe_requirements',
            {'dish': 'Lasanha ao forno',
             'recipe_text': 'Monte em uma travessa e leve ao forno preaquecido '
                            'ate gratinar.'},
        )
        result = await _she_says(
            built, client, 'nao tenho forno, so um cooktop de 4 bocas',
            category='equipment', item='forno', state='confirmed_no',
        )
    ruled = result.data['dish_now_ruled_out']
    assert ruled is not None
    assert ruled['verdict'] == 'rejected'
    assert 'forno' in ruled['blocked_by']
    assert 'lasanha ao forno' in ruled['dish']


async def _kill_the_lasagna(built, client, dish='Lasanha ao forno'):
    """She asks for an oven dish and says she has no oven."""
    await client.call_tool(
        'kitchen_analyse_recipe_requirements',
        {'dish': dish,
         'recipe_text': 'Leve ao forno preaquecido ate gratinar.'},
    )
    return await _she_says(
        built, client, 'nao tenho forno, so um cooktop de 4 bocas',
        category='equipment', item='forno', state='confirmed_no',
    )


@pytest.mark.asyncio
async def test_an_answer_she_never_gave_is_refused(server):
    """The most expensive failure this agent ever produced: it decided she owned
    an oven nobody had asked about, the gate approved on that, and it priced a
    whole lasagna she cannot bake."""
    async with Client(server) as client:
        invented = await client.call_tool(
            'kitchen_record_capability',
            {'category': 'equipment', 'item': 'air fryer',
             'state': 'confirmed_yes',
             'her_words': 'ela tem uma air fryer grande'},
        )
    assert invented.data['ok'] is False
    assert 'unknown' in invented.data['next_step']


@pytest.mark.asyncio
async def test_a_confirmed_answer_without_her_words_is_refused(server):
    """Silence is not consent, and neither is inference."""
    async with Client(server) as client:
        bare = await client.call_tool(
            'kitchen_record_capability',
            {'category': 'equipment', 'item': 'liquidificador',
             'state': 'confirmed_yes'},
        )
    assert bare.data['ok'] is False
    assert 'palavras dela' in bare.data['error']


@pytest.mark.asyncio
async def test_unknown_needs_no_quote_because_it_is_a_question(server):
    async with Client(server) as client:
        pending = await client.call_tool(
            'kitchen_record_capability',
            {'category': 'equipment', 'item': 'batedeira', 'state': 'unknown'},
        )
    assert pending.data['ok'] is True


@pytest.mark.asyncio
async def test_her_own_words_are_accepted_and_kept(built, server):
    async with Client(server) as client:
        told = await _she_says(
            built, client, 'tenho uma panela de pressao de 5 litros',
            category='equipment', item='panela de pressao', state='confirmed_yes',
        )
    assert told.data['ok'] is True
    assert told.data['her_words_verified'] is True


@pytest.mark.asyncio
async def test_moving_on_is_refused_until_she_hears_the_verdict(built, server):
    """The worst turn this agent produced: she says she has no oven, the server
    files it correctly, and the reply is about something else."""
    from fastmcp.exceptions import ToolError

    async with Client(server) as client:
        await _kill_the_lasagna(built, client)
        for tool, args in [
            ('kitchen_next_questions', {'limit': 3}),
            ('dishes_survey_categories', {}),
            ('recipes_search_recipes', {'query': 'strogonofe'}),
        ]:
            with pytest.raises(ToolError, match='announce_verdict'):
                await client.call_tool(tool, args)
        # Reading is never refused: checking before speaking is the right move.
        await client.call_tool('kitchen_read_kitchen_profile', {})
        await client.call_tool('pantry_list_ingredients', {})


@pytest.mark.asyncio
async def test_a_polite_acknowledgement_does_not_settle_the_debt(built, server):
    """'Entendido, vou ver outras opções' is a sentence about the agent, not an
    answer about her dish."""
    async with Client(server) as client:
        await _kill_the_lasagna(built, client)
        weak = await client.call_tool(
            'kitchen_announce_verdict',
            {'message_to_her': 'Entendido, vou procurar outras opcoes para voce'},
        )
        assert weak.data['ok'] is False
        assert weak.data['missing_from_your_message']

        good = await client.call_tool(
            'kitchen_announce_verdict',
            {'message_to_her': 'A lasanha ao forno fica fora porque ela precisa de '
                               'forno e voce so tem o cooktop, mas da pra fazer '
                               'lasanha de panela'},
        )
        assert good.data['ok'] is True
        # And now the conversation moves again.
        await client.call_tool('kitchen_next_questions', {'limit': 2})


@pytest.mark.asyncio
async def test_the_dish_comes_back_when_she_says_she_has_the_oven(built, server):
    """She may not have an oven today and say she has one next week. The block
    recorded what stopped it precisely so this can happen."""
    async with Client(server) as client:
        await _kill_the_lasagna(built, client, 'Lasanha ao forno da vovo')
        await client.call_tool(
            'kitchen_announce_verdict',
            {'message_to_her': 'A lasanha da vovo fica fora porque precisa de forno '
                               'e voce so tem cooktop, mas fazemos de panela'},
        )
        back = await _she_says(
            built, client, 'olha, acabei de comprar um forno eletrico',
            category='equipment', item='forno', state='confirmed_yes',
        )
    revived = back.data['dishes_back_on_the_table']
    assert revived is not None
    assert any('vovo' in dish for dish in revived['dishes'])
    assert 'forno' in revived['say_now']


@pytest.mark.asyncio
async def test_a_yes_with_a_but_in_it_is_refused(built, server):
    """The failure that survived every other guard: an ambiguous answer collapses
    into a clean yes, and the gate clears a dish her oven will burn."""
    async with Client(server) as client:
        await capture_her_message(
            built, 'meu forno acende mas nao esquenta direito, as vezes queima embaixo'
        )
        hedged = await client.call_tool(
            'kitchen_record_capability',
            {'category': 'equipment', 'item': 'forno', 'state': 'confirmed_yes',
             'her_words': 'meu forno acende mas nao esquenta direito, as vezes '
                          'queima embaixo'},
        )
    assert hedged.data['ok'] is False
    assert hedged.data['hedges']
    assert "state='unknown'" in hedged.data['next_step']


@pytest.mark.asyncio
async def test_the_agent_cannot_reserve_money_she_did_not_agree_to(built, server):
    """The agent has no wallet. It once told her 'já comprei a massa' about
    money it cannot spend, because nothing made the decision hers."""
    async with Client(server) as client:
        # The gate comes first, and rightly so: no money moves for a dish the
        # kitchen has not been checked against.
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': 'Lasanha de panela', 'equipment_needed': [],
             'techniques_needed': []},
        )
        alone = await client.call_tool(
            'budget_reserve_purchase',
            {'dish': 'Lasanha de panela',
             'description': 'massa de lasanha, oregano', 'amount': 12.0},
        )
        assert alone.data['reserved'] is False
        assert 'palavras dela' in alone.data['error']
        assert 'não compra nada' in alone.data['next_step']

        await capture_her_message(built, 'pode comprar a massa de lasanha sim')
        hers = await client.call_tool(
            'budget_reserve_purchase',
            {'dish': 'Lasanha de panela',
             'description': 'massa de lasanha, oregano', 'amount': 12.0,
             'her_words': 'pode comprar a massa de lasanha sim'},
        )
    assert hers.data['reserved'] is True
    assert 'Nunca diga que você comprou' in hers.data['next_step']
    assert hers.data['reserved_for_her_to_buy'] >= 12.0


@pytest.mark.asyncio
async def test_the_ledger_holds_what_she_decided_not_what_was_spent(built, server):
    """A second dish has to be costed against what is honestly left."""
    async with Client(server) as client:
        before = await client.call_tool('budget_get_status', {})
        left = before.data['remaining']
        fits = await client.call_tool('budget_check_purchase', {'amount': left + 1})
    assert fits.data['verdict'] == 'over_budget'
    assert fits.data['shortfall'] > 0


@pytest.mark.asyncio
async def test_a_dish_she_dislikes_leaves_the_table_for_good(server):
    """She said the parmegiana gives her too much work and never turns out well.
    The agent answered 'anotado, nem entra na conversa' and wrote nothing: the
    next_step asked for a second call, and a second call gets skipped."""
    # A name of its own: this database is shared with every other test and with
    # whatever the last real conversation refused, and the shelving is
    # deliberately idempotent.
    import uuid

    dish = f'Parmegiana de teste {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        told = await client.call_tool(
            'menu_record_feedback',
            {'dish': dish, 'likes_cooking': False,
             'comment': 'da muito trabalho e nunca fica boa'},
        )
        assert told.data['shelved_for_good'] == [dish]
        assert 'recipes_reject_candidate' not in told.data['next_step']

        catalogue = await client.call_tool(
            'recipes_list_candidates', {'only_open': False}
        )
    entry = next(
        row for row in catalogue.data['blocked']
        if row['dish'].lower() == dish.lower()
    )
    assert 'disliked' in entry['reasons']
    assert entry['liftable'] is False, 'gosto não é um problema esperando solução'


@pytest.mark.asyncio
async def test_shelving_the_same_dish_twice_does_not_stack_blocks(server):
    import uuid

    dish = f'Prato Repetido {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        for _ in range(2):
            await client.call_tool(
                'menu_record_feedback',
                {'dish': dish, 'likes_cooking': False, 'comment': 'nao gosto'},
            )
        catalogue = await client.call_tool(
            'recipes_list_candidates', {'only_open': False}
        )
    row = next(r for r in catalogue.data['candidates'] if r['dish'] == dish)
    assert len(row['active_blocks']) == 1
