'''Market price research: what comparable dishes actually sell for.

A multiplier over cost is not a price. This module goes and looks at what
delivery menus charge for the same dish, so a scenario can be positioned
against the market instead of invented.
'''

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from .search import Freshness, RecencyFilter, SearchError, SearchProvider


@dataclass(frozen=True)
class PriceObservation:
    '''One price seen in the wild, kept with its source for auditing.'''

    value: float
    source_title: str
    source_url: str
    context: str

    def as_dict(self) -> dict:
        return {
            'value': round(self.value, 2),
            'source_title': self.source_title,
            'source_url': self.source_url,
            'context': self.context,
        }


class MarketPriceResearch:
    '''Searches delivery listings and extracts plausible dish prices.'''

    # 'R$ 24,90', 'R$24.90', 'R$ 1.249,00'
    PRICE = re.compile(r'R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:\.\d{2})?)')
    # A delivery main course outside this range is almost certainly not a
    # single-dish price: a combo, a monthly plan, or a scraped phone number.
    PLAUSIBLE_RANGE = (8.0, 200.0)
    CONTEXT_WINDOW = 60

    def __init__(self, provider: SearchProvider, freshness: str = Freshness.MONEY):
        self.provider = provider
        self.freshness = freshness
        self.recency = RecencyFilter(freshness)

    @classmethod
    def _parse_amount(cls, raw: str) -> float | None:
        text = raw.strip()
        if ',' in text:
            text = text.replace('.', '').replace(',', '.')
        try:
            return float(text)
        except ValueError:
            return None

    def _extract(self, title: str, url: str, snippet: str) -> list[PriceObservation]:
        found = []
        for match in self.PRICE.finditer(snippet):
            value = self._parse_amount(match.group(1))
            if value is None:
                continue
            low, high = self.PLAUSIBLE_RANGE
            if not low <= value <= high:
                continue
            start = max(0, match.start() - self.CONTEXT_WINDOW)
            end = min(len(snippet), match.end() + self.CONTEXT_WINDOW)
            found.append(
                PriceObservation(
                    value=value,
                    source_title=title,
                    source_url=url,
                    context=snippet[start:end].strip(),
                )
            )
        return found

    def research(self, dish: str, city: str = '', limit: int = 10) -> dict:
        '''Collect recently published delivery prices for a dish.

        Stale prices are worse than none: a 2019 menu would anchor her below
        today's market. Freshness is applied at the provider and again here.
        '''
        query = ' '.join(part for part in ['preco', dish, 'delivery marmita', city] if part)
        try:
            results = self.provider.search(query, limit, self.freshness)
        except SearchError as error:
            return {
                'query': query,
                'provider': self.provider.name,
                'error': str(error),
                'observations': [],
                'sample_size': 0,
                'confidence': 'none',
            }

        results, stale_dropped = self.recency.apply(results)
        observations: list[PriceObservation] = []
        for result in results:
            observations.extend(
                self._extract(result.title, result.url, f'{result.title} {result.snippet}')
            )

        return {
            'query': query,
            'provider': self.provider.name,
            'freshness': self.freshness,
            'pages_searched': len(results),
            'stale_results_dropped': stale_dropped,
            **self.summarise(observations),
        }

    @staticmethod
    def summarise(observations: list[PriceObservation]) -> dict:
        '''Turn raw observations into a reference band, honest about sample size.'''
        values = sorted(observation.value for observation in observations)
        sample_size = len(values)
        # Five prices scraped off one menu is one opinion, not five. Confidence
        # follows distinct sources, not raw observation count.
        distinct_sources = len({observation.source_url for observation in observations})

        if sample_size == 0:
            return {
                'observations': [],
                'sample_size': 0,
                'distinct_sources': 0,
                'confidence': 'none',
                'reference': None,
                'caveat': (
                    'No prices found. Say so out loud; do not present a price as '
                    'market-backed when it is not.'
                ),
                'next_step': (
                    "Tightening freshness to the last month often returns nothing. "
                    "Retry with freshness='year' and, if that finds prices, tell "
                    'Dona Maria the reference is up to a year old and that her costs '
                    'have moved since (economy_current_indicators says by how much). '
                    'A labelled older reference beats no reference; an unlabelled '
                    'one does not.'
                ),
            }

        confidence = (
            'low'
            if distinct_sources < 3
            else 'medium'
            if distinct_sources < 6
            else 'good'
        )
        return {
            'observations': [observation.as_dict() for observation in observations],
            'sample_size': sample_size,
            'distinct_sources': distinct_sources,
            'confidence': confidence,
            'reference': {
                'min': round(values[0], 2),
                'median': round(statistics.median(values), 2),
                'max': round(values[-1], 2),
            },
            'caveat': (
                'Scraped from public listings, so treat it as a sanity check on the '
                'range, not a precise benchmark. Always show the sources.'
            ),
            'source_warning': (
                f'All {sample_size} prices came from {distinct_sources} source(s). '
                'Say so before presenting this as the market.'
            )
            if distinct_sources < 3
            else None,
        }
