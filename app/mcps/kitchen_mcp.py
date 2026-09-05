'''MCP surface for the kitchen capability gate.'''

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..domain.elicitation import (
    ElicitationCatalogue,
    ElicitationPlanner,
    RequirementExtractor,
)
from ..domain.catalogue import BlockReason, CatalogueUnavailable, RecipeCatalogue
from ..domain.kitchen import Hedge, KitchenProfile
from ..domain.memory import ConversationStore, RedisBackend
from ..domain.verdict import VerdictAnnouncement
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
        self.catalogue = RecipeCatalogue(db)
        # Read-only here: the kitchen never writes the chat, it only checks a
        # claim about her words against them.
        self.chat = ConversationStore(RedisBackend(settings.redis_url))
        super().__init__(settings)

    def _she_really_said(self, quote: str) -> dict:
        try:
            return self.chat.she_said(quote)
        except Exception:
            # No Redis is a reason to be careful, not a reason to break the
            # consultation. Say so instead of pretending it checked out.
            return {'said': False, 'turns_on_record': 0, 'unavailable': True}

    @staticmethod
    def _session() -> str:
        from .middleware import ConfidenceMiddleware

        return ConfidenceMiddleware.SESSION_FALLBACK

    def _park_dish(
        self, dish: str, blockers: list[str], requirements: list[str], note: str
    ) -> list[str]:
        '''File the dead dish as a conditional block, not as a dead end.

        She may not have an oven today and say she has one next week. A dish
        ruled out only inside the conversation cannot come back when that
        happens; one recorded against the capability that stopped it comes back
        on its own, because that is what the block stored.

        A dish she named herself is usually not in the catalogue yet - nobody
        searched for it, she just said it. It gets a stub row, honest about
        where it came from, so the block has something to hang on.
        '''
        parked: list[str] = []
        try:
            if self.catalogue.get(dish) is None:
                self.catalogue.save(
                    dish=dish, source_url='', source_title='dito por ela na conversa',
                    ingredients=[], equipment=list(requirements), techniques=[],
                    pantry_coverage=0.0,
                    notes='Prato que ela pediu; a receita ainda não foi buscada.',
                )
            recipe = self.catalogue.get(dish)
            already = {b.get('blocking_item') for b in (recipe.active_blocks if recipe else [])}
            for item in blockers:
                if item in already:
                    continue
                self.catalogue.block(
                    dish, BlockReason.MISSING_EQUIPMENT, item,
                    note or f'ela disse que não tem {item}',
                )
                parked.append(item)
        except Exception:
            # The dish is already ruled out in the conversation. Failing to
            # park it costs the comeback later; it must not take the verdict
            # she is owed right now down with it.
            return parked
        return parked

    def _bring_dishes_back(self, item: str, note: str) -> dict | None:
        '''She said yes to something she had said no to. Undo the damage.

        A block that recorded what stopped it can lift itself, and that is the
        whole reason it recorded it. Doing it here rather than asking the agent
        to remember recipes_revisit_blocks is the same choice made everywhere
        else in this server: the answer changes the world, not a reminder.
        '''
        try:
            revived = self.catalogue.lift_for_capability(
                item, note or f'ela disse que tem {item}'
            )
        except Exception:
            return None
        if not revived:
            return None
        dishes = [entry['dish'] for entry in revived]
        announcement = VerdictAnnouncement.for_unblock(dishes, item)
        if self.observer is not None:
            if self.observer.already_announced(self._session(), announcement):
                return None
            self.observer.owe_announcement(self._session(), announcement)
        return {'dishes': dishes, 'recipes': revived, **announcement}

    def _recheck_dish_in_play(self, state: str, note: str = '') -> dict | None:
        '''Re-run the gate after an answer, but only if the answer was a no.'''
        if state != 'confirmed_no':
            return None
        return self._blocked_dish_in_play(park=True, note=note)

    def _blocked_dish_in_play(self, park: bool = False, note: str = '') -> dict | None:
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

        announcement = VerdictAnnouncement.for_block(dish, blockers)
        if self.observer.already_announced(session, announcement):
            # She heard this one. Repeating it is not diligence, it is a reply
            # that ignores where the conversation got to.
            return None
        if park:
            announcement['parked_for_later'] = self._park_dish(
                dish, blockers, requirements, note
            )
            # From here the session owes her this sentence, and the tools that
            # mean 'moving on' are refused until it is paid.
            self.observer.owe_announcement(session, announcement)
        return {
            'dish': dish,
            'verdict': 'rejected',
            'blocked_by': blockers,
            **announcement,
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
            her_words: Annotated[str, Field(description='The words SHE used, copied from her message - not your paraphrase. Checked against the saved conversation. Only omit for state=unknown.')] = '',
            note: Annotated[str, Field(description="Detail in her own words, e.g. 'fogao de 4 bocas, sem forno'.")] = '',
        ) -> dict:
            '''Store what Dona Maria answered about her kitchen.

            Persists across sessions, so she never has to repeat herself.

            A ``confirmed_yes`` or ``confirmed_no`` is a claim about something
            she said, so it has to carry her words, and they are looked up in
            the saved conversation. Anything you have not asked about is
            ``unknown`` - which is a question, never a yes.
            '''
            # This is the failure that costs her money: the agent decided she
            # owned an oven nobody had asked about, the gate approved on that,
            # and it priced an entire lasagna she cannot bake. Silence is not
            # consent, and neither is inference.
            if state in ('confirmed_yes', 'confirmed_no'):
                spoken = self._she_really_said(her_words)
                if len(her_words.split()) < 2:
                    return {
                        'ok': False,
                        'error': 'Um confirmado é uma afirmação sobre o que ELA '
                                 'disse, e precisa das palavras dela.',
                        'next_step': (
                            f'Se ela já respondeu sobre {item!r}, copie a frase dela '
                            'em her_words. Se ela não respondeu, então isto é '
                            "state='unknown' e você ainda tem uma pergunta a fazer."
                        ),
                    }
                hedges = Hedge.found_in(her_words) if state == 'confirmed_yes' else []
                if hedges:
                    return {
                        'ok': False,
                        'error': f'Isso não é um sim: ela disse {her_words!r}.',
                        'hedges': hedges,
                        'next_step': (
                            f'Um {item!r} que ela tem "mas" alguma coisa não passa '
                            'no portão como se estivesse inteiro, e o detalhe fica '
                            'na nota, que o portão não lê. Grave como '
                            "state='unknown' e pergunte a ela o que exatamente "
                            'acontece, para saber se dá para contar com isso neste '
                            'prato. Se ela confirmar que funciona bem, aí sim '
                            'confirmed_yes.'
                        ),
                    }
                if not spoken['said'] and not spoken.get('unavailable'):
                    # Nothing on record is the same problem as the wrong thing
                    # on record: either way the claim answers to nobody.
                    detail = (
                        f"Procurei {her_words!r} nas {spoken['turns_on_record']} "
                        'falas dela e não achei.'
                        if spoken['turns_on_record']
                        else 'Não há nenhuma fala dela guardada para conferir.'
                    )
                    return {
                        'ok': False,
                        'error': f'Não dá para confirmar isso. {detail}',
                        'next_step': (
                            'Guarde a mensagem dela com chat_save_turn '
                            "(role='dona_maria', o texto exatamente como ela "
                            'escreveu) e registre de novo. Se ela nunca falou '
                            f'sobre {item!r}, isto é unknown, e você tem uma '
                            'pergunta a fazer - não uma dedução a registrar.'
                        ),
                    }
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

            entry = self._profile().record(
                category, resolved.key, state,
                f'{note} | ela: “{her_words}”'.strip(' |') if her_words else note,
            )
            item = resolved.key
            planner = self._planner()
            coverage = planner.coverage()
            ruled_out = self._recheck_dish_in_play(state, note)
            back_on = (
                self._bring_dishes_back(item, note)
                if state == 'confirmed_yes' else None
            )
            return {
                'dish_now_ruled_out': ruled_out,
                'dishes_back_on_the_table': back_on,
                'already_answered': [
                    row['item'] for row in coverage['answered_items']
                ],
                'still_unknown': [row['item'] for row in coverage['still_unknown']],
                'ok': True,
                # Honest about how much this was checked: with no saved chat,
                # her words could not be verified against anything.
                'her_words_verified': (
                    self._she_really_said(her_words)['said']
                    if her_words else False
                ),
                'category': category,
                'item': item,
                **entry,
                'next_step': (
                    (
                        back_on['say_now'] if back_on else
                        'She can do this now. Go straight back to the dish you '
                        'were working on: kitchen_check_feasibility with its '
                        'requirements. Everything in already_answered is settled '
                        '- asking about any of it again tells her you were not '
                        'listening.'
                    )
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
        def announce_verdict(
            message_to_her: Annotated[str, Field(description='The sentence you are about to send her, word for word, in Portuguese. Not a summary of it.')],
        ) -> dict:
            '''Deliver the verdict she is owed about her own dish.

            When a dish dies or comes back, she has to hear it. Everything that
            means moving on - searching, costing, pricing, asking the next
            question - is refused until this call goes through, and it only
            goes through if the sentence names her dish and what decided it.

            Send her exactly the text you pass here.
            '''
            if self.observer is None:
                return {'ok': True, 'note': 'nothing pending'}
            session = self._session()
            owed = self.observer.owed_announcement(session)
            if owed is None:
                return {
                    'ok': True,
                    'note': 'Nada pendente. Siga a conversa.',
                }
            check = VerdictAnnouncement.check(
                message_to_her, owed.get('dish', ''), owed.get('items', []),
            )
            if not check['ok']:
                # Refusing here is the point. A sentence that does not name her
                # dish is not an answer about her dish.
                return {
                    'ok': False,
                    'still_owed': owed,
                    'missing_from_your_message': check['missing'],
                    'next_step': (
                        'Reescreva a frase para ela cobrindo o que falta acima, '
                        'com as suas palavras, e chame de novo. Não copie os '
                        'itens da lista para dentro da frase: eles descrevem o '
                        'que ela precisa entender, não como dizer.'
                    ),
                }
            # Drafted, not delivered. The turn boundary sees the message she
            # actually receives; this only proves the sentence exists.
            self.observer.draft_announcement(session)
            return {
                'ok': True,
                'delivered': owed.get('kind'),
                'dish': owed.get('dish'),
                'send_this': message_to_her,
                'next_step': (
                    'Mande exatamente essa frase a ela, nesta resposta. O fim do '
                    'turno confere se ela chegou; se não chegar, o próximo turno '
                    'começa com tudo fechado de novo. Depois dela, e só depois: '
                    'se o prato caiu, ofereça a versão que cabe na cozinha dela; '
                    'se voltou, retome de onde parou.'
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
