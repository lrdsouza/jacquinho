'''MCP surface over the top-up budget ledger.'''

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ..domain.budget import BudgetLedger
from ..domain.costing import RecipeLock
from ..domain.memory import ConversationStore, RedisBackend
from .base import BaseMCP


class BudgetMCP(BaseMCP):
    '''Owns the R$ 80.00 top-up budget as spendable, decreasing state.'''

    name = 'budget'
    instructions = (
        'The top-up budget is state, not a number to recall. Read it with '
        'get_status and test a shopping list with check_purchase. Nothing here '
        'buys anything: you have no wallet, and the shopping happens when Dona '
        'Maria goes to the market. reserve_purchase records what SHE decided to '
        'spend, and it needs her own words agreeing to it. Never tell her what '
        'is left without reading it here first, and never tell her you bought '
        'something.'
    )

    def __init__(self, settings, db):
        self.db = db
        self.chat = ConversationStore(RedisBackend(settings.redis_url))
        self.lock = RecipeLock(db)
        super().__init__(settings)

    def _ledger(self) -> BudgetLedger:
        return BudgetLedger(self.db, self.settings.top_up_budget)

    def register(self) -> None:
        @self.mcp.tool
        def get_status() -> dict:
            '''Show the budget: total, set aside for her to buy, and what is left.'''
            return self._ledger().status()

        @self.mcp.tool
        def check_purchase(
            amount: Annotated[float, Field(gt=0, description='Total cost of the shopping list, in R$.')],
        ) -> dict:
            '''Test whether a shopping list fits, without setting anything aside.'''
            return self._ledger().check(amount)

        @self.mcp.tool
        def reserve_purchase(
            dish: Annotated[str, Field(description='Dish this shopping is for.')],
            description: Annotated[str, Field(description="What SHE will buy, e.g. '100 g mussarela, farinha de rosca'.")],
            amount: Annotated[float, Field(gt=0, description='Estimated total cost in R$.')],
            her_words: Annotated[str, Field(description='The words SHE used agreeing to buy it, copied from her message. Checked against the saved conversation.')] = '',
        ) -> dict:
            '''Set money aside for a shopping list Dona Maria decided to buy.

            **You are not buying anything.** You have no wallet and no card.
            This records what she said she would spend, so the next dish is
            costed against what is honestly left.

            Because it is her decision, it needs her words. Estimate the cost,
            tell her what it would leave her, and ask. Then come here.
            '''
            if len(her_words.split()) < 2:
                return {
                    'reserved': False,
                    'error': 'Reservar orçamento é uma decisão dela, e precisa '
                             'das palavras dela.',
                    'next_step': (
                        'Diga a ela quanto a lista custa e quanto sobraria, e '
                        'pergunte se ela quer comprar. Quando ela responder, '
                        'copie a resposta em her_words. Você não compra nada: '
                        'quem vai ao mercado é ela.'
                    ),
                }
            try:
                spoken = self.chat.she_said(her_words)
            except Exception:
                spoken = {'said': False, 'turns_on_record': 0, 'unavailable': True}
            if not spoken['said'] and not spoken.get('unavailable'):
                return {
                    'reserved': False,
                    'error': f'Ela não disse isso. Procurei {her_words!r} nas '
                             f"{spoken['turns_on_record']} falas dela e não achei.",
                    'next_step': (
                        'Não reserve o dinheiro dela com base numa suposição. '
                        'Pergunte se ela quer comprar, e volte com a resposta.'
                    ),
                }
            # The amount is not the agent's to choose. It is what the recipe
            # needs minus what she has, and `calculate_cmv` already worked it
            # out. Letting the model pass a number here is how R$ 6,95 of massa
            # became R$ 12,00 of "massa e orégano" between two messages, with
            # the orégano appearing from nowhere and the total never explained.
            settled = self.lock.locked(dish)
            expected = (settled or {}).get('shopping_cost')
            if settled and expected is not None and abs(expected - amount) > 0.005:
                return {
                    'reserved': False,
                    'error': (
                        f'A lista de compras de {dish!r} custa R$ {expected:.2f}, '
                        f'não R$ {amount:.2f}.'
                    ),
                    'the_shopping_list_is': settled.get('shopping', []),
                    'next_step': (
                        'Use o valor e os itens que o calculate_cmv apurou. Se '
                        'faltou algum ingrediente na receita, isso muda a '
                        'receita: chame pricing_reopen_recipe com as palavras '
                        'dela e refaça a conta. Não invente item nem total.'
                    ),
                }

            result = self._ledger().reserve(dish, description, amount)
            if result.get('reserved'):
                result['next_step'] = (
                    'Diga a ela o que comprar e quanto vai custar, no futuro: '
                    '"a massa e os temperos saem por uns R$ 30,85, e sobram '
                    'R$ 49,15 do seu orçamento". Nunca diga que você comprou.'
                )
            return result

        @self.mcp.tool
        def release_purchase(
            entry_id: Annotated[str, Field(description='entry_id from get_status.')],
        ) -> dict:
            '''Free the money again when she drops a dish she had decided on.'''
            return self._ledger().release(entry_id)
