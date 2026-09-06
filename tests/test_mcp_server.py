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
        # 'Ovos' is bought by the piece with no weight anywhere, and unlike
        # 'Cobertura de chocolate' nothing can have recorded a package size for
        # it: a real conversation may well have answered that one, and this
        # database outlives the suite.
        result = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': 'Brownie',
             'lines': [{'ingredient': 'Ovos', 'quantity': 200, 'unit': 'g'}]},
        )
    assert result.data['cmv_per_portion'] is None
    assert result.data['open_questions']
    assert 'resolve_with' in result.data['open_questions'][0]


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
    # A dish of its own: a dish with a settled recipe has a settled shopping
    # list too, and this test is about her decision, not about the amount.
    import uuid

    dish = f'Prato Sem Acordo {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        # The gate comes first, and rightly so: no money moves for a dish the
        # kitchen has not been checked against.
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        alone = await client.call_tool(
            'budget_reserve_purchase',
            {'dish': dish, 'description': 'massa de lasanha', 'amount': 12.0},
        )
        assert alone.data['reserved'] is False
        assert 'palavras dela' in alone.data['error']
        assert 'não compra nada' in alone.data['next_step']

        await capture_her_message(built, 'pode comprar a massa de lasanha sim')
        hers = await client.call_tool(
            'budget_reserve_purchase',
            {'dish': dish, 'description': 'massa de lasanha', 'amount': 12.0,
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


async def _tell_her(built, text):
    """Put a message through the turn boundary, the way a real reply goes out."""
    import httpx

    transport = httpx.ASGITransport(app=built.root.http_app())
    async with httpx.AsyncClient(transport=transport, base_url='http://mcp') as wire:
        await wire.post('/hooks/final-message',
                        json={'session_id': 'testes', 'assistant_response': text})


@pytest.mark.asyncio
async def test_a_cost_she_never_heard_is_not_a_promise(built, server):
    """The correction itself went wrong first: comparing against tool history
    made the agent open a message with 'eu tinha te dito R$ 9,90' about a number
    she had never seen. Inside one turn the recipe is costed several times and
    only the last is spoken."""
    import uuid

    dish = f'Prato Silencioso {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish,
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'}]},
        )
        # She asks for a change, so the recipe legitimately reopens.
        await capture_her_message(built, 'poe menos frango, metade ja serve')
        await client.call_tool(
            'pricing_reopen_recipe',
            {'dish': dish, 'her_words': 'poe menos frango, metade ja serve'},
        )
        # Nothing had been said to her, so the new cost corrects nothing.
        second = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish,
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 100, 'unit': 'g'}]},
        )
    assert second.data['cmv_changed_since_you_told_her'] is None


@pytest.mark.asyncio
async def test_a_cost_she_already_heard_cannot_change_in_silence(built, server):
    """The flagship transcript of this repository said R$ 8,51 in one turn and
    R$ 7,80 in the next, with no word about it. Both came from a tool, so the
    figure audit saw nothing wrong: it asks whether a number was produced, not
    whether a different one was already promised."""
    import uuid

    dish = f'Prato Recalculado {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        first = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish,
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'},
                       {'ingredient': 'Cebola', 'quantity': 50, 'unit': 'g'}]},
        )
        assert first.data['cmv_changed_since_you_told_her'] is None
        told = first.data['cmv_per_portion']

    await _tell_her(built, f'Cada marmita custa R$ {told:.2f}'.replace('.', ','))

    async with Client(server) as client:
        await capture_her_message(built, 'tira a cebola, nao gosto de cebola')
        await client.call_tool(
            'pricing_reopen_recipe',
            {'dish': dish, 'her_words': 'tira a cebola, nao gosto de cebola'},
        )
        second = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish,
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'}]},
        )
    changed = second.data['cmv_changed_since_you_told_her']
    assert changed is not None, 'ela ouviu um número, e ele mudou'
    assert changed['told_her_before'] == told
    assert changed['now'] == second.data['cmv_per_portion']
    assert 'caiu' in changed['say_now']
    # And it says WHY it moved, which is the only useful part.
    assert 'Cebola' in changed['what_moved']['left_the_recipe']
    assert 'saiu Cebola' in changed['say_now']


