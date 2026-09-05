'''MCP surface for the kitchen capability gate.'''

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..domain.elicitation import (
    ElicitationCatalogue,
    ElicitationPlanner,
    RequirementExtractor,
)
from ..domain.kitchen import KitchenProfile
from .base import BaseMCP


class KitchenMCP(BaseMCP):
    '''Guards against Dona Maria buying for a dish she cannot cook.'''

    name = 'kitchen'
    instructions = (
        'Constraint elicitation and the capability gate: the heart of this job. '
        'She must never buy ingredients and only then find out she cannot cook the '
        'dish. Before any shopping, run elicitation_gaps for the dish; if '
        'safe_to_shop is false, ask what it lists, one question at a time, and '
        'store every answer with record_capability. next_questions gives you the '
        'checklist to work through in the background of the conversation. Silence '
        "is not consent: 'unknown' is a question, never a yes."
    )

    def __init__(self, settings, db, observer=None):
        self.db = db
        self.observer = observer
        super().__init__(settings)

    def _recheck_dish_in_play(self, state: str) -> dict | None:
        '''Re-run the gate after an answer, but only if the answer was a no.'''
        if state != 'confirmed_no':
            return None
        return self._blocked_dish_in_play()

    def _blocked_dish_in_play(self) -> dict | None:
        '''Re-run the gate for the dish under discussion, right here.

        Telling the agent to go and re-check was not enough: it recorded the
        answer that ruled the dish out and then carried on as if nothing had
        happened. So the recording does the re-check itself and hands back the
        verdict as data, not as advice.
        '''
        if self.observer is None:
            return None
        from .middleware import ConfidenceMiddleware

        session = ConfidenceMiddleware.SESSION_FALLBACK
        dish = self.observer.dish_in_play(session)
        requirements = self.observer.requirements_of(session)
        if not dish or not requirements:
            return None

        gaps = self._planner().gaps_for_dish(requirements)
        blockers = [entry['item'] for entry in gaps['known_blockers']]
        if not blockers:
            return None
        return {
            'dish': dish,
            'verdict': 'rejected',
            'blocked_by': blockers,
            'say_now': (
                f'A cozinha dela não faz {dish}: falta {blockers}. Diga isso a ela '
                'com todas as letras AGORA, e ofereça uma versão do prato DELA que '
                'caiba no que ela tem. Não mude de assunto sem fechar este.'
            ),
        }

    def _profile(self) -> KitchenProfile:
        return KitchenProfile(self.db)

    def _planner(self) -> ElicitationPlanner:
        ElicitationCatalogue.load_custom(self.db)
        return ElicitationPlanner(self._profile())

    def register(self) -> None:
        @self.mcp.tool
        def check_feasibility(
            equipment_needed: Annotated[list[str], Field(description="e.g. ['forno', 'liquidificador'].")],
            techniques_needed: Annotated[list[str], Field(description="e.g. ['massa fresca', 'ponto de carne'].")],
            dish: Annotated[str, Field(description='The dish this gate is about. Name it: the approval is recorded against this dish and nothing else.')] = '',
        ) -> dict:
            '''Check whether she can actually produce the dish, before costing it.

            Mandatory gate. Anything never asked about comes back under
            ``ask_before_proceeding``.

            Always pass ``dish``. The approval attaches to the dish you name, so
            that asking about a second dish later cannot quietly un-approve the
            first one - and so that pricing and the menu can tell them apart.
            '''
            return self._profile().check(equipment_needed, techniques_needed)

        @self.mcp.tool
        def record_capability(
            category: Annotated[Literal['equipment', 'techniques', 'constraints'], Field(description='Where to file it.')],
            item: Annotated[str, Field(description="e.g. 'forno', 'air fryer', 'massa fresca'.")],
            state: Annotated[Literal['confirmed_yes', 'confirmed_no', 'unknown'], Field(description='What she answered.')],
            note: Annotated[str, Field(description="Detail in her own words, e.g. 'fogao de 4 bocas, sem forno'.")] = '',
        ) -> dict:
            '''Store what Dona Maria answered about her kitchen.

            Persists across sessions, so she never has to repeat herself.
            '''
            # Free text here is how the gate gets bypassed: 'forno de 45l' is
            # stored, check_feasibility('forno') finds nothing, and reading the
            # profile becomes a better answer than running the gate. Resolve to
            # a catalogue key or refuse.
            ElicitationCatalogue.load_custom(self.db)
            resolved = ElicitationCatalogue.get(item)
            if resolved is None:
                matches = ElicitationCatalogue.for_requirement(item)
                resolved = matches[0] if len(matches) == 1 else None
            if resolved is None:
                return {
                    'ok': False,
                    'error': f'{item!r} is not a checklist item, so the gate would '
                             'never find it again.',
                    'did_you_mean': [
                        entry.key
                        for entry in ElicitationCatalogue.ITEMS
                        if entry.category == category
                    ],
                    'next_step': (
                        'Record it under the checklist key that covers it - the '
                        "detail she gave goes in `note`, so 'forno de 45 litros' "
                        "becomes item='forno', note='forno de 45 litros'. If nothing "
                        'covers it, call register_requirement first.'
                    ),
                }
            if resolved.category != category:
                category = resolved.category

            entry = self._profile().record(category, resolved.key, state, note)
            item = resolved.key
            planner = self._planner()
            coverage = planner.coverage()
            ruled_out = self._recheck_dish_in_play(state)
            return {
                'dish_now_ruled_out': ruled_out,
                'already_answered': [
                    row['item'] for row in coverage['answered_items']
                ],
                'still_unknown': [row['item'] for row in coverage['still_unknown']],
                'ok': True,
                'category': category,
                'item': item,
                **entry,
                'next_step': (
                    f"She can do this now. Call recipes_revisit_blocks('{item}'), "
                    'then go straight back to the dish you were working on: '
                    'kitchen_check_feasibility with its requirements. Everything '
                    'in already_answered is settled - asking about any of it again '
                    'tells her you were not listening.'
                    if state == 'confirmed_yes'
                    else (
                        # A 'no' that leaves the dish unresolved is the worst
                        # outcome: she told you the thing that rules it out and
                        # heard nothing back about the dish she asked for.
                        f"She cannot do this. If a dish was on the table, close "
                        f"it now: run kitchen_check_feasibility for it, tell her "
                        f"plainly that it is out because of '{item}', and offer a "
                        'version of HER dish that fits the kitchen she has - '
                        'lasanha de panela instead of lasanha ao forno - before '
                        'suggesting anything else. Do not go back to asking what '
                        'she wants: she already told you.'
                        if state == 'confirmed_no'
                        else 'Recorded.'
                    )
                ),
            }

        @self.mcp.tool
        def read_kitchen_profile() -> dict:
            '''Return everything known about equipment, techniques and constraints.'''
            profile = self._profile()
            recorded = profile.recorded_count()
            return {
                'profile': profile.data,
                'recorded_items': recorded,
                'hint': (
                    'Empty means nothing has been asked yet, not that she lacks it.'
                    if recorded == 0
                    else 'Only ask about what is not already here.'
                ),
            }

        @self.mcp.tool
        def next_questions(
            limit: Annotated[int, Field(ge=1, le=6, description='How many to return.')] = 3,
        ) -> dict:
            """The most useful things you still have not asked her.

            Works through the checklist the brief names: burners, oven, pressure
            cooker, air fryer, blender; fresh pasta, bechamel, meat doneness;
            power, gas, fridge space, time per batch. Priority 1 items gate any
            recommendation.
            """
            planner = self._planner()
            coverage = planner.coverage()
            # Asking for the next question is the moment the agent is about to
            # move on. If the dish on the table is already dead, say so instead.
            ruled_out = self._blocked_dish_in_play()
            return {
                'dish_now_ruled_out': ruled_out,
                'questions': planner.next_questions(limit),
                'coverage_percent': coverage['coverage_percent'],
                'ready_to_recommend': coverage['ready_to_recommend'],
                'instruction': (
                    'Ask ONE of these at a time, woven into the conversation. Do not '
                    'read the list out as a form.'
                ),
            }

        @self.mcp.tool
        def elicitation_coverage() -> dict:
            """How much of the constraint checklist she has actually answered."""
            return self._planner().coverage()

        @self.mcp.tool
        def elicitation_gaps(
            requirements: Annotated[list[str], Field(description="What the dish demands, in plain words, e.g. ['assar no forno', 'molho branco'].")],
            dish: Annotated[str, Field(description='The dish these demands belong to. Name it, so the verdict attaches to the right dish.')] = '',
        ) -> dict:
            """Check a dish's demands against what she has told you, before buying.

            This is the guard from section 2.2 of the brief. safe_to_shop false
            means nothing gets bought for this dish yet: ask what it lists first.
            """
            return self._planner().gaps_for_dish(requirements)

        @self.mcp.tool
        def elicitation_catalogue() -> dict:
            """The full constraint checklist, with why each item matters."""
            return {
                'items': [item.as_dict() for item in ElicitationCatalogue.ITEMS],
                'categories': list(KitchenProfile.CATEGORIES),
            }

        @self.mcp.tool
        def analyse_recipe_requirements(
            dish: Annotated[str, Field(description='Dish name.')],
            recipe_text: Annotated[str, Field(description='The recipe as written: ingredients and steps, pasted in full.')],
            extra_requirements: Annotated[list[str], Field(description='Anything you can see the recipe needs that the text does not spell out.')] = [],
        ) -> dict:
            """Work out what a recipe demands, then check it against her answers.

            Reads the recipe wording for equipment and technique markers, so the
            demands come from the recipe in front of you rather than from memory
            of how the dish is usually made. Then it runs the same gate as
            elicitation_gaps: anything she has never been asked about comes back
            as a question, and she buys nothing until it is answered.
            """
            planner = self._planner()
            found = RequirementExtractor.extract(recipe_text)
            requirements = [entry['item'] for entry in found['detected_requirements']]
            gaps = planner.gaps_for_dish(requirements + list(extra_requirements))
            return {
                'dish': dish,
                'from_the_recipe': found,
                'gate': gaps,
                'next_step': (
                    'Nothing to ask: she has already answered everything this recipe '
                    'needs.'
                    if gaps['safe_to_shop']
                    else 'Ask what the gate lists, one question at a time. Show her '
                    'the evidence words so she knows why you are asking.'
                ),
            }

        @self.mcp.tool
        def register_requirement(
            key: Annotated[str, Field(description="Short id, e.g. 'maquina_de_macarrao'.")],
            category: Annotated[Literal['equipment', 'techniques', 'constraints'], Field(description='What kind of constraint it is.')],
            question: Annotated[str, Field(description='The question to ask her, in Portuguese, in her language.')],
            why_it_matters: Annotated[str, Field(description='Why this can stop the dish.')],
            priority: Annotated[int, Field(ge=1, le=3, description='1 gates any recommendation, 3 is nice to know.')] = 2,
            triggers: Annotated[list[str], Field(description='Recipe words that should raise this in future.')] = [],
        ) -> dict:
            """Add a constraint the checklist did not have.

            Use it whenever a recipe needs something nobody has asked her about,
            so the next dish does not have to rediscover it.
            """
            ElicitationCatalogue.load_custom(self.db)
            item, created = ElicitationCatalogue.register(
                self.db,
                key, category, question, why_it_matters, priority, triggers,
            )
            return {
                'created': created,
                'item': item.as_dict(),
                'note': None if created else 'already in the checklist',
            }
