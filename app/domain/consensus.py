'''Cross-source agreement for dish discovery.

One recipe blog saying a dish is easy is an opinion. The same dish coming back
from several unrelated sites is a signal. This module runs a set of query
variations, keeps only recent results, and promotes a dish name to a candidate
only once independent domains agree on it.
'''

from __future__ import annotations

import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field

from .search import (
    Freshness,
    RecencyFilter,
    SearchError,
    SearchProvider,
    SearchResult,
)
from .units import UnitConverter


@dataclass
class SourceMention:
    '''One place a candidate dish was seen.'''

    domain: str
    title: str
    url: str

    def as_dict(self) -> dict:
        return {'domain': self.domain, 'title': self.title, 'url': self.url}


@dataclass
class ConsensusCandidate:
    '''A dish name that survived cross-source agreement.'''

    phrase: str
    mentions: list[SourceMention] = field(default_factory=list)
    pantry_tokens: set[str] = field(default_factory=set)

    @property
    def domains(self) -> set[str]:
        return {mention.domain for mention in self.mentions}

    @property
    def source_count(self) -> int:
        return len(self.domains)

    def as_dict(self) -> dict:
        return {
            'dish': self.phrase,
            'source_count': self.source_count,
            'sources': sorted(self.domains),
            'pantry_tokens_matched': sorted(self.pantry_tokens),
            'seen_at': [mention.as_dict() for mention in self.mentions[:4]],
        }


class PhraseExtractor:
    '''Pulls plausible dish names out of result titles.'''

    # Words that appear in every recipe headline and name no dish at all.
    NOISE = frozenset(
        {
            'receita', 'receitas', 'facil', 'faceis', 'rapida', 'rapido', 'simples',
            'como', 'fazer', 'melhor', 'melhores', 'deliciosa', 'delicioso', 'caseira',
            'caseiro', 'ingredientes', 'modo', 'preparo', 'passo', 'minutos', 'dicas',
            'aprenda', 'perfeita', 'perfeito', 'tradicional', 'super', 'incrivel',
            'para', 'com', 'sem', 'de', 'da', 'do', 'dos', 'das', 'em', 'no', 'na',
            'e', 'a', 'o', 'os', 'as', 'um', 'uma', 'que', 'seu', 'sua', 'melhorar',
            'video', 'blog', 'brasil', 'tudogostoso', 'panelinha', 'globo', 'cybercook',
            # Headline filler: these glue words survive the first pass and end up
            # in n-grams like 'rapidas bacon jantar complicacao'.
            'rapidas', 'rapidos', 'praticas', 'pratica', 'pratico', 'praticos',
            'jantar', 'almoco', 'janta', 'opcoes', 'opcao', 'ideias', 'ideia',
            'lista', 'saiba', 'veja', 'confira', 'completa', 'completo', 'caseiras',
            'deliciosas', 'deliciosos', 'favorita', 'favoritas', 'minuto', 'hoje',
            'semana', 'dia', 'noite', 'complicacao', 'gastar', 'muito', 'pouco',
            'barata', 'baratas', 'economica', 'economicas', 'nota', 'top', 'guia',
            'nao', 'sim', 'mais', 'menos', 'muita', 'todo', 'toda', 'todos', 'todas',
            'esse', 'essa', 'este', 'esta', 'isso', 'aqui', 'agora', 'ainda',
        }
    )
    # A dish name says how the thing is made or what shape it takes. Without
    # one of these the phrase is a pile of ingredients: 'brigadeiro com bacon'
    # got offered as a lunchbox because nothing asked it to look like a dish.
    PREPARATION = frozenset({
        'assado', 'assada', 'frito', 'frita', 'refogado', 'refogada', 'grelhado',
        'grelhada', 'cozido', 'cozida', 'empanado', 'empanada', 'gratinado',
        'gratinada', 'recheado', 'recheada', 'ensopado', 'ensopada', 'moqueca',
        'estrogonofe', 'parmegiana', 'milanesa', 'escondidinho', 'lasanha',
        'panqueca', 'risoto', 'torta', 'bolinho', 'bolinhos', 'croquete',
        'coxinha', 'empada', 'quibe', 'almondega', 'almondegas', 'nhoque',
        'suflê', 'sufle', 'farofa', 'salada', 'sopa', 'caldo', 'creme',
        'purê', 'pure', 'frigideira', 'panela', 'forno', 'churrasco',
        'strogonoff', 'feijoada', 'virado', 'cuscuz', 'omelete', 'fricasse',
        'soltinho', 'desfiado', 'desfiada', 'picadinho', 'bolo', 'pudim',
        'mousse', 'brigadeiro', 'pave', 'pavê', 'sanduiche', 'wrap', 'marmita',
    })
    MIN_WORDS = 2
    MAX_WORDS = 4
    SPLITTERS = re.compile(r'[|\-–—:•/(),.!?]')

    @classmethod
    def phrases(cls, title: str) -> set[str]:
        '''Return normalised n-grams from a title, noise words stripped.'''
        found: set[str] = set()
        for segment in cls.SPLITTERS.split(title):
            words = [
                word
                for word in UnitConverter.normalise_text(segment).split()
                if word not in cls.NOISE and not word.isdigit() and len(word) > 2
            ]
            for size in range(cls.MIN_WORDS, cls.MAX_WORDS + 1):
                for start in range(len(words) - size + 1):
                    found.add(' '.join(words[start : start + size]))
        return found


