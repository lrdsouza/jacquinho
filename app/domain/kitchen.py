'''Kitchen capability profile: the viability gate of the challenge.

Every capability carries one of three states. The whole point is that
``unknown`` can never be read as ``yes``: that is what stops the agent from
letting Dona Maria buy ingredients for a dish she cannot actually produce.
'''

from __future__ import annotations

from .database import Database


class CapabilityState:
    '''Tri-state answer for one kitchen capability.'''

    YES = 'confirmed_yes'
    NO = 'confirmed_no'
    UNKNOWN = 'unknown'

    ALL = (YES, NO, UNKNOWN)


class Hedge:
    """Finds the answer that is neither yes nor no.

    She said "meu forno acende mas não esquenta direito, às vezes queima
    embaixo". It was filed as ``confirmed_yes``, note and all - and the note is
    where the truth went, which is the one place the gate cannot read. From
    then on the gate would clear any oven dish for a kitchen whose oven burns
    the bottom, and she would buy ingredients for it.

    Three states have no room for "has one, sort of". Until they do, a hedged
    yes is refused and turned back into a question. The asymmetry is what makes
    a word list acceptable here: a false positive costs one extra question, a
    false negative costs her the ingredients.
    """

    # Not a grammar. The shapes people actually use to answer "do you have X?"
    # with something other than yes or no.
    MARKERS = (
        'mas ', ' mas', 'porem', 'porém', 'so que', 'só que',
        'as vezes', 'às vezes', 'de vez em quando',
        'nao muito', 'não muito', 'mais ou menos', 'meio ',
        'nao direito', 'não direito', 'nao funciona bem', 'não funciona bem',
        'quebrad', 'estragad', 'com problema', 'com defeito',
        'acho que', 'talvez', 'nao sei se', 'não sei se',
        'ta ruim', 'tá ruim', 'nao presta', 'não presta',
        'precisa consertar', 'ta velho', 'tá velho',
    )

    @classmethod
    def found_in(cls, text: str) -> list[str]:
        lowered = f' {(text or "").lower()} '
        return [marker.strip() for marker in cls.MARKERS if marker in lowered]


class KitchenProfile:
    """Persistent record of equipment, techniques and operating limits.

    Kept in Postgres rather than a file: a capability is read on nearly every
    turn, joined against recipe requirements, and its history decides whether a
    blocked dish comes back. None of that survives being a JSON blob.
    """

    CATEGORIES = ('equipment', 'techniques', 'constraints')

    def __init__(self, db: Database):
        self.db = db

    @property
    def data(self) -> dict[str, dict]:
        """The whole profile, shaped as it reads in a conversation."""
        out: dict[str, dict] = {category: {} for category in self.CATEGORIES}
        for row in self.db.query(
            'SELECT category, item, state, note, updated_at FROM kitchen_capabilities'
        ):
            out[row['category']][row['item']] = {
                'state': row['state'],
                'note': row['note'] or '',
                'updated_at': row['updated_at'].isoformat(timespec='seconds'),
            }
        return out

    def record(self, category: str, item: str, state: str, note: str = '') -> dict:
        if category not in self.CATEGORIES:
            raise ValueError(f'category must be one of {self.CATEGORIES}')
        if state not in CapabilityState.ALL:
            raise ValueError(f'state must be one of {CapabilityState.ALL}')

        row = self.db.returning(
            """INSERT INTO kitchen_capabilities (category, item, state, note)
                    VALUES (%s, %s, %s, %s)
               ON CONFLICT (category, item) DO UPDATE
                    SET state = EXCLUDED.state,
                        note = EXCLUDED.note,
                        updated_at = now()
                 RETURNING state, note, updated_at""",
            (category, item.strip().lower(), state, note),
        )[0]
        return {
            'state': row['state'],
            'note': row['note'] or '',
            'updated_at': row['updated_at'].isoformat(timespec='seconds'),
        }

    def state_of(self, category: str, item: str) -> str:
        row = self.db.one(
            'SELECT state FROM kitchen_capabilities WHERE category = %s AND item = %s',
            (category, item.strip().lower()),
        )
        return row['state'] if row else CapabilityState.UNKNOWN

    def check(self, equipment: list[str], techniques: list[str]) -> dict:
        """Decide whether a dish may proceed to costing and pricing."""
        blockers: list[dict] = []
        questions: list[dict] = []
        known = self.data

        for category, needed in (('equipment', equipment), ('techniques', techniques)):
            for item in needed:
                key = item.strip().lower()
                entry = known[category].get(key)
                state = entry['state'] if entry else CapabilityState.UNKNOWN
                if state == CapabilityState.NO:
                    blockers.append(
                        {
                            'category': category,
                            'item': item,
                            'reason': (entry or {}).get('note')
                            or 'Dona Maria confirmed she does not have or cannot do this.',
                        }
                    )
                elif state == CapabilityState.UNKNOWN:
                    questions.append({'category': category, 'item': item})

        if blockers:
            verdict = 'rejected'
        elif questions:
            verdict = 'needs_answers'
        else:
            verdict = 'approved'

        return {
            'verdict': verdict,
            'may_price': verdict == 'approved',
            'blockers': blockers,
            'ask_before_proceeding': questions,
            'rule': (
                "Only move on to costing and pricing when the verdict is 'approved'. "
                "'unknown' does NOT count as 'she has it'."
            ),
        }

    def recorded_count(self) -> int:
        row = self.db.one('SELECT count(*) AS n FROM kitchen_capabilities')
        return int(row['n']) if row else 0
