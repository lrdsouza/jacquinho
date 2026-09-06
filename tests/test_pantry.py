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


# --------------------------------------------------------- finite stock

def test_stock_starts_at_what_the_spreadsheet_says(pantry):
    beef = pantry.find('Carne moída (patinho)')
    assert beef.stock == pytest.approx(1.5)
    assert beef.used == pytest.approx(0.0)
    assert beef.seeded_stock == pytest.approx(1.5)


def test_a_committed_dish_takes_its_share_out_of_the_pantry(pantry):
    """Her kilo of patinho is a kilo, not a supply."""
    pantry.record_usage('lasanha de panela', [('carne moida patinho', 1.0)], portions=8)

    beef = pantry.find('Carne moída (patinho)')
    assert beef.stock == pytest.approx(0.5)
    assert beef.used == pytest.approx(1.0)
    assert beef.seeded_stock == pytest.approx(1.5)


def test_the_second_dish_sees_what_the_first_one_ate(pantry):
    """Two dishes wanting a kilo each, and only 1,5 kg in the fridge."""
    pantry.record_usage('lasanha de panela', [('carne moida patinho', 1.0)], portions=8)
    pantry.record_usage('escondidinho de carne', [('carne moida patinho', 1.0)], portions=8)

    beef = pantry.find('Carne moída (patinho)')
    # Stock never goes negative: what is missing is a shopping line, not a
    # pantry with less than nothing in it.
    assert beef.stock == pytest.approx(0.0)
    assert beef.used == pytest.approx(1.5)


def test_the_history_says_which_dish_took_what(pantry):
    pantry.record_usage('lasanha de panela', [('carne moida patinho', 1.0)], portions=8)
    history = pantry.usage_history('carne moida patinho')
    assert [(row['dish'], row['quantity']) for row in history] == [
        ('lasanha de panela', 1.0)
    ]


def test_a_dish_she_drops_gives_its_ingredients_back(pantry):
    pantry.record_usage('lasanha de panela', [('carne moida patinho', 1.0)], portions=8)
    assert pantry.forget_usage('lasanha de panela') == 1
    assert pantry.find('Carne moída (patinho)').stock == pytest.approx(1.5)


def test_nothing_is_written_for_an_empty_batch(pantry):
    report = pantry.record_usage('prato nenhum', [], portions=4)
    assert report['recorded'] is False
    assert pantry.find('Carne moída (patinho)').stock == pytest.approx(1.5)


def test_one_line_per_ingredient_even_when_the_recipe_asks_twice():
    """A recipe can ask for tomato twice - the fresh one and the sauce."""
    from tests.conftest import FakeDatabase
    from app.domain.pantry import PantryRepository, PantrySheet
    from tests.conftest import spreadsheet

    pantry = PantryRepository(FakeDatabase(PantrySheet(spreadsheet()).rows()))
    pantry.record_usage(
        'bolonhesa',
        [('tomate', 1.02), ('tomate', 0.8)],
        portions=18,
    )
    history = pantry.usage_history('tomate')
    assert len(history) == 1
    assert history[0]['quantity'] == pytest.approx(1.82)


def test_accepting_the_same_dish_twice_does_not_eat_the_pantry_twice(pantry):
    for _ in range(2):
        pantry.record_usage('lasanha', [('carne moida patinho', 1.0)], portions=8)
    assert pantry.find('Carne moída (patinho)').stock == pytest.approx(0.5)
