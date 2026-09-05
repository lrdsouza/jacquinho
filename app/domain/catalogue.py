'''Durable recipe catalogue, in Postgres.

Recipes are not conversation state. A recipe carries what it demands of her
kitchen, and a block on it is a fact about a relationship: this dish is out
*because* of that capability. When the capability changes - she buys the stove
she did not have - the block has to lift itself and the dish has to come back.

That relationship is what Postgres is for. Redis holds the conversation; this
holds what the conversation decided.
'''

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from .database import Database, DatabaseUnavailable
from .units import UnitConverter

# Kept as an alias so the MCP layer reads in its own vocabulary.
CatalogueUnavailable = DatabaseUnavailable


class BlockReason:
    '''Why a dish is off the table, and whether that can change.'''

    DISLIKED = 'disliked'
    IMPEDIMENT = 'impediment'
    MISSING_EQUIPMENT = 'missing_equipment'
    MISSING_TECHNIQUE = 'missing_technique'
    OVER_BUDGET = 'over_budget'
    TOO_EXPENSIVE = 'too_expensive'

    ALL = (
        DISLIKED, IMPEDIMENT, MISSING_EQUIPMENT,
        MISSING_TECHNIQUE, OVER_BUDGET, TOO_EXPENSIVE,
    )

    # A block that a change in her kitchen or her budget can lift. Taste is not
    # one of them: she is allowed to simply not want to cook something, and
    # that is not a problem waiting to be solved.
    CONDITIONAL = frozenset(
        {MISSING_EQUIPMENT, MISSING_TECHNIQUE, OVER_BUDGET, TOO_EXPENSIVE}
    )

    @classmethod
    def is_conditional(cls, reason: str) -> bool:
        return reason in cls.CONDITIONAL


@dataclass(frozen=True)
class Recipe:
    slug: str
    dish: str
    source_url: str
    source_title: str
    ingredients: list[str]
    pantry_coverage: float
    notes: str
    accepted: bool
    equipment: list[str]
    techniques: list[str]
    active_blocks: list[dict]

    @property
    def blocked(self) -> bool:
        return bool(self.active_blocks)

    def as_dict(self) -> dict:
        return {
            'dish': self.dish,
            'slug': self.slug,
            'source_url': self.source_url,
            'source_title': self.source_title,
            'ingredients': self.ingredients,
            'required_equipment': self.equipment,
            'required_techniques': self.techniques,
            'pantry_coverage': float(self.pantry_coverage or 0),
            'notes': self.notes,
            'accepted': self.accepted,
            'blocked': self.blocked,
            'active_blocks': self.active_blocks,
        }


