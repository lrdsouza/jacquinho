'''Constraint elicitation: the heart of the challenge.

Section 2.2 of the brief is explicit: the agent must not let Dona Maria buy
ingredients and only then discover she cannot cook the dish. That means the
gap between what she said and what the dish needs has to be tracked, and the
missing half has to be asked about before anything is bought.

The catalogue below is the checklist from the brief itself: how many burners,
oven, pressure cooker, air fryer, blender; fresh pasta, bechamel, meat
doneness; power, gas, fridge space, time per batch.
'''

from __future__ import annotations

from dataclasses import dataclass

from .kitchen import CapabilityState, KitchenProfile
from .units import UnitConverter


@dataclass(frozen=True)
class ElicitationItem:
    '''One thing that has to be known before she spends money.'''

    key: str
    category: str
    question: str
    why_it_matters: str
    priority: int  # 1 asked first
    triggers: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            'item': self.key,
            'category': self.category,
            'question': self.question,
            'why_it_matters': self.why_it_matters,
            'priority': self.priority,
        }


class ElicitationCatalogue:
    '''The canonical set of constraints, straight from the brief.'''

    ITEMS = (
        # --- equipment -------------------------------------------------
        ElicitationItem(
            'fogao', 'equipment',
            'Seu fogao tem quantas bocas? E de gas ou eletrico?',
            'Decide quantas panelas andam ao mesmo tempo, logo o tamanho da fornada.',
            1, ('cozinhar', 'refogar', 'fritar', 'ferver')),
        ElicitationItem(
            'forno', 'equipment',
            'Voce tem forno? Funciona bem, assa por igual?',
            'Metade dos pratos gratinados e assados depende disso.',
            1, ('assar', 'gratinar', 'forno')),
        ElicitationItem(
            'panela_de_pressao', 'equipment',
            'Tem panela de pressao? De quantos litros?',
            'Sem ela, carne de panela e feijao dobram de tempo e de gas.',
            2, ('cozimento longo', 'carne dura', 'feijao')),
        ElicitationItem(
            'air_fryer', 'equipment',
            'Tem air fryer? De quantos litros?',
            'Substitui o forno em varios pratos, mas em porcao pequena.',
            2, ('fritar', 'assar', 'crocante')),
        ElicitationItem(
            'liquidificador', 'equipment',
            'Tem liquidificador ou mixer?',
            'Molhos, cremes e massas liquidas dependem dele.',
            # 'molho' and 'creme' alone were too broad: a bechamel is made in a
            # pan, not a blender.
            2, ('liquidificador', 'mixer', 'bater no liquidificador', 'triturar')),
        ElicitationItem(
            'geladeira', 'equipment',
            'Sua geladeira e a de casa mesmo? Cabe quanta marmita pronta?',
            'Limita quantas porcoes ela pode adiantar por vez.',
            2, ('armazenar', 'gelar', 'refrigerar', 'descansar na geladeira')),
        ElicitationItem(
            'freezer', 'equipment',
            'Voce tem freezer separado, ou so o congelador da geladeira?',
            'Sem freezer ela nao congela marmita e produz so para o dia.',
            2, ('congelar', 'congelador', 'freezer')),
        ElicitationItem(
            'batedeira', 'equipment',
            'Voce tem batedeira? De mao ou planetaria?',
            'Massa de bolo, claras em neve e chantilly na mao levam o dobro do tempo.',
            2, ('bater', 'claras em neve', 'chantilly', 'massa de bolo', 'batedeira')),
        ElicitationItem(
            'formas_e_assadeiras', 'equipment',
            'Que formas e assadeiras voce tem? De que tamanho?',
            'Sem a forma certa o prato nao sai, por mais que ela saiba fazer.',
            2, ('forma', 'assadeira', 'refratario', 'travessa', 'forma de bolo')),
        ElicitationItem(
            'microondas', 'equipment',
            'Tem micro-ondas?',
            'Resolve reaquecimento e derretimento sem ocupar boca de fogao.',
            3, ('microondas', 'micro ondas', 'derreter')),
        ElicitationItem(
            'processador', 'equipment',
            'Tem processador de alimentos ou so o liquidificador?',
            'Muda o que da para picar e triturar em escala.',
            3, ('processador', 'picar', 'triturar')),
        ElicitationItem(
            'balanca', 'equipment',
            'Voce tem balanca de cozinha?',
            'Sem pesar, o custo por marmita vira chute e a margem some.',
            2, ('pesar', 'balanca', 'gramas')),
        ElicitationItem(
            'utensilios_basicos', 'equipment',
            'Voce tem peneira, ralador, escumadeira e tabua boa?',
            'Sao os itens que ninguem lembra e que travam a receita na hora.',
            3, ('peneirar', 'peneira', 'ralar', 'ralador', 'escumadeira', 'tabua')),
        ElicitationItem(
            'embalagens', 'equipment',
            'Voce ja tem as embalagens de marmita? Quais e quantas?',
            'Embalagem entra no custo de cada marmita e costuma ficar de fora.',
            1, ('embalar', 'marmita', 'embalagem', 'pote')),
        # --- techniques ------------------------------------------------
        ElicitationItem(
            'massa_fresca', 'techniques',
            'Voce ja fez massa fresca em casa? Se sente segura fazendo?',
            'Separa lasanha e nhoque caseiros dos que precisam de massa pronta.',
            2, ('massa fresca', 'lasanha', 'nhoque', 'macarrao caseiro')),
        ElicitationItem(
            'molho_bechamel', 'techniques',
            'Voce faz molho branco, aquele de manteiga com farinha e leite?',
            'Base de gratinados e escondidinhos; se empelota, o prato cai.',
            2, ('bechamel', 'molho branco', 'gratinado')),
        ElicitationItem(
            'pontos_de_carne', 'techniques',
            'Voce se vira bem com ponto de carne, sabe quando esta no ponto certo?',
            'Corte nobre no ponto errado vira prejuizo direto.',
            2, ('ponto de carne', 'bife', 'grelhar')),
        ElicitationItem(
            'fritura', 'techniques',
            'Voce costuma fritar por imersao? Tem onde descartar o oleo depois?',
            'Fritura muda custo de oleo e a logistica da cozinha.',
            3, ('fritar', 'empanar', 'imersao', 'milanesa', 'oleo quente')),
        ElicitationItem(
            'calda_e_caramelo', 'techniques',
            'Voce se sente segura fazendo calda de acucar, ponto de caramelo?',
            'Caramelo queima em segundos e leva o doce junto.',
            3, ('caramelo', 'calda', 'ponto de bala', 'pudim')),
        ElicitationItem(
            'confeitar', 'techniques',
            'Voce decora doce, faz cobertura e acabamento?',
            'Sobremesa de delivery vende pela aparencia.',
            3, ('confeitar', 'decorar', 'cobertura', 'glace')),
        ElicitationItem(
            'porcionamento', 'techniques',
            'Como voce porciona hoje: no olho ou pesando?',
            'Porcao desigual quebra o CMV que a gente calculou.',
            2, ('porcionar', 'dividir em porcoes', 'montar marmita')),
        # --- operating constraints -------------------------------------
        ElicitationItem(
            'tempo_por_cozinhada', 'constraints',
            'Quantas horas seguidas voce consegue ficar cozinhando por dia?',
            'Define quantas marmitas saem por fornada e se o preco fecha.',
            1, ()),
        ElicitationItem(
            'gas', 'constraints',
            'Voce usa botijao? Quanto tempo costuma durar?',
            'Gas e custo variavel que ninguem lembra de por no preco.',
            2, ()),
        ElicitationItem(
            'energia', 'constraints',
            'Ja teve problema de disjuntor caindo com varios aparelhos ligados?',
            'Air fryer e forno eletrico juntos derrubam instalacao antiga.',
            3, ()),
        ElicitationItem(
            'espaco_geladeira', 'constraints',
            'Quanto espaco de geladeira sobra para o delivery?',
            'Sem espaco, ela nao adianta producao e o custo por marmita sobe.',
            2, ()),
        ElicitationItem(
            'ajuda', 'constraints',
            'Voce cozinha sozinha ou tem ajuda?',
            'Muda quantas marmitas cabem numa cozinhada.',
            3, ()),
    )

    BY_KEY = {item.key: item for item in ITEMS}
    # Connectives match everything and mean nothing. Counting 'de' made
    # 'maquina de macarrao' trigger batedeira, formas and caramelo at once.
    STOP_WORDS = frozenset({'de', 'da', 'do', 'dos', 'das', 'em', 'no', 'na', 'com',
                            'e', 'a', 'o', 'os', 'as', 'um', 'uma', 'para'})

    @classmethod
    def load_custom(cls, db) -> None:
        '''Merge items discovered in conversation into the catalogue.'''
        if db is None:
            return
        for row in db.query('SELECT * FROM elicitation_items'):
            item = ElicitationItem(
                key=row['key'],
                category=row['category'],
                question=row['question'],
                why_it_matters=row['why_it_matters'],
                priority=int(row['priority']),
                triggers=tuple(row['triggers']),
            )
            if item.key not in cls.BY_KEY:
                cls.ITEMS = cls.ITEMS + (item,)
                cls.BY_KEY[item.key] = item

    @classmethod
    def register(cls, db, key, category, question, why_it_matters, priority, triggers):
        '''Add a constraint the catalogue did not know about.'''
        from psycopg.types.json import Json

        normalised = UnitConverter.normalise_text(key).replace(' ', '_')
        if normalised in cls.BY_KEY:
            return cls.BY_KEY[normalised], False

        item = ElicitationItem(
            normalised, category, question, why_it_matters, priority, tuple(triggers)
        )
        cls.ITEMS = cls.ITEMS + (item,)
        cls.BY_KEY[normalised] = item

        if db is not None:
            db.execute(
                '''INSERT INTO elicitation_items
                       (key, category, question, why_it_matters, priority, triggers)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                   ON CONFLICT (key) DO NOTHING''',
                (item.key, category, question, why_it_matters, priority,
                 Json(list(triggers))),
            )
        return item, True

    @classmethod
    def get(cls, key: str) -> ElicitationItem | None:
        return cls.BY_KEY.get(key.strip().lower().replace(' ', '_'))

    @classmethod
    def _significant(cls, text: str) -> set[str]:
        return set(UnitConverter.normalise_text(text).split()) - cls.STOP_WORDS

    @classmethod
    def for_requirement(cls, requirement: str) -> list[ElicitationItem]:
        '''Map a free-text dish requirement onto catalogue items.

        A trigger matches only when ALL of its meaningful words are present, so
        'massa fresca' does not fire on 'massa de lasanha pronta'. Matching too
        eagerly is worse than not matching: it turns an unasked constraint into
        one that looks handled.
        '''
        # A catalogue key handed straight back, as the recipe extractor does.
        # Without this, 'formas_e_assadeiras' fails every text match and lands
        # in the unrecognised bucket, which blocks correctly but asks an ugly
        # question instead of the one already written for it.
        exact = cls.get(requirement)
        if exact is not None:
            return [exact]

        text = UnitConverter.normalise_text(requirement)
        tokens = cls._significant(requirement)
        matched = []
        for item in cls.ITEMS:
            label = item.key.replace('_', ' ')
            if label in text or (text and text in label):
                matched.append(item)
                continue
            for trigger in item.triggers:
                wanted = cls._significant(trigger)
                if wanted and wanted <= tokens:
                    matched.append(item)
                    break
        return matched


