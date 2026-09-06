'''MCP surface for the confidence layer.'''

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from psycopg.types.json import Json

from ..domain.database import DatabaseUnavailable
from ..domain.memory import RedisBackend
from ..domain.audit import MessageAudit
from ..domain.pacing import check as pacing_check
from ..domain.confidence import (
    Claim,
    ConfidenceBadge,
    ConfidenceMode,
    ConfidenceReport,
    DeterministicScorer,
    DeterministicVerdict,
    JudgementRegistry,
    LLMJudge,
    Signal,
)
from .base import BaseMCP
from .middleware import ConfidenceMiddleware


class EvidenceBundle(BaseModel):
    '''The tool payloads backing an answer, pasted back verbatim.

    Every field is the untouched output of the tool named in its description.
    Leaving one out is itself evidence: the scorer counts a missing step as a
    step that never happened.
    '''

    pantry: Annotated[dict | None, Field(description='Output of pantry_list_ingredients or recipes_check_pantry_coverage.')] = None
    feasibility: Annotated[dict | None, Field(description='Output of kitchen_check_feasibility.')] = None
    cmv: Annotated[dict | None, Field(description='Output of pricing_calculate_cmv.')] = None
    consensus: Annotated[dict | None, Field(description='Output of dishes_discover_dishes.')] = None
    market: Annotated[dict | None, Field(description='Output of market_research_dish_prices.')] = None
    economy: Annotated[dict | None, Field(description="The 'indicator' block from economy_current_indicators.")] = None


