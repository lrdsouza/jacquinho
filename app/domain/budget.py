'''The R$ 80.00 top-up budget, as a ledger instead of a constant.

Kept as state rather than a number repeated in prose: once Dona Maria commits
to buying something, the money is gone and the next dish has to fit in what is
left. A rule written in a persona file cannot enforce that; this can.
'''

from __future__ import annotations

import uuid

from .database import Database


class BudgetLedger:
    """Tracks what is left of the top-up budget across sessions.

    In Postgres because it is money: entries are appended, never edited, the
    remaining balance is derived by the database rather than stored, and the
    numeric type refuses the rounding drift a float would accumulate.
    """

    def __init__(self, db: Database, total: float):
        self.db = db
        self.total = total

    @property
    def committed(self) -> float:
        row = self.db.one('SELECT COALESCE(sum(amount), 0) AS spent FROM budget_entries')
        return float(row['spent'])

    @property
    def remaining(self) -> float:
        return self.total - self.committed

    def entries(self) -> list[dict]:
        return [
            {
                'entry_id': row['entry_id'],
                'dish': row['dish'],
                'description': row['description'],
                'amount': float(row['amount']),
                'committed_at': row['committed_at'].isoformat(timespec='seconds'),
            }
            for row in self.db.query(
                'SELECT * FROM budget_entries ORDER BY committed_at'
            )
        ]

    def status(self) -> dict:
        committed = self.committed
        return {
            'total_budget': round(self.total, 2),
            'committed': round(committed, 2),
            'remaining': round(self.total - committed, 2),
            'entries': self.entries(),
        }

    def check(self, amount: float) -> dict:
        """Decide whether a purchase fits, without changing anything."""
        remaining = self.remaining
        fits = amount <= remaining + 1e-9
        return {
            'amount': round(amount, 2),
            'remaining_before': round(remaining, 2),
            'fits': fits,
            'remaining_after': round(remaining - amount, 2),
            'shortfall': round(max(0.0, amount - remaining), 2),
            'verdict': 'fits' if fits else 'over_budget',
        }

    def commit(self, dish: str, description: str, amount: float) -> dict:
        """Spend against the budget. Refuses to overspend."""
        verdict = self.check(amount)
        if not verdict['fits']:
            return {'committed': False, **verdict}

        entry_id = uuid.uuid4().hex[:8]
        self.db.execute(
            """INSERT INTO budget_entries (entry_id, dish, description, amount)
                    VALUES (%s, %s, %s, %s)""",
            (entry_id, dish, description, amount),
        )
        return {'committed': True, 'entry_id': entry_id, **self.status()}

    def release(self, entry_id: str) -> dict:
        """Undo a commitment, for when she changes her mind about a dish."""
        removed = self.db.returning(
            'DELETE FROM budget_entries WHERE entry_id = %s RETURNING entry_id',
            (entry_id,),
        )
        if not removed:
            return {'released': False, 'reason': f'no entry with id {entry_id}'}
        return {'released': True, **self.status()}
