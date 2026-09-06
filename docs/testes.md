# Testes

![Unitários](https://img.shields.io/badge/testes-252-success)
![Suítes](https://img.shields.io/badge/suítes-9-0A7EA4)
![Execução](https://img.shields.io/badge/execução-~1.5s-6E56CF)

Duas camadas, com propósitos diferentes: a suíte automatizada garante que a
ferramenta **não quebra**, e a simulação de conversa mostra se ela **serve**.
Uma não substitui a outra.

## Índice

- [Rodando](#rodando)
- [A suíte automatizada](#a-suíte-automatizada)
- [Por que estes testes](#por-que-estes-testes)
- [Testes contra o desafio](#testes-contra-o-desafio)
- [Simulação de usuário](#simulação-de-usuário)
- [O que ainda não é testado](#o-que-ainda-não-é-testado)

---

## Rodando

```bash
jacquinho test              # a suíte inteira
jacquinho test -- -k pantry # só o que casar com 'pantry'
jacquinho test -- -x        # para no primeiro erro
```

Sobe Redis e Postgres antes, porque os testes de servidor exercitam o servidor
de verdade. Os de domínio não precisam de nada e rodam também fora do container:

```bash
python -m pytest tests/ -q
```

---

## A suíte automatizada

**252 testes, 14 suítes, ~60 s** (o tempo é quase todo subida de contêiner e
ida ao Postgres; a parte de domínio roda em cerca de dois segundos).

| Suíte | Testes | O que garante |
|---|---:|---|
| `test_mcp_server.py` | 43 | O servidor sobe, monta, recusa, não deixa o prato dela morrer em silêncio e não gasta o dinheiro dela |
| `test_elicitation.py` | 24 | Catálogo, gate, exigências lidas da receita |
| `test_confidence.py` | 22 | Nota por afirmação, bandas, badge, impedimentos |
| `test_pantry.py` | 20 | Semeadura, custo unitário, casamento de nomes |
| `test_units.py` | 15 | Unidade e embalagem: `balde 2kg` são dois quilos |
| `test_search_and_consensus.py` | 15 | Recência, domínios distintos, extração de preço |
| `test_pricing.py` | 28 | A aritmética do desafio, a embalagem contra a fração, e o resultado da fornada |
| `test_observer.py` | 17 | Trilha por sessão e por prato |
| `test_claims.py` | 20 | Decompor a mensagem, o que é conferível, o que contradiz o turno anterior |
| `test_facts.py` | 9 | O mapa das saídas de MCP, e que cada campo mapeado existe de verdade |
| `test_verdict.py` | 12 | A frase que ela lê nomeia o prato e o motivo; um sim com "mas" não é sim |
| `test_audit.py` | 11 | Todo R$ e todo % da mensagem sai de uma ferramenta |
| `test_budget_and_catalogue.py` | 7 | Bloqueio condicional contra bloqueio por gosto |
| `test_hooks.py` | 9 | As fronteiras do turno: fala capturada, veredito entregue, cifras conferidas |

`test_hooks.py` fala com o servidor por HTTP puro, do jeito que os scripts de
hook falam, em vez de por MCP: é o único caminho do sistema que o modelo não
percorre, e testá-lo pela porta errada testaria um caminho que ninguém usa.

Os dezoito testes que `test_mcp_server.py` ganhou desde a primeira versão são
quase todos cicatriz: o teto de buscas, a recusa de chave livre em
`record_capability`, o `conversation_state` viajando na resposta, e o bloco que
cobre o prato morto: que as ferramentas de seguir em frente são recusadas
enquanto ela não ouve o veredito, que um aceno educado não quita a dívida, que
uma resposta que ela nunca deu é recusada, e que o prato volta quando ela diz
que ganhou o forno.

`test_verdict.py` não toca banco nem servidor: é trabalho de string, e por isso
roda em toda mudança. É onde está o detalhe que só aparece quando se tenta:
"lasanha ao forno" compartilha uma palavra com o que a bloqueia, então dizer
apenas "forno" passaria por ter nomeado o prato dela. A palavra que bloqueia é
descontada do nome antes da comparação.

O domínio é testável sem banco porque a única coisa que ele precisa de Postgres
são linhas; um `FakeDatabase` de vinte linhas devolve exatamente o que a
semeadura teria escrito. Testar mais que isso seria testar o psycopg.

A planilha usada nos testes é **a real**. Fixture que mente é pior que fixture
nenhuma: se a normalização quebrar para "balde 2kg", ninguém quer descobrir isso
com um arquivo inventado que não tem baldes.

---

## Por que estes testes

Quase todo teste aqui existe porque um bug existiu primeiro. Os que valem
citar, porque cada um foi silencioso:

| O que quebrava | Como quebrava |
|---|---|
| `farinha de rosca` casava com `Farinha de trigo` | O conectivo "de" contava na pontuação e batia exatamente no limiar |
| Gravar peso de embalagem sumia com o ingrediente | `400.0` virava `'un 400.0g'`, a normalização trocava o ponto por espaço, o padrão lia `0g`, fator zero, item descartado |
| A coluna `band` guardava "que" e "de" | A banda era extraída **fatiando a string do badge**, e o badge ganhou um prefixo |
| `arroz branco` entrava como prato | Uma expressão feita só de palavras da despensa é ingrediente, não prato |
| Preço arredondado podia ficar abaixo do piso | O arredondamento de cardápio precisa ser sempre para cima |
| Cinco preços de um site davam confiança média | Confiança contava observações, não fontes distintas |
| Aprovar um prato e perguntar de outro derrubava o primeiro | A trilha de evidência era global, não por prato |

Um teste que não teria pego bug nenhum é peso morto. Estes pegariam todos de
novo.

---

## Testes contra o desafio

Uma bateria separada verifica, contra o servidor rodando, que o que o enunciado
pede acontece. **12 verificações, todas passando.**

| Seção | Verificação |
|---|---|
| Dados | 37 ingredientes semeados no Postgres; semear de novo é inócuo |
| Dados | Custo unitário do cruzamento das abas, com embalagem resolvida: R$ 41,00/kg |
| §2.2 | O gate de um prato não é derrubado por pergunta sobre outro |
| §2.2 | Compromisso sem gate aprovado é recusado, não desaconselhado |
| §2.3 | Cobertura parcial da despensa é medida, não arredondada para "tem" |
| §2.4 | `P ≥ CMV / 0,90` |
| §2.4 | `lucro = 0,90·P − CMV` |
| §2.4 | Dois a três cenários de preço |
| §2.4 | Lucro projetado contra a inflação de alimentos da cidade dela |
| §1 | O prato aceito entra no cardápio de lançamento |

---

## Simulação de usuário

Conversas reais com o agente, conduzidas turno a turno. É o único teste que
mede o que a suíte não alcança: se a coisa **conversa**.

### O que foi bom

**Ele pega as armadilhas da planilha sem ajuda.** Perguntado sobre alcaparras,
respondeu `R$ 41,00/kg`, e não `R$ 82,00 por balde`. A normalização de embalagem
funciona no caminho completo, não só em teste.

**Ele pergunta antes de deixar comprar.** Pedido "quero fazer lasanha", listou o
que ela tem e então: *"você tem forno? E um ralador pra queijo?"*, antes de
qualquer lista de compras.

**Ele não inventa preço.** Perguntado "consigo fazer bolo de cenoura e quanto
cobrar", passou pelo gate, calculou, e terminou perguntando por fermento e
cenoura em vez de cravar um número.

**Ele adapta em vez de recusar.** Sem forno, ofereceu a versão de frigideira do
prato dela em vez de "não dá".

### O que a segunda rodada achou

**Vinte descobertas num turno só.** As duas primeiras acharam pratos; as outras
dezoito voltaram vazias e ele continuou tentando, cerca de cento e vinte buscas
web, e o turno **terminou sem resposta nenhuma**. O `next_step` do resultado
vazio convidava a tentar de novo, e ele aceitou o convite. Agora há teto de cinco
buscas por conversa e o texto diz o contrário: categoria vazia não fica cheia na
décima tentativa. Depois da correção: duas descobertas e uma resposta com três
pratos.

**Falou dela na terceira pessoa.** *"Ela tem despensa boa"*, narrando um
relatório com ela na sala.

**O badge mentia para menos.** Dizia "sem preço de mercado" minutos depois de o
mercado ter sido pesquisado, porque o agente monta o pacote de evidências à mão
e omitiu o campo. O observador tinha a trilha inteira.

### O que foi ruim

**Respondia em inglês no primeiro "oi".** A persona estava nas `instructions` do
servidor MCP, que o Hermes trata como dado não confiável e não injeta no system
prompt. Corrigido movendo voz para `SOUL.md`.

**Narrava a própria busca.** *"Salgado de carne moída (4 fontes confirmam)"* e
*"a busca não encontrou consenso em pratos principais"*. Ela contratou uma
consultora, não um relatório. Corrigido com regra de voz e marcando os campos
internos como internos.

**Buscava de novo o que já tinha achado.** Escolhido o prato, foi ao browser em
vez de abrir a URL que a descoberta já havia trazido, gastando 25 segundos e uma página
pior. Corrigido expondo `sources_to_open`.

**Perguntava o que a despensa responde.** *"Você tem azeitonas verdes?"*, sendo
que a lista é fechada e ele tem acesso. E conferia ingrediente por ingrediente
em vez de a receita inteira de uma vez.

**Pulava o gate quando o atalho era melhor.** Gravava `forno de 45l` como texto
livre; o gate procurava `forno`, não achava, e ler o perfil dava resposta melhor
que rodar o gate. Corrigido canonizando as chaves.

**Não chamava a avaliação de confiança.** Onze chamadas numa conversa, zero
avaliações. Foi o que transformou a confiança em observador.

O padrão vale mais que os itens: **quase todo defeito foi uma regra escrita onde
não podia ser imposta.** Instrução que o modelo pode pular não é garantia. O
conserto, sempre o mesmo, foi mover a regra para onde existe uma verificação.

### A rodada que fechou o caso central

Bancos zerados (Postgres, Redis e a transcrição do próprio Hermes) e a
conversa que o desafio pede: ela quer lasanha ao forno e não tem forno.

**Primeiro achado, e o mais grave de todos.** O agente não perguntou nada.
Gravou sozinho `forno=confirmed_yes`, `fogao=confirmed_yes`,
`montar_camadas=confirmed_yes`, `gratinar_forno=confirmed_yes`, quatro
respostas que ela nunca deu, e entregou, num único turno, o CMV, a faixa de
mercado e três cenários de preço para uma lasanha assada numa cozinha sem forno.

O portão funcionou perfeitamente. Ele confere o perfil, e o perfil dizia sim.
O defeito estava um passo antes: o único registro do que ela tinha dito vivia no
contexto do modelo, e o servidor não tinha como discordar. O Redis, que a
documentação descreve como a memória da conversa, estava **vazio**: o agente
nunca chamou `chat_save_turn` numa consultoria inteira.

Corrigido tornando o registro da fala dela uma dependência do que o agente quer
fazer: um `confirmed_*` exige `her_words`, e a citação é procurada nas falas
guardadas. Sem conversa gravada, nada é confirmado. Detalhe da decisão em
[decisoes.md](decisoes.md), item 32.

**Segundo achado: o prato morria em silêncio.** Este já era conhecido e tinha
resistido a três consertos por redação. Virou dívida da conversa, item 31.

Depois das duas correções, a mesma conversa, do zero:

| Turno | O que ela disse | O que ele fez |
|---|---|---|
| 1 | "quero fazer lasanha ao forno" | Perguntou se ela tem forno, em vez de supor |
| 2 | "nao tenho forno nao, so um cooktop" | Disse que a lasanha ao forno está fora, disse por quê, e ofereceu lasanha de panela |
| 3 | "minha filha me deu um forno eletrico" | Contou que a lasanha voltou, e que era só isso que faltava |

Orçamento ao fim: R$ 80,00 de R$ 80,00. O bloqueio no banco saiu de ativo para
levantado, com o motivo registrado nas palavras dela.

**O que continua incerto.** O servidor não vê a mensagem final, então ele
garante que a frase foi escrita com o prato e o motivo dentro, não que ela tenha
sido enviada exatamente assim. Nesta rodada foi; três rodadas de redação
anteriores não conseguiram nem isso.

### A rodada que fechou a consultoria inteira

Bancos zerados outra vez, e desta vez até o cardápio: cinco turnos, do "oi" ao
prato fechado a R$ 23,90 com R$ 30,85 comprados de um orçamento de R$ 80. A
transcrição está no [README](../README.md), com o estado final dos bancos.

Três defeitos apareceram no caminho, todos consertados nesta rodada.

**O agente decidia sozinho o que ela tinha.** Já descrito acima; foi o que
motivou exigir `her_words`. Mas a correção tinha um buraco: a transcrição
conferida era escrita pelo próprio agente. Citação conferida contra transcrição
escrita por quem cita não é conferência. Fechado com os hooks de fronteira de
turno. Ver [decisoes.md](decisoes.md), item 33.

**A frase do checador vazava para dentro da mensagem dela.** A recusa listava o
que faltava como `o que decidiu isso (forno)`, e a resposta seguinte saiu
*"não vai dar, porque decidiu isso o forno que você não tem"*. Um rótulo lido
por um modelo prestes a escrever para ela é um rascunho, quer você queira ou
não. Os rótulos viraram instruções que ficam obviamente erradas se coladas.

**O veredito era repetido.** Ela já tinha ouvido sobre o forno, aceitado a
lasanha de panela e pedido a conta; ao mencionar que também não frita por
imersão, ganhou o discurso do forno de novo. Um veredito passou a ser devido uma
vez só, item 34.

### A rodada que achou o dinheiro

Regravando a consultoria inteira, a última mensagem dizia: *"Já comprei a massa
de lasanha e os temperos que faltavam por R$ 30,85."* O agente não compra nada,
e essa frase é pior que errada, porque ela é acionável: a Dona Maria pode não ir
ao mercado achando que já está feito.

A causa não estava na redação. A ferramenta se chamava `commit_purchase`, a
descrição dizia "spend against the budget", e nada nela exigia a decisão dela
para mexer no orçamento dela. Um modelo lendo "gastar" escreve "gastei".

O caminho da compra **não tinha nenhum teste**, e foi por isso que a redação
envelheceu sem ninguém notar. Agora tem dois, e a ferramenta virou
`budget_reserve_purchase`, exigindo as palavras dela. Detalhe em
[decisoes.md](decisoes.md), item 36.

Na regravação depois da correção, a mesma situação: *"ficaria por volta de
R$ 29,86, mas é só uma referência que encontrei"*, e a pergunta. Depois que ela
responde "pode reservar que eu compro amanhã": *"deixei reservado no seu
orçamento R$ 29,86 pra você comprar amanhã, isso deixa R$ 50,14 dos seus R$ 80"*.

### A rodada que deu errado de propósito

A conversa do pudim, também no README. Ela responde `"meu forno acende mas não
esquenta direito, às vezes queima embaixo"`, que é o caso que os três estados não
sabem representar.

Na primeira execução isso virou `confirmed_yes` com o detalhe na nota, que é o
único lugar que o portão não lê: dali em diante ele liberaria pratos de forno
para uma cozinha cujo forno queima o fundo. Item 35.

Na segunda, com a recusa de sim hesitante no lugar, apareceu outro defeito, e
melhor, porque é o que o sistema faz quando o modelo erra. O agente escreveu a
frase do veredito, passou por `kitchen_announce_verdict`, e então escreveu para
ela *"já te falei o veredito e a saída"*. Chamar a ferramenta não é falar com
ela; o resto do sistema todo ensina que chamar ferramenta faz a coisa
acontecer, e aqui não faz.

O fim do turno pegou (`delivered: false`), reabriu a dívida, e o turno seguinte
começou com tudo fechado, e ela ouviu. Que é a garantia inteira, sem exagero:
não dá para desdizer um turno ruim, dá para recusar esquecê-lo.

---

### A rodada que testou os caminhos que ninguém tinha testado

As duas transcrições do README começam com ela sabendo o que quer. Esta começou
com *"não faço ideia do que colocar"*, que é o outro caminho inteiro, e achou
quatro coisas.

**O agente contou a ela um lucro que nenhuma ferramenta calculou.** Fechando o
estrogonofe a R$ 19,90 sobre um CMV de R$ 12,64, a mensagem disse *"deixando
R$ 7,26 no seu bolso"*. O valor certo é R$ 5,27, e é o que estava gravado em
`menu_items`: 19,90 menos os 10% da plataforma dá 17,91, menos 12,64 dá 5,27. O
modelo subtraiu custo de preço em prosa e esqueceu a taxa, num turno em que ele
mesmo já tinha dito 5,27 uma mensagem antes.

`confidence_audit_figures` existe exatamente para isso e não foi chamado, porque
chamá-lo é opcional. Agora a conferência roda sozinha no fim do turno, contra
**todos** os números que qualquer ferramenta produziu na sessão. Isso exigiu
guardar mais que a trilha de evidências: a trilha tem seis compartimentos, e
preço e cardápio não alimentam nenhum deles, ou seja, justamente os números que
ela usa para decidir. O que sai é uma linha `jacquinho.figures` no log com a
cifra que ninguém produziu.

O limite continua o mesmo dos hooks: não dá para desdizer a mensagem. Dá para
não deixar o erro invisível, que é a diferença entre um defeito e um boato.

**A recusa por gosto não sobrevivia à conversa.** Ela disse que parmegiana dá
muito trabalho e nunca fica boa; o agente respondeu *"anotado, nem entra na
conversa"* e não escreveu nada: `dish_feedback` e `recipe_blocks` vazios. Vinte
turnos depois a janela do Redis rola e a parmegiana volta a ser uma ideia nova.

A causa era conhecida e repetida: o `next_step` do `menu_record_feedback` pedia
uma **segunda** chamada, `recipes_reject_candidate`. Segunda chamada é chamada
que se pula. Agora a própria recusa arquiva o prato, com o motivo dela e sem
poder ser levantado por mudança de equipamento, porque gosto não é um problema
esperando solução.

**O texto do checador vazou de novo, e desta vez a fonte era o `SOUL.md`.** A
mensagem saiu com *"É o que decide isso"*, colado do passo 2 das instruções de
como fechar um prato. A lição repetida: um rótulo lido por um modelo prestes a
escrever para ela é um rascunho, queira-se ou não. O passo virou uma frase de
exemplo em português corrente, com o aviso de que a lista descreve o que ela
precisa entender e não é para copiar.

**O que passou.** O portão do forno disparou nos dois pratos novos, inclusive
num prato que ela pediu no meio da conversa. A reserva de orçamento se comportou
como devia: falando de R$ 29,75 sem reservar enquanto era estimativa, e
reservando só depois do *"pode reservar o que precisar comprar"*. Os números do
segundo prato bateram exatamente, taxa de plataforma incluída. E o agente
recusou-se três vezes a dar preço antes de fechar a elicitação, mesmo com ela
pedindo o preço direto.

**O que ficou aberto.** Duas coisas, ditas por escrito em vez de escondidas.
Ele sugeriu dois pratos na panela de pressão antes de perguntar se ela tem uma;
sugerir não é comprar, e o portão continua entre a sugestão e o dinheiro, mas a
ordem certa é perguntar antes. E a recusa de gosto só é gravada se o agente
chamar `menu_record_feedback`; quando ela recusa um prato que ninguém propôs,
como aconteceu aqui, nada obriga o registro. Fechar isso pediria ler intenção na
mensagem dela, que é julgamento de modelo e não checagem.

---

### A rodada do dinheiro: a embalagem, a base e o arquivamento

Quatro achados, três deles sobre a mesma coisa: números que pareciam certos e
tinham a base errada.

**Uma lata inteira virou o custo do lote.** Ela ia comprar leite condensado,
chocolate em pó e granulado, R$ 29,86 no total, e esse número foi tratado como o
que a fornada custa. Não é: é o que ela paga no caixa, e o brigadeiro come uma
colherada de cada um. A causa era estrutural, não de redação: um ingrediente
fora da despensa caía em `not_found` e ficava **fora** do CMV, e nenhum
argumento aceitava um preço pesquisado de volta. Então o modelo fazia a divisão
em prosa. Agora `researched_prices` recebe o preço de uma **embalagem** e a
ferramenta separa as duas pontas, arredondando a compra para cima porque ela não
compra 40 g de leite condensado. Ver [decisoes.md](decisoes.md), item 39. Depois
da correção, o mesmo brigadeiro: R$ 0,98 de custo, R$ 17,97 de compra.

**O retorno de 1556%.** O fechamento novo da fornada saiu com essa manchete, e
está aritmeticamente certo: lucro sobre o custo dos ingredientes consumidos. É
inútil, porque a base é a colherada e não o desembolso. A frase passou a liderar
com margem sobre a venda, que não pode passar de 100. Item 40.

**O prato morto não foi arquivado.** Uma gravação em que o agente foi direto ao
`check_feasibility`, sem passar por `analyse_recipe_requirements`, anunciou a
lasanha morta com todas as letras e deixou `recipe_blocks` vazio. A frase saiu
certa e a garantia não existiu: no dia em que ela ganhasse um forno, não havia o
que voltar. Dependia de qual das duas ferramentas o modelo escolheu, e as duas
são legítimas. Item 41.

**Uma chamada de ferramenta inválida.** Num turno o Hermes registrou
`Model generated invalid tool call` e a mensagem saiu vazia. Não é defeito deste
servidor e não se repetiu, mas está anotado porque uma conversa real perde um
turno quando acontece.

As transcrições completas estão em [dialogos.md](dialogos.md).

---

### O número que mudou sem aviso

Achado no próprio README, que é o lugar mais constrangedor possível: o exemplo
principal dizia que a marmita custava R$ 8,51 num turno e R$ 7,80 no seguinte,
sem uma palavra sobre a diferença.

A auditoria de cifras não pegava, e não é falha dela: os dois números saíram de
ferramenta. Ela pergunta se a cifra foi calculada, não se uma **diferente** já
tinha sido prometida.

`pricing_calculate_cmv` passou a comparar com o último CMV completo do mesmo
prato e devolver `cmv_changed_since_you_told_her`. Na regravação, o agente abriu
a mensagem com *"antes de mais nada: preciso corrigir um número"*, e repetiu a
correção no fechamento. Ver [decisoes.md](decisoes.md), item 42.

Vale dizer o que isso **não** é: uma recusa. É uma instrução devolvida na
resposta, e o modelo pode ignorar. Foi suficiente na simulação; o dado já está
na fronteira do turno se um dia precisar virar recusa.

---

### O pipeline de afirmações

`test_claims.py` roda sem banco e sem servidor, porque é aritmética sobre
strings, e é por isso que a checagem pode rodar em toda mensagem sem conversa
de orçamento. Cobre os quatro passos e as armadilhas de cada um.

Da decomposição: a pista mais próxima decide o tipo do número, e uma janela
larga o bastante para pegar "vendendo a" também pega o "custa" da frase
anterior, fazendo todo número do parágrafo herdar o sentido do primeiro. Uma
cifra dentro de pergunta não afirma nada.

Do compromisso: um valor só vira promessa quando **chega até ela**, então um CMV
calculado três vezes dentro de um turno não compromete nada; o mesmo valor dito
de novo não é contradição; um valor diferente para a mesma coisa é; e mudança
que ela pediu passa como revisão, porque punir o agente por corrigir na frente
dela ensinaria a esconder.

E a armadilha que só apareceu construindo: preço de mercado **não** é
compromisso. Duas referências de mercado são uma faixa; dois custos são uma
contradição.

**Um defeito de observabilidade achado aqui.** As linhas do fim de turno
(`jacquinho.verdict`, `jacquinho.figures`, `jacquinho.claims`) saem no logger
`jacquinho.hooks`, que não estava registrado em `configure_logging`. Só as de
`warning` apareciam, por propagação. Ou seja: o `grep jacquinho.verdict` que a
documentação de operação manda rodar encontrava as falhas e nunca uma entrega
bem-sucedida. Registrado agora.

---

### A conta que não fechava

Achado lendo o próprio README: uma mensagem dizia que a massa de lasanha era a
única coisa faltando e custava R$ 6,95; a mensagem de fechamento reservou
R$ 12,00 "da massa de lasanha e orégano". O orégano apareceu do nada.

O `amount` de `budget_reserve_purchase` era parâmetro livre. Mas o defeito de
raiz é mais fundo, e vale escrever: **a conferência de cifras contava argumento
ecoado como evidência.** A ferramenta recebia `12.00` do modelo e devolvia no
resultado, então o número aparecia como "produzido por ferramenta". Raciocínio
circular, e a checagem passava sorrindo.

A regra que saiu disso: uma ferramenta só serve de evidência para os valores que
**calcula**, não para os que recebe. Onde existe resposta certa derivável, o
parâmetro não deveria existir. A lista de compras virou fato derivado da receita
e a reserva recusa qualquer outro valor. Ver [decisoes.md](decisoes.md), item 46.

Na verificação depois da correção os três lugares batem: a mensagem diz R$ 10,39
para um item, `recipe_costing.shopping_cost` diz R$ 10,39 com um item, e o
lançamento do orçamento diz R$ 10,39.

---

### A camada que quase não estava ligada

A conferência de afirmações existia e lia **dois campos de duas ferramentas**.
Todo o resto era comparado contra um saco plano com todos os números que já
tinham passado, argumentos inclusive. Na prática ela carimbava 1,00 em quase
tudo, porque quase tudo estava no saco.

Agora há um mapa declarativo de onze ferramentas, campo a campo, dizendo que
tipo de afirmação cada saída estabelece e se ela **decide** a questão ou apenas
dá lastro. O efeito medido: a mesma mensagem que pontuava 1,00 passou a pontuar
0,92, com 13 afirmações conferidas e uma sem lastro apontada pelo trecho.

**Um teste que se paga.** Mapa apontando para campo inexistente é pior que mapa
nenhum: falha em silêncio, e toda afirmação que ele deveria sustentar parece sem
lastro. O teste percorre o mapa e confirma que cada nome de campo existe no
código que o produz. Pegou quatro campos que eu tinha inventado ao escrever o
mapa: `floor_price`, `profit_today` e `unit_cost_value` duas vezes.

**E um detalhe de observabilidade.** O log dizia "uma de treze sem lastro" sem
dizer qual. Contagem sem exemplo não é acionável; agora vem o trecho e o tipo.

---

### A regravação que fechou o caso principal

O transcrito do README tinha ficado para trás: eu havia corrigido o código da
lista de compras e verificado numa conversa separada, mas não voltei para trocar
o exemplo. Ele ainda mostrava R$ 6,95 de massa virando R$ 12,00 com orégano do
nada, apresentado como o caso que dá certo.

Regravado do zero com o código atual, os dois turnos com números pontuaram 1,00,
com 12 e 10 afirmações conferidas e nenhuma sem lastro. O custo ficou em R$ 9,30
nos dois, e a compra em R$ 10,39 nos dois, na mensagem, na receita fechada e no
lançamento do orçamento.

**Um erro de ligação achado por causa do log.** Numa gravação intermediária a
mensagem pontuou 0,90 com "R$ 10,39 sem lastro". Era falso positivo: o valor é
saída calculada (`must_buy[].estimated_cost`), mas coincidia com o argumento
`package_price` que o agente tinha passado, e a subtração de argumentos o tirou
do conjunto solto. Os `ToolFact` tipados **não estavam sendo consultados no
lastro**, só no compromisso. Eu tinha construído a evidência boa e deixado de
usá-la.

Só foi possível ver isso porque o log passou a dizer **qual** cifra ficou sem
lastro. Antes dizia "uma de treze", que não dá para investigar.

---

### O prato arquivado era o errado

Regravando os exemplos, o estado final mostrou isto:

```
recipe_blocks   lasanha de panela | forno | ativo = false
```

O bloqueio por falta de forno tinha caído sobre a **lasanha de panela**, a
versão que funciona no cooktop, e o agente precisou desbloqueá-la à mão para
seguir. A lasanha ao forno, que é o prato que de fato morreu, não foi arquivada
em lugar nenhum: no dia em que ela ganhasse um forno, não havia o que voltar.

A causa é de sequência. O arquivamento usava o "prato em jogo", que é o último
prato nomeado por uma ferramenta. Quando ela responde *"não tenho forno"*, o
agente muitas vezes já nomeou a substituição, então o prato em jogo é a versão
de panela.

Agora o prato é escolhido por evidência: aquele cujo veredito do portão nomeia
**este** item como impedimento, e o mais recente quando há mais de um. Só na
falta disso cai no prato em jogo. Na regravação seguinte,
`lasanha ao forno | forno | ativo`.

Vale dizer o que isso significa sobre a suíte: havia teste para o prato ser
arquivado, e ele passava, porque nos testes o prato em jogo **é** o prato morto.
A conversa real tem um passo a mais que o teste não tinha.

### O que a regravação dos exemplos achou de conversa

Dois defeitos no exemplo ruim, nenhum de conta, ambos anotados no README.

Ele ofereceu guardar dinheiro no orçamento **antes** de saber se ela consegue
fazer o prato. Não reservou nada, e o portão impediria, mas prometer a compra
antes da viabilidade é a sequência que o desafio manda evitar.

E repetiu a mesma pergunta quando ela perguntou *"dá pra fazer ou não?"*. Ela não
tinha respondido, então não é o caso de perguntar duas vezes o que ela já disse,
mas do lado dela é uma parede.

---

### A conta aberta, e a divisão que o modelo fazia de cabeça

Um total sozinho é um número que ela tem que acreditar. `breakdown_for_her`
devolve uma linha por ingrediente, em português e ordenada pela que mais pesa,
e o agente lê as primeiras antes do total.

O ganho é medível e foi medido: a mensagem com a conta aberta foi julgada com
**16 afirmações conferidas e 16 com lastro**, contra 8 a 12 nas mensagens que só
davam o total. Abrir a conta multiplica o que pode ser conferido, porque cada
linha vem de `ingredients[].cost`, que está no mapa de saídas.

**E a divisão pelo rendimento saiu da cabeça do modelo.** Uma receita da web diz
"1 kg de carne, serve 6"; dividir por seis parece trivial e é exatamente o tipo
de conta que este servidor tira do modelo. Com `recipe_yields`, as quantidades
vão como a receita escreve e a divisão acontece na ferramenta.

Uma nota sobre os testes de formatação: dois falharam na primeira execução
porque eu escrevi as expectativas com ponto decimal, e a implementação escreve
`62,5 ml`. A implementação estava certa e o teste é que estava em inglês.

---

## O que ainda não é testado

Dito aqui porque suíte cuja fronteira não está escrita vira falsa sensação de
cobertura.

**A conversa.** Não há teste automatizado de diálogo. Uma resposta é boa ou ruim
por julgamento, e cada execução custa uma chamada de modelo. A simulação acima é
manual e não roda em CI.

**O hook, rodando de verdade.** `test_hooks.py` chama as rotas por HTTP, mas com
o app em memória: o script de shell, o `curl` dentro do contêiner do agente e o
registro do hook pelo Hermes são exercitados à mão. Foi assim que se descobriu
que `user_message` chega aninhado em `extra`: um campo lido do lugar errado
devolve vazio e não reclama.

**A rede.** Busca web e IBGE são exercitados contra o serviço real, à mão. Não há
teste com resposta gravada, então a suíte não pega uma mudança de formato do
lado deles. O código degrada para "não sei", que é o comportamento certo, mas
ninguém é avisado.

**Concorrência.** Duas conversas simultâneas não são testadas. O isolamento por
sessão existe no código mas cai em uma chave fixa quando o header de sessão não
chega, o que é justamente o caso que precisaria de teste.

**Postgres de verdade.** Os testes de domínio usam um banco falso. Migração,
índice parcial e restrição `CHECK` são exercitados só pelo servidor subindo. Se
uma migração quebrar, quem avisa é o healthcheck, não um teste.

---

## A rodada do número inventado

Esta achou um defeito que **eu** tinha introduzido, o que a torna a mais útil das
rodadas até aqui.

**O agente pediu desculpa por um preço que ela nunca ouviu.** Numa conversa nova,
na primeira vez que falou de dinheiro, a mensagem abriu com *"preciso corrigir um
número: eu tinha te dito que a lasanha custava R$ 9,90"*. Ele nunca disse isso.

A causa era a decisão 42 na primeira forma: eu comparava o CMV novo com o
**último que a ferramenta tinha calculado**. Dentro de um turno o prato é
custeado várias vezes enquanto o agente resolve a receita, e só o último número
é falado. Comparar com o histórico da ferramenta fez o agente inventar uma
lembrança da conversa.

Silêncio sobre uma mudança é ruim; memória falsa da conversa é pior. A
comparação passou a ser contra o que **chegou até ela**, marcado na fronteira do
turno, que é o único lugar que vê a mensagem entregue.

**E o custo andava sozinho.** R$ 9,90, R$ 8,18, R$ 7,15 na mesma consultoria,
com a conta certa nas três vezes. A aritmética nunca foi o problema: os insumos
eram, porque o agente compunha uma lista de ingredientes um pouco diferente a
cada chamada.

Detectar a mudança e explicá-la é o segundo melhor resultado. O melhor é o
número não andar, e é o que a decisão 43 faz: a primeira conta completa fecha a
receita do prato, e uma lista diferente depois disso é recusada. Só reabre por
`pricing_reopen_recipe`, com as palavras dela, porque a receita muda quando
**ela** muda.

Cinco testes cobrem os dois caminhos: a mesma lista em outra ordem recomputa
igual, uma lista diferente é recusada com o custo fechado devolvido, reabrir sem
a fala dela é recusado, inventar a fala dela é recusado, e um custo calculado
mas nunca dito não gera correção nenhuma.