class RecipeCatalogue:
    '''Every recipe ever opened, with its demands and its block history.'''

    def __init__(self, db: Database):
        self.db = db

    def _connect(self):
        return self.db.connect()

    def ensure_schema(self) -> None:
        self.db.ensure_schema()

    @staticmethod
    def _slug(dish: str) -> str:
        return UnitConverter.normalise_text(dish).replace(' ', '-')

    # ------------------------------------------------------------- writing

    def save(
        self,
        dish: str,
        source_url: str,
        source_title: str,
        ingredients: list[str],
        equipment: list[str],
        techniques: list[str],
        pantry_coverage: float,
        notes: str,
    ) -> dict:
        '''Insert or refresh a recipe and the demands it makes.'''
        self.ensure_schema()
        slug = self._slug(dish)
        with self._connect() as conn:
            conn.execute(
                '''INSERT INTO recipes
                       (slug, dish, source_url, source_title, ingredients,
                        pantry_coverage, notes)
                   VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                   ON CONFLICT (slug) DO UPDATE SET
                       dish = EXCLUDED.dish,
                       source_url = EXCLUDED.source_url,
                       source_title = EXCLUDED.source_title,
                       ingredients = EXCLUDED.ingredients,
                       pantry_coverage = EXCLUDED.pantry_coverage,
                       notes = EXCLUDED.notes,
                       updated_at = now()''',
                (slug, dish, source_url, source_title,
                 psycopg.types.json.Json(ingredients), pantry_coverage, notes),
            )
            # Requirements are replaced wholesale: a re-read of the recipe is
            # the authority on what it needs now.
            conn.execute('DELETE FROM recipe_requirements WHERE recipe_slug = %s', (slug,))
            rows = [(slug, 'equipment', item) for item in equipment]
            rows += [(slug, 'technique', item) for item in techniques]
            if rows:
                conn.cursor().executemany(
                    '''INSERT INTO recipe_requirements (recipe_slug, kind, item)
                       VALUES (%s, %s, %s) ON CONFLICT DO NOTHING''',
                    rows,
                )
            conn.commit()
        return self.get(dish).as_dict()

    def block(
        self, dish: str, reason: str, blocking_item: str | None, note: str
    ) -> dict | None:
        '''Take a dish off the table, recording what would bring it back.'''
        self.ensure_schema()
        slug = self._slug(dish)
        with self._connect() as conn:
            found = conn.execute(
                'SELECT 1 FROM recipes WHERE slug = %s', (slug,)
            ).fetchone()
            if not found:
                return None
            conn.execute(
                '''INSERT INTO recipe_blocks
                       (recipe_slug, reason, blocking_item, note, conditional)
                   VALUES (%s, %s, %s, %s, %s)''',
                (slug, reason, blocking_item, note, BlockReason.is_conditional(reason)),
            )
            conn.commit()
        return self.get(dish).as_dict()

    def lift_for_capability(self, capability: str, because: str) -> list[dict]:
        '''Lift every conditional block waiting on this capability.

        This is what makes a block revisable: she buys the stove she did not
        have, and the dishes that needed it come back on their own instead of
        staying buried because of an answer that is no longer true.
        '''
        self.ensure_schema()
        item = capability.strip().lower()
        with self._connect() as conn:
            revived = conn.execute(
                '''UPDATE recipe_blocks
                      SET lifted_at = now(), lifted_because = %s
                    WHERE lifted_at IS NULL
                      AND conditional
                      AND blocking_item = %s
                RETURNING recipe_slug, reason''',
                (because, item),
            ).fetchall()
            conn.commit()
        slugs = {row['recipe_slug'] for row in revived}
        return [
            recipe.as_dict()
            for recipe in (self.get_by_slug(slug) for slug in slugs)
            if recipe is not None
        ]

    def lift_block(self, dish: str, because: str) -> dict | None:
        '''Lift every active block on one dish, by hand.'''
        self.ensure_schema()
        slug = self._slug(dish)
        with self._connect() as conn:
            conn.execute(
                '''UPDATE recipe_blocks SET lifted_at = now(), lifted_because = %s
                    WHERE recipe_slug = %s AND lifted_at IS NULL''',
                (because, slug),
            )
            conn.commit()
        recipe = self.get_by_slug(slug)
        return recipe.as_dict() if recipe else None

    def accept(self, dish: str) -> dict | None:
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(
                'UPDATE recipes SET accepted = TRUE, updated_at = now() WHERE slug = %s',
                (self._slug(dish),),
            )
            conn.commit()
        recipe = self.get(dish)
        return recipe.as_dict() if recipe else None

    # ------------------------------------------------------------- reading

    ROW_QUERY = '''
        SELECT r.*,
               COALESCE(eq.items, ARRAY[]::text[])  AS equipment,
               COALESCE(te.items, ARRAY[]::text[])  AS techniques,
               COALESCE(bl.blocks, '[]'::json)      AS active_blocks
          FROM recipes r
          LEFT JOIN (SELECT recipe_slug, array_agg(item ORDER BY item) AS items
                       FROM recipe_requirements WHERE kind = 'equipment'
                      GROUP BY recipe_slug) eq ON eq.recipe_slug = r.slug
          LEFT JOIN (SELECT recipe_slug, array_agg(item ORDER BY item) AS items
                       FROM recipe_requirements WHERE kind = 'technique'
                      GROUP BY recipe_slug) te ON te.recipe_slug = r.slug
          LEFT JOIN (SELECT recipe_slug,
                            json_agg(json_build_object(
                                'reason', reason, 'blocking_item', blocking_item,
                                'note', note, 'conditional', conditional,
                                'since', created_at)) AS blocks
                       FROM recipe_blocks WHERE lifted_at IS NULL
                      GROUP BY recipe_slug) bl ON bl.recipe_slug = r.slug
    '''

    @staticmethod
    def _to_recipe(row: dict) -> Recipe:
        return Recipe(
            slug=row['slug'],
            dish=row['dish'],
            source_url=row['source_url'] or '',
            source_title=row['source_title'] or '',
            ingredients=row['ingredients'] or [],
            pantry_coverage=row['pantry_coverage'] or 0,
            notes=row['notes'] or '',
            accepted=row['accepted'],
            equipment=list(row['equipment']),
            techniques=list(row['techniques']),
            active_blocks=list(row['active_blocks']),
        )

    def get(self, dish: str) -> Recipe | None:
        return self.get_by_slug(self._slug(dish))

    def get_by_slug(self, slug: str) -> Recipe | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                f'{self.ROW_QUERY} WHERE r.slug = %s', (slug,)
            ).fetchone()
        return self._to_recipe(row) if row else None

    def all(self, only_open: bool = False) -> list[Recipe]:
        self.ensure_schema()
        clause = (
            'WHERE NOT EXISTS (SELECT 1 FROM recipe_blocks b '
            'WHERE b.recipe_slug = r.slug AND b.lifted_at IS NULL)'
            if only_open
            else ''
        )
        with self._connect() as conn:
            rows = conn.execute(
                f'{self.ROW_QUERY} {clause} ORDER BY r.pantry_coverage DESC NULLS LAST'
            ).fetchall()
        return [self._to_recipe(row) for row in rows]

    def history(self, dish: str) -> list[dict]:
        '''Every block ever placed on a dish, lifted or not.'''
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                '''SELECT reason, blocking_item, note, conditional,
                          created_at, lifted_at, lifted_because
                     FROM recipe_blocks WHERE recipe_slug = %s
                    ORDER BY created_at''',
                (self._slug(dish),),
            ).fetchall()
        return [
            {
                'reason': r['reason'],
                'blocking_item': r['blocking_item'],
                'note': r['note'],
                'conditional': r['conditional'],
                'since': r['created_at'].isoformat(),
                'lifted_at': r['lifted_at'].isoformat() if r['lifted_at'] else None,
                'lifted_because': r['lifted_because'],
            }
            for r in rows
        ]


