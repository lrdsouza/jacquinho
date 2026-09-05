'''Confidence layer: how much the evidence actually supports the answer.

Two independent assessors, because they fail differently. The deterministic
scorer cannot be talked into anything but only sees what it was told to look
for. The LLM judge reads the draft answer against the evidence and catches
claims nothing supports, but can be persuaded. Combining them conservatively
is the point: the answer is only as strong as the weaker assessment.
'''

from __future__ import annotations

import json
from dataclasses import dataclass, field


class ConfidenceMode:
    '''How the assessment is produced.'''

    DETERMINISTIC = 'deterministic'
    LLM = 'llm'
    HYBRID = 'hybrid'

    ALL = (DETERMINISTIC, LLM, HYBRID)


@dataclass
class Signal:
    '''One measurable ground for trusting, or not trusting, the answer.'''

    name: str
    weight: int
    score: float
    reason: str

    def as_dict(self) -> dict:
        return {
            'signal': self.name,
            'weight': self.weight,
            'score': round(self.score, 2),
            'reason': self.reason,
        }


@dataclass
class DeterministicVerdict:
    score: float
    signals: list[Signal] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    claim: str = 'price'

    def as_dict(self) -> dict:
        return {
            'score': round(self.score, 2),
            'band': band_for(self.score),
            'claim': self.claim,
            'signals': [signal.as_dict() for signal in self.signals],
            'blocking_issues': self.blocking_issues,
        }


# Confidence is reported on 0..1. A 0..100 score reads as a school mark and
# invites arguing about a point either way; 0..1 reads as what it is, a degree
# of belief, and keeps the two assessors on the same scale as each other.
HIGH = 0.75
MEDIUM = 0.50


def band_for(score: float) -> str:
    return 'high' if score >= HIGH else 'medium' if score >= MEDIUM else 'low'


BAND_LABEL = {'high': 'alta', 'medium': 'média', 'low': 'baixa'}


class ConfidenceBadge:
    """A one-line marker the agent appends to what it says.

    Confidence that only exists in a tool result is confidence nobody sees. The
    badge turns the score into something readable at the end of a message -
    which band, and the two or three facts that decided it - so a weak answer
    announces itself instead of reading exactly like a strong one.

    It is deliberately not a bare percentage: a number invites false precision
    about a heuristic, while 'CMV completo, 6 fontes de preço' says what is
    actually known.
    """

    @staticmethod
    def _evidence(signals: list) -> list[str]:
        table = {
            'pantry': {1.0: 'lido da planilha dela', 0.0: 'despensa não consultada'},
            'feasibility': {1.0: 'cozinha confere', 0.3: 'faltam respostas dela',
                            0.0: 'cozinha não dá conta'},
            'cost': {1.0: 'CMV completo', 0.1: 'CMV incompleto', 0.0: 'CMV não calculado'},
            'web_consensus': {1.0: 'consenso forte entre fontes', 0.8: '3 fontes concordam',
                              0.6: '2 fontes concordam', 0.25: 'fonte única',
                              0.0: 'sem concordância'},
            'market': {1.0: 'preço de mercado bem apurado', 0.75: 'preço de mercado apurado',
                       0.4: 'poucas fontes de preço', 0.0: 'sem preço de mercado'},
            'economy': {1.0: 'inflação atual', 0.7: 'inflação defasada',
                        0.3: 'inflação antiga', 0.0: 'inflação não consultada'},
        }
        # Weakest first. A badge that lists what went well and hides the one
        # thing that did not is worse than no badge: it reads as reassurance.
        out = []
        for signal in sorted(signals, key=lambda item: item.score):
            options = table.get(signal.name, {})
            if not options:
                continue
            closest = min(options, key=lambda value: abs(value - signal.score))
            out.append(options[closest])
        return out

    @classmethod
    def build(
        cls, score: float, signals: list, blocking: list[str], claim: str = ''
    ) -> str:
        band = BAND_LABEL[band_for(score)]
        kind = f'{Claim.label(claim)}: ' if claim else ''
        if blocking:
            return f'〔{kind}confiança {band} — {len(blocking)} impedimento(s)〕'
        evidence = cls._evidence(signals)
        return f'〔{kind}confiança {band} · ' + ' · '.join(evidence[:3]) + '〕'