@pytest.mark.asyncio
async def test_recalculating_to_the_same_number_says_nothing(built, server):
    import uuid

    dish = f'Prato Estavel {uuid.uuid4().hex[:6]}'
    lines = [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'}]
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        await client.call_tool('pricing_calculate_cmv', {'dish': dish, 'lines': lines})
        again = await client.call_tool(
            'pricing_calculate_cmv', {'dish': dish, 'lines': lines}
        )
    assert again.data['cmv_changed_since_you_told_her'] is None


@pytest.mark.asyncio
async def test_the_recipe_of_a_dish_is_settled_once(built, server):
    """The cost wandered from R$ 9,90 to R$ 8,18 to R$ 7,15 in one consultation,
    every figure arithmetically right and none of them the dish. The arithmetic
    was never the problem; the inputs were."""
    import uuid

    dish = f'Prato Fechado {uuid.uuid4().hex[:6]}'
    lines = [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'},
             {'ingredient': 'Cebola', 'quantity': 50, 'unit': 'g'}]
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        first = await client.call_tool(
            'pricing_calculate_cmv', {'dish': dish, 'lines': lines, 'portions': 4}
        )
        assert first.data['recipe_now_settled'] is True
        settled_cost = first.data['cmv_per_portion']

        # The same list in another order is the same recipe, and recomputes fine.
        same = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish, 'lines': list(reversed(lines)), 'portions': 4},
        )
        assert same.data['cmv_per_portion'] == settled_cost

        # A different list is refused, with the settled cost handed back.
        drift = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish,
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'}],
             'portions': 4},
        )
    assert drift.data['ok'] is False
    assert drift.data['cmv_per_portion'] == settled_cost
    assert 'cebola' in drift.data['what_you_passed_differs_by']['left_the_recipe']
    assert 'reopen_recipe' in drift.data['next_step']


@pytest.mark.asyncio
async def test_only_her_words_can_reopen_a_recipe(built, server):
    """A recipe changes when SHE changes it, not because the model composed the
    list differently on the second call."""
    import uuid

    dish = f'Prato Reaberto {uuid.uuid4().hex[:6]}'
    lines = [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'},
             {'ingredient': 'Cebola', 'quantity': 50, 'unit': 'g'}]
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        await client.call_tool('pricing_calculate_cmv', {'dish': dish, 'lines': lines})

        alone = await client.call_tool(
            'pricing_reopen_recipe', {'dish': dish, 'her_words': ''},
        )
        assert alone.data['reopened'] is False

        invented = await client.call_tool(
            'pricing_reopen_recipe',
            {'dish': dish, 'her_words': 'ela quis trocar a cebola por alho'},
        )
        assert invented.data['reopened'] is False
        assert 'não disse isso' in invented.data['error']

        await capture_her_message(built, 'tira a cebola dai, nao gosto')
        real = await client.call_tool(
            'pricing_reopen_recipe',
            {'dish': dish, 'her_words': 'tira a cebola dai, nao gosto',
             'what_changed': 'tirou a cebola'},
        )
        assert real.data['reopened'] is True

        # And now a different list is accepted again.
        after = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish,
             'lines': [{'ingredient': 'Peito de frango', 'quantity': 200, 'unit': 'g'}]},
        )
    assert after.data.get('ok') is not False
    assert after.data['recipe_now_settled'] is True


