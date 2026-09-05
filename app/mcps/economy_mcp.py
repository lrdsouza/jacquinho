'''MCP surface for current economic conditions.'''

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ..domain.economy import EconomicContext, EconomicDataUnavailable
from .base import BaseMCP


class EconomyMCP(BaseMCP):
    '''Reads official inflation so profit is judged in today's money.'''

    name = 'economy'
    instructions = (
        'Current economic conditions. Call current_indicators before discussing '
        'profit, and restate_cost when her grocery prices are not fresh. If the '
        'indicator cannot be fetched, say the profit figure is nominal only.'
    )

    def __init__(self, settings):
        self.context = EconomicContext(settings.ibge_locality)
        super().__init__(settings)

    def register(self) -> None:
        @self.mcp.tool
        def current_indicators() -> dict:
            '''Read the latest official IPCA, with the period it refers to.

            Sourced from IBGE. IPCA is published with a lag, so the reference
            period and its age come back with the number.
            '''
            try:
                reading = self.context.read()
            except EconomicDataUnavailable as error:
                return {
                    'available': False,
                    'error': str(error),
                    'next_step': (
                        'Tell her the profit figure is nominal and not checked '
                        'against inflation. Do not guess an inflation rate.'
                    ),
                }
            return {
                'available': True,
                'city': f'{self.settings.city} - {self.settings.state}',
                'indicator': reading.as_dict(),
                'which_index_to_use': (
                    'Use the food-at-home figure for her ingredient costs. The '
                    'headline index describes the economy, not her grocery bill.'
                ),
            }

        @self.mcp.tool
        def restate_cost(
            cost: Annotated[float, Field(gt=0, description='A cost as recorded, in R$.')],
            cost_basis_age_months: Annotated[int, Field(ge=0, le=120, description='How long ago she paid it. Ask her; default assumes a year.')] = 12,
        ) -> dict:
            '''Restate a cost she paid in the past at today's prices.

            Her spreadsheet records what she paid but never when, so the age is
            an input, not a guess. Use it to show whether a margin computed on
            old grocery prices still holds if she reshops today.
            '''
            try:
                return {'available': True, **self.context.restate_cost(cost, cost_basis_age_months)}
            except EconomicDataUnavailable as error:
                return {'available': False, 'error': str(error)}
