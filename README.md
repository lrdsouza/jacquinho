# Jacquinho, seu Sous-chef

![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![FastMCP](https://img.shields.io/badge/FastMCP-4.0.3-6E56CF)
![MCP](https://img.shields.io/badge/protocolo-MCP%202025--06--18-0A7EA4)
![Hermes Agent](https://img.shields.io/badge/agente-Hermes-1F2937)
![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)
![Redis](https://img.shields.io/badge/redis-7-DC382D?logo=redis&logoColor=white)
![Postgres](https://img.shields.io/badge/postgres-17-4169E1?logo=postgresql&logoColor=white)
![Modelo](https://img.shields.io/badge/modelo-Claude%20Sonnet%205-D97757)
![Servidores MCP](https://img.shields.io/badge/servidores%20MCP-11-success)
![Ferramentas](https://img.shields.io/badge/ferramentas-59-success)
![Testes](https://img.shields.io/badge/testes-276-success)

Um sous-chef de IA para a **Dona Maria**, cozinheira que está abrindo o primeiro
delivery dela, o *Sabor da Maria*. Ela sabe cozinhar. O que ela não sabe é quais
pratos a despensa dela consegue produzir, se a cozinha dela dá conta de
fazê-los, e quanto cobrar para o delivery valer a pena.

Sous-chef, e não chefe: **quem decide o prato, o preço e a compra é ela.** Ele lê
a despensa, pergunta o que não sabe, faz as contas e abre os números.

E é construído de modo que **todo número que ele diz veio de uma chamada de
ferramenta, nunca da memória do modelo**.

> *O nome é uma homenagem ao chef **Érick Jacquin**, e o sotaque francês
> acaba aí: o Jacquinho fala português claro e não grita com ninguém.*

## Índice

- [Começando](#começando)
- [Uma consultoria que deu certo](#uma-consultoria-que-deu-certo)
- [Uma conversa que deu errado](#uma-conversa-que-deu-errado)
- [As decisões que sustentam isso](#as-decisões-que-sustentam-isso)
- [Onde cada exigência do desafio foi cumprida](#onde-cada-exigência-do-desafio-foi-cumprida)
- [O que eu não fiz, e por quê](#o-que-eu-não-fiz-e-por-quê)
- [Documentação](#documentação)

---

## Começando

```bash
./bin/jacquinho install     # cria o link em ~/.local/bin
jacquinho login             # autoriza com a conta Anthropic Pro
jacquinho                   # abre o chat
```

A credencial é a de uma conta Anthropic no plano **Pro**, autorizada por OAuth.
Não há chave de API porque o plano Pro não emite uma. Outros provedores têm bloco
pronto em `dockerfile/hermes-config.yaml`.

Comandos úteis: `jacquinho status`, `jacquinho tools`, `jacquinho confidence`
(acompanha ao vivo o quanto ele confia no que vai dizer), `jacquinho test`,
`jacquinho reset`. O passo a passo completo, os modos de falha e as linhas de log
que valem `grep` estão em **[docs/operacao.md](docs/operacao.md)**.

---

## Uma consultoria que deu certo

Transcrição real, bancos zerados. Dois pratos, e o segundo encontra a despensa
como o primeiro a deixou. Nada foi reescrito: as falas estão palavra por palavra,
e o que está entre colchetes são turnos de cozinha inteiros que ficaram de fora
para o exemplo caber.

```
Dona Maria ▸ oi! vou começar a vender marmita por delivery. quero fazer
             escondidinho de carne moída, é o que sai melhor aqui em casa.
             faço 8 marmitas por fornada

Jacquinho  ▸ Escondidinho de carne moída combina muito bem com sua despensa!
             Você já tem quase tudo: batata, carne moída, mussarela, cebola,
             alho, leite, manteiga. Só falta a pimenta branca.
             Antes de fechar, preciso saber uma coisa da sua cozinha: você tem
             forno? Funciona bem, assa por igual? Pergunto porque esse prato
             vai gratinado no forno.

Dona Maria ▸ tenho forno a gás que assa por igual, fogão de 4 bocas, panela
             grande, espremedor de batata e refratário. e tenho prática com
             purê e com refogado, faço há anos. porciono na balança

Jacquinho  ▸ Sua cozinha tá anotada e o escondidinho de carne moída fechou o
             portão: seu forno assa por igual, você já manja de refogado e de
             purê há anos, e o refratário dá conta do gratinado.
             Cada porção leva:
             - 70 g de carne moída: R$ 1,96
             - 40 g de mussarela: R$ 1,60
             - 100 g de batata: R$ 0,60
             - 39 g de tomate: R$ 0,31
             - 0,2 g de pimenta-do-reino: R$ 0,12
             - 24 ml de leite: R$ 0,12
             - e o resto (manteiga, azeite, cebola, alho, sal): R$ 0,28
             Dá R$ 5,00 por porção pra você fazer.
             Só falta uma coisa na sua despensa: pimenta-do-reino. Um potinho
             de 15g custa uns R$ 8,99 e rende várias fornadas. Isso deixaria
             R$ 71,01 dos seus R$ 80 pra próxima fornada.
             Achei pouca referência firme de preço pra esse prato específico,
             então trate como indicativo: marmita parecida gira uns R$ 24 por
             aí. Vendendo a R$ 24,90, sobram R$ 17,41 por marmita pra você.
             Quer fechar nesse preço, ou prefere outro?

Dona Maria ▸ vou vender a 24,90. pode colocar no cardápio e reservar a compra

             [entra no cardápio, e a fornada de 8 tira 560 g de patinho dos
              1,5 kg dela]

Dona Maria ▸ gostei! agora quero botar um segundo prato no cardápio: macarrão
             à bolonhesa, também com carne moída. essa fornada eu faço maior,
             18 marmitas

             [a bolonhesa exige peneira, ralador, escumadeira, tábua, prática
              de molho e de massa, e onde descartar a gordura do bacon. Ele
              pergunta tudo isso, um por turno, antes de qualquer conta]

Jacquinho  ▸ Cada porção leva:
             - 100 g de carne moída: R$ 2,80
             - 17 ml de azeite: R$ 1,05
             - 20 g de parmesão ralado: R$ 0,86
             - 50 g de macarrão espaguete: R$ 0,70
             - 80 g de tomate: R$ 0,64
             - 20 g de bacon: R$ 0,48
             - e o resto (cenoura, cebola, pimenta-do-reino, sal): R$ 0,16
             Dá R$ 6,70 por porção pra você fazer.
             Da carne moída você tinha 1,5 kg; o escondidinho levou 560 g e
             sobraram 940 g. Essa fornada de bolonhesa (18 marmitas) pede
             1,8 kg, então faltam 860 g pra comprar — uns R$ 24,08.
             Do parmesão você tinha 200 g; a fornada pede 360 g, faltam 160 g
             — uns R$ 6,86.
             Cenoura e pimenta-do-reino não estão na sua despensa: um pacote de
             1 kg de cenoura sai por R$ 8,99, e um potinho de 100 g de
             pimenta-do-reino por R$ 8,49.
             No total, a compra fica em R$ 48,42. Isso deixa R$ 22,59 dos seus
             R$ 71,01 pra próxima fornada, se você comprar tudo isso.
             Marmita parecida de macarrão à bolonhesa está saindo entre R$ 18 e
             R$ 29,90 por aí — achei poucas referências, então trate como
             indicativo. Três opções pra você:
             - vendendo a R$ 18,90 → sobram R$ 10,31 por porção pra você
             - vendendo a R$ 25,90 → sobram R$ 16,61 por porção pra você
             - vendendo a R$ 29,90 → sobram R$ 20,21 por porção pra você
             Qual preço você quer colocar?
```

### O estoque dela acaba, e ela ouve para onde foi

A frase que faz esta conversa valer é *"o escondidinho levou 560 g e sobraram
940 g"*. Um "faltam 860 g" solto parece erro de planilha, e o que ela faz com um
erro de planilha é duvidar do número em vez de comprar a carne.

Nada disso é lembrança do modelo. Quando o escondidinho entrou no cardápio, a
fornada dele saiu da despensa, e o Postgres guarda para onde:

```
 dish                         | ingredient_key         | quantity | portions
------------------------------+------------------------+----------+----------
 escondidinho de carne moída  | carne moida patinho    |   0.5600 |        8
 macarrão à bolonhesa         | carne moida patinho    |   1.8000 |       18
 macarrão à bolonhesa         | queijo parmesao ralado |   0.3600 |       18
```

`1,5 − 0,56 = 0,94`, e `1,8 − 0,94 = 0,86` — os 860 g que ela precisa comprar,
a R$ 28,00 o quilo que ela mesma pagou, dão os R$ 24,08. O parmesão conta a mesma
história sem que ninguém tenha pedido. **A fornada é de 18 porque ela disse 18**:
`portions` não tem valor padrão, e um número diferente do que ela falou é
recusado. O como e o porquê estão
[mais abaixo](#o-estoque-dela-é-finito-e-baixa-quando-ela-aceita-o-prato).

### A conta é aberta, e por isso pode ser conferida

Repare no que ele **não** faz: dar um total e pedir fé. Cada linha sai com a
gramatura e o preço, **em lista**, ordenada pela que mais pesa — e a cauda vira
uma linha só, porque onze marcadores terminando em "uma pitada de sal: R$ 0,00"
são piores que dar apenas o total: ela para de ler antes da linha que teria
questionado.

Ela compra carne, sabe quanto pagou pelo quilo, e reconhece o R$ 2,80. O custo
unitário vem do cruzamento das duas abas da planilha dela
(`preço pago ÷ quantidade comprada`), e a conta bate ao centavo:

| Ingrediente | Por marmita | Custo unitário | Custo |
|---|---:|---:|---:|
| Carne moída (patinho) | 100 g | R$ 28,00/kg | R$ 2,80 |
| Azeite de oliva | 17 ml | R$ 61,98/L | R$ 1,05 |
| Parmesão ralado | 20 g | R$ 42,90/kg | R$ 0,86 |
| Macarrão espaguete | 50 g | R$ 13,99/kg | R$ 0,70 |
| Tomate | 80 g | R$ 8,00/kg | R$ 0,64 |
| Bacon | 20 g | R$ 23,90/kg | R$ 0,48 |
| *…e o resto* | | | R$ 0,16 |
| | | **por marmita** | **R$ 6,70** |

As opções de preço saem na mesma forma, e pelo mesmo motivo: uma por linha, para
ela descer a coluna e escolher. `25,90 × 0,90 − 6,70 = 16,61`, e o piso
`6,70 / 0,90 = 7,44`.

E **nenhuma sigla**: "cada marmita custa R$ 6,70 pra você fazer", "abaixo de
R$ 7,44 você paga pra vender". Ela é cozinheira, não consultora. Decisão
[50](docs/decisoes.md#50-a-conta-é-aberta-em-português-e-a-divisão-é-da-ferramenta).

Quando a receita da web vem em porções, como *"1 kg de carne, serve 6"*, quem
divide é a ferramenta, não o modelo de cabeça. A gramatura da receita determina o
valor por porção, e o que falta comprar é estimado sobre a mesma base: a
**fração** que a fornada consome entra no custo, a **embalagem inteira** entra na
lista de compras — daí o pacote de 1 kg de cenoura ao lado dos 160 g de parmesão.

**E o servidor confere sozinho.** A mensagem foi julgada na fronteira do turno,
afirmação por afirmação, cada uma ligada ao campo de saída do MCP que a produziu:

```
jacquinho.claims {"dish":"macarrao a bolonhesa","score":1.0,"verdict":"tudo confere","verifiable":23,"grounded":23,"contradictions":0}
```

Vinte e três afirmações, vinte e três com lastro. Abrir a conta multiplicou o que
pode ser **conferido**, em vez de multiplicar o que precisa ser acreditado.

## Uma conversa que deu errado

Vale mais que a de cima, porque mostra onde o sistema ainda falha. Gravada do
mesmo jeito, no mesmo build.

```
Dona Maria ▸ quero vender pudim de leite condensado, minha amiga disse que
             vende muito

Jacquinho  ▸ Pudim de leite condensado é uma boa pedida mesmo, sai bem em
             delivery.
             Dei uma olhada: leite, ovos e açúcar você já tem na despensa. Só
             falta o leite condensado, que não está na sua lista — mas isso é
             fácil, já deixo separado no orçamento quando chegar a hora. ← ERRADO
             Antes de fechar o prato, preciso entender sua cozinha. Me conta:
             você tem forno, e ele assa bem, por igual?

Dona Maria ▸ meu forno acende mas nao esquenta direito, as vezes queima embaixo

Jacquinho  ▸ Pudim de leite condensado do jeito tradicional não vai dar, porque
             seu forno não esquenta por igual e ainda queima embaixo — ia
             arriscar o pudim assado.
             Mas dá pra fazer pudim de panela: você cozinha ele em banho-maria
             direto no fogão, numa panela com tampa, sem precisar do forno.
             Você topa fazer esse, o de panela? E me conta: seu fogão dá conta
             de manter fogo baixo por bastante tempo sem apagar?

Dona Maria ▸ e ai, da pra fazer ou nao?

Jacquinho  ▸ Pudim de panela dá pra fazer sim, só falta eu confirmar uma coisa
             antes de fechar: seu fogão consegue manter fogo baixo por bastante
             tempo sem apagar?                                        ← ERRADO
```

**Dois erros, e nenhum deles é de conta.**

O primeiro é de ordem: ele oferece guardar dinheiro no orçamento **antes** de
saber se ela consegue fazer o prato. Não chega a reservar nada, e o portão
impediria se tentasse, mas prometer a compra antes da viabilidade é exatamente a
sequência que o desafio manda evitar.

O segundo é de condução: ela pergunta *"dá pra fazer ou não?"* e recebe de volta
a mesma pergunta do turno anterior. Ela não tinha respondido, então não é o caso
de perguntar duas vezes o que ela já disse, mas do lado dela é uma parede.

**O que funcionou, e é o motivo de a conversa não ter virado prejuízo.** O
*"acende mas não esquenta direito"* não virou um sim: um sim com hesitação dentro
é recusado, e o forno ficou `confirmed_no`. O prato morto foi fechado em voz
alta, com o motivo, e a fronteira do turno confirmou a entrega:

```
jacquinho.verdict {"dish":"pudim de leite condensado","delivered":true,"kind":"ruled_out"}
```

Se aquela mensagem **não** tivesse contado a ela, a dívida reabriria e o turno
seguinte começaria com todas as ferramentas de seguir em frente recusadas. É a
garantia que este projeto consegue dar, dita sem exagero: **não dá para desdizer
um turno ruim; dá para recusar esquecê-lo.**

Outras conversas, com o diagnóstico de cada falha, estão em
**[docs/dialogos.md](docs/dialogos.md)**.

## As decisões que sustentam isso

As cinquenta e três decisões de arquitetura, cada uma com motivo e
consequência, estão em **[docs/decisoes.md](docs/decisoes.md)**. Estas seis são
as que respondem o desafio.

### Ferramentas MCP, e nenhuma skill

**O que dá para conferir vira ferramenta; o que só pode ser dito continua texto.**

Uma skill é instrução: texto que o modelo lê e, se tudo correr bem, segue. Uma
ferramenta é execução: código que roda e devolve um valor que o modelo não
produziu. A diferença aparece exatamente onde este trabalho não pode falhar,
porque ela vai gastar dinheiro em cima da resposta.

|  | Skill | Ferramenta MCP |
|---|---|---|
| "sempre calcule o CMV" | o modelo escreve um número plausível | `pricing_calculate_cmv` multiplica e devolve `0,20 × 14,00 = 2,80` |
| "não deixe ela comprar sem checar a cozinha" | um pedido educado | `budget_reserve_purchase` é **recusado** até o portão aprovar |
| "diga o quanto você confia" | o modelo estima | o middleware pontua a evidência sem ninguém pedir |

O caso extremo é o preço: sem uma faixa de mercado observada, `price_scenarios`
**não devolve preço de venda nenhum**, por mais que se peça. Uma skill só
conseguiria pedir isso educadamente.

O outro lado, dito por justiça: ferramenta custa esquema, validação e caminho de
erro para cada argumento; skill custa um parágrafo. Para comportamento sem certo
e errado computável, a ferramenta é peso morto. É por isso que a **voz** mora em
texto, e não em ferramenta. Decisões [3](docs/decisoes.md#3-o-procedimento-vai-com-o-servidor-a-voz-não-pode)
e [4](docs/decisoes.md#4-ferramentas-mcp-em-vez-de-skills).

### O que ela tem é estado, e muda quando ela muda de ideia

Toda capacidade da cozinha tem **três estados**, e só um deles é sim:

```mermaid
flowchart LR
    U["unknown<br/><i>nunca perguntado</i>"] -->|"'tenho sim'"| Y["confirmed_yes"]
    U -->|"'não tenho'"| N["confirmed_no"]
    U -.->|bloqueia a compra| B["safe_to_shop = false"]
    N -.->|bloqueia a compra| B
    U -->|"'tenho, mas queima embaixo'"| H{{"recusado:<br/>volta como pergunta"}}
    H --> U
    Y --> OK["safe_to_shop = true"]
```

`unknown` é uma pergunta, nunca um sim. Um "sim" hesitante também não é sim: um
forno que ela tem *"mas queima embaixo"* volta como pergunta, porque o detalhe
que a desqualifica ficaria na nota, e a nota é o único lugar que o portão não lê.

E um "não" nunca é definitivo. Quando um prato cai por falta de equipamento, ele
é **arquivado contra aquele equipamento**, não descartado:

```
ela não tem forno  →  lasanha ao forno bloqueada por 'forno'
                      parmegiana bloqueada por gosto
ela ganha um forno →  a lasanha volta sozinha, e ela é avisada
                      a parmegiana continua fora: gosto não é problema
                      esperando solução
```

A volta não depende de o modelo lembrar: gravar o `confirmed_yes` levanta os
bloqueios daquele item na mesma chamada. Se a receita de um prato aceito mudar
porque **ela** pediu, tudo que pendurava nela é refeito: buscar a receita, rodar
o portão, recalcular custo e preço. Decisões
[7](docs/decisoes.md#7-capacidades-têm-três-estados-e-silêncio-não-é-consentimento),
[30](docs/decisoes.md#30-o-prato-morto-é-fechado-pela-ferramenta-não-pelo-lembrete),
[49](docs/decisoes.md#49-o-prato-arquivado-é-o-que-morreu-não-o-que-sobrou),
[35](docs/decisoes.md#35-um-sim-com-mas-dentro-não-é-um-sim) e
[43](docs/decisoes.md#43-a-receita-de-um-prato-fecha-uma-vez).

### O estoque dela é finito, e baixa quando ela aceita o prato

Ela tem **1,5 kg** de patinho. Não patinho à vontade. Se o segundo prato calcula
em cima da geladeira que o primeiro já esvaziou, a lista de compras sai curta — e
ela chega na cozinha com metade da carne que a fornada pede. É o que acontece na
conversa lá em cima, e é por isso que ela ouve *"o escondidinho levou 560 g e
sobraram 940 g"* em vez de *"faltam 860 g"*.

**O estoque é uma subtração, não um número guardado.** O que a planilha semeou,
menos o que os pratos já aceitos consumiram. `pantry_items` nunca é reescrita;
o consumo mora em `pantry_usage`, uma linha por ingrediente por prato.

```sql
-- o que ela ainda tem, em uma consulta
SELECT i.ingredient,
       i.stock_quantity - COALESCE(sum(u.quantity), 0) AS sobra
  FROM pantry_items i
  LEFT JOIN pantry_usage u ON u.ingredient_key = i.ingredient_key
 GROUP BY i.ingredient, i.stock_quantity;
```

**Só-adição, e não um `UPDATE` no saldo.** Um `UPDATE` guarda quanto sobrou e
joga fora o porquê. O que ela precisa ouvir não é o saldo, é para onde a carne
foi. Com o consumo ao lado do estoque semeado, a frase inteira é uma consulta;
com um saldo só, o porquê teria sido jogado fora na primeira escrita.

**Baixa no aceite, nunca no cálculo.** Orçar um prato é uma pergunta; colocá-lo
no cardápio é uma decisão. O mesmo prato é orçado várias vezes, e às vezes ela
recusa no fim — se cada orçamento baixasse o estoque, a despensa esvaziaria por
conta de perguntas. Quem escreve é `menu_add_dish`.

**As quantidades vêm da receita fechada.** `pricing_calculate_cmv` já resolveu
cada linha para unidade base ao calcular o custo, e guarda isso no cadeado da
receita. O aceite lê de lá: re-derivar a partir dos nomes seria resolver o mesmo
fato duas vezes, e duas resoluções são duas chances de discordar.

**E volta sozinho.** Tirar o prato do cardápio devolve o que ele tinha levado.
Reabrir a receita porque ela mudou de ideia também — o que aquela versão
consumia era de um prato que não vai mais ser feito. Nada disso depende de o
modelo lembrar de um segundo passo.

**Uma linha por ingrediente, e o prato é dono das dela.** A receita da bolonhesa
pede tomate duas vezes, o fresco e o que vira molho: o consumo é somado antes de
ser escrito, senão a história vira *"levou 1,02 kg e levou 1,8 kg"*. E aceitar o
mesmo prato de novo substitui as linhas dele em vez de comer a despensa duas
vezes.

**E a fornada é o número dela.** `portions` diz quantas marmitas saem de uma
fornada, e é essa quantidade que sai da despensa. O argumento nasceu com `= 1` e
o agente pegou o padrão: ela tinha aberto a conversa com *"faço 8 marmitas por
fornada"* e o prato foi custeado para uma fornada de uma — o custo por porção
certo, e a despensa perdendo um oitavo do que a fornada come. Hoje o argumento é
obrigatório, e um número diferente do que ela falou é recusado com a frase dela
devolvida. Um padrão errado sete vezes em oito é pior que um argumento faltando:
faltando, a chamada falha e alguém decide; com padrão, ela passa e ninguém vê.
Decisão [52](docs/decisoes.md#52-a-fornada-é-o-número-dela-e-não-tem-valor-padrão).

**A vantagem prática do Postgres, bem concreta.** O estoque é um dado que o
operador precisa poder mexer: repor o que ela comprou, corrigir o que a planilha
trouxe errado, montar um cenário para demonstração. É um `UPDATE` de uma linha,
conferível na hora com um `SELECT`.

```sql
-- ela comprou mais meio quilo de patinho
UPDATE pantry_items SET stock_quantity = stock_quantity + 0.5
 WHERE ingredient_key = 'carne moida patinho';
```

Guardado junto do estado de conversa, seria um blob que só o código sabe abrir.
Decisão [51](docs/decisoes.md#51-o-estoque-dela-é-finito-e-baixa-quando-o-prato-entra-no-cardápio).

### Confiança por afirmação atômica, tipada pela saída do MCP

Uma nota por mensagem não diz nada: uma mensagem tem várias afirmações e elas não
têm o mesmo lastro. Toda mensagem entregue é decomposta e cada afirmação é
julgada sozinha:

```mermaid
flowchart LR
    M["a mensagem que ela recebeu"] --> D["decompor em<br/>afirmações atômicas"]
    D --> F{"é conferível?"}
    F -->|"pergunta, conselho"| N["fora da conta"]
    F -->|"afirma um número"| G{"qual saída de MCP<br/>produziu isso?"}
    G -->|nenhuma| U["sem lastro"]
    G -->|"uma, e do tipo certo"| C{"bate com o que<br/>ela já ouviu?"}
    C -->|sim| OK["confere"]
    C -->|"ela pediu a mudança"| R["revisado"]
    C -->|não| X["<b>contradiz</b><br/>zera a mensagem"]
```

Três escolhas fazem isso funcionar:

**A identidade da afirmação vem da saída de MCP que a produziu**, não das
palavras ao redor do número. Um mapa declarativo liga cada campo de saída a um
tipo: `pricing_calculate_cmv.cmv_per_portion` é custo,
`menu_add_dish.price` é preço, `market_research_dish_prices.reference.median` é
mercado. Ler o tipo da frase é tentador e errado: *"sobram R$ 63,91 dos seus
R$ 80"* é orçamento, e todas as pistas que o classificariam como lucro estão ali.

**Saída, nunca argumento.** Uma ferramenta é evidência do que **calcula**. O que
ela recebe é o modelo conversando consigo mesmo, e contar isso fecha um círculo
com nada dentro. Os números que chegaram como argumento são subtraídos, em toda
chamada.

**Lastro não é compromisso.** `price_scenarios` devolve três preços: são
candidatos, e nenhum é o preço do prato. Só o que foi para o cardápio compromete.
Um valor só vira promessa quando **chega até ela**, e uma contradição com o que
ela já ouviu **zera** a mensagem, sem média: ouvir dois custos diferentes para o
mesmo prato não é oitenta por cento certo.

Os tipos são modelos Pydantic e o pipeline é determinístico, então roda em toda
mensagem sem custar uma chamada de modelo. O método, com as referências
científicas que o embasam, está em
[docs/metricas.md](docs/metricas.md#afirmações-atômicas-o-pipeline-por-mensagem);
as decisões, em [45](docs/decisoes.md#45-a-confiança-de-uma-mensagem-é-a-soma-das-afirmações-dela)
e [47](docs/decisoes.md#47-as-afirmações-são-conferidas-contra-a-saída-do-mcp-que-as-produziu).

### Redis para a conversa, Postgres para o que ela decidiu

O agente recebe sempre os **20 últimos turnos mais um resumo** de tudo antes
deles. O custo em tokens por turno fica limitado por construção, e os turnos
antigos continuam gravados: o corte é do que o agente segura, não do que se
guarda. O resumo é reescrito pelo próprio agente quando 20 turnos novos se
acumulam, sem um segundo modelo no circuito.

Isso é o que é **quente**, e vive no Redis. O que a conversa **decidiu** vive no
Postgres, e a régua que separa os dois é simples: vai para o Redis quando perdê-lo
custa contexto; vai para o Postgres quando perdê-lo custa uma pergunta repetida
ou dinheiro gasto duas vezes.

Três razões pelas quais o perfil da cozinha não podia ficar na conversa. Um
bloqueio é uma **relação**, não um valor: a lasanha saiu *por causa do* forno, e
quando o forno aparece os pratos voltam com um `UPDATE ... WHERE blocking_item =
'forno' RETURNING`. A janela de 20 turnos **descarta**, e um perfil descartado
faz a próxima consultoria recomeçar perguntando tudo. E *"o que ela ainda não
respondeu"* é uma **consulta**, não uma dedução: `unknown` é um estado guardado.

Decisões [18](docs/decisoes.md#18-o-redis-guarda-a-conversa-20-turnos-mais-1-resumo)
e [19](docs/decisoes.md#19-o-postgres-guarda-os-dados-da-dona-maria). O esquema
inteiro está em [docs/modelo-de-dados.md](docs/modelo-de-dados.md).

### A voz mora no `SOUL.md`, porque não pode morar em outro lugar

O Hermes trata texto vindo de um servidor MCP como **dado não confiável**, com
um scanner de injeção sobre ele, e não injeta as `instructions` do servidor no
system prompt. Persona escrita ali simplesmente não chega ao modelo.

Por isso `hermes/SOUL.md` existe, e por isso ele contém **só** o que não pode ser
verificado: idioma, quem fala primeiro, postura, e as regras de voz que nenhuma
ferramenta consegue impor. A ideia central que o organiza:

> **Ela contratou um sous-chef, não um relatório.** Ele fala *com* ela, não
> *sobre* ela. Não narra a própria busca, não menciona ferramenta, não devolve a
> pergunta que a despensa já responde, e nunca pergunta duas vezes o que ela já
> respondeu.

Uma regra de voz, porém, tinha como ser medida — e por isso foi. Ela lê no
celular com a panela no fogo: receita, custo, compras, mercado e preço soldados
num parágrafo é um parágrafo que ela passa o olho, e o que estava no meio se
perde, em geral a pergunta. Então a resposta vai **em partes**, uma por linha, com
a pergunta sozinha na última. O que se mede é empilhamento, não comprimento — uma
resposta longa para uma pergunta grande é uma boa resposta. `message_pacing`
volta em `confidence_assess_answer` dizendo em quantas partes o rascunho está e
onde é a costura, sem nunca reescrever nada: prosa quebrada por regra soa
quebrada, e o agente já sabe onde os próprios parágrafos terminam. Decisão
[53](docs/decisoes.md#53-a-mensagem-vai-em-partes-e-o-tamanho-não-é-o-problema).

E o que ela lê em lista **é** lista: a conta da porção e as opções de preço saem
com um item por linha, na mesma forma. Corridos dentro de um parágrafo, seis
ingredientes e seis valores viram uma coisa que ela passa o olho, e a linha que
ela questionaria é justamente a que some. A cauda é dobrada, não escondida — *"e
o resto (cebola, leite, alho, sal): R$ 0,14"* —, porque onze marcadores
terminando em "uma pitada de sal: R$ 0,00" são piores que dar só o total.

O procedimento (que ferramenta chamar, em que ordem, o que exige o quê) **não**
está lá. Está nas descrições das ferramentas e no `next_step` de cada resultado,
onde existe verificação. Decisão [3](docs/decisoes.md#3-o-procedimento-vai-com-o-servidor-a-voz-não-pode).

---

## Onde cada exigência do desafio foi cumprida

O enunciado chama o custo de **CMV**, e esta tabela usa o termo dele. Na conversa
com a Dona Maria a sigla nunca aparece: lá é "cada marmita custa R$ 7,53 pra você
fazer".

| Enunciado | O que ele pede | Onde vive no código |
|---|---|---|
| **2.1** | Pesquisar receitas reais na internet | `recipes_search_recipes`, `dishes_discover_dishes` |
| **2.1** | Apresentar candidatas e pedir feedback dela | `menu_record_feedback` |
| **2.2** | Utensílios, equipamentos, técnicas, restrições | catálogo de 26 itens, `kitchen_next_questions` |
| **2.2** | **Não deixar comprar e descobrir depois** | `kitchen_elicitation_gaps`, `safe_to_shop` |
| **2.3** | O que ela já tem, e em que quantidade | `recipes_check_pantry_coverage`, `pantry_what_is_left` (o estoque baixa a cada prato aceito) |
| **2.3** | O que falta comprar, o custo, e se cabe | `pricing_calculate_cmv`, `budget_check_purchase` |
| **2.4** | CMV = Σ (quantidade usada × custo unitário) | `pricing_calculate_cmv`, aritmética em Python |
| **2.4** | Custo unitário = preço pago ÷ quantidade comprada | `PantrySheet`, `UnitConverter` |
| **2.4** | Incluir compras complementares no CMV | `researched_prices`, pela fração usada |
| **2.4** | Ela recebe `0,90 × P`; piso `P ≥ CMV / 0,90` | `net_share`, `break_even` |
| **2.4** | Lucro `0,90 × P − CMV` | `profit` |
| **2.4** | **2–3 cenários, e ela decide** | `pricing_price_scenarios` |
| **3** | Orçamento de R$ 80,00 para complementos | `budget_reserve_purchase` |

Três coisas fora do enunciado, que a conversa mostrou serem necessárias: dizer
**o quanto confia** no que está falando, fechar com **o resultado da fornada**,
que é a pergunta que ela de fato faz, e tratar a quantidade em estoque como
**finita** — o enunciado dá a coluna, e um segundo prato que ignora o que o
primeiro comeu manda ela para a cozinha com metade da carne.

As **cinco escolhas** que o enunciado deixou a meu critério (modelo, context
files, tools/MCP, estrutura de memória, skills) estão respondidas uma a uma em
[docs/decisoes.md](docs/decisoes.md#as-cinco-escolhas-que-o-enunciado-deixou-em-aberto).

---

## O que eu não fiz, e por quê

Escopo cortado de propósito. O motivo importa mais que o item.

**Nenhum cálculo passa por modelo.** CMV, preço mínimo, lucro, saldo e projeção
de inflação são Python. Um modelo a quem se pede para multiplicar preços devolve
um número plausível, e plausível é indistinguível de correto até alguém gastar
dinheiro em cima.

**Não persisti a conversa entre sessões, só o que ela decidiu.** Reconstituir o
diálogo de semanas atrás não ajuda ninguém; saber que ela não tem forno, sim.

**Não construí memória vetorial nem RAG.** A despensa tem 37 linhas. Busca
semântica sobre isso é infraestrutura para um problema que `SELECT` resolve, e
traz uma classe de erro nova: recuperar o ingrediente parecido em vez do certo.

**Não coloquei um segundo modelo como juiz.** O enunciado pede um agente, e dois
provedores no circuito é uma dependência e uma conta a mais.

**Não calibrei os limiares de confiança.** Calibrar exige registrar desfecho (o
prato foi aceito? o preço se sustentou?) e não há esse dado. A nota **ordena**
respostas; não mede probabilidade de nada, e isso está escrito onde alguém possa
tropeçar nela.

**Não isolei sessões simultâneas de verdade.** Correto para uma consultoria por
vez, que é o caso de uso; insuficiente para várias pessoas ao mesmo tempo.

**Não usei um plugin em Python do Hermes.** Ele poderia reescrever a mensagem que
está saindo. Um servidor escrevendo direto para a Dona Maria é uma garantia pior
que a de recusar esquecer.

**Não fiz teste automatizado de diálogo.** Cada execução custa uma chamada de
modelo e o julgamento do resultado é humano. A simulação é manual, e o que ela
achou está em [docs/dialogos.md](docs/dialogos.md), inclusive o que continua
torto.

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/arquitetura.md](docs/arquitetura.md) | Componentes, camadas, fluxogramas e diagramas de sequência |
| [docs/decisoes.md](docs/decisoes.md) | As 53 decisões de arquitetura, com motivo e consequência |
| [docs/dialogos.md](docs/dialogos.md) | Nove conversas reais: cinco que deram certo, quatro que deram errado |
| [docs/metricas.md](docs/metricas.md) | Como a confiança é calculada, o pipeline de afirmações, e as referências |
| [docs/modelo-de-dados.md](docs/modelo-de-dados.md) | Esquema do Postgres, chaves do Redis, normalização de unidades |
| [docs/referencia-mcp.md](docs/referencia-mcp.md) | As 59 ferramentas, os prompts e os recursos |
| [docs/operacao.md](docs/operacao.md) | Execução, credenciais, depuração, modos de falha |
| [docs/testes.md](docs/testes.md) | A suíte automatizada e o que cada rodada de simulação achou |

### Estrutura

```
bin/jacquinho          ponto de entrada de linha de comando
app/domain/            cálculo e regras, sem conhecer MCP
app/mcps/              uma classe por servidor MCP, mais a raiz de composição
hooks/                 fronteiras de turno: a fala dela, a resposta dela
hermes/SOUL.md         voz e quem fala primeiro, lido pelo agente
dockerfile/            imagem, compose, dependências, config do agente
```