@pytest.mark.asyncio
async def test_the_shopping_list_is_not_the_agents_to_choose(built, server):
    """One message said the massa costs R$ 6,95 and was the only thing missing;
    the closing reserved R$ 12,00 for 'massa e orégano', with the orégano
    appearing from nowhere. The amount was a free parameter, so it drifted."""
    import uuid

    dish = f'Prato Compras {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        costed = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish, 'portions': 8,
             'lines': [{'ingredient': 'massa de lasanha', 'quantity': 60,
                        'unit': 'g'}],
             'researched_prices': [
                 {'ingredient': 'massa de lasanha', 'package_price': 6.95,
                  'package_quantity': 500, 'package_unit': 'g'}]},
        )
        expected = costed.data['shopping_cost']
        assert expected == 6.95

        await capture_her_message(built, 'pode reservar que eu compro amanha')
        invented = await client.call_tool(
            'budget_reserve_purchase',
            {'dish': dish, 'description': 'massa e orégano', 'amount': 12.00,
             'her_words': 'pode reservar que eu compro amanha'},
        )
        assert invented.data['reserved'] is False
        assert 'R$ 6,95' in invented.data['error'].replace('.', ',')
        assert invented.data['the_shopping_list_is']

        right = await client.call_tool(
            'budget_reserve_purchase',
            {'dish': dish, 'description': 'massa de lasanha', 'amount': expected,
             'her_words': 'pode reservar que eu compro amanha'},
        )
    assert right.data['reserved'] is True


@pytest.mark.asyncio
async def test_an_extra_ingredient_has_to_go_through_the_recipe(built, server):
    """Adding orégano to the shopping list is adding it to the recipe, and the
    recipe only changes when she changes it."""
    import uuid

    dish = f'Prato Extra {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish, 'portions': 8,
             'lines': [{'ingredient': 'massa de lasanha', 'quantity': 60,
                        'unit': 'g'}],
             'researched_prices': [
                 {'ingredient': 'massa de lasanha', 'package_price': 6.95,
                  'package_quantity': 500, 'package_unit': 'g'}]},
        )
        # Slipping the orégano in as a new line is refused: same dish, new list.
        slipped = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish, 'portions': 8,
             'lines': [{'ingredient': 'massa de lasanha', 'quantity': 60,
                        'unit': 'g'},
                       {'ingredient': 'oregano', 'quantity': 2, 'unit': 'g'}]},
        )
    assert slipped.data['ok'] is False
    assert 'oregano' in slipped.data['what_you_passed_differs_by']['joined_the_recipe']


@pytest.mark.asyncio
async def test_the_cost_comes_with_the_breakdown_she_can_check(built, server):
    """A total on its own is a number she has to take on faith."""
    import uuid

    dish = f'Prato Aberto {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        result = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish, 'portions': 8,
             'lines': [{'ingredient': 'Carne moída (patinho)', 'quantity': 100,
                        'unit': 'g'},
                       {'ingredient': 'Queijo mussarela', 'quantity': 50,
                        'unit': 'g'}]},
        )
    data = result.data
    assert data['breakdown_for_her'][0].startswith('100 g de Carne moída')
    assert 'R$ 2,80' in data['breakdown_for_her'][0]
    # Biggest first: the first lines explain most of the number.
    assert data['breakdown_for_her'] == sorted(
        data['breakdown_for_her'],
        key=lambda line: -float(line.rsplit('R$ ', 1)[1].replace(',', '.')),
    )
    assert data['cost_per_portion_for_her'] == 'custo por porção: R$ 4,80'
    assert 'CMV' not in data['next_step'] or 'Never say "CMV"' in data['next_step']