class Claim:
    '''What a message is actually asserting, and what that assertion needs.

    Scoring every message against the whole pipeline was wrong. 'Você tem 37
    ingredientes' is read straight off the spreadsheet and is as certain as
    anything here gets; marking it 0.00 for want of a market price says nothing
    about the sentence and everything about a scorer measuring the wrong thing.

    So confidence is relative to the claim. A price is only as good as its
    weakest support - gate, cost, market and inflation. A pantry fact needs the
    pantry and nothing else.
    '''

    PANTRY = 'pantry_fact'
    DISH = 'dish_suggestion'
    FEASIBILITY = 'feasibility'
    COST = 'cost'
    PRICE = 'price'

    # claim -> (how to say it in Portuguese, the signals it rests on)
    REQUIRES = {
        PANTRY: ('o que ela tem', ('pantry',)),
        DISH: ('sugestão de prato', ('pantry', 'web_consensus')),
        FEASIBILITY: ('se ela consegue fazer', ('feasibility',)),
        COST: ('custo', ('pantry', 'feasibility', 'cost')),
        PRICE: ('preço', ('feasibility', 'cost', 'market', 'economy')),
    }

    # A question cannot be wrong, and neither can a message that asserts
    # nothing. Anything not listed here leaves the claim where it was.
    FROM_TOOL = {
        'pantry_list_ingredients': PANTRY,
        'pantry_find_ingredient': PANTRY,
        'pantry_record_package_size': PANTRY,
        'recipes_check_pantry_coverage': DISH,
        'dishes_discover_dishes': DISH,
        'dishes_survey_categories': DISH,
        'dishes_assess_category': DISH,
        'recipes_search_recipes': DISH,
        'recipes_next_candidate': DISH,
        'kitchen_check_feasibility': FEASIBILITY,
        'kitchen_elicitation_gaps': FEASIBILITY,
        'kitchen_analyse_recipe_requirements': FEASIBILITY,
        'pricing_calculate_cmv': COST,
        'market_research_dish_prices': PRICE,
        'economy_current_indicators': PRICE,
        'pricing_price_scenarios': PRICE,
    }

    @classmethod
    def label(cls, claim: str) -> str:
        return cls.REQUIRES.get(claim, ('afirmação', ()))[0]

    @classmethod
    def signals_for(cls, claim: str) -> tuple[str, ...]:
        return cls.REQUIRES.get(claim, tuple(DeterministicScorer.WEIGHTS))[1]