class ConfidenceMCP(BaseMCP):
    '''Grades how well the collected evidence supports what is about to be said.'''

    name = 'confidence'
    instructions = (
        'Run assess_answer before telling Dona Maria anything she would act on: a '
        'dish recommendation, a cost, a price. In hybrid or llm mode it hands back '
        'a judging ticket; evaluate it as its own turn, answering only against the '
        'evidence, then call submit_judgement with that ticket. An answer whose '
        'band is low, or that carries blocking_issues, is not ready to send. '
        'The badge never leaves this server: it is telemetry, it goes to the log '
        'and to answer_assessments, and she never sees it. What she gets is '
        'caveat_for_her - the reservation as a sentence in her own language, '
        'said inside the message. Also read message_pacing: a draft that settles '
        'four subjects at once is four messages, not one.'
    )

    def __init__(self, settings, db, observer=None):
        self.db = db
        self.observer = observer
        super().__init__(settings)

    def _complete(self, given: dict) -> dict:
        '''Fill the gaps in what the agent handed over from what was observed.

        The agent assembles the evidence bundle by hand and leaves things out -
        a real run produced a badge saying 'sem preço de mercado' minutes after
        the market had been researched. The observer already holds the whole
        trail; what the agent passes wins, and the rest is filled in rather than
        counted as absent.
        '''
        if self.observer is None:
            return given
        trail = self.observer.trails.get(
            (ConfidenceMiddleware.SESSION_FALLBACK, self.observer.active_dish.get(
                ConfidenceMiddleware.SESSION_FALLBACK, self.observer.NO_DISH))
        )
        if trail is None:
            return given
        observed = {
            'pantry': trail.pantry, 'feasibility': trail.feasibility,
            'cmv': trail.cmv, 'consensus': trail.consensus,
            'market': trail.market, 'economy': trail.economy,
        }
        return {
            slot: given.get(slot) if given.get(slot) else observed.get(slot)
            for slot in observed
        }

    def _persist(self, dish: str, draft: str, report: dict) -> None:
        '''Keep the assessment, so a weak answer can be found after the fact.'''
        judge = report.get('llm_judge') or {}
        judge_score = judge.get('confidence') if isinstance(judge, dict) else None
        try:
            self.db.execute(
                '''INSERT INTO answer_assessments
                       (dish, draft_answer, mode, claim, deterministic_score,
                        judge_score, final_score, band, badge, blocking_issues,
                        signals)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)''',
                (dish, draft, report['mode'],
                 report['deterministic'].get('claim', 'price'),
                 report['deterministic']['score'],
                 judge_score if isinstance(judge_score, (int, float)) else None,
                 report['confidence'], report['band'],
                 report['telemetry']['badge'],
                 Json(report['blocking_issues']),
                 Json(report['deterministic']['signals'])),
            )
        except DatabaseUnavailable:
            # Losing the audit trail must never lose the assessment itself.
            pass

    @staticmethod
    def _for_the_agent(report: dict) -> dict:
        """The report minus the one field she must never read.

        The badge is telemetry, and it stayed in the payload with an instruction
        to paste it at the end of her message. The agent obeyed - which is what
        agents do with instructions in tool results - and she read
        '〔preço: confiança média · sem preço de mercado〕' under a message about
        her own lasagna. Removing the instruction was not enough twice; removing
        the field is.
        """
        return {key: value for key, value in report.items() if key != 'telemetry'}

    def _registry(self) -> JudgementRegistry:
        # Redis: a ticket lives for one exchange and is worthless after it.
        return JudgementRegistry(RedisBackend(self.settings.redis_url))

    @staticmethod
    def _ticket_id(dish: str, answer: str) -> str:
        digest = hashlib.sha256(f'{dish}|{answer}'.encode('utf-8')).hexdigest()
        return digest[:12]

    def register(self) -> None:
        @self.mcp.tool
        def assess_answer(
            dish: Annotated[str, Field(description='Dish the answer is about.')],
            draft_answer: Annotated[str, Field(description='Exactly what you are about to say to her.')],
            evidence: Annotated[EvidenceBundle, Field(description='The tool outputs backing it.')],
            claim: Annotated[Literal['pantry_fact', 'dish_suggestion', 'feasibility', 'cost', 'price'], Field(description='What the message actually asserts. Only the evidence that claim rests on is scored.')] = 'price',
            mode: Annotated[Literal['hybrid', 'deterministic', 'llm'], Field(description='hybrid runs both assessors and keeps the lower score.')] = 'hybrid',
        ) -> dict:
            '''Score how far the evidence actually supports the draft answer.

            Confidence is relative to what the message asserts. A pantry fact
            rests on the pantry and nothing else; a price rests on the gate, the
            CMV, the market and inflation. Set ``claim`` to what you are about
            to say, or the score answers a question you did not ask.

            The deterministic pass scores only the evidence that claim needs,
            and returns immediately.

            ``message_pacing`` comes back in every mode and is not part of the
            score: it says whether the draft is one message or four stapled
            together. A grounded wall of text is still a wall, and the question
            buried in the middle of it is a question she never answers.

            In hybrid or llm mode the reply also carries a judging ticket. Run
            it as a separate turn, judging the draft against the evidence and
            nothing else, then call submit_judgement. In hybrid the final score
            is the lower of the two assessors.
            '''
            payload = self._complete(evidence.model_dump())
            verdict = DeterministicScorer().score(
                feasibility=payload['feasibility'],
                cmv=payload['cmv'],
                consensus=payload['consensus'],
                market=payload['market'],
                economy=payload['economy'],
                pantry=payload.get('pantry'),
                claim=claim,
            )

            # How much the draft is carrying is a property of the draft, not of
            # the evidence, so it is checked in every mode and never lowers the
            # score: a message can be perfectly grounded and still be a wall.
            pacing = pacing_check(draft_answer)

            if mode == ConfidenceMode.DETERMINISTIC:
                report = ConfidenceReport.combine(mode, verdict, None, None)
                self._persist(dish, draft_answer, report)
                return {**self._for_the_agent(report), 'message_pacing': pacing}

            ticket_id = self._ticket_id(dish, draft_answer)
            self._registry().open(
                ticket_id,
                {
                    'mode': mode,
                    'dish': dish,
                    'draft_answer': draft_answer,
                    'deterministic': {
                        'score': verdict.score,
                        'signals': [signal.as_dict() for signal in verdict.signals],
                        'blocking_issues': verdict.blocking_issues,
                    },
                },
            )

            return {
                'status': 'awaiting_judgement',
                'mode': mode,
                'deterministic': verdict.as_dict(),
                'message_pacing': pacing,
                'caveat_for_her': ConfidenceBadge.caveats_for_her(
                    verdict.signals, verdict.blocking_issues
                ),
                'judging_ticket': {
                    'ticket': ticket_id,
                    'system_prompt': LLMJudge.SYSTEM_PROMPT,
                    'prompt': LLMJudge.build_prompt(dish, draft_answer, payload),
                },
                'next_step': (
                    'Answer the judging prompt in its own turn, as a strict evaluator '
                    'and not as the consultant. Judge only whether the evidence '
                    'supports the draft. Then call submit_judgement with the ticket '
                    'and your verdict. Do not send anything to Dona Maria until you '
                    'have the combined report.'
                ),
                'why_two_steps': (
                    'MCP sampling, which would have let this server call the model '
                    'directly, was deprecated on 2026-07-28 (SEP-2577). Handing the '
                    'judging turn back also puts it in the transcript, where a '
                    'skipped judgement is visible.'
                ),
            }

        @self.mcp.tool
        def submit_judgement(
            ticket: Annotated[str, Field(description='ticket value from assess_answer.')],
            verdict: Annotated[Literal['supported', 'partially_supported', 'unsupported'], Field(description='Does the evidence support the draft?')],
            confidence: Annotated[float, Field(ge=0, le=1, description='How far the evidence supports the answer, from 0 to 1.')],
            unsupported_claims: Annotated[list[str], Field(description='Claims in the draft that no evidence backs.')] = [],
            issues: Annotated[list[str], Field(description='Other problems found.')] = [],
        ) -> dict:
            '''Return a judging verdict and get the combined confidence report.

            In hybrid mode the final score is the lower of the deterministic
            score and yours: an answer is only as trustworthy as its least
            convinced reviewer.
            '''
            stored = self._registry().close(ticket)
            if stored is None:
                return {
                    'error': f'unknown or already-used ticket {ticket!r}',
                    'next_step': 'Call assess_answer again to open a fresh ticket.',
                }

            deterministic = DeterministicVerdict(
                score=stored['deterministic']['score'],
                signals=[
                    Signal(
                        name=entry['signal'],
                        weight=entry['weight'],
                        score=entry['score'],
                        reason=entry['reason'],
                    )
                    for entry in stored['deterministic']['signals']
                ],
                blocking_issues=stored['deterministic']['blocking_issues'],
            )
            judgement = {
                'verdict': verdict,
                'confidence': confidence,
                'unsupported_claims': unsupported_claims,
                'issues': issues,
            }
            report = ConfidenceReport.combine(
                stored['mode'], deterministic, judgement, None
            )
            self._persist(stored['dish'], '', report)
            return {
                **self._for_the_agent(report),
                'message_pacing': pacing_check(stored.get('draft_answer') or ''),
            }

        @self.mcp.tool
        def recent_assessments(
            limit: Annotated[int, Field(ge=1, le=50, description='How many to return.')] = 10,
        ) -> dict:
            """Every answer that was graded, most recent first.

            The audit trail behind the badges: what was about to be said, how
            strongly the evidence backed it, and what was blocking. Readable
            without replaying the conversation.
            """
            try:
                rows = self.db.query(
                    """SELECT dish, band, badge, final_score, deterministic_score,
                              judge_score, blocking_issues, assessed_at
                         FROM answer_assessments
                        ORDER BY assessed_at DESC LIMIT %s""",
                    (limit,),
                )
            except DatabaseUnavailable as error:
                return {'available': False, 'error': str(error)}
            return {
                'available': True,
                'count': len(rows),
                'assessments': [
                    {
                        'dish': r['dish'],
                        'band': r['band'],
                        'badge': r['badge'],
                        'final_score': float(r['final_score']),
                        'deterministic_score': float(r['deterministic_score']),
                        'judge_score': float(r['judge_score']) if r['judge_score'] is not None else None,
                        'blocking_issues': list(r['blocking_issues']),
                        'at': r['assessed_at'].isoformat(timespec='seconds'),
                    }
                    for r in rows
                ],
            }

        @self.mcp.tool
        def audit_figures(
            message: Annotated[str, Field(description='Exactly what you are about to send her.')],
            evidence: Annotated[EvidenceBundle, Field(description='The tool outputs behind it.')],
        ) -> dict:
            """Check every number in the message against what the tools produced.

            The observer scores the evidence and never reads the sentence; the
            judge reads it but has to be invoked. This sits between them and
            needs neither: a figure in the message is either one a tool returned
            or it is not, and that is decidable.

            It does not catch every kind of wrong. It catches the one this
            system exists to prevent - a price nobody calculated.
            """
            return MessageAudit.check(message, evidence.model_dump())
