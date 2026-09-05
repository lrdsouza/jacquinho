"""The observer: confidence that does not wait to be asked."""

import pytest

from app.domain.observer import ConfidenceObserver

APPROVED = {'verdict': 'approved', 'blockers': []}
COMPLETE_CMV = {'calculation_complete': True, 'budget': {'fits': True}, 'must_buy': []}


@pytest.fixture
def observer():
    return ConfidenceObserver()


def test_reports_on_every_call_not_only_evidence_ones(observer):
    """A watcher that goes quiet while the agent works looks broken."""
    report = observer.record('s', 'kitchen_read_kitchen_profile', {'x': 1})
    assert report['moved'] is False
    assert 'badge' in report


def test_band_comes_from_the_score_not_from_slicing_the_badge(observer):
    """Reading the band out of the badge string filled the column with 'que'
    the day the badge gained a prefix."""
    report = observer.record('s', 'pantry_list_ingredients', {'total_ingredients': 37})
    assert report['band'] in {'alta', 'média', 'baixa'}
    assert report['score'] == pytest.approx(1.0)
    assert report['band'] == 'alta'


def test_claim_follows_the_tool_that_just_ran(observer):
    assert observer.record('s', 'pantry_list_ingredients', {'total_ingredients': 37})['claim'] == 'pantry_fact'
    assert observer.record('s', 'pricing_calculate_cmv', COMPLETE_CMV)['claim'] == 'cost'
    assert observer.record('s', 'pricing_price_scenarios', {})['claim'] == 'price'


def test_evidence_is_kept_per_dish(observer):
    """Approving the parmegiana and then asking about lasanha used to
    un-approve the parmegiana, and the menu then refused it silently."""
    observer.record('s', 'kitchen_check_feasibility', APPROVED, dish='Parmegiana')
    assert observer.gate_approved('s', 'Parmegiana')

    observer.record('s', 'kitchen_check_feasibility',
                    {'verdict': 'needs_answers'}, dish='Lasanha')
    assert not observer.gate_approved('s', 'Lasanha')
    assert observer.gate_approved('s', 'Parmegiana')


def test_a_call_without_a_dish_stays_on_the_current_dish(observer):
    observer.record('s', 'kitchen_check_feasibility', APPROVED, dish='Parmegiana')
    observer.record('s', 'pricing_calculate_cmv', COMPLETE_CMV)
    assert observer.gate_approved('s', 'Parmegiana')
    assert observer.current('s', 'Parmegiana')['claim'] == 'cost'


def test_pantry_is_shared_across_dishes(observer):
    """Reading the pantry is about her kitchen, not about one dish."""
    observer.record('s', 'pantry_list_ingredients', {'total_ingredients': 37})
    observer.record('s', 'kitchen_check_feasibility', APPROVED, dish='Bolo')
    assert observer.trails[('s', observer.key_for('Bolo'))].pantry is not None


def test_gate_for_an_unknown_dish_is_not_approved(observer):
    observer.record('s', 'kitchen_check_feasibility', APPROVED, dish='Parmegiana')
    assert not observer.gate_approved('s', 'Escondidinho')


def test_elicitation_gaps_translates_into_a_verdict(observer):
    report = observer.record(
        's', 'kitchen_elicitation_gaps', {'safe_to_shop': True, 'known_blockers': []},
        dish='Bolo',
    )
    assert report['moved']
    assert observer.gate_approved('s', 'Bolo')


def test_reset_clears_one_dish_or_all(observer):
    observer.record('s', 'kitchen_check_feasibility', APPROVED, dish='A')
    observer.record('s', 'kitchen_check_feasibility', APPROVED, dish='B')
    observer.reset('s', 'A')
    assert not observer.gate_approved('s', 'A')
    assert observer.gate_approved('s', 'B')
    observer.reset()
    assert observer.trails == {}


def test_two_sessions_do_not_share_evidence(observer):
    """One client's approved gate is not another client's."""
    observer.record('ana', 'kitchen_check_feasibility', APPROVED, dish='Bolo')
    assert observer.gate_approved('ana', 'Bolo')
    assert not observer.gate_approved('bia', 'Bolo')


def test_a_declared_claim_beats_the_inferred_one(observer):
    observer.record('s', 'pricing_calculate_cmv', COMPLETE_CMV, dish='Bolo')
    observer.declare_claim('s', 'Bolo', 'price')
    observer.record('s', 'pantry_list_ingredients', {'total_ingredients': 37})
    assert observer.current('s', 'Bolo')['claim'] == 'price'


def test_assessment_is_remembered_per_dish(observer):
    observer.declare_claim('s', 'Bolo', 'price')
    assert observer.assessed('s', 'Bolo')
    assert not observer.assessed('s', 'Torta')


def test_a_coverage_check_is_not_overwritten_by_a_plain_list_read(observer):
    observer.record('s', 'recipes_check_pantry_coverage',
                    {'coverage_ratio': 0.6, 'not_in_pantry': [{'ingredient': 'x'}]})
    observer.record('s', 'pantry_list_ingredients', {'total_ingredients': 37})
    assert observer.current('s')['score'] == pytest.approx(0.6)


def test_the_gate_verdict_is_enough_to_park_the_dish():
    """A run that called check_feasibility directly announced the dead dish
    correctly and left recipe_blocks empty: the lasagna had nothing to come back
    from the day she got an oven."""
    from app.domain.observer import ConfidenceObserver

    observer = ConfidenceObserver()
    observer.record('s', 'kitchen_check_feasibility', {
        'verdict': 'rejected',
        'blockers': [{'category': 'equipment', 'item': 'forno'}],
    }, dish='Lasanha ao forno')
    assert observer.requirements_of('s') == ['forno']


def test_the_recipe_reading_still_wins_when_there_is_one():
    from app.domain.observer import ConfidenceObserver

    observer = ConfidenceObserver()
    observer.record('s', 'kitchen_analyse_recipe_requirements', {
        'from_the_recipe': {'detected_requirements': [{'item': 'forno'},
                                                      {'item': 'molho_bechamel'}]},
        'gate': {'safe_to_shop': False, 'known_blockers': []},
    }, dish='Lasanha ao forno')
    assert observer.requirements_of('s') == ['forno', 'molho_bechamel']