class DeterministicScorer:
    '''Scores the evidence a claim rests on, and nothing else.

    The thresholds below are **ordinal, not calibrated**. Four agreeing domains
    scoring 1.00 and three scoring 0.80 came from judgement, not from measuring
    that four-source dishes go wrong less often. They order answers correctly;
    the absolute value is not a probability of anything. They are class
    attributes so a calibration run can replace them without touching logic.
    '''

    WEIGHTS = {
        'pantry': 20,
        'feasibility': 25,
        'cost': 25,
        'web_consensus': 20,
        'market': 20,
        'economy': 10,
    }

    # Ordinal thresholds, gathered here so they can be tuned or calibrated in
    # one place. Each is (minimum, score), highest first.
    CONSENSUS_STEPS = ((4, 1.0), (3, 0.8), (2, 0.6), (1, 0.25))
    MARKET_STEPS = ((6, 1.0), (3, 0.75), (1, 0.4))
    ECONOMY_STEPS = ((3, 1.0), (6, 0.7))

    @staticmethod
    def for_count(count: int, steps: tuple) -> float:
        return next((value for minimum, value in steps if count >= minimum), 0.0)

    # What each claim refuses to be said without.
    BLOCKS = {
        Claim.FEASIBILITY: ('feasibility',),
        Claim.COST: ('feasibility', 'cost'),
        Claim.PRICE: ('feasibility', 'cost', 'market'),
    }

    BLOCK_TEXT = {
        'feasibility': 'O gate de viabilidade não aprovou: não apresente o prato como decidido.',
        'cost': 'O CMV não está completo: não afirme custo nem preço.',
        'market': 'Sem preço de mercado observado: só o preço mínimo pode ser dito.',
    }

    def score(
        self,
        feasibility: dict | None = None,
        cmv: dict | None = None,
        consensus: dict | None = None,
        market: dict | None = None,
        economy: dict | None = None,
        pantry: dict | None = None,
        claim: str = Claim.PRICE,
    ) -> DeterministicVerdict:
        '''Score only what this kind of claim rests on.'''
        computed = {
            'pantry': self._pantry(pantry),
            'feasibility': self._feasibility(feasibility),
            'cost': self._cost(cmv),
            'web_consensus': self._consensus(consensus),
            'market': self._market(market),
            'economy': self._economy(economy),
        }
        wanted = Claim.signals_for(claim)
        signals = [computed[name] for name in wanted if name in computed]
        if not signals:
            signals = list(computed.values())

        total_weight = sum(signal.weight for signal in signals)
        score = sum(signal.score * signal.weight for signal in signals) / total_weight

        strength = {
            'feasibility': feasibility is not None
            and feasibility.get('verdict') == 'approved',
            'cost': cmv is not None and bool(cmv.get('calculation_complete')),
            'market': market is not None and bool(market.get('sample_size')),
        }
        blocking = [
            self.BLOCK_TEXT[name]
            for name in self.BLOCKS.get(claim, ())
            if not strength[name]
        ]

        return DeterministicVerdict(
            score=score, signals=signals, blocking_issues=blocking, claim=claim
        )

    def _pantry(self, payload: dict | None) -> Signal:
        '''How much of what the message needs was actually looked up.

        Reading the whole list used to score 1.00 even for a message about an
        ingredient nobody checked - the signal said 'the file was opened', not
        'this was verified'. When a recipe has been checked against the pantry,
        its coverage is the score.
        '''
        weight = self.WEIGHTS['pantry']
        if not payload:
            return Signal('pantry', weight, 0.0, 'a despensa não foi consultada')

        coverage = payload.get('coverage_ratio')
        if isinstance(coverage, (int, float)):
            missing = len(payload.get('not_in_pantry', []))
            return Signal(
                'pantry', weight, float(coverage),
                f'{coverage:.0%} dos ingredientes conferidos'
                + (f', {missing} fora da lista' if missing else ''),
            )
        # A plain list read: her whole pantry is known, nothing specific checked.
        return Signal('pantry', weight, 1.0, 'lido direto da planilha dela')

    def _feasibility(self, payload: dict | None) -> Signal:
        weight = self.WEIGHTS['feasibility']
        if not payload:
            return Signal('feasibility', weight, 0.0, 'kitchen_check_feasibility never ran')
        verdict = payload.get('verdict')
        table = {'approved': 1.0, 'needs_answers': 0.3, 'rejected': 0.0}
        return Signal(
            'feasibility',
            weight,
            table.get(verdict, 0.0),
            f'gate verdict is {verdict!r}',
        )

    def _cost(self, payload: dict | None) -> Signal:
        weight = self.WEIGHTS['cost']
        if not payload:
            return Signal('cost', weight, 0.0, 'pricing_calculate_cmv never ran')
        if not payload.get('calculation_complete'):
            return Signal(
                'cost',
                weight,
                0.1,
                f"CMV incomplete: {len(payload.get('open_questions', []))} open "
                f"question(s), {len(payload.get('not_found', []))} unmatched ingredient(s)",
            )
        score, notes = 1.0, ['CMV complete']
        if not payload.get('budget', {}).get('fits', True):
            score -= 0.3
            notes.append('shopping does not fit the remaining budget')
        estimated = [
            item for item in payload.get('must_buy', []) if 'estimated' in item.get('basis', '')
        ]
        if estimated:
            score -= 0.2
            notes.append(
                f'{len(estimated)} purchase(s) priced from what she paid before, '
                'not from a current quote'
            )
        return Signal('cost', weight, max(score, 0.0), '; '.join(notes))

    def _consensus(self, payload: dict | None) -> Signal:
        weight = self.WEIGHTS['web_consensus']
        if not payload:
            return Signal('web_consensus', weight, 0.0, 'no cross-source search was run')
        dishes = payload.get('agreed_dishes', [])
        if not dishes:
            return Signal('web_consensus', weight, 0.0, 'no dish reached agreement')
        best = max(dish.get('source_count', 0) for dish in dishes)
        score = self.for_count(best, self.CONSENSUS_STEPS)
        return Signal(
            'web_consensus', weight, score, f'best dish agreed on by {best} domain(s)'
        )

    def _market(self, payload: dict | None) -> Signal:
        weight = self.WEIGHTS['market']
        if not payload or not payload.get('sample_size'):
            return Signal('market', weight, 0.0, 'no market prices were observed')
        sources = payload.get('distinct_sources', 0)
        score = self.for_count(sources, self.MARKET_STEPS)
        return Signal(
            'market',
            weight,
            score,
            f"{payload.get('sample_size')} price(s) from {sources} distinct source(s)",
        )

    def _economy(self, payload: dict | None) -> Signal:
        weight = self.WEIGHTS['economy']
        if not payload:
            return Signal('economy', weight, 0.0, 'no current inflation figure was read')
        age = payload.get('age_in_months', 99)
        score = next(
            (value for limit, value in self.ECONOMY_STEPS if age <= limit), 0.3
        )
        return Signal(
            'economy',
            weight,
            score,
            f"IPCA reference {payload.get('reference_period')}, {age} month(s) old",
        )