class ConsensusEngine:
    '''Searches many ways, then keeps only what independent sources agree on.'''

    def __init__(
        self,
        provider: SearchProvider,
        pantry_tokens: set[str],
        freshness: str = Freshness.DEFAULT,
    ):
        self.provider = provider
        self.pantry_tokens = pantry_tokens
        self.freshness = freshness
        self.recency = RecencyFilter(freshness)

    # The searches are independent, so they run at the same time. Serially, six
    # phrasings against a slow engine is six timeouts end to end, and the caller
    # is an MCP client with a 90 second budget: the tool would blow the client
    # timeout before returning anything, the call would be retried, and the
    # conversation would sit there for minutes with nothing on the screen.
    LANES = 6

    # And a wall clock over the whole thing, for the case the pool does not save
    # us. What is late is dropped and reported, never waited for: a partial
    # consensus that arrives is worth more than a complete one that times out.
    DEADLINE = 45.0

    def gather(self, queries: list[str], per_query: int = 8) -> dict:
        """Run every query at once, drop stale results, and pool what is left.

        Results are collected in query order and not in completion order. The
        pooling dedups by URL and keeps the first sighting, so completion order
        would make the same searches produce different output run to run.
        """
        results: list[SearchResult] = []
        errors: list[dict] = []
        stale_dropped = 0

        if not queries:
            return {'results': [], 'queries_run': 0, 'queries_failed': [],
                    'stale_results_dropped': 0}

        started = time.monotonic()
        pool = ThreadPoolExecutor(max_workers=min(self.LANES, len(queries)))
        try:
            running = [
                pool.submit(self.provider.search, query, per_query, self.freshness)
                for query in queries
            ]
            for query, task in zip(queries, running):
                left = self.DEADLINE - (time.monotonic() - started)
                try:
                    found = task.result(timeout=max(left, 0.0))
                except FuturesTimeout:
                    errors.append({'query': query, 'error': 'demorou demais'})
                    continue
                except SearchError as error:
                    errors.append({'query': query, 'error': str(error)})
                    continue
                kept, dropped = self.recency.apply(found)
                stale_dropped += dropped
                results.extend(kept)
        finally:
            # Never `with`: leaving the block joins the pool, and joining is
            # precisely what the deadline exists to avoid. A search still in
            # flight is abandoned, and dies on its own when the HTTP timeout
            # below it fires.
            pool.shutdown(wait=False, cancel_futures=True)

        deduped: dict[str, SearchResult] = {}
        for result in results:
            deduped.setdefault(result.url, result)

        return {
            'results': list(deduped.values()),
            'queries_run': len(queries),
            'queries_failed': errors,
            'stale_results_dropped': stale_dropped,
        }

    def agree(
        self, results: list[SearchResult], min_sources: int = 2
    ) -> list[ConsensusCandidate]:
        '''Promote phrases seen on ``min_sources`` distinct domains.

        A phrase must also touch at least one pantry ingredient: consensus on
        a dish she has no ingredients for is agreement about nothing useful.
        '''
        by_phrase: dict[str, ConsensusCandidate] = defaultdict(
            lambda: ConsensusCandidate(phrase='')
        )

        for result in results:
            mention = SourceMention(result.domain, result.title, result.url)
            for phrase in PhraseExtractor.phrases(result.title):
                words = set(phrase.split())
                matched = self.pantry_tokens & words
                # A dish name touches the pantry AND adds something to it: a
                # preparation, a style, a cut. A phrase made only of pantry
                # tokens is an ingredient ('arroz branco', 'carne moida'),
                # which is not a dish she can put on a menu.
                if not matched or not (words - self.pantry_tokens):
                    continue
                # And it has to name a way of cooking or a form. Without this,
                # any two words that happen to co-occur become a dish.
                if not (words & PhraseExtractor.PREPARATION):
                    continue
                candidate = by_phrase[phrase]
                candidate.phrase = phrase
                candidate.mentions.append(mention)
                candidate.pantry_tokens |= matched

        agreed = [
            candidate
            for candidate in by_phrase.values()
            if candidate.source_count >= min_sources
        ]
        agreed.sort(key=lambda candidate: (-candidate.source_count, candidate.phrase))
        return self._drop_subsumed(agreed)

    @staticmethod
    def _drop_subsumed(candidates: list[ConsensusCandidate]) -> list[ConsensusCandidate]:
        '''Remove phrases fully contained in a stronger one.

        'frango parmegiana' and 'frango parmegiana forno' are the same finding;
        keep the one backed by more sources.
        '''
        kept: list[ConsensusCandidate] = []
        for candidate in candidates:
            words = set(candidate.phrase.split())
            if any(
                words < set(other.phrase.split())
                and other.source_count >= candidate.source_count
                for other in candidates
                if other is not candidate
            ):
                continue
            kept.append(candidate)
        return kept
