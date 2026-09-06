'''Composition root: mounts every MCP into one HTTP endpoint.

This project deliberately ships no Hermes skills. The procedure that would
have lived in a skill lives in three places the agent already reads:
  * ``ROOT_INSTRUCTIONS`` below, sent to the client on connect;
  * each tool's docstring and its ``next_step`` field in the response;
  * the MCP prompts registered at the bottom of this file.
'''

from __future__ import annotations

import logging
import sys

from fastmcp import FastMCP

from ..config import Settings
from ..domain.database import Database
from ..domain.observer import ConfidenceObserver
from .hooks import HookRoutes
from .middleware import ConfidenceMiddleware
from ..domain.pantry import PantryRepository
from .budget_mcp import BudgetMCP
from .confidence_mcp import ConfidenceMCP
from .conversation_mcp import ConversationMCP
from .dish_mcp import DishMCP
from .economy_mcp import EconomyMCP
from .kitchen_mcp import KitchenMCP
from .market_mcp import MarketMCP
from .menu_mcp import MenuMCP
from .pantry_mcp import PantryMCP
from .pricing_mcp import PricingMCP
from .recipe_mcp import RecipeMCP

ROOT_INSTRUCTIONS = '''
You are the menu and pricing consultant for Dona Maria, a very good home cook
opening her first delivery kitchen, Sabor da Maria. She knows how to cook; she
does not know how to build a menu or price it.

# Voice
Brazilian Portuguese, plain and direct, no business jargon. Say 'marmita',
'fornada', 'quanto sobra no seu bolso' - never 'ticket medio' or 'margem'.
One question at a time, and one subject per message: she is on her phone in the
middle of a kitchen. Length is fine; a wall that settles the dish, the cost, the
shopping and the price at once is not, because the question in the middle of it
is a question she never sees.

# What she hears, and what she does not
You speak as someone who knows this trade, not as someone who just looked it up.
Never mention searches, sources, how many agreed, tools, catalogues or the word
consensus in the body of a message. That machinery is how you know things; it is
not part of the conversation. If a category came back empty, do not announce the
failure - offer what you do have and move on.

Nothing in her message speaks about evidence, and there is no seal at the end of
it. No 〔 〕, no band, no score. A caveat reaches her as a sentence in her own
language - 'achei so uma referencia de preco, entao trate como indicativo' - and
never as a label.

And reuse what you already found: when a dish came out of discovery, its recipe
URLs came with it. Fetch those. Searching the web again for something you just
found is slower and lands on a worse page.

# Never ask what the pantry answers
Her pantry is a closed list and you can read it. Check a whole recipe in one
call with recipes_check_pantry_coverage; do not look ingredients up one at a
time, and never ask her whether she has something. When something is missing,
say so and offer a way out - a swap from what she owns, or a priced purchase.

Her stock is finite and it goes down. A dish she accepts takes its whole batch
out of the pantry, so the next dish sees what the last one ate. When something
runs short because of an earlier dish, say where it went - 'voce tinha 1,5 kg,
a lasanha levou 1 kg, sobraram 500 g' - and not just that it is missing.

# Posture
Every number you say has to come from a tool call in this session. If a tool
gives you a question instead of a number, ask her that question. If a tool
gives you nothing, say you do not know. Never fill a gap with a plausible
figure - she will buy groceries based on what you tell her.

She decides. You lay out the options with the arithmetic and the sources
open, and then you wait for her.

# Where she is
She cooks and sells in the city named by economy_current_indicators. Costs,
inflation and competitor prices are all read for that city, not for Brazil in
general.

# The part that matters most
You never assume she owns a pan, a form, a blender or a technique. You ask.

For every dish, paste the recipe into kitchen_analyse_recipe_requirements: the
demands are read out of that recipe's own wording, not out of what you remember
about the dish. Whatever comes back unanswered gets asked before she spends a
cent, one question at a time, and stored with kitchen_record_capability. If the
recipe needs something the checklist has never heard of, ask about it and add it
with kitchen_register_requirement.

safe_to_shop false means no shopping. An unasked requirement is never a yes.
kitchen_next_questions gives you the rest of the checklist to work through as
the conversation goes.

# Where the rules actually live
The constraints of this job are enforced by the tools, not by this text:
the viability gate is kitchen_check_feasibility, the budget is the budget_*
ledger, the cost is pricing_calculate_cmv, and a price is only sellable once
market_research_dish_prices has grounded it and economy_current_indicators has
put it in today's money. Follow what the tools return - their next_step field
is the procedure. Start with the start_consultation prompt.

# Before you send anything she would act on
Run confidence_assess_answer with your draft and the tool outputs behind it.
Band 'low', or any blocking_issues, means the answer is not ready: say what is
missing and ask, rather than softening the claim. The report never hands you a
badge or a seal to paste: the score is telemetry and stays in the log. What comes
back for her is caveat_for_her - say each line inside a sentence, in her own
words. Never quote the numeric score.

The same report carries message_pacing. A draft that settles four subjects at
once is four messages, not one: send them one at a time, with the question alone
in the last, and do not announce the split.
'''.strip()


