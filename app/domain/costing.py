'''The recipe of a dish, settled once.

The agent costed the same dish three times in one consultation and passed a
slightly different ingredient list each time, so the cost wandered: R$ 9,90,
then R$ 8,18, then R$ 7,15. Every one of those came out of the arithmetic
correctly. The arithmetic was never the problem; the inputs were, and nothing in
the system could say which list *was* the dish.

Detecting the drift afterwards and explaining it to her is a worse answer than
not drifting. So the lines are locked the first time a dish is costed
completely, and stay locked until the dish itself changes in the conversation.
That is a thing she says, not a thing the model decides: she wants a different
dish, or she gave up on this one. Then the recipe is reopened and everything
that hung off it - search, gate, cost, price - is done again.
'''

from __future__ import annotations

import re
import unicodedata

import psycopg

from .database import Database


class RecipeLock:
    '''Holds the ingredient list a dish was costed with.'''

    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def slug(dish: str) -> str:
        text = unicodedata.normalize('NFKD', dish or '')
        text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
        return re.sub(r'[^a-z0-9]+', '-', text).strip('-')

    @staticmethod
    def signature(lines: list) -> list[dict]:
        '''What counts as the same recipe: ingredient, amount and unit.

        Order does not matter, and neither does how the agent capitalised the
        name, because neither changes what the dish costs.
        '''
        out = []
        for line in lines:
            name = getattr(line, 'ingredient', None) or line.get('ingredient', '')
            quantity = getattr(line, 'quantity', None)
            unit = getattr(line, 'unit', None)
            if quantity is None:
                quantity, unit = line.get('quantity'), line.get('unit')
            out.append({
                'ingredient': str(name).strip().lower(),
                'quantity': round(float(quantity), 4),
                'unit': str(unit).strip().lower(),
            })
        return sorted(out, key=lambda e: (e['ingredient'], e['unit'], e['quantity']))

    def locked(self, dish: str) -> dict | None:
        '''The settled recipe for this dish, if there is one.'''
        self.db.ensure_schema()
        row = self.db.one(
            'SELECT * FROM recipe_costing WHERE slug = %s AND reopened_at IS NULL',
            (self.slug(dish),),
        )
        if row is None:
            return None
        return {
            'dish': row['dish'],
            'lines': row['lines'],
            'portions': int(row['portions']),
            'cmv_per_portion': float(row['cmv']) if row['cmv'] is not None else None,
            'shopping': row['shopping'],
            'shopping_cost': float(row['shopping_cost']),
            'locked_at': row['locked_at'].isoformat(timespec='seconds'),
        }

    def lock(
        self, dish: str, lines: list, portions: int, cmv: float,
        shopping: list | None = None, shopping_cost: float = 0.0,
    ) -> dict:
        '''Settle the recipe, and with it the shopping list it implies.

        The list travels with the recipe because it is the same fact: what she
        has to buy is the recipe minus the pantry, not a number the agent gets
        to pick. It was pickable, and it drifted: one turn said the massa costs
        R$ 6,95 and was the only thing missing, and the closing message reserved
        R$ 12,00 for "massa e orégano", with the orégano appearing from nowhere.
        '''
        self.db.ensure_schema()
        self.db.execute(
            '''INSERT INTO recipe_costing
                       (slug, dish, lines, portions, cmv, shopping, shopping_cost)
                    VALUES (%s, %s, %s::jsonb, %s, %s, %s::jsonb, %s)
               ON CONFLICT (slug) DO UPDATE SET
                    dish = EXCLUDED.dish,
                    lines = EXCLUDED.lines,
                    portions = EXCLUDED.portions,
                    cmv = EXCLUDED.cmv,
                    shopping = EXCLUDED.shopping,
                    shopping_cost = EXCLUDED.shopping_cost,
                    locked_at = now(),
                    reopened_at = NULL,
                    reopened_because = NULL''',
            (self.slug(dish), dish, psycopg.types.json.Json(self.signature(lines)),
             portions, cmv, psycopg.types.json.Json(shopping or []),
             round(shopping_cost, 2)),
        )
        return self.locked(dish) or {}

    def reopen(self, dish: str, because: str) -> bool:
        '''Let the dish be costed again, because the dish itself changed.'''
        self.db.ensure_schema()
        rows = self.db.query(
            '''UPDATE recipe_costing
                  SET reopened_at = now(), reopened_because = %s
                WHERE slug = %s AND reopened_at IS NULL
            RETURNING slug''',
            (because, self.slug(dish)),
        )
        return bool(rows)

    @classmethod
    def differs(cls, locked_lines: list, lines: list) -> dict:
        '''What changed between the settled recipe and the one being passed.'''
        was = {e['ingredient']: f"{e['quantity']:g} {e['unit']}" for e in locked_lines}
        now = {e['ingredient']: f"{e['quantity']:g} {e['unit']}"
               for e in cls.signature(lines)}
        return {
            'left_the_recipe': sorted(set(was) - set(now)),
            'joined_the_recipe': sorted(set(now) - set(was)),
            'changed_amount': sorted(
                k for k in set(was) & set(now) if was[k] != now[k]
            ),
        }
