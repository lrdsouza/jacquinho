"""The claim pipeline: decompose, ground, compare against what she was told.

No database and no server: it is arithmetic over strings, which is exactly why
it can run on every turn without a budget conversation.
"""

import pytest

from app.domain.claims import (
    AtomicClaim, ClaimExtractor, ClaimKind, ClaimPipeline, CommitmentLedger,
    MessageJudgement, ToolFact, Verdict,
)


# --- decomposition ----------------------------------------------------------

def test_the_nearest_cue_decides_what_a_figure_is():
    """A window wide enough to catch 'vendendo a' also catches the 'custa' of
    the sentence before, and then every number inherits the first one's meaning."""
    claims = ClaimExtractor.extract(
        'Cada marmita custa R$ 4,15 pra fazer. Vendendo a R$ 24,90 você recebe '
        'R$ 22,41 e sobra R$ 18,26 no seu bolso.',
        'lasanha',
    )
    kinds = [c.kind for c in claims]
    assert kinds == [ClaimKind.COST, ClaimKind.PRICE, ClaimKind.RECEIPT,
                     ClaimKind.PROFIT]


def test_a_figure_inside_a_question_asserts_nothing():
    """'quer vender a R$ 30?' is not a claim, and counting it would mark the
    agent wrong for asking."""
    claims = ClaimExtractor.extract('Quer vender a R$ 30,00?', 'lasanha')
    assert claims == []


def test_a_cue_before_the_figure_beats_one_after():
    claims = ClaimExtractor.extract('Vendendo a R$ 24,90 você recebe menos.', 'x')
    assert claims[0].kind is ClaimKind.PRICE


def test_a_trailing_cue_wins_when_nothing_leads():
    """'R$ 22,41 depois da taxa' has no verb in front of it, so the cue that
    follows decides. When both exist the leading one wins, which is why
    'Sobram R$ 22,41 depois da taxa' reads as profit: ambiguous in Portuguese
    too, and the agent does not write it that way."""
    claims = ClaimExtractor.extract('São R$ 22,41 depois da taxa.', 'x')
    assert claims[0].kind is ClaimKind.RECEIPT

    both = ClaimExtractor.extract('Sobram R$ 22,41 depois da taxa.', 'x')
    assert both[0].kind is ClaimKind.PROFIT


# --- grounding --------------------------------------------------------------

def test_a_figure_no_tool_produced_is_ungrounded():
    ledger = CommitmentLedger()
    claim = AtomicClaim(kind=ClaimKind.PRICE, subject='x', value=7.26,
                        quoted='R$ 7,26', exclusive=True)
    assert ledger.ground(claim, {5.27, 12.64}).verdict is Verdict.UNGROUNDED


def test_a_figure_a_tool_produced_is_grounded():
    ledger = CommitmentLedger()
    claim = AtomicClaim(kind=ClaimKind.COST, subject='x', value=5.27,
                        quoted='R$ 5,27', exclusive=True)
    assert ledger.ground(claim, {5.27, 12.64}).verdict is Verdict.GROUNDED


# --- commitments across turns ----------------------------------------------

def test_a_value_only_binds_once_it_reaches_her():
    """A cost computed three times inside one turn commits to nothing; the one
    sentence she reads does."""
    ledger = CommitmentLedger()
    facts = [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=9.90)]
    ledger.bind(facts, 'Ainda estou fechando a conta, já te digo.')
    assert ledger.promised == {}

    ledger.bind(facts, 'Cada marmita custa R$ 9,90.')
    assert ledger.promised[('lasanha', 'cost')] == 9.90


def test_the_same_value_stated_again_is_not_a_contradiction():
    ledger = CommitmentLedger()
    facts = [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=4.15)]
    ledger.bind(facts, 'Custa R$ 4,15.')
    assert ledger.contradictions(facts, 'Continua R$ 4,15 por marmita.') == []


