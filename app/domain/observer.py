'''Confidence as an observer, not as a step the agent has to remember.

Grading the answer was a tool the agent was told to call before speaking. It
did not: eleven tool calls into a real conversation, zero assessments. An
instruction the model can skip is not a guarantee, and this one was the whole
point of the confidence layer.

So the server watches instead. Every tool call passes through here, the
evidence-bearing ones are remembered per session, and after each of them the
deterministic score is recomputed and written to the log. Nothing depends on
the agent opting in.
'''

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .confidence import (
    BAND_LABEL,
    Claim,
    ConfidenceBadge,
    DeterministicScorer,
    band_for,
)
from .units import UnitConverter

logger = logging.getLogger('jacquinho.confidence')


@dataclass
class EvidenceTrail:
    '''What the tools have established about ONE dish.

    Keyed by dish, not by session. A gate check about lasanha used to overwrite
    the approval for the parmegiana, and the parmegiana would then be refused
    entry to the menu without anyone being told why. Evidence belongs to the
    thing it is evidence about.
    '''

    pantry: dict | None = None
    feasibility: dict | None = None
    cmv: dict | None = None
    consensus: dict | None = None
    market: dict | None = None
    economy: dict | None = None
    claim: str = Claim.PANTRY
    # A claim the agent stated beats one guessed from the last tool call.
    claim_declared: bool = False
    assessed: bool = False
    seen: list[str] = field(default_factory=list)

    def as_bundle(self) -> dict:
        return {
            'pantry': self.pantry,
            'feasibility': self.feasibility,
            'cmv': self.cmv,
            'consensus': self.consensus,
            'market': self.market,
            'economy': self.economy,
        }


