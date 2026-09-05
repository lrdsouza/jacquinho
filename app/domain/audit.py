'''Checking the sentence against the numbers, without asking a model.

The observer scores the evidence trail and never sees the message. The judge
sees the message but has to be invoked. Between them sits something neither
does: every figure in a message is either a number a tool produced, or it is
not - and that is decidable.

This does not replace the judge. A message can be wrong in ways no number
reveals. But the specific failure this system exists to prevent - a price that
was never calculated - is caught here, deterministically and for free.
'''

from __future__ import annotations

import re
from dataclasses import dataclass

MONEY = re.compile(r'R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)')
PERCENT = re.compile(r'(\d+(?:[.,]\d+)?)\s*%')


@dataclass(frozen=True)
class Figure:
    '''One number found in a message, and where it sits in the text.'''

    value: float
    kind: str
    quoted: str

    def as_dict(self) -> dict:
        return {'value': self.value, 'kind': self.kind, 'quoted': self.quoted}


class MessageAudit:
    '''Finds figures in a message and asks whether a tool produced them.'''

    # Two figures that differ by less than a cent are the same figure written
    # differently, not a discrepancy.
    TOLERANCE = 0.011

    @staticmethod
    def _to_float(raw: str) -> float | None:
        text = raw.strip()
        if ',' in text:
            text = text.replace('.', '').replace(',', '.')
        try:
            return float(text)
        except ValueError:
            return None

    @classmethod
    def figures(cls, message: str) -> list[Figure]:
        '''Every money amount and percentage the message states.'''
        found: list[Figure] = []
        for pattern, kind in ((MONEY, 'money'), (PERCENT, 'percent')):
            for match in pattern.finditer(message):
                value = cls._to_float(match.group(1))
                if value is not None:
                    found.append(Figure(value, kind, match.group(0)))
        return found

    @classmethod
    def known_values(cls, evidence: dict) -> set[float]:
        '''Every number the tools actually produced, flattened.

        Walks the whole payload rather than naming fields: a scorer that has to
        be told about each new field goes stale the day a tool gains one.
        '''
        values: set[float] = set()

        def walk(node) -> None:
            if isinstance(node, dict):
                for item in node.values():
                    walk(item)
            elif isinstance(node, (list, tuple)):
                for item in node:
                    walk(item)
            elif isinstance(node, bool):
                return
            elif isinstance(node, (int, float)):
                values.add(round(float(node), 2))
            elif isinstance(node, str):
                for figure in cls.figures(node):
                    values.add(round(figure.value, 2))

        walk(evidence)
        return values

    @classmethod
    def check(cls, message: str, evidence: dict) -> dict:
        '''Which figures in the message no tool produced.'''
        known = cls.known_values(evidence)
        stated = cls.figures(message)
        unsupported = [
            figure
            for figure in stated
            if not any(abs(figure.value - value) <= cls.TOLERANCE for value in known)
        ]
        return {
            'figures_stated': len(stated),
            'figures_supported': len(stated) - len(unsupported),
            'unsupported': [figure.as_dict() for figure in unsupported],
            'verdict': 'clean' if not unsupported else 'unsupported_figures',
            'note': (
                'Every figure in the message matches something a tool produced.'
                if not unsupported
                else 'These figures appear in the message and in no tool result. '
                'Either they were computed in prose - which this system does not '
                'allow - or a tool result is missing from the evidence.'
            ),
        }
