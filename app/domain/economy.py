'''Current economic conditions for the city she actually sells in.

Two indices are read, not one. The headline IPCA frames the economy; the food
at home index is what her ingredient costs actually track, and in Sao Paulo
those two are far enough apart to change a margin.
'''

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


class EconomicDataUnavailable(RuntimeError):
    '''Raised when the indicator source cannot be reached or parsed.'''


@dataclass(frozen=True)
class InflationReading:
    '''IPCA for one locality, headline and food, with its reference period.'''

    locality: str
    headline_12m: float
    food_at_home_12m: float
    reference_period: str
    age_in_months: int
    source: str

    @property
    def cost_index(self) -> float:
        '''The rate her grocery bill follows.'''
        return self.food_at_home_12m

    def as_dict(self) -> dict:
        return {
            'locality': self.locality,
            'ipca_headline_12m_percent': self.headline_12m,
            'ipca_food_at_home_12m_percent': self.food_at_home_12m,
            'cost_index_used': 'food at home',
            'reference_period': self.reference_period,
            'age_in_months': self.age_in_months,
            'source': self.source,
            'staleness_note': (
                'IPCA is published with a lag; this is the most recent official '
                'figure, not today.'
            ),
        }


class EconomicContext:
    '''Reads IPCA from IBGE for a configured locality.'''

    BASE = 'https://servicodados.ibge.gov.br/api/v3/agregados/7060'
    TWELVE_MONTH_VARIABLE = '2265'
    HEADLINE_CATEGORY = '7169'      # Indice geral
    FOOD_AT_HOME_CATEGORY = '7171'  # 11.Alimentacao no domicilio
    SOURCE = 'IBGE SIDRA, agregado 7060 (IPCA por grupo)'

    def __init__(self, locality: str = 'N7[3501]', timeout: float = 30.0):
        self.locality = locality
        self.timeout = timeout
        self._cached: InflationReading | None = None

    @property
    def _url(self) -> str:
        categories = f'{self.HEADLINE_CATEGORY},{self.FOOD_AT_HOME_CATEGORY}'
        return (
            f'{self.BASE}/periodos/-1/variaveis/{self.TWELVE_MONTH_VARIABLE}'
            f'?localidades={self.locality}&classificacao=315[{categories}]'
        )

    @staticmethod
    def _months_since(period: str) -> int:
        year, month = int(period[:4]), int(period[4:])
        now = datetime.now(timezone.utc)
        return (now.year - year) * 12 + (now.month - month)

    def read(self) -> InflationReading:
        '''Fetch both indices, caching for the life of the process.'''
        if self._cached is not None:
            return self._cached

        try:
            response = httpx.get(self._url, timeout=self.timeout, follow_redirects=True)
            response.raise_for_status()
            blocks = response.json()[0]['resultados']
        except (httpx.HTTPError, ValueError, IndexError, KeyError) as error:
            raise EconomicDataUnavailable(f'IBGE unreachable or changed: {error}') from error

        values: dict[str, float] = {}
        locality_name, period = self.locality, ''
        for block in blocks:
            category_id = next(iter(block['classificacoes'][0]['categoria']))
            series = block['series'][0]
            locality_name = series['localidade']['nome']
            period = max(series['serie'])
            raw = series['serie'][period]
            if raw not in ('-', '', None):
                values[category_id] = float(raw)

        if self.HEADLINE_CATEGORY not in values:
            raise EconomicDataUnavailable('IBGE returned no headline IPCA')

        self._cached = InflationReading(
            locality=locality_name,
            headline_12m=values[self.HEADLINE_CATEGORY],
            # Fall back to headline rather than inventing a food figure.
            food_at_home_12m=values.get(
                self.FOOD_AT_HOME_CATEGORY, values[self.HEADLINE_CATEGORY]
            ),
            reference_period=f'{period[:4]}-{period[4:]}',
            age_in_months=self._months_since(period),
            source=self.SOURCE,
        )
        return self._cached

    def restate_cost(self, cost: float, cost_basis_age_months: int) -> dict:
        '''What that cost would be at today's prices, indexed by food inflation.

        Her spreadsheet records what she paid, never when. This says plainly
        what assumption is being made rather than pretending the cost is fresh.
        '''
        reading = self.read()
        monthly_rate = (1 + reading.cost_index / 100) ** (1 / 12) - 1
        restated = cost * (1 + monthly_rate) ** cost_basis_age_months
        return {
            'cost_as_paid': round(cost, 2),
            'cost_basis_age_months': cost_basis_age_months,
            'cost_if_rebought_today': round(restated, 2),
            'uplift': round(restated - cost, 2),
            'assumption': (
                f'Her groceries are assumed to be {cost_basis_age_months} month(s) '
                f'old and to have tracked food-at-home inflation in '
                f'{reading.locality} ({reading.cost_index}% over 12 months). Ask her '
                'when she shopped to sharpen this.'
            ),
            'indicator': reading.as_dict(),
        }
