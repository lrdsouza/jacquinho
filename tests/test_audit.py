"""Auditing the sentence against the numbers."""

import pytest

from app.domain.audit import MessageAudit

EVIDENCE = {
    'cmv': {'cmv_per_portion': 8.68, 'shopping_cost': 4.0},
    'scenarios': [{'selling_price': 19.90, 'profit_per_portion': 9.23}],
    'market': {'reference': {'min': 16.0, 'median': 19.0, 'max': 26.0}},
}


@pytest.mark.parametrize(
    'text, values',
    [
        ('Custa R$ 8,68 por marmita', [8.68]),
        ('R$ 19,90 e R$ 9,23', [19.90, 9.23]),
        ('R$ 1.249,00', [1249.0]),
        ('margem de 46%', [46.0]),
    ],
)
def test_figures_are_extracted(text, values):
    assert [f.value for f in MessageAudit.figures(text)] == pytest.approx(values)


def test_a_message_quoting_computed_numbers_is_clean():
    result = MessageAudit.check(
        'O CMV é R$ 8,68 e vendendo a R$ 19,90 sobram R$ 9,23 pra você.', EVIDENCE
    )
    assert result['verdict'] == 'clean'
    assert result['figures_supported'] == 3


def test_an_invented_price_is_caught():
    """The failure this whole system exists to prevent."""
    result = MessageAudit.check('Eu cobraria uns R$ 24,50 nessa marmita.', EVIDENCE)
    assert result['verdict'] == 'unsupported_figures'
    assert result['unsupported'][0]['value'] == pytest.approx(24.50)


def test_one_invented_number_among_good_ones_is_still_caught():
    result = MessageAudit.check(
        'CMV de R$ 8,68, vendendo a R$ 19,90, dá R$ 11,00 de lucro.', EVIDENCE
    )
    assert [f['value'] for f in result['unsupported']] == pytest.approx([11.0])


def test_rounding_within_a_cent_is_the_same_number():
    assert MessageAudit.check('R$ 8,68', {'x': 8.679})['verdict'] == 'clean'


def test_numbers_nested_anywhere_in_the_evidence_count():
    deep = {'a': [{'b': {'c': [{'d': 42.5}]}}]}
    assert MessageAudit.check('R$ 42,50', deep)['verdict'] == 'clean'


def test_booleans_are_not_numbers():
    """True must not make 'R$ 1,00' look supported."""
    assert MessageAudit.check('R$ 1,00', {'fits': True})['verdict'] != 'clean'


def test_a_message_with_no_figures_is_clean():
    assert MessageAudit.check('Você tem forno?', EVIDENCE)['figures_stated'] == 0
