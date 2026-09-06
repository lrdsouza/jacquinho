# Testes

![Unitários](https://img.shields.io/badge/testes-277-success)
![Suítes](https://img.shields.io/badge/suítes-15-0A7EA4)
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

**277 testes, 15 suítes, ~60 s** (o tempo é quase todo subida de contêiner e
ida ao Postgres; a parte de domínio roda em cerca de dois segundos).

| Suíte | Testes | O que garante |
|---|---:|---|
| `test_mcp_server.py` | 46 | O servidor sobe, monta, recusa, não deixa o prato dela morrer em silêncio, não gasta o dinheiro dela e não usa carne que ela já gastou |
| `test_pricing.py` | 32 | A aritmética do desafio, a embalagem contra a fração, e o resultado da fornada |
| `test_pantry.py` | 28 | Semeadura, custo unitário, casamento de nomes, e o estoque finito que baixa e volta |
| `test_elicitation.py` | 24 | Catálogo, gate, exigências lidas da receita |
| `test_confidence.py` | 22 | Nota por afirmação, bandas, badge, impedimentos |
| `test_claims.py` | 20 | Decompor a mensagem, o que é conferível, o que contradiz o turno anterior |
| `test_observer.py` | 17 | Trilha por sessão e por prato |
| `test_units.py` | 15 | Unidade e embalagem: `balde 2kg` são dois quilos |
| `test_search_and_consensus.py` | 15 | Recência, domínios distintos, extração de preço |
| `test_verdict.py` | 12 | A frase que ela lê nomeia o prato e o motivo; um sim com "mas" não é sim |
| `test_audit.py` | 11 | Todo R$ e todo % da mensagem sai de uma ferramenta |
| `test_pacing.py` | 10 | A mensagem vai em partes: as mesmas palavras passam quebradas e reprovam soldadas |
| `test_facts.py` | 9 | O mapa das saídas de MCP, e que cada campo mapeado existe de verdade |
| `test_hooks.py` | 9 | As fronteiras do turno: fala capturada, veredito entregue, cifras conferidas |
| `test_budget_and_catalogue.py` | 7 | Bloqueio condicional contra bloqueio por gosto |

`test_hooks.py` fala com o servidor por HTTP puro, do jeito que os scripts de
hook falam, em vez de por MCP: é o único caminho do sistema que o modelo não
percorre, e testá-lo pela porta errada testaria um caminho que ninguém usa.

`test_mcp_server.py` é a suíte mais pesada porque cobre as garantias que só
existem com o servidor de pé: o teto de buscas por sessão, a recusa de chave
livre em `record_capability`, o `conversation_state` viajando em toda resposta, e
o bloco inteiro do prato morto. Esse último vale listar: as ferramentas de seguir
em frente são recusadas enquanto ela não ouve o veredito, um aceno educado não
quita a dívida, uma resposta que ela nunca deu é recusada, e o prato volta
sozinho quando ela diz que ganhou o forno.

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

Um teste que não pegaria defeito nenhum é peso morto. A suíte é escrita contra
os pontos onde este sistema erra em silêncio, que são sempre os mesmos sete
lugares:

| O que o teste protege | Por que é silencioso |
|---|---|
| Casamento de nomes de ingrediente | `farinha de rosca` e `Farinha de trigo` compartilham tokens sem significado, e um quase-acerto é indistinguível de um acerto |
| Normalização de peso de embalagem | Um fator zero descarta o ingrediente sem erro nenhum, e o custo simplesmente sai menor |
| Banda de confiança lida de campo, não de texto | Extrair a banda fatiando a string de exibição quebra na hora em que a string muda |
| Prato contra ingrediente | Uma expressão feita só de palavras da despensa é ingrediente, e entra no cardápio como se fosse prato |
| Arredondamento de preço | Arredondar para baixo pode pousar abaixo do piso, e o piso é a fronteira do prejuízo |
| Confiança contando fontes distintas | Cinco preços do mesmo site parecem consenso e não são |
| Trilha de evidência por prato | Uma trilha global faz a pergunta sobre um prato derrubar o gate de outro |

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

Conversas reais com o agente, conduzidas turno a turno, com os bancos zerados
antes de cada uma e **uma conversa por vez**. É o único teste que mede o que a
suíte não alcança: se a coisa **conversa**.

Não roda em CI. Cada turno custa uma chamada de modelo e leva de sessenta a
noventa segundos, e o julgamento do resultado é humano. As transcrições, boas e
ruins, estão em [dialogos.md](dialogos.md).

### O que cada rodada verifica

Uma rodada só vale se o estado no banco for conferido depois, com `psql`, e cada
cifra conferida à mão contra a taxa de plataforma de 10%. O roteiro:

| Verificação | Como se confere |
|---|---|
| O gate segurou a compra | `kitchen_capabilities` não tem `unknown` para o prato, e `budget_entries` está vazio até ela concordar |
| O prato morto foi anunciado | `jacquinho.verdict` com `delivered: true` no log do turno |
| Nenhuma cifra foi inventada | `jacquinho.figures` ausente, ou com a lista `unsupported` vazia |
| A mensagem tem lastro | `jacquinho.claims` com `score: 1.0` e nenhuma contradição |
| O custo não andou | O mesmo número em todos os turnos, e `recipe_costing` fechado para o prato |
| O estoque baixou certo | `pantry_usage` com a fornada inteira, e só depois do aceite dela |
| A mensagem foi em partes | `jacquinho.pacing` ausente no log do turno |
| Nada de selo na mensagem | Nenhum `〔 〕`, nenhuma banda, nenhuma porcentagem de confiança |

### O que a simulação encontra hoje

Duas coisas, e as duas estão na conversa que deu errado do
[README](../README.md).

**Pergunta fechada dela recebe o turno anterior de volta.** Quando ela pergunta
*"dá pra fazer ou não?"*, o que volta é a explicação inteira outra vez. O
servidor sabe onde a consultoria está, porque `conversation_state` viaja em toda
resposta de ferramenta, e não sabe o que a última frase **dela** pediu.

**O portão pergunta um item por vez.** É correto e é impaciente: quatro turnos
podem passar sem que ela veja um número, porque cada versão nova da receita traz
exigência nova. Correção e paciência estão em conflito, e hoje a correção ganha
sozinha.

Ambas estão no README como trabalho futuro, com o desenho proposto.

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
