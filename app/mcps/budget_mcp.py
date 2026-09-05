'''MCP surface over the top-up budget ledger.'''

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ..domain.budget import BudgetLedger
from .base import BaseMCP


class BudgetMCP(BaseMCP):
    '''Owns the R$ 80.00 top-up budget as spendable, decreasing state.'''

    name = 'budget'
    instructions = (
        'The top-up budget is state, not a number to recall. Read it with '
        'get_status, test a shopping list with check_purchase, and only call '
        'commit_purchase once Dona Maria has actually agreed to buy. Never tell '
        'her what is left without reading it here first.'
    )

    def __init__(self, settings, db):
        self.db = db
        super().__init__(settings)

    def _ledger(self) -> BudgetLedger:
        return BudgetLedger(self.db, self.settings.top_up_budget)

    def register(self) -> None:
        @self.mcp.tool
        def get_status() -> dict:
            '''Show the budget: total, already committed, and what is left.'''
            return self._ledger().status()

        @self.mcp.tool
        def check_purchase(
            amount: Annotated[float, Field(gt=0, description='Total cost of the shopping list, in R$.')],
        ) -> dict:
            '''Test whether a shopping list fits, without spending anything.'''
            return self._ledger().check(amount)

        @self.mcp.tool
        def commit_purchase(
            dish: Annotated[str, Field(description='Dish this shopping is for.')],
            description: Annotated[str, Field(description="What she is buying, e.g. '100 g mussarela, farinha de rosca'.")],
            amount: Annotated[float, Field(gt=0, description='Total cost in R$.')],
        ) -> dict:
            '''Spend against the budget, after she agreed to buy.

            Refuses to overspend rather than going negative.
            '''
            return self._ledger().commit(dish, description, amount)

        @self.mcp.tool
        def release_purchase(
            entry_id: Annotated[str, Field(description='entry_id from get_status.')],
        ) -> dict:
            '''Give the money back when she drops a dish she had committed to.'''
            return self._ledger().release(entry_id)
