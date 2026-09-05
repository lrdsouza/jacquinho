"""Recency, domain grouping and cross-source agreement."""

import pytest

from app.domain.consensus import ConsensusEngine, PhraseExtractor
from app.domain.market import MarketPriceResearch, PriceObservation
from app.domain.search import Freshness, RecencyFilter, SearchResult


def result(title, url, snippet=''):
    return SearchResult(title=title, url=url, snippet=snippet)


def test_domain_ignores_www_and_port():
    assert result('t', 'https://www.tudogostoso.com.br/a').domain == 'tudogostoso.com.br'
    assert result('t', 'https://x.com:443/a').domain == 'x.com'


def test_dishes_keep_five_years_money_keeps_one_month():
    assert Freshness.MAX_AGE_YEARS[Freshness.DISHES] == 5
    assert Freshness.MONEY == Freshness.MONTH


def test_recency_only_drops_what_dates_itself_as_old():
    kept, dropped = RecencyFilter(Freshness.YEAR).apply([
        result('Receita de 2019', 'https://a.com/x', 'publicado em 2019'),
        result('Sem data', 'https://b.com/x', 'nada aqui'),
    ])
    assert dropped == 1
    assert [r.title for r in kept] == ['Sem data']


def test_a_page_comparing_old_and_new_years_survives():
    kept, dropped = RecencyFilter(Freshness.YEAR).apply([
        result('De 2019 a 2026', 'https://a.com/x', 'compara 2019 com 2026'),
    ])
    assert dropped == 0


def test_phrases_drop_recipe_boilerplate():
    phrases = PhraseExtractor.phrases('Frango à Parmegiana | Receita Fácil - TudoGostoso')
    assert 'frango parmegiana' in phrases
    assert not any('receita' in p for p in phrases)


PANTRY_TOKENS = {'arroz', 'branco', 'carne', 'moida', 'frango', 'peito', 'bacon'}


def _engine():
    return ConsensusEngine(provider=None, pantry_tokens=PANTRY_TOKENS)


def test_agreement_counts_domains_not_pages():
    """Five pages of one site are one opinion."""
    pages = [result('Frango parmegiana frigideira', f'https://a.com/{i}') for i in range(5)]
    assert _engine().agree(pages, min_sources=2) == []


def test_a_dish_on_two_domains_is_promoted():
    pages = [
        result('Frango parmegiana frigideira', 'https://a.com/x'),
        result('Frango parmegiana frigideira', 'https://b.com/y'),
    ]
    agreed = _engine().agree(pages, min_sources=2)
    assert [c.phrase for c in agreed] == ['frango parmegiana frigideira']


def test_a_phrase_made_only_of_pantry_words_is_an_ingredient():
    """'arroz branco' is something she owns, not something she can sell."""
    pages = [result('Arroz branco', f'https://{d}.com/x') for d in 'abcd']
    assert _engine().agree(pages, min_sources=2) == []


def test_a_phrase_touching_no_pantry_ingredient_is_discarded():
    pages = [result('Sopa de cebola francesa', f'https://{d}.com/x') for d in 'abcd']
    assert _engine().agree(pages, min_sources=2) == []


@pytest.mark.parametrize(
    'raw, value', [('24,90', 24.90), ('24.90', 24.90), ('1.249,00', 1249.0)]
)
def test_price_parsing_handles_brazilian_formatting(raw, value):
    assert MarketPriceResearch._parse_amount(raw) == pytest.approx(value)


def test_implausible_prices_are_ignored():
    """R$ 5,00 is the delivery fee; R$ 500,00 is not one lunchbox."""
    found = MarketPriceResearch._extract(
        MarketPriceResearch, 'Cardapio', 'http://x',
        'Marmita R$ 24,90. Frete R$ 5,00. Plano mensal R$ 500,00',
    )
    assert [o.value for o in found] == [24.90]


def test_confidence_counts_distinct_sources_not_observations():
    one_site = [PriceObservation(v, 't', 'http://a', 'c') for v in (16, 17, 19)]
    assert MarketPriceResearch.summarise(one_site)['confidence'] == 'low'
    assert MarketPriceResearch.summarise(one_site)['source_warning']

    three_sites = one_site + [
        PriceObservation(22, 't', 'http://b', 'c'),
        PriceObservation(25, 't', 'http://c', 'c'),
    ]
    assert MarketPriceResearch.summarise(three_sites)['confidence'] == 'medium'


def test_no_observations_is_a_real_answer():
    summary = MarketPriceResearch.summarise([])
    assert summary['reference'] is None
    assert summary['confidence'] == 'none'
