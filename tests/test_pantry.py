"""Reading the spreadsheet, and refusing to guess when it is ambiguous."""

import pytest

from app.domain.units import UnitConverter


def test_both_sheets_are_joined(sheet_rows):
    assert len(sheet_rows) == 37


def test_the_repository_reads_rows_not_the_file(pantry):
    """The spreadsheet seeds Postgres once; the application reads the rows."""
    assert len(pantry.items) == 37
    assert pantry.seed_from is None


def test_packaging_is_resolved_into_unit_cost(pantry):
    """82.00 for one 'balde 2kg' is 41.00 per kilo, not 82.00 per bucket."""
    capers = pantry.find('Alcaparras')
    assert capers.unit_cost == pytest.approx(41.0)
    assert capers.base_unit == 'kg'


@pytest.mark.parametrize(
    'name, cost',
    [
        ('Peito de frango', 14.0),      # 28.00 / 2 kg
        ('Arroz branco tipo 1', 4.98),  # 24.90 / 5 kg
        ('Ovos', 0.80),                 # 24.00 / 30 un
        ('Azeite de oliva extra virgem', 61.98),  # 30.99 / 0.5 L
    ],
)
def test_unit_cost_is_price_over_quantity(pantry, name, cost):
    assert pantry.find(name).unit_cost == pytest.approx(cost, abs=0.01)


def test_loose_piece_without_a_weight_is_flagged(pantry):
    """Chocolate coating cost 79.90 per 'un' and the sheet never says the weight."""
    item = pantry.find('Cobertura de chocolate')
    assert item.priced_per_piece
    assert 'note' in item.as_dict()


def test_eggs_priced_per_piece_are_not_a_problem(pantry):
    """A recipe counting eggs works fine at 0.80 each; this is not ambiguity."""
    assert pantry.find('Ovos').unit_cost == pytest.approx(0.80)


@pytest.mark.parametrize(
    'query, expected',
    [
        ('Carne moida', 'Carne moída (patinho)'),
        ('peito de frango', 'Peito de frango'),
        ('oleo de soja', 'Óleo de soja'),
        ('QUEIJO MUSSARELA', 'Queijo mussarela'),
    ],
)
def test_matching_tolerates_accents_case_and_parentheticals(pantry, query, expected):
    assert pantry.find(query).name == expected


@pytest.mark.parametrize(
    'query', ['farinha de rosca', 'linguica calabresa', 'leite condensado', 'azeitona verde']
)
def test_near_misses_are_refused(pantry, query):
    """Telling her she owns something she does not is worse than asking.

    'farinha de rosca' once matched 'Farinha de trigo' because the connective
    'de' counted towards the score.
    """
    assert pantry.find(query) is None


def test_suggestions_are_offered_when_nothing_matches(pantry):
    assert 'Farinha de trigo' in pantry.suggest('farinha de rosca')


def test_learned_package_size_does_not_zero_the_factor(database):
    """A float 400.0 once rendered as 'un 400.0g', which normalisation turned
    into '400 0g' and the pattern read as zero grams - dropping the ingredient
    out of the pantry entirely."""
    database.package_sizes = [
        {'ingredient_key': 'cobertura de chocolate', 'quantity': 400.0, 'unit': 'g'}
    ]
    from app.domain.pantry import PantryRepository

    item = PantryRepository(database).find('Cobertura de chocolate')
    assert item is not None
    assert item.unit_cost == pytest.approx(199.75, abs=0.01)  # 79.90 / 0.4 kg


def test_search_keyword_drops_grading_noise(pantry):
    assert pantry.find('Arroz branco tipo 1').search_keyword == 'Arroz branco'