@pytest.mark.asyncio
async def test_a_recipe_that_serves_six_is_divided_by_the_tool(built, server):
    """'1 kg de carne, serve 6' becomes 166 g per portion here, not in prose."""
    import uuid

    dish = f'Prato Rendimento {uuid.uuid4().hex[:6]}'
    async with Client(server) as client:
        await client.call_tool(
            'kitchen_check_feasibility',
            {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
        )
        whole = await client.call_tool(
            'pricing_calculate_cmv',
            {'dish': dish, 'portions': 6, 'recipe_yields': 6,
             'lines': [{'ingredient': 'Carne moída (patinho)', 'quantity': 1,
                        'unit': 'kg'}]},
        )
    # 1 kg for six portions is 166,7 g each, at R$ 28,00/kg.
    assert whole.data['cmv_per_portion'] == 4.67
    assert '166' in whole.data['breakdown_for_her'][0]


@pytest.mark.asyncio
async def test_a_committed_dish_empties_what_it_used(built, server):
    """Her stock is finite, and the second dish has to see the first one's bill.

    Measured as a difference, never against 1,5 kg: this database is shared with
    every other test and with whatever the last real conversation accepted, and a
    test that asserts an absolute stock tests the neighbours.
    """
    BEEF = 'Carne moída (patinho)'

    def left() -> float:
        built.repository.reload()
        return built.repository.find(BEEF).stock

    async with Client(server) as client:
        try:
            for dish in ('Primeira fornada', 'Segunda fornada'):
                await client.call_tool('menu_remove_dish', {'dish': dish})
                await client.call_tool(
                    'kitchen_check_feasibility',
                    {'dish': dish, 'equipment_needed': [], 'techniques_needed': []},
                )

            before = left()
            first = await client.call_tool(
                'pricing_calculate_cmv',
                {'dish': 'Primeira fornada', 'portions': 4,
                 'lines': [{'ingredient': BEEF, 'quantity': 250, 'unit': 'g'}]},
            )
            # Nothing has left the pantry yet: she has not accepted the dish.
            beef_line = next(line for line in first.data['ingredients']
                             if 'patinho' in line['ingredient'].lower())
            assert beef_line['stock_left_quantity'] == pytest.approx(before)
            assert first.data['takes_out_of_the_pantry'][0]['quantity'] == pytest.approx(1.0)

            await client.call_tool(
                'confidence_assess_answer',
                {'dish': 'Primeira fornada',
                 'draft_answer': 'O custo dessa fornada é o que a conta mostrou.',
                 'claim': 'cost', 'mode': 'deterministic', 'evidence': {}},
            )
            await client.call_tool(
                'menu_add_dish',
                {'dish': 'Primeira fornada', 'category': 'main_course',
                 'cmv': first.data['cmv_per_portion'], 'price': 19.90,
                 'confidence_band': 'high'},
            )

            # A whole kilo of hers is gone, and the history says where it went.
            assert left() == pytest.approx(max(before - 1.0, 0.0))
            history = built.repository.usage_history('carne moida patinho')
            assert ('Primeira fornada', 1.0) in [
                (row['dish'], row['quantity']) for row in history
            ]

            second = await client.call_tool(
                'pricing_calculate_cmv',
                {'dish': 'Segunda fornada', 'portions': 4,
                 'lines': [{'ingredient': BEEF, 'quantity': 250, 'unit': 'g'}]},
            )
            short = next(entry for entry in second.data['must_buy']
                         if 'patinho' in entry['ingredient'].lower())
            assert short['buy_quantity'] == pytest.approx(1.0 - left())
            # And it says why, in her words, instead of announcing a shortfall.
            assert 'Primeira fornada' in short['why_short']
        finally:
            for dish in ('Primeira fornada', 'Segunda fornada'):
                await client.call_tool('menu_remove_dish', {'dish': dish})
                await client.call_tool(
                    'pricing_reopen_recipe',
                    {'dish': dish, 'what_changed': 'fim do teste',
                     'her_words': 'desisti desse prato'},
                )


@pytest.mark.asyncio
async def test_costing_a_dish_she_never_accepts_leaves_the_pantry_alone(built, server):
    """Pricing is a question. Only the menu is a decision."""
    BEEF = 'Carne moída (patinho)'
    async with Client(server) as client:
        try:
            built.repository.reload()
            before = built.repository.find(BEEF).used
            await client.call_tool(
                'kitchen_check_feasibility',
                {'dish': 'Orçamento solto', 'equipment_needed': [],
                 'techniques_needed': []},
            )
            await client.call_tool(
                'pricing_calculate_cmv',
                {'dish': 'Orçamento solto', 'portions': 4,
                 'lines': [{'ingredient': BEEF, 'quantity': 250, 'unit': 'g'}]},
            )
            built.repository.reload()
            assert built.repository.find(BEEF).used == pytest.approx(before)
        finally:
            await client.call_tool(
                'pricing_reopen_recipe',
                {'dish': 'Orçamento solto', 'what_changed': 'fim do teste',
                 'her_words': 'desisti desse prato'},
            )
