'''Unit normalisation for the pantry spreadsheet.

The spreadsheet mixes clean units ('kg', 'L', 'un') with strings that actually
describe a *package* and carry the quantity inside the text: 'balde 2kg',
'un 500g', 'un 400g', 'un 500ml', 'un 100ml'.

Dividing price by quantity without reading that yields 'R$ 82.00 per bucket',
which is useless for a recipe calling for 20 g of capers. This module resolves
a package down to one base unit per dimension.
'''

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


class UnknownUnitError(ValueError):
    '''Raised when a unit string cannot be mapped to any known dimension.'''


class Dimension:
    '''The three physical dimensions the pantry deals in.'''

    MASS = 'mass'
    VOLUME = 'volume'
    COUNT = 'count'

    ALL = (MASS, VOLUME, COUNT)
    BASE_UNIT = {MASS: 'kg', VOLUME: 'L', COUNT: 'un'}


@dataclass(frozen=True)
class Package:
    '''How one spreadsheet unit converts into its base unit.

    ``factor`` is what ONE of these units is worth in the dimension's base
    unit. Example: 'un 500g' -> dimension=mass, factor=0.5.
    '''

    dimension: str
    factor: float
    label: str
    is_packaged: bool

    @property
    def base_unit(self) -> str:
        return Dimension.BASE_UNIT[self.dimension]


class UnitConverter:
    '''Parses spreadsheet and recipe units into :class:`Package` values.'''

    FACTORS: dict[str, tuple[str, float]] = {
        'kg': (Dimension.MASS, 1.0),
        'quilo': (Dimension.MASS, 1.0),
        'quilos': (Dimension.MASS, 1.0),
        'g': (Dimension.MASS, 0.001),
        'gr': (Dimension.MASS, 0.001),
        'grama': (Dimension.MASS, 0.001),
        'gramas': (Dimension.MASS, 0.001),
        'mg': (Dimension.MASS, 1e-6),
        'l': (Dimension.VOLUME, 1.0),
        'lt': (Dimension.VOLUME, 1.0),
        'litro': (Dimension.VOLUME, 1.0),
        'litros': (Dimension.VOLUME, 1.0),
        'ml': (Dimension.VOLUME, 0.001),
        'un': (Dimension.COUNT, 1.0),
        'und': (Dimension.COUNT, 1.0),
        'uni': (Dimension.COUNT, 1.0),
        'unid': (Dimension.COUNT, 1.0),
        'unidade': (Dimension.COUNT, 1.0),
        'unidades': (Dimension.COUNT, 1.0),
        'pct': (Dimension.COUNT, 1.0),
        'pacote': (Dimension.COUNT, 1.0),
        'balde': (Dimension.COUNT, 1.0),
        'pote': (Dimension.COUNT, 1.0),
        'lata': (Dimension.COUNT, 1.0),
        'duzia': (Dimension.COUNT, 12.0),
    }

    EMBEDDED_QUANTITY = re.compile(
        r'(\d+(?:[.,]\d+)?)\s*(kg|mg|g|gr|ml|l|lt)\b', re.IGNORECASE
    )

    @staticmethod
    def normalise_text(text: str) -> str:
        '''Lowercase, strip accents and punctuation, collapse whitespace.'''
        stripped = ''.join(
            char
            for char in unicodedata.normalize('NFD', str(text))
            if unicodedata.category(char) != 'Mn'
        )
        return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', stripped.lower())).strip()

    @classmethod
    def parse(cls, unit: str) -> Package:
        '''Translate a spreadsheet or recipe unit string into a Package.'''
        raw = str(unit or '').strip()
        if not raw:
            raise UnknownUnitError('empty unit')

        text = cls.normalise_text(raw)

        match = cls.EMBEDDED_QUANTITY.search(text)
        if match:
            amount = float(match.group(1).replace(',', '.'))
            dimension, factor = cls.FACTORS[match.group(2).lower()]
            return Package(dimension, amount * factor, raw, is_packaged=True)

        for token in reversed(text.split()):
            if token in cls.FACTORS:
                dimension, factor = cls.FACTORS[token]
                return Package(dimension, factor, raw, is_packaged=False)

        raise UnknownUnitError(f'unrecognised unit: {raw!r}')

    @classmethod
    def to_base(cls, quantity: float, unit: str) -> tuple[float, str, str]:
        '''Return (quantity in base unit, base unit, dimension).'''
        package = cls.parse(unit)
        return quantity * package.factor, package.base_unit, package.dimension