class DishFeedbackStore:
    """What she said about each dish: does she want to cook it, what stops her.

    A record, not a cache: her opinion is what a later turn checks before
    re-proposing something, and it has to outlive the conversation it came from.
    """

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _slug(dish: str) -> str:
        return UnitConverter.normalise_text(dish).replace(' ', '-')

    def record(
        self, dish: str, likes_cooking: bool, comment: str, impediments: list[str]
    ) -> dict:
        row = self.db.returning(
            """INSERT INTO dish_feedback (slug, dish, likes_cooking, comment, impediments)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (slug) DO UPDATE
                    SET likes_cooking = EXCLUDED.likes_cooking,
                        comment = EXCLUDED.comment,
                        impediments = EXCLUDED.impediments,
                        recorded_at = now()
                 RETURNING *""",
            (self._slug(dish), dish, likes_cooking, comment,
             psycopg.types.json.Json(impediments)),
        )[0]
        return self._to_dict(row)

    def get(self, dish: str) -> dict | None:
        row = self.db.one(
            'SELECT * FROM dish_feedback WHERE slug = %s', (self._slug(dish),)
        )
        return self._to_dict(row) if row else None

    def all(self) -> list[dict]:
        return [
            self._to_dict(row)
            for row in self.db.query('SELECT * FROM dish_feedback ORDER BY recorded_at')
        ]

    @staticmethod
    def _to_dict(row: dict) -> dict:
        return {
            'dish': row['dish'],
            'likes_cooking': row['likes_cooking'],
            'comment': row['comment'] or '',
            'impediments': list(row['impediments'] or []),
            'recorded_at': row['recorded_at'].isoformat(timespec='seconds'),
        }