class LLMJudge:
    '''LLM-as-a-judge over the draft answer, as an explicit two-step exchange.

    MCP sampling would have let this server call the client's model directly,
    but sampling was deprecated on 2026-07-28 (SEP-2577) and FastMCP 4 no
    longer opens a back-channel for server-initiated requests. So the judging
    turn is handed back out: request_judgement issues the rubric and the
    evidence, the agent evaluates it as a separate constrained turn, and
    submit_judgement returns the verdict to be combined.

    Handing it out is not only a workaround. The ticket makes the judging turn
    visible in the transcript, so a skipped or contradicted judgement is
    something you can see rather than something you have to trust.
    '''

    SYSTEM_PROMPT = (
        'You are a strict evaluator of a cooking-business assistant. You are given '
        'the evidence the assistant collected from its tools and the answer it is '
        'about to give a home cook who will spend real money on it.\n\n'
        'Judge ONLY whether the evidence supports the answer. Do not judge whether '
        'the cooking advice is good. Flag every number, price or claim in the answer '
        'that does not appear in the evidence.\n\n'
        'Reply with JSON only, no prose, no code fence:\n'
        '{"verdict": "supported" | "partially_supported" | "unsupported", '
        '"confidence": <number between 0 and 1, two decimals>, '
        '"unsupported_claims": [<string>], '
        '"issues": [<string>]}'
    )
    MAX_TOKENS = 900

    @classmethod
    def build_prompt(cls, dish: str, answer: str, evidence: dict) -> str:
        return (
            f'DISH: {dish}\n\n'
            f'EVIDENCE COLLECTED BY TOOLS:\n'
            f'{json.dumps(evidence, ensure_ascii=False, indent=2, default=str)[:12000]}\n\n'
            f'ANSWER THE ASSISTANT WANTS TO GIVE:\n{answer}\n\n'
            'Grade the answer against the evidence. JSON only.'
        )

    @staticmethod
    def parse(raw: str) -> dict:
        '''Read the judge reply, surviving fences and surrounding prose.'''
        text = raw.strip()
        if '```' in text:
            parts = [part for part in text.split('```') if '{' in part]
            text = parts[0] if parts else text
            if text.lstrip().startswith('json'):
                text = text.lstrip()[4:]
        start, end = text.find('{'), text.rfind('}')
        if start == -1 or end == -1:
            return {
                'verdict': 'unparsed',
                'confidence': None,
                'issues': ['judge did not return JSON'],
                'raw': raw[:500],
            }
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as error:
            return {
                'verdict': 'unparsed',
                'confidence': None,
                'issues': [f'judge JSON invalid: {error}'],
                'raw': raw[:500],
            }
        parsed.setdefault('verdict', 'unparsed')
        parsed.setdefault('confidence', None)
        parsed.setdefault('unsupported_claims', [])
        parsed.setdefault('issues', [])
        return parsed


