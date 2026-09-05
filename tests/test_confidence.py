"""Confidence scoring: relative to the claim, and blocking when it must."""

import pytest

from app.domain.confidence import (
    BAND_LABEL,
    Claim,
    ConfidenceBadge,
    DeterministicScorer,
    band_for,
)

APPROVED = {'verdict': 'approved', 'blockers': []}
COMPLETE_CMV = {'calculation_complete': True, 'budget': {'fits': True}, 'must_buy': []}
STRONG_MARKET = {'sample_size': 9, 'distinct_sources': 6}
FRESH_IPCA = {'age_in_months': 2}
PANTRY = {'total_ingredients': 37}


@pytest.fixture
def scorer():
    return DeterministicScorer()


def test_scale_is_zero_to_one(scorer):
    verdict = scorer.score(pantry=PANTRY, claim=Claim.PANTRY)
    assert 0.0 <= verdict.score <= 1.0


@pytest.mark.parametrize(
    'score, band', [(1.0, 'high'), (0.75, 'high'), (0.74, 'medium'), (0.5, 'medium'), (0.49, 'low')]
)
def test_band_thresholds(score, band):
    assert band_for(score) == band


def test_pantry_fact_needs_only_the_pantry(scorer):
    """'Você tem 37 ingredientes' is read off the spreadsheet and is certain.

    Scoring it against market prices gave 0.00, which said nothing about the
    sentence and everything about a scorer aimed at the wrong thing.
    """
    verdict = scorer.score(pantry=PANTRY, claim=Claim.PANTRY)
    assert verdict.score == pytest.approx(1.0)
    assert verdict.blocking_issues == []


def test_price_claim_without_evidence_scores_zero_and_blocks(scorer):
    verdict = scorer.score(pantry=PANTRY, claim=Claim.PRICE)
    assert verdict.score == pytest.approx(0.0)
    assert len(verdict.blocking_issues) == 3


def test_price_claim_fully_supported(scorer):
    verdict = scorer.score(
        pantry=PANTRY, feasibility=APPROVED, cmv=COMPLETE_CMV,
        market=STRONG_MARKET, economy=FRESH_IPCA, claim=Claim.PRICE,
    )
    assert verdict.score == pytest.approx(1.0)
    assert verdict.blocking_issues == []


def test_weak_market_lowers_but_does_not_block(scorer):
    """Two sources is little, not nothing."""
    verdict = scorer.score(
        pantry=PANTRY, feasibility=APPROVED, cmv=COMPLETE_CMV,
        market={'sample_size': 2, 'distinct_sources': 1}, economy=FRESH_IPCA,
        claim=Claim.PRICE,
    )
    assert 0.75 <= verdict.score < 1.0
    assert verdict.blocking_issues == []


def test_needs_answers_is_progress_but_still_blocks(scorer):
    verdict = scorer.score(
        feasibility={'verdict': 'needs_answers'}, claim=Claim.FEASIBILITY
    )
    assert verdict.score == pytest.approx(0.30)
    assert len(verdict.blocking_issues) == 1


def test_pantry_fact_is_never_blocked_by_a_missing_price(scorer):
    verdict = scorer.score(pantry=PANTRY, claim=Claim.PANTRY)
    assert verdict.blocking_issues == []


@pytest.mark.parametrize(
    'sources, expected', [(4, 1.0), (3, 0.8), (2, 0.6), (1, 0.25)]
)
def test_consensus_counts_distinct_domains(scorer, sources, expected):
    verdict = scorer.score(
        pantry=PANTRY,
        consensus={'agreed_dishes': [{'source_count': sources}]},
        claim=Claim.DISH,
    )
    signal = next(s for s in verdict.signals if s.name == 'web_consensus')
    assert signal.score == pytest.approx(expected)


def test_badge_names_the_claim_and_hides_the_number(scorer):
    verdict = scorer.score(pantry=PANTRY, claim=Claim.PANTRY)
    badge = ConfidenceBadge.build(
        verdict.score, verdict.signals, verdict.blocking_issues, verdict.claim
    )
    assert badge.startswith('〔o que ela tem: confiança alta')
    assert '1.0' not in badge and '100' not in badge


def test_badge_lists_the_weakest_signal_first(scorer):
    """A badge that lists what went well and hides what did not reads as
    reassurance."""
    verdict = scorer.score(
        pantry=PANTRY, feasibility=APPROVED, cmv=COMPLETE_CMV,
        market={'sample_size': 2, 'distinct_sources': 1}, economy=FRESH_IPCA,
        claim=Claim.PRICE,
    )
    badge = ConfidenceBadge.build(
        verdict.score, verdict.signals, verdict.blocking_issues, verdict.claim
    )
    assert 'poucas fontes de preço' in badge


def test_badge_with_impediments_says_do_not_send(scorer):
    verdict = scorer.score(claim=Claim.PRICE)
    badge = ConfidenceBadge.build(
        verdict.score, verdict.signals, verdict.blocking_issues, verdict.claim
    )
    assert 'impedimento' in badge


def test_band_label_covers_every_band():
    assert set(BAND_LABEL) == {'high', 'medium', 'low'}


def test_pantry_signal_uses_coverage_when_a_recipe_was_checked(scorer):
    """'The file was opened' is not 'this ingredient was verified'."""
    partial = scorer.score(
        pantry={'coverage_ratio': 0.6, 'not_in_pantry': [{'ingredient': 'azeitona'}]},
        claim=Claim.PANTRY,
    )
    assert partial.score == pytest.approx(0.6)

    whole = scorer.score(pantry={'total_ingredients': 37}, claim=Claim.PANTRY)
    assert whole.score == pytest.approx(1.0)


def test_thresholds_live_in_one_place_for_calibration(scorer):
    assert scorer.for_count(4, scorer.CONSENSUS_STEPS) == 1.0
    assert scorer.for_count(0, scorer.CONSENSUS_STEPS) == 0.0
    assert scorer.for_count(6, scorer.MARKET_STEPS) == 1.0