class ConfidenceObserver:
    '''Watches tool calls and keeps a running confidence for the session.

    The mapping below is the only coupling: which tool result feeds which
    signal. A tool not listed here is not evidence and changes nothing.
    '''

    FEEDS = {
        'pantry_list_ingredients': 'pantry',
        'pantry_find_ingredient': 'pantry',
        'recipes_check_pantry_coverage': 'pantry',
        'kitchen_check_feasibility': 'feasibility',
        'kitchen_elicitation_gaps': 'feasibility',
        'kitchen_analyse_recipe_requirements': 'feasibility',
        'pricing_calculate_cmv': 'cmv',
        'dishes_discover_dishes': 'consensus',
        'market_research_dish_prices': 'market',
        'economy_current_indicators': 'economy',
    }

    NO_DISH = '(sem prato)'

    def __init__(self):
        # Keyed by (session, dish). Two conversations at once must not share
        # evidence: one client's approved gate is not another's.
        self.trails: dict[tuple[str, str], EvidenceTrail] = {}
        self.scorer = DeterministicScorer()
        # Reading the pantry is about her kitchen, not about one dish - but it
        # is still per session, because sessions may be different people.
        self.pantry: dict[str, dict] = {}
        self.active_dish: dict[str, str] = {}

    def _trail(self, key: tuple[str, str]) -> EvidenceTrail:
        trail = self.trails.get(key)
        if trail is None:
            trail = EvidenceTrail(pantry=self.pantry.get(key[0]))
            self.trails[key] = trail
        return trail

    @staticmethod
    def key_for(dish: str | None) -> str:
        return UnitConverter.normalise_text(dish) if dish else ''

    @staticmethod
    def _normalise(name: str, payload: dict) -> dict:
        '''Shape a tool result into what the scorer expects.'''
        if name == 'kitchen_elicitation_gaps':
            # The gate speaks a different vocabulary from check_feasibility.
            return {
                'verdict': 'approved' if payload.get('safe_to_shop') else 'needs_answers',
                'blockers': payload.get('known_blockers', []),
            }
        if name == 'kitchen_analyse_recipe_requirements':
            gate = payload.get('gate') or {}
            return {
                'verdict': 'approved' if gate.get('safe_to_shop') else 'needs_answers',
                'blockers': gate.get('known_blockers', []),
            }
        if name == 'economy_current_indicators':
            return payload.get('indicator') or {}
        return payload

    @staticmethod
    def _better_pantry(current: dict | None, incoming: dict) -> dict:
        '''A coverage check is more informative than a plain list read.

        Keep whichever says more about what was actually verified, so opening
        the list after checking a recipe does not wipe the specific answer.
        '''
        if current is None:
            return incoming
        if 'coverage_ratio' in current and 'coverage_ratio' not in incoming:
            return current
        return incoming

    def record(
        self, session: str, tool: str, payload: dict | None, dish: str | None = None
    ) -> dict:
        '''Fold a tool result into the trail and report where confidence stands.

        Reports on EVERY call, not only the ones that move the score. A watcher
        that goes quiet while the agent works looks broken, and 'still 0.10
        after four calls' is itself the useful signal: nothing has been
        established yet.
        '''
        # A tool naming a dish moves the conversation to that dish; one that
        # names none carries on with whatever was being discussed.
        named = self.key_for(dish)
        if named:
            self.active_dish[session] = named
        current = self.active_dish.setdefault(session, self.NO_DISH)
        trail = self._trail((session, current))

        slot = self.FEEDS.get(tool)
        moved = False

        if slot is not None and isinstance(payload, dict):
            value = self._normalise(tool, payload)
            if slot == 'pantry':
                # Dish-independent within a session: remember it and give it to
                # every trail belonging to that session.
                value = self._better_pantry(self.pantry.get(session), value)
                self.pantry[session] = value
                for (owner, _), other in self.trails.items():
                    if owner == session:
                        other.pantry = value
            else:
                setattr(trail, slot, value)
            trail.seen.append(tool)
            moved = True

        # The claim in play is the strongest thing the agent has just gone and
        # established. Reading the pantry means it is about to talk about the
        # pantry; pricing means it is about to talk about a price.
        claim = Claim.FROM_TOOL.get(tool)
        if claim is not None and not trail.claim_declared:
            trail.claim = claim

        verdict = self.scorer.score(claim=trail.claim, **trail.as_bundle())
        badge = ConfidenceBadge.build(
            verdict.score, verdict.signals, verdict.blocking_issues, verdict.claim
        )
        report = {
            'session': session,
            'dish': current,
            'after': tool,
            'moved': moved,
            'claim': verdict.claim,
            'score': round(verdict.score, 2),
            # Read the band from the score, never by slicing the badge: the
            # badge is prose and changed shape once already, which quietly
            # filled this column with 'que' and 'de'.
            'band': BAND_LABEL[band_for(verdict.score)],
            'badge': badge,
            'blocking_issues': verdict.blocking_issues,
            'signals': [signal.as_dict() for signal in verdict.signals],
            'evidence_so_far': trail.seen,
        }
        logger.info('%s', json.dumps(report, ensure_ascii=False))
        return report

    def gate_approved(self, session: str, dish: str | None = None) -> bool:
        '''Has the viability gate passed for this dish, in this session?'''
        name = self.key_for(dish) or self.active_dish.get(session, self.NO_DISH)
        trail = self.trails.get((session, name))
        return bool(trail and (trail.feasibility or {}).get('verdict') == 'approved')

    def cmv_ready(self, session: str, dish: str | None = None) -> bool:
        '''Was a complete CMV calculated for this dish?'''
        name = self.key_for(dish) or self.active_dish.get(session, self.NO_DISH)
        trail = self.trails.get((session, name))
        return bool(trail and (trail.cmv or {}).get('calculation_complete'))

    def assessed(self, session: str, dish: str | None = None) -> bool:
        '''Has a confidence assessment been made for this dish?'''
        name = self.key_for(dish) or self.active_dish.get(session, self.NO_DISH)
        trail = self.trails.get((session, name))
        return bool(trail and trail.assessed)

    def declare_claim(self, session: str, dish: str | None, claim: str) -> None:
        '''The agent saying what it is about to assert beats guessing from tools.'''
        name = self.key_for(dish) or self.active_dish.get(session, self.NO_DISH)
        trail = self._trail((session, name))
        trail.claim = claim
        trail.claim_declared = True
        trail.assessed = True

    def state_of(self, session: str, dish: str | None = None) -> dict:
        '''A compact reminder of where the conversation is.

        Attached to every tool result. The agent kept losing the thread and
        going back to re-offer what she had already chosen - not from bad
        intent, but because nothing in front of it said where things stood.
        Telling it once, in a prompt it may not re-read, is not the same as
        telling it on every single call.
        '''
        name = self.key_for(dish) or self.active_dish.get(session, self.NO_DISH)
        trail = self.trails.get((session, name))
        if trail is None:
            return {
                'dish_in_play': None,
                'next_action': 'Nada em andamento. Se ela já pediu sugestões, '
                               'chame dishes_survey_categories.',
            }

        gate = (trail.feasibility or {}).get('verdict')
        if gate != 'approved':
            nxt = ('kitchen_check_feasibility com o prato nomeado, ou '
                   'kitchen_analyse_recipe_requirements com o texto da receita')
        elif trail.cmv is None:
            nxt = 'pricing_calculate_cmv'
        elif trail.market is None:
            nxt = 'market_research_dish_prices'
        elif not trail.assessed:
            nxt = 'pricing_price_scenarios, depois confidence_assess_answer'
        else:
            nxt = 'mostre os cenários e deixe ela escolher; então menu_add_dish'

        return {
            'dish_in_play': None if name == self.NO_DISH else name,
            'gate': gate or 'não rodou',
            'cmv_calculado': trail.cmv is not None,
            'mercado_pesquisado': trail.market is not None,
            'avaliado': trail.assessed,
            'next_action': nxt,
            'reminder': (
                'Continue daqui. Não volte a perguntar o que ela já respondeu, '
                'e não reofereça procurar se ela já mandou procurar.'
            ),
        }

    def current(self, session: str, dish: str | None = None) -> dict | None:
        name = self.key_for(dish) or self.active_dish.get(session, self.NO_DISH)
        trail = self.trails.get((session, name))
        if trail is None:
            return None
        verdict = self.scorer.score(claim=trail.claim, **trail.as_bundle())
        return {
            'dish': name,
            'claim': verdict.claim,
            'score': round(verdict.score, 2),
            'badge': ConfidenceBadge.build(
                verdict.score, verdict.signals, verdict.blocking_issues, verdict.claim
            ),
            'blocking_issues': verdict.blocking_issues,
            'signals': [signal.as_dict() for signal in verdict.signals],
            'evidence_so_far': trail.seen,
        }

    def reset(self, session: str | None = None, dish: str | None = None) -> None:
        if session is None:
            self.trails.clear()
            self.pantry.clear()
            self.active_dish.clear()
        elif dish is None:
            for key in [k for k in self.trails if k[0] == session]:
                self.trails.pop(key)
        else:
            self.trails.pop((session, self.key_for(dish)), None)