class JudgementRegistry:
    """Open judging tickets, so a verdict can be matched to its evidence.

    In Redis with a TTL, not in Postgres: a ticket exists for the length of one
    exchange, and one abandoned mid-conversation should expire rather than
    accumulate. Nothing downstream depends on a ticket after it is closed.
    """

    KEY_PREFIX = 'judgement:'
    TTL_SECONDS = 3600

    def __init__(self, backend):
        self.backend = backend

    def _key(self, ticket_id: str) -> str:
        return f'{self.KEY_PREFIX}{ticket_id}'

    def open(self, ticket_id: str, payload: dict) -> None:
        # Keep only what is needed to combine later; evidence stays with the
        # agent, which already has it.
        self.backend.guard(
            self.backend.client.setex,
            self._key(ticket_id),
            self.TTL_SECONDS,
            json.dumps(payload, ensure_ascii=False),
        )

    def close(self, ticket_id: str) -> dict | None:
        key = self._key(ticket_id)
        raw = self.backend.guard(self.backend.client.get, key)
        if raw is None:
            return None
        self.backend.guard(self.backend.client.delete, key)
        return json.loads(raw)


class ConfidenceReport:
    '''Combines both assessors, conservatively.'''

    @staticmethod
    def combine(
        mode: str,
        deterministic: DeterministicVerdict,
        judge: dict | None,
        judge_error: str | None,
    ) -> dict:
        det_score = deterministic.score
        judge_score = judge.get('confidence') if judge else None
        if isinstance(judge_score, (int, float)):
            judge_score = float(judge_score)
            # A judge that answers 80 meant 0.80: accept it rather than let a
            # scale slip turn into a confidence of eighty.
            if judge_score > 1:
                judge_score = judge_score / 100
            judge_score = max(0.0, min(1.0, judge_score))
        else:
            judge_score = None

        if mode == ConfidenceMode.DETERMINISTIC or judge_score is None:
            final = det_score
            basis = 'deterministic only'
        elif mode == ConfidenceMode.LLM:
            final = judge_score
            basis = 'llm judge only'
        else:
            # The weaker assessor wins: an answer is only as trustworthy as its
            # least convinced reviewer.
            final = min(det_score, judge_score)
            basis = 'hybrid, taking the lower of the two'

        disagreement = (
            judge_score is not None and abs(det_score - judge_score) > 0.25
        )

        badge = ConfidenceBadge.build(
            final, deterministic.signals, deterministic.blocking_issues,
            deterministic.claim,
        )

        return {
            'mode': mode,
            'confidence': round(final, 2),
            'band': band_for(final),
            'basis': basis,
            'display': {
                'badge': badge,
                'instruction': (
                    'Append this line, exactly as written, at the end of the message '
                    'you send her. It is how she can tell a well-supported answer '
                    'from a shaky one at a glance. Do not quote the numeric score.'
                ),
            },
            'deterministic': deterministic.as_dict(),
            'llm_judge': judge if judge else {'ran': False, 'reason': judge_error},
            'assessors_disagree': disagreement,
            'disagreement_note': (
                f'Deterministic scored {det_score:.2f} and the judge {judge_score:.2f}. '
                'Treat the answer as unsettled and say what is uncertain.'
            )
            if disagreement
            else None,
            'blocking_issues': deterministic.blocking_issues,
            'how_to_use': (
                'band "low" means do not present this as a recommendation; say what '
                'is missing and ask. Send the display.badge line at the end of the '
                'message; do not quote the numeric score, which invites false '
                'precision about a heuristic.'
            ),
        }