class RequirementExtractor:
    """Reads a recipe and says what it demands, from the text and nothing else.

    The point is that the demands come from the recipe in front of them, not
    from what a model remembers about parmegiana. Every detection carries the
    words that triggered it, so the agent can show her why it is asking.
    """

    # marker -> catalogue item. Markers are matched against the normalised
    # recipe text, so accents and case do not matter.
    MARKERS: dict[str, tuple[str, ...]] = {
        'forno': ('forno', 'assar', 'assada', 'assado', 'gratinar', 'gratinado',
                  'preaquec', 'leve ao forno'),
        'fogao': ('panela', 'frigideira', 'refogue', 'refogar', 'ferver', 'fogo baixo',
                  'fogo medio', 'fogo alto', 'leve ao fogo'),
        'panela_de_pressao': ('pressao',),
        'air_fryer': ('air fryer', 'airfryer', 'fritadeira eletrica'),
        'liquidificador': ('liquidificador', 'mixer'),
        'processador': ('processador', 'triturar', 'triture'),
        'batedeira': ('batedeira', 'claras em neve', 'bata as claras', 'chantilly',
                      'bata a manteiga'),
        'formas_e_assadeiras': ('forma', 'assadeira', 'refratario', 'travessa',
                                'untada', 'untar'),
        'microondas': ('microondas', 'micro ondas', 'derreta no micro'),
        'geladeira': ('geladeira', 'gelar', 'refrigerar', 'descanse na geladeira'),
        'freezer': ('freezer', 'congelar', 'congelador'),
        'balanca': ('pesar', 'balanca'),
        'utensilios_basicos': ('peneir', 'ralador', 'ralado', 'ralar', 'escumadeira',
                               'tabua', 'espremedor', 'espremer'),
        'massa_fresca': ('massa fresca', 'sove', 'sovar', 'abra a massa', 'cilindro'),
        'molho_bechamel': ('bechamel', 'molho branco', 'roux'),
        'pontos_de_carne': ('ao ponto', 'mal passado', 'bem passado', 'selar', 'sele a carne'),
        'fritura': ('fritar', 'frite', 'imersao', 'oleo quente', 'empanar', 'empanado',
                    'milanesa'),
        'calda_e_caramelo': ('caramelo', 'calda', 'ponto de bala'),
        'confeitar': ('confeit', 'decorar', 'glace', 'cobertura'),
    }

    @classmethod
    def extract(cls, recipe_text: str) -> dict:
        """Detect the catalogue items a recipe text implies."""
        text = UnitConverter.normalise_text(recipe_text)
        detected: list[dict] = []

        for key, markers in cls.MARKERS.items():
            hits = [marker for marker in markers if marker in text]
            if not hits:
                continue
            item = ElicitationCatalogue.get(key)
            if item is None:
                continue
            detected.append(
                {
                    'item': item.key,
                    'category': item.category,
                    'question': item.question,
                    'why_it_matters': item.why_it_matters,
                    'priority': item.priority,
                    'evidence': hits,
                }
            )

        detected.sort(key=lambda entry: entry['priority'])
        return {
            'detected_requirements': detected,
            'detected_count': len(detected),
            'text_length': len(recipe_text),
            'caveat': (
                'Detected from the recipe wording only. A step written loosely can '
                'hide a requirement, so read the recipe and add anything missing '
                'with the extra_requirements argument rather than assuming this is '
                'the whole list.'
            ),
        }


