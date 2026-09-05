'''Recipe search: pantry ingredients turned into keywords, then queried.

Two responsibilities, deliberately separate:
  * :class:`RecipeQueryBuilder` turns the spreadsheet into search keywords.
  * :class:`SearchProvider` subclasses actually hit the web.
'''

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from .pantry import PantryItem, PantryRepository
from .units import UnitConverter


class SearchError(RuntimeError):
    '''Raised when the upstream search backend cannot be reached.'''


class Freshness:
    '''How recent a result has to be, in vocabulary each provider maps itself.'''

    DAY = 'day'
    WEEK = 'week'
    MONTH = 'month'
    YEAR = 'year'
    FIVE_YEARS = 'five_years'
    ANY = 'any'

    ALL = (DAY, WEEK, MONTH, YEAR, FIVE_YEARS, ANY)
    # Dish discovery: a good recipe from four years ago is still a good recipe.
    DISHES = FIVE_YEARS
    # Anything about money: last month, or it is not the current market.
    MONEY = MONTH
    DEFAULT = FIVE_YEARS

    # Neither search engine can express 'past five years', so FIVE_YEARS sends
    # no upstream filter and is enforced entirely by RecencyFilter below.
    BRAVE = {DAY: 'pd', WEEK: 'pw', MONTH: 'pm', YEAR: 'py'}
    DUCKDUCKGO = {DAY: 'd', WEEK: 'w', MONTH: 'm', YEAR: 'y'}

    MAX_AGE_YEARS = {DAY: 1, WEEK: 1, MONTH: 1, YEAR: 2, FIVE_YEARS: 5, ANY: 99}


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str

    @property
    def domain(self) -> str:
        '''Registrable host, so two pages of one site count as one source.'''
        host = urlsplit(self.url).netloc.lower()
        host = host.split('@')[-1].split(':')[0]
        if host.startswith('www.'):
            host = host[4:]
        return host

    def as_dict(self) -> dict:
        return {
            'title': self.title,
            'url': self.url,
            'snippet': self.snippet,
            'domain': self.domain,
        }


class RecencyFilter:
    '''Drops results that visibly date themselves as too old.

    Deliberately conservative: it only rejects a result that states a year
    older than the cutoff. Undated pages pass, because provider-side freshness
    is the primary filter and guessing here would throw away good recipes.
    '''

    YEAR_PATTERN = re.compile(r'\b(19\d{2}|20\d{2})\b')

    def __init__(self, freshness: str):
        self.freshness = freshness if freshness in Freshness.ALL else Freshness.DEFAULT
        self.cutoff_year = (
            datetime.now(timezone.utc).year - Freshness.MAX_AGE_YEARS[self.freshness]
        )

    def keep(self, result: SearchResult) -> bool:
        years = [
            int(year)
            for year in self.YEAR_PATTERN.findall(f'{result.title} {result.snippet}')
        ]
        # Only reject when every year mentioned is stale; a page comparing
        # 2019 to 2026 is still current.
        return not years or max(years) >= self.cutoff_year

    def apply(self, results: list[SearchResult]) -> tuple[list[SearchResult], int]:
        kept = [result for result in results if self.keep(result)]
        return kept, len(results) - len(kept)


class RecipeQueryBuilder:
    '''Builds web-search queries out of what is actually in the pantry.

    Groups ingredients so queries look like something a cook would type:
    a protein plus a side plus the word 'receita', rather than a dump of all
    37 ingredients into one query.
    '''

    PROTEIN_TOKENS = {
        'frango', 'carne', 'patinho', 'acem', 'alcatra', 'bacon', 'ovos', 'ovo'
    }
    STAPLE_TOKENS = {
        'arroz', 'feijao', 'macarrao', 'espaguete', 'batata', 'polenta', 'fuba',
        'farinha', 'mandioca'
    }
    AROMATIC_TOKENS = {'tomate', 'cebola', 'alho', 'couve', 'salsinha'}
    # Checked before proteins: 'Caldo de carne' is a seasoning, not a protein.
    SEASONING_TOKENS = {
        'caldo', 'sal', 'acucar', 'canela', 'acafrao', 'tempero', 'oleo', 'adocante'
    }
    # Pricey items that wreck the cost of a lunchbox if used as a base.
    PREMIUM_TOKENS = {
        'alcaparras', 'amendoa', 'chantilly', 'cobertura', 'azeite', 'aceto',
        'ninho', 'adocante'
    }

    def __init__(self, pantry: PantryRepository):
        self.pantry = pantry

    def _bucket(self, item: PantryItem) -> str:
        tokens = set(item.key.split())
        for name, group in (
            ('premium', self.PREMIUM_TOKENS),
            ('seasoning', self.SEASONING_TOKENS),
            ('protein', self.PROTEIN_TOKENS),
            ('staple', self.STAPLE_TOKENS),
            ('aromatic', self.AROMATIC_TOKENS),
        ):
            if tokens & group:
                return name
        return 'other'

    def buckets(self) -> dict[str, list[PantryItem]]:
        grouped: dict[str, list[PantryItem]] = {}
        for item in self.pantry.sorted_items():
            grouped.setdefault(self._bucket(item), []).append(item)
        return grouped

    def build(self, constraints: list[str] | None = None, limit: int = 8) -> list[dict]:
        '''Return ranked query strings, each with the keywords it came from.'''
        grouped = self.buckets()
        suffix = ' '.join(constraints or [])
        queries: list[dict] = []

        proteins = grouped.get('protein', [])
        staples = grouped.get('staple', [])

        # Rotate through the staples so the queries explore the pantry instead
        # of pairing every protein with the single cheapest side.
        ranked_staples = sorted(staples, key=lambda item: item.unit_cost)
        for index, protein in enumerate(proteins):
            keywords = [protein.search_keyword]
            if ranked_staples:
                partner = ranked_staples[index % len(ranked_staples)]
                if partner.key != protein.key:
                    keywords.append(partner.search_keyword)
            queries.append(self._query(keywords, suffix, 'protein + staple'))

        for staple in staples[:3]:
            queries.append(self._query([staple.search_keyword], suffix, 'staple only'))

        seen, unique = set(), []
        for query in queries:
            if query['query'] not in seen:
                seen.add(query['query'])
                unique.append(query)
        return unique[:limit]

    @staticmethod
    def _query(keywords: list[str], suffix: str, rationale: str) -> dict:
        text = ' '.join(['receita'] + keywords + ([suffix] if suffix else []))
        return {
            'query': re.sub(r'\s+', ' ', text).strip(),
            'keywords': keywords,
            'rationale': rationale,
        }

    def coverage(self, ingredients: list[str]) -> dict:
        '''How much of a found recipe the pantry already covers.'''
        available, missing = [], []
        for name in ingredients:
            item = self.pantry.find(name)
            if item is None:
                missing.append({'ingredient': name, 'suggestions': self.pantry.suggest(name)})
            else:
                available.append(
                    {
                        'ingredient': name,
                        'matched_to': item.name,
                        'unit_cost': f'R$ {item.unit_cost:.2f}/{item.base_unit}',
                        'stock': f'{item.stock:g} {item.base_unit}',
                    }
                )
        total = len(ingredients) or 1
        premium = [
            entry['matched_to']
            for entry in available
            if set(UnitConverter.normalise_text(entry['matched_to']).split())
            & self.PREMIUM_TOKENS
        ]
        return {
            'coverage_ratio': round(len(available) / total, 2),
            'in_pantry': available,
            'not_in_pantry': missing,
            'premium_ingredients_used': premium,
            'warning': (
                'This recipe leans on expensive pantry items; check the CMV before '
                'suggesting it as a lunchbox.'
            )
            if premium
            else None,
        }


