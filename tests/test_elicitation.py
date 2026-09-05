"""Constraint elicitation: never assuming, and never asking twice."""

import pytest

from app.domain.elicitation import (
    ElicitationCatalogue,
    ElicitationPlanner,
    RequirementExtractor,
)
from app.domain.kitchen import CapabilityState


class FakeProfile:
    """A profile without a database, so the planner can be tested alone."""

    CATEGORIES = ('equipment', 'techniques', 'constraints')

    def __init__(self, states=None):
        self.states = states or {}

    @property
    def data(self):
        out = {c: {} for c in self.CATEGORIES}
        for (category, item), state in self.states.items():
            out[category][item] = {'state': state, 'note': ''}
        return out

    def state_of(self, category, item):
        return self.states.get((category, item.strip().lower()), CapabilityState.UNKNOWN)


@pytest.mark.parametrize(
    'key',
    ['fogao', 'forno', 'panela_de_pressao', 'air_fryer', 'liquidificador',
     'massa_fresca', 'molho_bechamel', 'pontos_de_carne',
     'energia', 'gas', 'espaco_geladeira', 'tempo_por_cozinhada'],
)
def test_catalogue_covers_every_named_constraint(key):
    assert ElicitationCatalogue.get(key) is not None


def test_unknown_blocks_shopping():
    planner = ElicitationPlanner(FakeProfile())
    gaps = planner.gaps_for_dish(['forno'])
    assert gaps['safe_to_shop'] is False
    assert gaps['must_ask_before_buying']


def test_confirmed_no_is_a_blocker_not_a_question():
    planner = ElicitationPlanner(FakeProfile({('equipment', 'forno'): CapabilityState.NO}))
    gaps = planner.gaps_for_dish(['forno'])
    assert gaps['known_blockers']
    assert not gaps['must_ask_before_buying']


def test_confirmed_yes_clears_the_gate():
    planner = ElicitationPlanner(FakeProfile({('equipment', 'forno'): CapabilityState.YES}))
    assert planner.gaps_for_dish(['forno'])['safe_to_shop'] is True


def test_a_requirement_the_catalogue_never_saw_also_blocks():
    """The most dangerous kind: nobody has ever asked her about it."""
    planner = ElicitationPlanner(FakeProfile())
    gaps = planner.gaps_for_dish(['maquina de macarrao'])
    assert gaps['safe_to_shop'] is False
    assert gaps['unrecognised_requirements']


def test_one_question_is_asked_once_however_many_demands_raise_it():
    planner = ElicitationPlanner(FakeProfile())
    gaps = planner.gaps_for_dish(['assar no forno', 'empanar e fritar'])
    items = [entry['item'] for entry in gaps['must_ask_before_buying']]
    assert len(items) == len(set(items))


def test_connectives_do_not_match_everything():
    """'maquina de macarrao' once triggered batedeira, formas and caramelo,
    because the shared word was 'de'."""
    assert ElicitationCatalogue.for_requirement('maquina de macarrao') == []


def test_a_catalogue_key_handed_back_resolves_to_itself():
    """The extractor returns keys like 'formas_e_assadeiras'; they must map
    back rather than land in the unrecognised bucket."""
    matched = ElicitationCatalogue.for_requirement('formas_e_assadeiras')
    assert [item.key for item in matched] == ['formas_e_assadeiras']


RECIPE = """Lasanha na travessa. Refogue a carne moida na panela. Para o molho
branco, derreta a manteiga em fogo baixo. Monte em uma travessa untada e leve ao
forno preaquecido ate gratinar. Deixe descansar na geladeira."""


def test_requirements_are_read_from_the_recipe_text():
    found = RequirementExtractor.extract(RECIPE)
    detected = {entry['item'] for entry in found['detected_requirements']}
    assert {'forno', 'fogao', 'molho_bechamel', 'formas_e_assadeiras'} <= detected


def test_each_detection_carries_the_words_that_raised_it():
    found = RequirementExtractor.extract(RECIPE)
    oven = next(e for e in found['detected_requirements'] if e['item'] == 'forno')
    assert 'forno' in oven['evidence']


def test_a_recipe_that_demands_nothing_detects_nothing():
    assert RequirementExtractor.extract('Misture tudo.')['detected_count'] == 0


def test_coverage_counts_answered_items():
    planner = ElicitationPlanner(FakeProfile({('equipment', 'forno'): CapabilityState.YES}))
    coverage = planner.coverage()
    assert coverage['answered'] == 1
    assert 0 < coverage['coverage_percent'] < 100


def test_priority_one_items_gate_recommendation():
    planner = ElicitationPlanner(FakeProfile())
    assert planner.coverage()['ready_to_recommend'] is False
    assert planner.next_questions(1)[0]['priority'] == 1
