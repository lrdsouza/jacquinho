# Testes

![Unitários](https://img.shields.io/badge/testes-140-success)
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

**163 testes, 10 suítes, ~9 s** (o tempo é quase todo subida de contêiner).

| Suíte | Testes | O que garante |
|---|---:|---|
| `test_elicitation.py` | 24 | Catálogo, gate, exigências lidas da receita |
| `test_mcp_server.py` | 23 | O servidor sobe, monta, recusa e fecha o prato morto |
| `test_confidence.py` | 22 | Nota por afirmação, bandas, badge, impedimentos |
| `test_pantry.py` | 20 | Semeadura, custo unitário, casamento de nomes |
| `test_units.py` | 15 | Unidade e embalagem: `balde 2kg` são dois quilos |
| `test_search_and_consensus.py` | 15 | Recência, domínios distintos, extração de preço |
| `test_pricing.py` | 13 | A aritmética do desafio |
| `test_observer.py` | 13 | Trilha por sessão e por prato |
| `test_audit.py` | 11 | Todo R$ e todo % da mensagem sai de uma ferramenta |
| `test_budget_and_catalogue.py` | 7 | Bloqueio condicional contra bloqueio por gosto |

Os doze testes que `test_mcp_server.py` ganhou desde a primeira versão são quase
todos cicatriz: o teto de buscas, a recusa de chave livre em `record_capability`,
o `conversation_state` viajando na resposta, e os dois que cobrem o prato morto —
gravar o "não tenho forno" devolve o veredito da lasanha na mesma resposta, e
pedir a próxima pergunta também o devolve, porque pedir a próxima pergunta é
exatamente o instante em que o agente ia mudar de assunto.

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
| Dados | 37 ingredientes semeados no Postgres; re-semear é inócuo |
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
respondeu `R$ 41,00/kg` — não `R$ 82,00 por balde`. A normalização de embalagem
funciona no caminho completo, não só em teste.

**Ele pergunta antes de deixar comprar.** Pedido "quero fazer lasanha", listou o
que ela tem e então: *"você tem forno? E um ralador pra queijo?"* — antes de
qualquer lista de compras.

**Ele não inventa preço.** Perguntado "consigo fazer bolo de cenoura e quanto
cobrar", passou pelo gate, calculou, e terminou perguntando por fermento e
cenoura em vez de cravar um número.

**Ele adapta em vez de recusar.** Sem forno, ofereceu a versão de frigideira do
prato dela em vez de "não dá".

### O que a segunda rodada achou

**Vinte descobertas num turno só.** As duas primeiras acharam pratos; as outras
dezoito voltaram vazias e ele continuou tentando — cerca de cento e vinte buscas
web, e o turno **terminou sem resposta nenhuma**. O `next_step` do resultado
vazio convidava a tentar de novo, e ele aceitou o convite. Agora há teto de cinco
buscas por conversa e o texto diz o contrário: categoria vazia não fica cheia na
décima tentativa. Depois da correção: duas descobertas e uma resposta com três
pratos.

**Falou dela na terceira pessoa.** *"Ela tem despensa boa"* — narrando um
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
vez de abrir a URL que a descoberta já havia trazido — 25 segundos e uma página
pior. Corrigido expondo `sources_to_open`.

**Perguntava o que a despensa responde.** *"Você tem azeitonas verdes?"* — sendo
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

---

## O que ainda não é testado

Dito aqui porque suíte cuja fronteira não está escrita vira falsa sensação de
cobertura.

**A conversa.** Não há teste automatizado de diálogo. Uma resposta é boa ou ruim
por julgamento, e cada execução custa uma chamada de modelo. A simulação acima é
manual e não roda em CI.

**A rede.** Busca web e IBGE são exercitados contra o serviço real, à mão. Não há
teste com resposta gravada, então a suíte não pega uma mudança de formato do
lado deles — o código degrada para "não sei", que é o comportamento certo, mas
ninguém é avisado.

**Concorrência.** Duas conversas simultâneas não são testadas. O isolamento por
sessão existe no código mas cai em uma chave fixa quando o header de sessão não
chega, o que é justamente o caso que precisaria de teste.

**Postgres de verdade.** Os testes de domínio usam um banco falso. Migração,
índice parcial e restrição `CHECK` são exercitados só pelo servidor subindo — se
uma migração quebrar, quem avisa é o healthcheck, não um teste.
