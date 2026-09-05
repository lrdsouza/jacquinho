"""The two turn boundaries the model does not control.

Everything else in this server runs because the model decided to call a tool.
These run because the turn started and because it ended, which is the whole
reason they are worth testing separately.
"""

import pytest

pytest.importorskip('fastmcp')

import httpx  # noqa: E402
from fastmcp import Client  # noqa: E402

from app.config import Settings  # noqa: E402
from app.domain.memory import ConversationStore  # noqa: E402
from app.mcps.hooks import CAPTURED_SESSION  # noqa: E402
from app.mcps.server import MCPServer  # noqa: E402


@pytest.fixture(scope='module')
def built():
    return MCPServer(Settings.from_env())


def _http(built):
    """Talk to the routes the way the hook scripts do: plain HTTP, no MCP."""
    transport = httpx.ASGITransport(app=built.root.http_app())
    return httpx.AsyncClient(transport=transport, base_url='http://mcp')


@pytest.fixture
def http(built):
    return _http(built)


@pytest.fixture(scope='module', autouse=True)
def a_transcript_of_its_own(built):
    """Start from an empty captured transcript.

    Redis outlives the suite and a real consultation may have run against it.
    A leftover turn here does not fail loudly - it silently vouches for a quote
    these tests expect to be refused.
    """
    backend = built.children['chat'].store.backend
    backend.client.delete(f'chat:{CAPTURED_SESSION}:turns')
    yield
    backend.client.delete(f'chat:{CAPTURED_SESSION}:turns')


@pytest.fixture(autouse=True)
def one_conversation_per_test(built):
    yield
    built.observer.pending.clear()
    built.observer.announced.clear()


async def _kill_the_lasagna(built):
    """She asks for an oven dish and says she has no oven - and her words come
    in the way they really come in, off the wire."""
    async with _http(built) as wire:
        await wire.post('/hooks/her-message', json={
            'session_id': 's1', 'user_message': 'nao tenho forno, so cooktop',
        })
    async with Client(built.root) as client:
        await client.call_tool(
            'kitchen_analyse_recipe_requirements',
            {'dish': 'Lasanha ao forno',
             'recipe_text': 'Leve ao forno preaquecido ate gratinar.'},
        )
        recorded = await client.call_tool(
            'kitchen_record_capability',
            {'category': 'equipment', 'item': 'forno', 'state': 'confirmed_no',
             'her_words': 'nao tenho forno, so cooktop'},
        )
    assert recorded.data['ok'] is True, recorded.data
    assert recorded.data['her_words_verified'] is True


@pytest.mark.asyncio
async def test_her_message_is_captured_before_the_model_reads_it(http, built):
    async with http as client:
        await client.post('/hooks/her-message', json={
            'hook_event_name': 'pre_llm_call', 'session_id': 's1',
            'user_message': 'tenho uma air fryer de 12 litros',
        })
    store = ConversationStore(built.children['chat'].store.backend)
    found = store.she_said('air fryer de 12 litros')
    assert found['said']
    assert found['match']['source'] == ConversationStore.CAPTURED
    assert 'capturadas' in found['checked_against']


@pytest.mark.asyncio
async def test_a_captured_transcript_beats_one_the_agent_wrote(built):
    """A quote checked against a transcript the quoter authored is not a check."""
    store = ConversationStore(built.children['chat'].store.backend)
    store.save_turn(CAPTURED_SESSION, 'dona_maria', 'so tenho o cooktop', [],
                    source=ConversationStore.CAPTURED)
    store.save_turn('inventada', 'dona_maria', 'tenho um forno combinado', [],
                    source=ConversationStore.AUTHORED)
    invented = store.she_said('tenho um forno combinado')
    assert not invented['said'], 'a turn the agent wrote must not vouch for it'
    assert store.she_said('so tenho o cooktop')['said']


@pytest.mark.asyncio
async def test_the_debt_is_settled_by_what_she_received(http, built):
    await _kill_the_lasagna(built)
    session = built.observer.pending and next(iter(built.observer.pending))
    assert session, 'a dead dish owes her a verdict'

    async with http as client:
        await client.post('/hooks/final-message', json={
            'session_id': 's1',
            'assistant_response': 'A lasanha ao forno fica fora porque precisa de '
                                  'forno e voce so tem cooktop, mas fazemos de panela',
        })
    assert built.observer.owed_announcement(session) is None


@pytest.mark.asyncio
async def test_a_reply_that_never_told_her_reopens_the_debt(http, built):
    """The server cannot unsend a bad turn. It can refuse to forget it."""
    await _kill_the_lasagna(built)
    session = next(iter(built.observer.pending))
    built.observer.draft_announcement(session)

    async with http as client:
        answer = await client.post('/hooks/final-message', json={
            'session_id': 's1',
            'assistant_response': 'Certo! Me conta, voce tem liquidificador em casa?',
        })
    owed = built.observer.owed_announcement(session)
    assert owed is not None, 'the debt survives a turn that changed the subject'
    assert owed['drafted'] is False, 'and the doors shut again'
    assert answer.json()['context']


@pytest.mark.asyncio
async def test_the_turn_opens_with_what_she_is_still_owed(http, built):
    await _kill_the_lasagna(built)
    async with http as client:
        answer = await client.post('/hooks/her-message', json={
            'session_id': 's1', 'user_message': 'e ai, achou alguma coisa?',
        })
    assert 'lasanha' in answer.json()['context'].lower()


@pytest.mark.asyncio
async def test_the_background_curator_is_not_dona_maria(http, built):
    """Hermes runs a review pass that speaks in her seat. Captured verbatim it
    would become evidence of something she said."""
    async with http as client:
        await client.post('/hooks/her-message', json={
            'session_id': 's9',
            'user_message': 'Review the conversation above and update the skill '
                            'library. Be ACTIVE about it.',
        })
    store = ConversationStore(built.children['chat'].store.backend)
    assert not store.she_said('update the skill library')['said']


@pytest.mark.asyncio
async def test_a_verdict_she_already_heard_is_not_owed_again(http, built):
    """She took the pan version and asked for the cost. Then she mentioned she
    does not deep-fry either - and the gate, re-run for the dish still marked in
    play, wanted to give her the oven speech a second time."""
    await _kill_the_lasagna(built)
    session = next(iter(built.observer.pending))
    async with _http(built) as wire:
        await wire.post('/hooks/final-message', json={
            'session_id': 's1',
            'assistant_response': 'A lasanha ao forno fica fora porque precisa de '
                                  'forno e voce so tem cooktop, fazemos de panela',
        })
    assert built.observer.owed_announcement(session) is None

    async with Client(built.root) as client:
        again = await client.call_tool(
            'kitchen_record_capability',
            {'category': 'techniques', 'item': 'fritura por imersao',
             'state': 'confirmed_no', 'her_words': 'nao tenho forno, so cooktop'},
        )
    assert again.data['dish_now_ruled_out'] is None
    assert built.observer.owed_announcement(session) is None
