'''Dish categories and what the pantry can actually support in each one.

The registry is the mechanism for dish types: five categories ship built in,
and new ones can be added at runtime and persisted, so 'sobremesa' and
'petisco vegetariano' are configuration rather than code.
'''

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from psycopg.types.json import Json

from .pantry import PantryItem, PantryRepository


@dataclass(frozen=True)
class DishCategory:
    '''One kind of dish, described by what the pantry must be able to supply.

    ``required_groups`` is an AND of ORs: the pantry needs at least one match
    in every group. A dessert needs something sweet AND something to build a
    body with, or it is not a dessert she can make.
    '''

    key: str
    label: str
    search_terms: list[str]
    required_groups: list[list[str]]
    built_in: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


class DishCategoryRegistry:
    '''Built-in categories plus any the agent creates during a conversation.'''

    BUILT_INS = (
        DishCategory(
            key='main_course',
            label='Prato principal',
            search_terms=['prato principal', 'marmita', 'almoco'],
            required_groups=[
                ['frango', 'carne', 'patinho', 'acem', 'alcatra', 'bacon', 'ovos'],
                ['arroz', 'feijao', 'macarrao', 'espaguete', 'batata', 'polenta', 'fuba'],
            ],
            built_in=True,
        ),
        DishCategory(
            key='starter',
            label='Entrada',
            search_terms=['entrada', 'aperitivo', 'petisco'],
            required_groups=[
                ['batata', 'queijo', 'bacon', 'ovos', 'mandioca', 'farinha', 'tomate',
                 'couve', 'alcaparras'],
            ],
            built_in=True,
        ),
        DishCategory(
            key='side',
            label='Acompanhamento',
            search_terms=['acompanhamento', 'guarnicao'],
            required_groups=[
                ['arroz', 'feijao', 'batata', 'couve', 'polenta', 'fuba', 'macarrao',
                 'farinha', 'tomate'],
            ],
            built_in=True,
        ),
        DishCategory(
            key='dessert',
            label='Sobremesa',
            search_terms=['sobremesa', 'doce'],
            required_groups=[
                ['acucar', 'chocolate', 'cobertura', 'chantilly', 'ninho', 'canela',
                 'adocante'],
                ['leite', 'ovos', 'farinha', 'manteiga', 'amendoa'],
            ],
            built_in=True,
        ),
        DishCategory(
            key='snack',
            label='Lanche ou salgado',
            search_terms=['salgado', 'lanche', 'bolinho'],
            required_groups=[
                ['farinha', 'batata', 'mandioca', 'polenta', 'fuba'],
                ['frango', 'carne', 'bacon', 'queijo', 'ovos'],
            ],
            built_in=True,
        ),
    )

    def __init__(self, db=None):
        self.db = db
        self.categories: dict[str, DishCategory] = {
            category.key: category for category in self.BUILT_INS
        }
        self._load_custom()

    def _load_custom(self) -> None:
        if self.db is None:
            return
        for row in self.db.query('SELECT * FROM dish_categories'):
            category = DishCategory(
                key=row['key'],
                label=row['label'],
                search_terms=list(row['search_terms']),
                required_groups=[list(group) for group in row['required_groups']],
                built_in=False,
            )
            self.categories[category.key] = category

    def get(self, key: str) -> DishCategory | None:
        return self.categories.get(key.strip().lower())

    def all(self) -> list[DishCategory]:
        return sorted(self.categories.values(), key=lambda item: item.label)

    def register(
        self,
        key: str,
        label: str,
        search_terms: list[str],
        required_groups: list[list[str]],
    ) -> DishCategory:
        '''Add or replace a custom category. Built-ins cannot be overwritten.'''
        normalised = key.strip().lower().replace(' ', '_')
        existing = self.categories.get(normalised)
        if existing and existing.built_in:
            raise ValueError(f'{normalised} is a built-in category and cannot be replaced')
        category = DishCategory(
            key=normalised,
            label=label,
            search_terms=search_terms,
            required_groups=required_groups,
            built_in=False,
        )
        self.categories[normalised] = category
        if self.db is not None:
            self.db.execute(
                '''INSERT INTO dish_categories (key, label, search_terms, required_groups)
                        VALUES (%s, %s, %s::jsonb, %s::jsonb)
                   ON CONFLICT (key) DO UPDATE
                        SET label = EXCLUDED.label,
                            search_terms = EXCLUDED.search_terms,
                            required_groups = EXCLUDED.required_groups''',
                (normalised, label, Json(search_terms), Json(required_groups)),
            )
        return category

    def remove(self, key: str) -> bool:
        category = self.categories.get(key.strip().lower())
        if category is None or category.built_in:
            return False
        del self.categories[category.key]
        if self.db is not None:
            self.db.execute('DELETE FROM dish_categories WHERE key = %s', (category.key,))
        return True