class ElicitationPlanner:
    '''Tracks what is still unknown and decides what to ask next.'''

    def __init__(self, profile: KitchenProfile):
        self.profile = profile

    def _state(self, item: ElicitationItem) -> str:
        return self.profile.state_of(item.category, item.key)

    def coverage(self) -> dict:
        '''How much of the checklist has actually been answered.'''
        answered, unknown = [], []
        for item in ElicitationCatalogue.ITEMS:
            state = self._state(item)
            entry = {'item': item.key, 'category': item.category, 'state': state}
            if state == CapabilityState.UNKNOWN:
                unknown.append(entry)
            else:
                answered.append(entry)

        total = len(ElicitationCatalogue.ITEMS)
        return {
            'total_items': total,
            'answered': len(answered),
            'unknown': len(unknown),
            'coverage_percent': round(len(answered) / total * 100, 1),
            'answered_items': answered,
            'still_unknown': unknown,
            'ready_to_recommend': not any(
                entry['state'] == CapabilityState.UNKNOWN
                for entry in unknown
                if ElicitationCatalogue.BY_KEY[entry['item']].priority == 1
            ),
        }

    def next_questions(self, limit: int = 3) -> list[dict]:
        '''The most useful unanswered questions, highest priority first.'''
        pending = [
            item
            for item in ElicitationCatalogue.ITEMS
            if self._state(item) == CapabilityState.UNKNOWN
        ]
        pending.sort(key=lambda item: (item.priority, item.key))
        return [item.as_dict() for item in pending[:limit]]

    def gaps_for_dish(self, requirements: list[str]) -> dict:
        '''What this specific dish needs that she has never been asked about.

        This is the guard the brief asks for: it runs before any shopping, so
        an unknown surfaces as a question rather than as a wasted purchase.
        '''
        # Keyed by item, not by requirement: two dish demands can point at the
        # same question, and asking her twice about the air fryer reads as not
        # having listened the first time.
        must_ask: dict[str, dict] = {}
        blockers: dict[str, dict] = {}
        satisfied: dict[str, dict] = {}
        unmapped = []

        for requirement in requirements:
            matches = ElicitationCatalogue.for_requirement(requirement)
            if not matches:
                unmapped.append(requirement)
                continue
            for item in matches:
                state = self._state(item)
                bucket = (
                    must_ask
                    if state == CapabilityState.UNKNOWN
                    else blockers
                    if state == CapabilityState.NO
                    else satisfied
                )
                existing = bucket.get(item.key)
                if existing:
                    existing['triggered_by'].append(requirement)
                else:
                    bucket[item.key] = {
                        **item.as_dict(),
                        'state': state,
                        'triggered_by': [requirement],
                    }

        must_ask = sorted(must_ask.values(), key=lambda entry: entry['priority'])
        blockers = list(blockers.values())
        satisfied = list(satisfied.values())

        # A requirement the catalogue does not recognise is the most dangerous
        # kind: it is something nobody has ever asked her about. Treat it as an
        # open question, never as satisfied.
        unknown_requirements = [
            {
                'requirement': requirement,
                'question': (
                    f'Para este prato precisa de "{requirement}". Voce tem isso, '
                    'ou sabe fazer?'
                ),
                'why_it_matters': (
                    'This is not in the checklist yet, so she has never been asked. '
                    'Ask her, then register it with register_requirement so the next '
                    'dish does not have to rediscover it.'
                ),
            }
            for requirement in unmapped
        ]

        return {
            'requirements_checked': requirements,
            'must_ask_before_buying': must_ask,
            'known_blockers': blockers,
            'already_satisfied': satisfied,
            'unrecognised_requirements': unknown_requirements,
            'safe_to_shop': not must_ask and not blockers and not unknown_requirements,
            'rule': (
                'safe_to_shop false means she must not buy anything for this dish '
                'yet. Ask must_ask_before_buying AND unrecognised_requirements '
                'first, one question at a time, and record each answer with '
                'record_capability. Never treat an unasked requirement as a yes.'
            ),
        }