def test_a_different_value_for_the_same_thing_is_a_contradiction():
    ledger = CommitmentLedger()
    ledger.bind([ToolFact(subject='lasanha', kind=ClaimKind.COST, value=4.15)],
                'Custa R$ 4,15.')
    clashes = ledger.contradictions(
        [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=7.15)],
        'Cada marmita custa R$ 7,15.',
    )
    assert len(clashes) == 1
    assert clashes[0].verdict is Verdict.CONTRADICTS
    assert clashes[0].earlier_value == 4.15
    assert 'custo' in clashes[0].note


def test_a_change_she_asked_for_is_not_a_contradiction():
    """Punishing the agent for doing the right thing would teach it to hide the
    change instead."""
    ledger = CommitmentLedger()
    ledger.bind([ToolFact(subject='lasanha', kind=ClaimKind.COST, value=4.15)],
                'Custa R$ 4,15.')
    ledger.authorise_revision('lasanha', ClaimKind.COST)
    clashes = ledger.contradictions(
        [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=7.15)],
        'Agora custa R$ 7,15.',
    )
    assert clashes[0].verdict is Verdict.REVISED


def test_a_new_value_the_message_never_states_binds_nothing():
    """What the tools know and what she knows are different things, and only the
    second one binds."""
    ledger = CommitmentLedger()
    ledger.bind([ToolFact(subject='lasanha', kind=ClaimKind.COST, value=4.15)],
                'Custa R$ 4,15.')
    facts = [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=7.15)]
    assert ledger.contradictions(facts, 'Vou ver o preço de mercado agora.') == []
    assert ledger.promised[('lasanha', 'cost')] == 4.15


def test_market_prices_are_a_range_not_a_commitment():
    """Two market references are a range; two costs are a contradiction."""
    ledger = CommitmentLedger()
    facts = [ToolFact(subject='lasanha', kind=ClaimKind.MARKET, value=14.98)]
    ledger.bind(facts, 'Está saindo a R$ 14,98.')
    assert ledger.promised == {}


# --- the whole pipeline -----------------------------------------------------

def test_a_message_with_nothing_checkable_scores_one():
    """A question is not suspicious. Scoring it low measures the scorer."""
    judgement = ClaimPipeline.run(
        'Você tem forno em casa?', 'lasanha', set(), [], CommitmentLedger()
    )
    assert judgement.verifiable == 0
    assert judgement.score == 1.0


def test_one_contradiction_sinks_the_message():
    """Being told two different costs is not eighty percent fine."""
    ledger = CommitmentLedger()
    known = {4.15, 24.90, 7.15}
    ClaimPipeline.run(
        'Cada marmita custa R$ 4,15 e vendendo a R$ 24,90.', 'lasanha', known,
        [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=4.15)], ledger,
    )
    second = ClaimPipeline.run(
        'Cada marmita custa R$ 7,15.', 'lasanha', known,
        [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=7.15)], ledger,
    )
    assert second.contradictions == 1
    assert second.score == 0.0
    assert second.verdict == 'contradiz o que ela já ouviu'


def test_an_ungrounded_figure_lowers_the_score_without_zeroing_it():
    judgement = ClaimPipeline.run(
        'Custa R$ 4,15 e vendendo a R$ 99,00.', 'lasanha', {4.15},
        [], CommitmentLedger(),
    )
    assert judgement.ungrounded == 1
    assert 0 < judgement.score < 1


def test_the_pipeline_binds_what_it_just_judged():
    ledger = CommitmentLedger()
    ClaimPipeline.run(
        'Custa R$ 4,15.', 'lasanha', {4.15},
        [ToolFact(subject='lasanha', kind=ClaimKind.COST, value=4.15)], ledger,
    )
    assert ledger.promised[('lasanha', 'cost')] == 4.15


def test_the_judgement_is_a_pydantic_model_and_serialises():
    judgement = MessageJudgement.of([])
    assert judgement.model_dump()['score'] == 1.0
