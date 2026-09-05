'''MCP surface for delivery market price research.'''

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..domain.market import MarketPriceResearch
from ..domain.search import Freshness, SearchProviderFactory
from .base import BaseMCP


class MarketMCP(BaseMCP):
    '''Finds what comparable dishes actually charge on delivery.'''

    name = 'market'
    instructions = (
        'Price reality check. Run research_dish_prices before any price is shown '
        'to Dona Maria, and pass its reference band into pricing_price_scenarios. '
        'A multiplier over cost is not a price until it is compared to the market. '
        'Prices default to the last month on purpose: a listing from last year is '
        'not the market she is selling into today.'
    )

    def _research(self, freshness: str = Freshness.MONEY) -> MarketPriceResearch:
        provider = SearchProviderFactory.create(
            self.settings.search_provider, self.settings.brave_api_key
        )
        return MarketPriceResearch(provider, freshness)

    def register(self) -> None:
        @self.mcp.tool
        def research_dish_prices(
            dish: Annotated[str, Field(description="Dish name as a customer would search it.")],
            city: Annotated[str, Field(description='City or neighbourhood. Defaults to her city from configuration.')] = '',
            limit: Annotated[int, Field(ge=1, le=15, description='Pages to scan.')] = 10,
            freshness: Annotated[Literal['day', 'week', 'month', 'year'], Field(description='How recent the listings must be. Money defaults to the last month.')] = 'month',
        ) -> dict:
            '''Collect real delivery prices for a comparable dish.

            Returns every observation with its source so the numbers can be
            audited, plus a min/median/max band and an honest confidence based
            on sample size. An empty result is a real answer: say the market
            price is unknown rather than inventing one.
            '''
            return self._research(freshness).research(
                dish, city or f'{self.settings.city} {self.settings.state}', limit
            )