class SearchProvider(ABC):
    '''Contract every search backend implements.'''

    name = 'abstract'

    @abstractmethod
    def search(
        self, query: str, limit: int, freshness: str = Freshness.DEFAULT
    ) -> list[SearchResult]:
        ...


class BraveSearchProvider(SearchProvider):
    '''Brave Search API. Stable JSON contract; needs BRAVE_API_KEY.'''

    name = 'brave'
    ENDPOINT = 'https://api.search.brave.com/res/v1/web/search'

    def __init__(self, api_key: str, timeout: float = 20.0):
        self.api_key = api_key
        self.timeout = timeout

    def search(
        self, query: str, limit: int, freshness: str = Freshness.DEFAULT
    ) -> list[SearchResult]:
        params = {'q': query, 'count': limit, 'country': 'br', 'search_lang': 'pt'}
        if freshness in Freshness.BRAVE:
            params['freshness'] = Freshness.BRAVE[freshness]
        try:
            response = httpx.get(
                self.ENDPOINT,
                params=params,
                headers={'Accept': 'application/json', 'X-Subscription-Token': self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SearchError(f'brave search failed: {error}') from error

        results = response.json().get('web', {}).get('results', [])
        return [
            SearchResult(
                title=entry.get('title', ''),
                url=entry.get('url', ''),
                snippet=re.sub(r'<[^>]+>', '', entry.get('description', '')),
            )
            for entry in results[:limit]
        ]


class DuckDuckGoSearchProvider(SearchProvider):
    '''Keyless fallback. Scrapes the HTML endpoint, so treat it as best effort.'''

    name = 'duckduckgo'
    ENDPOINT = 'https://html.duckduckgo.com/html/'
    RESULT = re.compile(r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    SNIPPET = re.compile(r'result__snippet"[^>]*>(.*?)</a>', re.S)

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout

    def search(
        self, query: str, limit: int, freshness: str = Freshness.DEFAULT
    ) -> list[SearchResult]:
        payload = {'q': query, 'kl': 'br-pt'}
        if freshness in Freshness.DUCKDUCKGO:
            payload['df'] = Freshness.DUCKDUCKGO[freshness]
        try:
            response = httpx.post(
                self.ENDPOINT,
                data=payload,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; SaborDaMaria/1.0)'},
                timeout=self.timeout,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise SearchError(f'duckduckgo search failed: {error}') from error

        snippets = self.SNIPPET.findall(response.text)
        results = []
        for index, (url, title) in enumerate(self.RESULT.findall(response.text)[:limit]):
            snippet = snippets[index] if index < len(snippets) else ''
            results.append(
                SearchResult(
                    title=self._clean(title),
                    url=html.unescape(url),
                    snippet=self._clean(snippet),
                )
            )
        return results

    @staticmethod
    def _clean(fragment: str) -> str:
        return html.unescape(re.sub(r'<[^>]+>', '', fragment)).strip()


class SearchProviderFactory:
    '''Picks a provider from configuration, preferring the keyed one.'''

    @staticmethod
    def create(provider: str, brave_api_key: str) -> SearchProvider:
        if provider == 'brave' or (provider == 'auto' and brave_api_key):
            if not brave_api_key:
                raise SearchError('SEARCH_PROVIDER=brave but BRAVE_API_KEY is empty')
            return BraveSearchProvider(brave_api_key)
        return DuckDuckGoSearchProvider()