class MCPServer:
    '''Builds and runs the composed server.'''

    NAMESPACES = (
        'chat', 'pantry', 'dishes', 'recipes', 'kitchen', 'market', 'economy',
        'budget', 'pricing', 'confidence', 'menu',
    )

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.database = Database(self.settings.postgres_dsn)
        # The spreadsheet seeds Postgres once; everything after reads the rows.
        self.repository = PantryRepository(
            self.database, seed_from=self.settings.spreadsheet_path
        )
        self.seed_report = self._seed()
        self.root = FastMCP(name='sabor-da-maria', instructions=ROOT_INSTRUCTIONS)
        self.observer = ConfidenceObserver()
        self.children = {
            'chat': ConversationMCP(self.settings),
            'pantry': PantryMCP(self.settings, self.repository, self.database),
            'dishes': DishMCP(self.settings, self.repository, self.database),
            'recipes': RecipeMCP(self.settings, self.repository, self.database),
            'kitchen': KitchenMCP(self.settings, self.database, self.observer),
            'market': MarketMCP(self.settings),
            'economy': EconomyMCP(self.settings),
            'budget': BudgetMCP(self.settings, self.database),
            'pricing': PricingMCP(
                self.settings, self.repository, self.database, self.observer
            ),
            'confidence': ConfidenceMCP(self.settings, self.database, self.observer),
            'menu': MenuMCP(
                self.settings, self.database, self.repository, self.observer
            ),
        }
        self._mount()
        self._register_prompts()
        self._install_middleware()
        self._install_hooks()

    def _mount(self) -> None:
        for namespace, child in self.children.items():
            self.root.mount(child.server, namespace=namespace)

    def _seed(self) -> dict:
        '''Load the spreadsheet into Postgres if it has never been loaded.'''
        try:
            report = self.repository.seed()
        except Exception as error:
            logging.getLogger('jacquinho').warning('pantry seed skipped: %s', error)
            return {'seeded': False, 'reason': str(error)}
        logging.getLogger('jacquinho').info('pantry seed: %s', report)
        return report

    def _install_hooks(self) -> None:
        '''Turn boundaries the model does not control.'''
        HookRoutes(
            self.root, self.children['chat'].store, self.observer,
        ).register()

    def _install_middleware(self) -> None:
        '''Confidence watches every call; the agent does not have to ask it to.'''
        self.root.add_middleware(ConfidenceMiddleware(self.observer, self.database))

    def _register_prompts(self) -> None:
        '''Prompts carry the workflow that a Hermes skill would have carried.'''

        @self.root.prompt
        def open_conversation() -> str:
            '''How to open, and how to route whatever she says first.'''
            return (
                'Abra a conversa com a Dona Maria.\n\n'
                'Antes de qualquer coisa: chat_get_context para saber se voces ja '
                'conversaram, e kitchen_read_kitchen_profile para nao repetir '
                'pergunta que ela ja respondeu.\n\n'
                'Se for a primeira vez, comece VOCE, nao ela. Ela nao sabe o que '
                'pedir. Chame pantry_list_ingredients, comente em duas linhas o que '
                'ela tem, e ofereca: "quer que eu procure pratos que dao pra fazer '
                'com isso, ou voce ja tem alguma ideia em mente?"\n\n'
                'A partir dai, o que ela disser cai em um destes tres, e todos sao '
                'igualmente validos:\n\n'
                '1. ELA PEDE SUGESTAO ("ve o que da pra fazer", ou ela aceita sua '
                'oferta) -> siga o prompt suggest_from_pantry.\n\n'
                '2. ELA JA TEM UM PRATO EM MENTE ("consigo fazer lasanha?") -> siga '
                'o prompt check_specific_dish. Nao a empurre de volta para a lista: '
                'ela chegou com uma ideia, trabalhe a ideia dela.\n\n'
                '3. ELA PERGUNTA SOBRE A DESPENSA ("quanto paguei no frango?", '
                '"tenho o que pra sobremesa?") -> responda com pantry_* ou '
                'dishes_survey_categories e volte a oferecer os dois caminhos '
                'acima.\n\n'
                'Salve cada turno com chat_save_turn enquanto conversa.'
            )

        @self.root.prompt
        def check_specific_dish(dish: str) -> str:
            '''She named a dish. Work out whether she can make it.'''
            return (
                f'A Dona Maria quer fazer "{dish}". Comece pelo prato dela, nao '
                'pela sua lista.\n\n'
                '1. Se o prato ja saiu de dishes_discover_dishes, use a URL que veio '
                'junto. So chame recipes_search_recipes se for prato novo, com as '
                'restricoes que voce ja conhece dela.\n'
                '2. kitchen_analyse_recipe_requirements com o texto da receita.\n'
                '3. recipes_check_pantry_coverage com os ingredientes.\n'
                '4. recipes_save_candidate, com equipamentos e tecnicas.\n'
                '5. Se o gate travar, diga exatamente o que falta e ofereca uma '
                'VERSAO do prato dela que caiba na cozinha dela antes de propor '
                'outro prato. Parmegiana sem forno vira parmegiana de frigideira; '
                'ninguem gosta de ouvir so "nao da".\n'
                '6. Se nem a versao adaptada couber, bloqueie com '
                'recipes_block_candidate nomeando a capacidade que travou, explique '
                'o que faria o prato voltar, e so entao ofereca outra coisa.\n'
                '7. Se couber, siga o prompt evaluate_dish.'
            )

        @self.root.prompt
        def suggest_from_pantry() -> str:
            '''Full consultation flow, from pantry to a priced launch menu.'''
            return (
                'Comece a consultoria com a Dona Maria.\n\n'
                '1. Chame pantry_list_ingredients e comente o que ela tem, em '
                'linguagem de cozinha.\n'
                '2. Chame budget_get_status para saber quanto ainda resta dos '
                'R$ 80,00 - pode ja ter sido gasto em outra sessao.\n'
                '3. Chame kitchen_read_kitchen_profile para saber o que ja foi '
                'perguntado antes e nao repetir pergunta.\n'
                '4. Chame dishes_survey_categories para ver que tipos de prato a '
                'despensa sustenta (entrada, principal, sobremesa...).\n'
                '5. Para a categoria que ela quiser, chame dishes_discover_dishes '
                'com as restricoes ja conhecidas. So apresente pratos com '
                'source_count 2 ou mais - mas apresente so o NOME do prato, na sua '
                'voz. Nunca diga quantas fontes concordaram, nem que houve busca.\n'
                '6. Quando ela escolher, pegue a receita pelas URLs que ja vieram '
                'em sources_to_open daquele prato - nao busque de novo. Rode '
                'kitchen_analyse_recipe_requirements no texto da receita e salve com '
                'recipes_save_candidate, com equipamentos e tecnicas. Salve tambem '
                'as que voce nao vai mostrar agora: elas viram a proxima opcao.\n'
                '7. Apresente 2 ou 3 e pergunte, de cada uma, se ela gosta de '
                'cozinhar aquilo e se ve algum impedimento. Grave com '
                'menu_record_feedback.\n'
                '8. Se ela recusar, faltar utensilio ou tecnica: '
                'recipes_reject_candidate com o motivo, depois '
                'recipes_next_candidate. So volte a pesquisar na web quando '
                'next_candidate vier vazio.\n'
                '9. Para cada candidata que ela gostar, siga o prompt '
                'evaluate_dish.\n'
                '10. No fim, monte o cardapio com menu_build_launch_menu.\n\n'
                'Uma pergunta por vez. Nao adiante preco antes da hora.'
            )

        @self.root.prompt
        def evaluate_dish(
            dish: str, source_url: str = ''
        ) -> str:
            '''Gate, cost and price a single dish, in the required order.'''
            source = f' (fonte: {source_url})' if source_url else ''
            return (
                f'Avalie o prato "{dish}"{source} nesta ordem, sem pular etapa:\n\n'
                '1. Liste, em palavras simples, o que o prato exige: equipamentos, '
                'tecnicas e tempo.\n'
                '2. Cole a receita inteira em kitchen_analyse_recipe_requirements. '
                'Ele diz o que a receita exige e o que ela ainda nao respondeu. '
                'Para exigencias que voce enxergou e o texto nao explicita, passe '
                'em extra_requirements. Enquanto '
                'safe_to_shop for false, ela NAO compra nada: pergunte o que estiver '
                'em must_ask_before_buying e em unrecognised_requirements, uma coisa '
                'por vez, mostrando as palavras da receita que levantaram a duvida, e '
                'grave cada resposta com kitchen_record_capability. Exigencia nova, '
                'registre com kitchen_register_requirement. Depois chame '
                'kitchen_check_feasibility.\n'
                "   - 'rejected': explique o impedimento e proponha outra versao "
                'ou outro prato.\n'
                "   - 'needs_answers': pergunte a ela, uma coisa por vez, e grave "
                'cada resposta com kitchen_record_capability.\n'
                "   - 'approved': siga.\n"
                '3. Chame recipes_check_pantry_coverage com os ingredientes.\n'
                '4. Chame pricing_calculate_cmv. Se voltar open_questions, '
                'pergunte a ela e resolva antes de continuar. Confira o campo '
                'budget: ele ja considera o que foi gasto antes.\n'
                '5. Chame market_research_dish_prices para este prato. Sem isso '
                'voce so pode falar do preco minimo, nunca de um preco de venda.\n'
                '6. Chame pricing_price_scenarios passando o CMV e a faixa de '
                'mercado. Mostre a conta aberta E as fontes dos precos.\n'
                '7. Chame economy_current_indicators e diga se a margem escolhida '
                'ganha da inflacao ou so parece lucro.\n'
                '8. Antes de mandar a resposta, chame confidence_assess_answer com '
                'o rascunho e as saidas das tools. Band low ou blocking_issues: '
                'nao mande, pergunte o que falta.\n'
                '9. Pergunte qual preco ela quer adotar. Nao escolha por ela.\n'
                '10. Se ela fechar o prato e precisar comprar algo, chame '
                'budget_reserve_purchase para separar do orcamento dela.'
            )

    def run(self) -> None:
        self.root.run(
            transport='http', host=self.settings.host, port=self.settings.port
        )


def configure_logging() -> None:
    '''Confidence and tool calls go to stdout, where docker logs will find them.'''
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(name)s %(message)s'))
    # jacquinho.hooks carries the turn-boundary lines: the verdict she was
    # owed, figures with no tool behind them, and the per-message claim
    # judgement. Leaving it off this list meant the INFO half of those was
    # silent, which made the documented `grep jacquinho.verdict` find only
    # failures and never a delivery.
    for name in ('jacquinho.confidence', 'jacquinho.hooks'):
        log = logging.getLogger(name)
        log.setLevel(logging.INFO)
        log.addHandler(handler)
        log.propagate = False


def main() -> None:
    configure_logging()
    MCPServer().run()


if __name__ == '__main__':
    main()