@dataclass
class GroupMatch:
    '''Which pantry items satisfy one required group.'''

    required_any_of: list[str]
    matched: list[PantryItem] = field(default_factory=list)

    @property
    def satisfied(self) -> bool:
        return bool(self.matched)

    def as_dict(self) -> dict:
        return {
            'required_any_of': self.required_any_of,
            'satisfied': self.satisfied,
            'matched_ingredients': [
                {
                    'ingredient': item.name,
                    'stock': f'{item.stock:g} {item.base_unit}',
                    'unit_cost': f'R$ {item.unit_cost:.2f}/{item.base_unit}',
                }
                for item in self.matched
            ],
        }


class DishPlanner:
    '''Reads the pantry ingredient by ingredient against a category.'''

    def __init__(self, pantry: PantryRepository, registry: DishCategoryRegistry):
        self.pantry = pantry
        self.registry = registry

    def _matches(self, tokens: list[str]) -> list[PantryItem]:
        wanted = set(tokens)
        return [
            item
            for item in self.pantry.sorted_items()
            if wanted & set(item.key.split()) and item.stock > 0
        ]

    def assess(self, category: DishCategory) -> dict:
        '''Say whether the pantry can support this category, and on what.'''
        groups = [
            GroupMatch(required_any_of=tokens, matched=self._matches(tokens))
            for tokens in category.required_groups
        ]
        unmet = [group for group in groups if not group.satisfied]
        supporting = sorted(
            {item.name for group in groups for item in group.matched}
        )

        return {
            'category': category.key,
            'label': category.label,
            'supported': not unmet,
            'groups': [group.as_dict() for group in groups],
            'supporting_ingredients': supporting,
            'blocked_because': [
                f'nothing in the pantry matches any of {group.required_any_of}'
                for group in unmet
            ],
        }

    def survey(self) -> dict:
        '''Assess every registered category at once.'''
        assessments = [self.assess(category) for category in self.registry.all()]
        return {
            'categories_assessed': len(assessments),
            'supported': [a['label'] for a in assessments if a['supported']],
            'not_supported': [a['label'] for a in assessments if not a['supported']],
            'detail': assessments,
        }

    def queries_for(self, category: DishCategory, constraints: list[str], limit: int) -> list[str]:
        '''Build several phrasings, so consensus is not one query repeated.'''
        assessment = self.assess(category)
        keywords = [
            self.pantry.find(name).search_keyword
            for name in assessment['supporting_ingredients']
        ]
        suffix = ' '.join(constraints or [])
        queries: list[str] = []

        for term in category.search_terms:
            for keyword in keywords[:limit]:
                queries.append(
                    ' '.join(part for part in ['receita', term, keyword, suffix] if part)
                )

        seen, unique = set(), []
        for query in queries:
            if query not in seen:
                seen.add(query)
                unique.append(query)
        return unique[:limit]

    def pantry_tokens(self) -> set[str]:
        tokens: set[str] = set()
        for item in self.pantry.items.values():
            tokens |= set(item.key.split())
        return tokens