class LaunchMenuStore:
    """The launch menu: the deliverable the whole consultation builds towards."""

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _slug(dish: str) -> str:
        return UnitConverter.normalise_text(dish).replace(' ', '-')

    def add(
        self,
        dish: str,
        category: str,
        cmv: float,
        price: float,
        platform_fee: float,
        confidence_band: str,
        notes: str,
    ) -> dict:
        receives = price * (1 - platform_fee)
        row = self.db.returning(
            """INSERT INTO menu_items
                   (slug, dish, category, cmv, price, she_receives, profit,
                    confidence_band, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (slug) DO UPDATE
                    SET category = EXCLUDED.category, cmv = EXCLUDED.cmv,
                        price = EXCLUDED.price, she_receives = EXCLUDED.she_receives,
                        profit = EXCLUDED.profit,
                        confidence_band = EXCLUDED.confidence_band,
                        notes = EXCLUDED.notes, added_at = now()
                 RETURNING *""",
            (self._slug(dish), dish, category, round(cmv, 2), round(price, 2),
             round(receives, 2), round(receives - cmv, 2), confidence_band, notes),
        )[0]
        return self._to_dict(row)

    def remove(self, dish: str) -> bool:
        return bool(
            self.db.returning(
                'DELETE FROM menu_items WHERE slug = %s RETURNING slug',
                (self._slug(dish),),
            )
        )

    def items(self) -> list[dict]:
        return [
            self._to_dict(row)
            for row in self.db.query('SELECT * FROM menu_items ORDER BY category, dish')
        ]

    @staticmethod
    def _to_dict(row: dict) -> dict:
        return {
            'dish': row['dish'],
            'category': row['category'],
            'cmv': float(row['cmv']),
            'price': float(row['price']),
            'she_receives': float(row['she_receives']),
            'profit': float(row['profit']),
            'confidence_band': row['confidence_band'],
            'notes': row['notes'] or '',
            'added_at': row['added_at'].isoformat(timespec='seconds'),
        }

    def summary(self) -> dict:
        """The menu, aggregated by the database rather than in Python."""
        items = self.items()
        if not items:
            return {
                'items': [],
                'dish_count': 0,
                'note': 'The launch menu is empty. Nothing has been accepted yet.',
            }
        totals = self.db.one(
            """SELECT count(*) AS n, avg(cmv) AS avg_cmv,
                      avg(profit) AS avg_profit, sum(profit) AS total_profit
                 FROM menu_items"""
        )
        by_category = {
            row['category']: int(row['n'])
            for row in self.db.query(
                'SELECT category, count(*) AS n FROM menu_items GROUP BY category'
            )
        }
        weak = [item['dish'] for item in items if item['confidence_band'] == 'low']
        return {
            'items': items,
            'dish_count': int(totals['n']),
            'by_category': by_category,
            'average_cmv': round(float(totals['avg_cmv']), 2),
            'average_profit': round(float(totals['avg_profit']), 2),
            'total_profit_per_round': round(float(totals['total_profit']), 2),
            'low_confidence_dishes': weak,
            'warning': (
                f'These went on the menu with weak evidence: {weak}. Revisit them '
                'before she prints anything.'
            )
            if weak
            else None,
        }
