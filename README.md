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
![Testes](https://img.shields.io/badge/testes-277-success)
![Confiança](https://img.shields.io/badge/confiança-afirmação%20atômica%20%2B%20Pydantic-6E56CF)


> **Antes de rodar: a planilha da Dona Maria não vem no repositório.**
>
> O `despensa_dona_maria.xlsx` é dado de entrada e fica fora do versionamento.
> Para testar, crie uma pasta `data/` na raiz e coloque o arquivo lá:
>
> ```
> jacquinho/
> └── data/
>     └── despensa_dona_maria.xlsx
> ```
>
> A planilha tem duas abas, e é dessas colunas que sai o custo unitário de
> cada ingrediente:
>
> | Aba        | Colunas                                                              |
> | ---------- | -------------------------------------------------------------------- |
> | `Despensa` | Ingrediente · Quantidade em estoque · Unidade                        |
> | `Precos`   | Ingrediente · Quantidade comprada · Unidade · Preço total pago (R$)  |
>
> Sem esse arquivo, o `jacquinho reset` sobe os bancos vazios e o agente
> começa a consultoria sem despensa nenhuma.

Um sous-chef de IA para a **Dona Maria**, cozinheira que está abrindo o primeiro
delivery dela, o *Sabor da Maria*. Ela sabe cozinhar. O que ela não sabe é quais
pratos a despensa dela consegue produzir, se a cozinha dela dá conta de
fazê-los, e quanto cobrar para o delivery valer a pena.

Sous-chef, e não chefe: **quem decide o prato, o preço e a compra é ela.** Ele lê
a despensa, pergunta o que não sabe, faz as contas e abre os números.

E é construído de modo que **todo número que ele diz veio de uma chamada de
ferramenta, nunca da memória do modelo**. Isso não é uma intenção: cada mensagem
entregue é quebrada em afirmações atômicas e cada uma é conferida contra a saída
de MCP que a produziu, com o que ela já ouviu nos turnos anteriores no meio da
comparação. Uma cifra sem lastro zera a afirmação; uma que contradiz o que ela
ouviu zera a mensagem. Está descrito em
[Confiança por afirmação atômica](#confiança-por-afirmação-atômica-tipada-pela-saída-do-mcp).

> *O nome é uma homenagem ao chef **Érick Jacquin**, e o sotaque francês
> acaba aí: o Jacquinho fala português claro e não grita com ninguém.*

## Índice

- [Começando](#começando)
- [Uma consultoria que deu certo](#uma-consultoria-que-deu-certo)
- [Uma conversa que deu errado](#uma-conversa-que-deu-errado)
- [Decisões de arquitetura](#decisões-de-arquitetura)
  - [Ferramentas MCP, e nenhuma skill](#ferramentas-mcp-e-nenhuma-skill)
  - [Confiança por afirmação atômica, tipada pela saída do MCP](#confiança-por-afirmação-atômica-tipada-pela-saída-do-mcp)
  - [O `SOUL.md` carrega a voz, e só a voz](#o-soulmd-carrega-a-voz-e-só-a-voz)
  - [Redis para a conversa, Postgres para o que ela decidiu](#redis-para-a-conversa-postgres-para-o-que-ela-decidiu)
  - [O preço da porção nasce da gramatura da receita](#o-preço-da-porção-nasce-da-gramatura-da-receita)
  - [O estoque é finito, e só baixa quando ela aceita o prato](#o-estoque-é-finito-e-só-baixa-quando-ela-aceita-o-prato)
  - [O que ela tem é estado, e muda quando ela muda de ideia](#o-que-ela-tem-é-estado-e-muda-quando-ela-muda-de-ideia)
- [O que pode melhorar](#o-que-pode-melhorar)
- [O sistema em números](#o-sistema-em-números)
- [O que eu deixei de fora, e por quê](#o-que-eu-deixei-de-fora-e-por-quê)
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

Transcrição real, bancos zerados. Dois pratos, o segundo encontra a despensa como
o primeiro a deixou, e no fim ela ouve quanto sobra no bolso dela. Nada foi
reescrito: as falas estão palavra por palavra, e o que está entre colchetes são
turnos de cozinha inteiros que ficaram de fora para o exemplo caber.

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

Dona Maria ▸ vou de 25,90. reserva a compra e coloca no cardápio

Dona Maria ▸ então fecha pra mim: vendendo as duas fornadas inteiras nesses
             preços, quanto eu ganho no fim?

Jacquinho  ▸ Fechando as duas fornadas juntas, nos preços que você escolheu:
             Escondidinho de carne moída (8 marmitas a R$ 24,90):
             - vende R$ 199,20
             - a plataforma fica com R$ 19,92
             - os ingredientes custam R$ 40,00
             - sobram R$ 139,28 no seu bolso
             (esse preço do escondidinho ainda é baseado em pouca referência de
             mercado, então trate como indicativo)
             Macarrão à bolonhesa (18 marmitas a R$ 25,90):
             - vende R$ 466,20
             - a plataforma fica com R$ 46,62
             - os ingredientes custam R$ 120,60
             - sobram R$ 298,98 no seu bolso
             Somando tudo (26 marmitas): você vende R$ 665,40, a plataforma
             fica com R$ 66,54, os ingredientes custam R$ 160,60, e sobram
             R$ 438,26 no seu bolso — ou seja, 66 centavos de cada real que
             entra ficam com você.
             Dessas duas fornadas, ainda falta você desembolsar R$ 57,41 em
             compras (carne moída, parmesão, cenoura e pimenta-do-reino), e
             sobra estoque de ingrediente pras próximas fornadas.
```

### O que essa conversa prova

**A conta é aberta, e por isso pode ser conferida.** Cada linha sai com a
gramatura e o preço, em lista, ordenada pela que mais pesa, e a cauda vira uma
linha só. Ela compra carne, sabe quanto pagou pelo quilo, e reconhece o R$ 2,80:

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

As opções de preço saem na mesma forma, uma por linha, para ela descer a coluna e
escolher. O piso é `6,70 / 0,90 = 7,44` e o lucro em cima do preço que ela pegou
é `25,90 × 0,90 − 6,70 = 16,61`. E nenhuma sigla em nenhuma frase: ela é
cozinheira, não consultora.

**O estoque baixou, e ela ouviu para onde foi.** Quando o escondidinho entrou no
cardápio, a fornada dele saiu da despensa, e o Postgres guarda para onde:

```
 dish                         | ingredient_key         | quantity | portions
------------------------------+------------------------+----------+----------
 escondidinho de carne moída  | carne moida patinho    |   0.5600 |        8
 macarrão à bolonhesa         | carne moida patinho    |   1.8000 |       18
 macarrão à bolonhesa         | queijo parmesao ralado |   0.3600 |       18
```

`1,5 − 0,56 = 0,94`, e `1,8 − 0,94 = 0,86`: os 860 g que faltam, a R$ 28,00 o
quilo que ela mesma pagou, dão os R$ 24,08. O parmesão conta a mesma história sem
que ninguém tenha pedido, e a fornada é de 18 porque ela disse 18.

**O fechamento fala do dia dela, não da marmita.** Uma marmita que deixa R$ 16,61
é uma informação; a pergunta que ela faz é se o dia valeu a pena, e essa só tem
resposta com a quantidade, que é dela:

| | Escondidinho | Bolonhesa | Juntas |
|---|---:|---:|---:|
| Marmitas | 8 × R$ 24,90 | 18 × R$ 25,90 | 26 |
| Ela vende | R$ 199,20 | R$ 466,20 | **R$ 665,40** |
| Plataforma leva 10% | R$ 19,92 | R$ 46,62 | R$ 66,54 |
| Ingrediente usado | R$ 40,00 | R$ 120,60 | R$ 160,60 |
| **Sobra no bolso dela** | R$ 139,28 | R$ 298,98 | **R$ 438,26** |

Os R$ 438,26 são `665,40 − 66,54 − 160,60`, e os 66% são margem sobre a **venda**,
não retorno sobre custo: uma porcentagem que não passa de 100 e por isso continua
acreditável. Os dois custos ficam separados de propósito: R$ 160,60 é o que a
comida custa, com a despensa que ela já tinha; R$ 57,41 é o que ainda sai do
bolso dela. Somar os dois cobraria duas vezes a mesma despensa.

**E o servidor confere sozinho.** Toda mensagem entregue é decomposta na
fronteira do turno e cada afirmação é ligada ao campo de saída do MCP que a
produziu:

```
jacquinho.claims {"dish":"macarrao a bolonhesa","score":1.0,"verdict":"tudo confere","verifiable":23,"grounded":23,"contradictions":0}
```

Vinte e três afirmações, vinte e três com lastro. Abrir a conta multiplica o que
pode ser **conferido**, em vez de multiplicar o que precisa ser acreditado.

## Uma conversa que deu errado

Gravada do mesmo jeito, no mesmo build. Vale mais que a de cima, porque mostra
onde o sistema ainda incomoda.

```
Dona Maria ▸ quero vender pudim de leite condensado, minha amiga disse que
             vende muito

Jacquinho  ▸ Pudim de leite condensado é uma ótima escolha: você já tem quase
             tudo aí na despensa — açúcar, leite integral, ovos. Só falta mesmo
             o leite condensado, que é baratinho de comprar.      ← INCOMPLETO
             Esse pudim vai ao forno, em banho-maria, por 1h30. Você tem forno
             que funciona bem e assa por igual?

Dona Maria ▸ meu forno acende mas nao esquenta direito, as vezes queima embaixo

Jacquinho  ▸ Dona Maria, o pudim de leite condensado do jeito que eu tinha
             pensado — assado no forno, em banho-maria por 1h30 — não vai dar
             certo do jeito que seu forno está: ele não esquenta direito e
             ainda queima embaixo, então numa assada longa dessas o pudim sai
             queimado na base e mal cozido por cima.
             Mas dá pra fazer o mesmo pudim sem usar o forno: pudim de panela,
             direto no fogão, numa panela com tampa e fogo bem baixo.
             Quer que eu já veja como fica essa versão de panela pra você?

Dona Maria ▸ e ai, da pra fazer ou nao?

Jacquinho  ▸ O pudim assado no forno, do jeito clássico, não vai dar: seu forno
             não assa por igual, queima embaixo, e a receita pede uma hora e
             meia de banho-maria.                                    ← ERRADO
             Mas dá pra fazer o seu pudim, só que de panela: no fogão mesmo,
             em banho-maria, numa panela com tampa. Fica cremoso igualzinho.
             Quer que eu já veja o que falta comprar e quanto fica o custo
             desse jeito?

Dona Maria ▸ eu ja disse que quero. me diz o custo logo

Jacquinho  ▸ Bora fechar o pudim de panela, do jeito que dá pra fazer no seu
             fogão, sem forno.
             Só falta eu confirmar uma coisa da sua cozinha antes de te dar a
             conta certinha: você tem liquidificador e uma forma de pudim aí
             em casa?                                                ← ERRADO
```

### Por que falhou

**Ela fez uma pergunta fechada e recebeu o turno anterior de novo.** *"Dá pra
fazer ou não?"* pede uma palavra. O que voltou foi a mesma explicação do forno,
o mesmo convite ao pudim de panela e a mesma pergunta no fim. Nada ali está
errado como fato, e do lado dela é uma parede: ela leu duas vezes o que já
tinha entendido e continua sem saber se pode começar.

A causa é conhecida e está no desenho. O servidor sabe onde a conversa está,
porque o `conversation_state` viaja em toda resposta de ferramenta, mas ele não
sabe o que a **última frase dela** pediu. Reconhecer "isso é uma pergunta de sim
ou não, responda em uma linha" é leitura de intenção, e leitura de intenção é
exatamente o que este projeto não delega a regra determinística nem confia ao
modelo sem conferência.

**Quatro turnos, nenhuma conta, e metade deles pedindo licença.** É tentador
culpar o portão de viabilidade, e a conta turno a turno diz outra coisa:

| Turno | Ela | Ele | Precisava? |
|---|---|---|---|
| 1 | quero vender pudim | pergunta do forno | **sim**, é o portão |
| 2 | forno queima embaixo | mata o assado, propõe panela, *"quer que eu já veja como fica?"* | **não** |
| 3 | dá pra fazer ou não? | repete tudo, *"quer que eu já veja o custo?"* | **não** |
| 4 | me diz o custo logo | pergunta liquidificador e forma | **sim**, é o portão |

O portão perguntou **duas** vezes, e as duas foram legítimas: pudim de panela
pede liquidificador e forma, e ninguém deveria mandar ela comprar leite
condensado para descobrir na cozinha que falta a forma. Os outros dois turnos
foram gastos **pedindo permissão para fazer o que ela já tinha pedido**. Ela
disse que quer vender pudim no primeiro turno; ele pergunta duas vezes se pode
calcular.

É a mesma falha do parágrafo anterior vista de outro ângulo. O agente trata cada
turno como se precisasse de autorização para o passo seguinte, e quando ela
responde com impaciência, ele lê a impaciência como pergunta nova.

O portão perguntar um item por vez é risco de verdade, mas latente, não
demonstrado aqui: `kitchen_register_requirement` não tem teto, e cada variante de
receita pode acrescentar exigência. Agrupar as perguntas por prioridade é
trabalho útil, e não é o que custou esta conversa.

**E o "baratinho" não tem lastro.** No primeiro turno, o leite condensado é
"baratinho de comprar" antes de qualquer pesquisa de preço. A conferência
automática de cifras não pega isso, porque ela confere **números** contra as
saídas das ferramentas, e adjetivo não é número. É um limite honesto da camada:
ela impede um R$ inventado, não uma impressão de preço.

### O que funcionou, e é o motivo de não ter virado prejuízo

O *"acende mas não esquenta direito"* não virou um sim. Um sim com hesitação
dentro é recusado, o forno ficou `confirmed_no`, e o prato morto foi anunciado
em voz alta com o motivo. A fronteira do turno confirmou a entrega:

```
jacquinho.verdict {"dish":"pudim de leite condensado","delivered":true,"kind":"ruled_out"}
```

Enquanto essa frase não chega até ela, o próximo turno começa com todas as
ferramentas de seguir em frente recusadas. É a garantia que este projeto
consegue dar, dita sem exagero: **não dá para desdizer um turno ruim; dá para
recusar esquecê-lo.**

Mais conversas, boas e ruins, com o diagnóstico de cada uma, estão em
**[docs/dialogos.md](docs/dialogos.md)**.

## Decisões de arquitetura

O desafio deixou cinco coisas a critério de quem implementa: modelo, context
files, tools/MCP, estrutura de memória e skills. As sete decisões abaixo
respondem essas cinco e carregam junto as exigências do enunciado, porque foram
elas que decidiram como cada exigência é cumprida. As cinquenta e três decisões,
com motivo e consequência, estão em **[docs/decisoes.md](docs/decisoes.md)**.

### Ferramentas MCP, e nenhuma skill

**O que dá para conferir vira ferramenta; o que só pode ser dito continua texto.**

Uma skill é instrução: texto que o modelo lê e, se tudo correr bem, segue. Uma
ferramenta é execução: código que roda e devolve um valor que o modelo não
escolheu. A diferença aparece quando o modelo está errado, que é o único momento
em que uma garantia importa.

Escrever numa skill *"nunca precifique um prato antes de confirmar o
equipamento"* funciona quase sempre. Quando não funciona, não sobra rastro:
ninguém consegue mostrar que a instrução foi lida e ignorada. O mesmo enunciado
como ferramenta é `kitchen_check_feasibility`, que devolve `safe_to_shop: false`
e fecha as ferramentas de compra até a pergunta ser respondida. O prato não é
precificado porque a ferramenta recusa, não porque o modelo lembrou.

Por isso o procedimento inteiro do enunciado virou ferramenta: a busca de
receitas reais na internet (`recipes_search_recipes`, com consenso entre fontes),
a coleta de opinião dela sobre cada candidata (`menu_record_feedback`), o
levantamento de utensílios, equipamentos, técnicas e restrições
(`kitchen_elicitation_gaps`, sobre um catálogo de 26 itens que cresce durante a
conversa), o CMV, os cenários de preço e o orçamento de R$ 80,00.

Onze servidores, um por área do problema, montados sob um **único endpoint
HTTP**. A separação é de responsabilidade, não de rede: cada servidor é dono de
um pedaço do estado, e uma tabela tem um dono só. Decisões
[2](docs/decisoes.md#2-um-endpoint-http-onze-servidores-montados) e
[4](docs/decisoes.md#4-ferramentas-mcp-em-vez-de-skills).

### Confiança por afirmação atômica, tipada pela saída do MCP

É a garantia que sustenta a frase do topo deste arquivo. Dizer *"todo número vem
de uma ferramenta"* só vale alguma coisa se alguém conferir, mensagem por
mensagem, e é isso que esta camada faz.

Uma nota por mensagem não diz nada, porque uma mensagem tem várias afirmações e
elas não têm o mesmo lastro. Então **toda** mensagem entregue é decomposta, e
cada afirmação é julgada sozinha:

```
"custa R$ 7,53 por marmita, e vendendo a R$ 23,90 sobram R$ 13,98"
        │                              │                    │
     COST 7.53                    PRICE 23.90          PROFIT 13.98
        └── pricing_calculate_cmv  └── price_scenarios  └── price_scenarios
            .cmv_per_portion           .scenarios[]        .scenarios[]
                                       .selling_price      .profit_per_portion
```

Quatro passos, e nenhum deles depende de o agente lembrar de pedir:

| Passo | O que faz |
|---|---|
| **1. Decompor** | Quebra a mensagem em afirmações atômicas, uma cifra e um tipo cada |
| **2. Filtrar** | Pergunta, conselho e opinião saem: só fica o que é conferível |
| **3. Conferir** | Cada afirmação contra a saída de MCP que a estabelece |
| **4. Comparar** | Contra o que ela **já ouviu** nos turnos anteriores |

O modelo `AtomicClaim` é Pydantic, e a tipagem é a garantia: uma afirmação
carrega o tipo (`COST`, `PRICE`, `PROFIT`, `RECEIPT`, `PANTRY`, `BUDGET`), o
valor e a fonte. Sem tipo, R$ 13,98 de lucro conferiria contra um R$ 13,98 de
compra que passou pela conversa por acaso.

**E o lastro vem da saída do MCP, não de um saco de números.** Um mapa declara,
campo por campo, qual saída de qual ferramenta estabelece qual tipo de afirmação:
`pricing_calculate_cmv.cmv_per_portion` é um custo,
`menu_expected_return.dishes[].platform_fee_paid` é uma taxa. Duas distinções
fazem o trabalho:

*Saída, nunca argumento.* Uma ferramenta é evidência do que ela **calcula**. O que
ela **recebe** é o modelo falando consigo mesmo, e contar isso fecha um círculo
com nada dentro. Sem essa regra, uma ferramenta que devolve no resultado o valor
que o modelo passou faz o próprio chute do modelo parecer conferido.

*Ter lastro não é comprometer.* `price_scenarios` devolve três preços, e nenhum
deles é o preço do prato. Só o que foi para o cardápio compromete. Marcar os três
como promessa transformaria "aqui estão três opções" em três contradições no
turno seguinte.

**O que acontece quando falha.** Uma cifra que nenhuma saída produziu zera
aquela afirmação. Uma que contradiz o que ela já ouviu zera a **mensagem
inteira**, porque dois preços na cabeça dela é pior que um preço vago. O
resultado sai no log a cada turno:

```
jacquinho.claims {"score":1.0,"verdict":"tudo confere","verifiable":23,"grounded":23,"contradictions":0}
```

Ao lado dele roda a camada irmã, mais crua: `confidence_audit_figures` extrai
todo R$ e todo % da mensagem e pergunta se alguma ferramenta produziu aquele
número, sem modelo nenhum no circuito. Um turno limpo não gera linha; quando
gera, ela vem com o valor e o trecho onde aparece, sob o prefixo
`jacquinho.figures`. É o que pega uma conta feita na prosa **mesmo quando o
resultado está certo**, que é o caso difícil: a conta certa feita na mensagem e a
errada de amanhã têm exatamente a mesma cara.

**Antes de enviar, e depois de enviar.** `confidence_assess_answer` pontua o
rascunho contra a evidência que a afirmação daquele tipo exige, e banda `low`
significa que a resposta não está pronta. O pipeline de afirmações roda depois,
na fronteira do turno, sobre o que realmente saiu, que é o único lugar onde a
mensagem existe. As duas medem coisas diferentes de propósito: a primeira
pergunta se há evidência suficiente, a segunda pergunta se o que foi dito bate
com ela.

O método vem da literatura de verificação factual, adaptado: decomposição atômica
do FActScore e do SAFE, o filtro de "só o que é verificável" do VeriScore, e o
registro de compromissos entre turnos do SKG-Eval. Nada disso vira selo na
mensagem dela, que é cozinheira e não avaliadora deste sistema: o que chega até
ela é a ressalva em português, dentro da frase. Decisões
[45](docs/decisoes.md#45-a-confiança-de-uma-mensagem-é-a-soma-das-afirmações-dela)
e [47](docs/decisoes.md#47-as-afirmações-são-conferidas-contra-a-saída-do-mcp-que-as-produziu);
a matemática e os limites conhecidos estão em
[docs/metricas.md](docs/metricas.md).

### O `SOUL.md` carrega a voz, e só a voz

O Hermes trata texto vindo de um servidor MCP como **dado não confiável**, com um
scanner de injeção por cima, e não injeta as `instructions` do servidor no system
prompt. Persona escrita ali simplesmente não chega ao modelo. É essa restrição do
runtime, e não estilo, que define o que mora em cada lugar.

Então `hermes/SOUL.md` contém **só o que nenhuma ferramenta consegue impor**:
idioma, quem fala primeiro, o que ela nunca deve ler, como dizer um preço sem
dizer "CMV", como quebrar a mensagem em partes. A ideia central que organiza o
arquivo inteiro:

> **Ela contratou um sous-chef, não um relatório.** Ele fala *com* ela, não
> *sobre* ela. Não narra a própria busca, não menciona ferramenta, não devolve a
> pergunta que a despensa já responde, e nunca pergunta duas vezes o que ela já
> respondeu.

O procedimento não está lá. Que ferramenta chamar, em que ordem, o que exige o
quê: isso viaja no campo `next_step` de cada resultado, junto do dado, onde
existe verificação. Uma regra escrita onde não pode ser imposta é um conselho, e
conselho o modelo às vezes segue. Decisão
[3](docs/decisoes.md#3-o-procedimento-vai-com-o-servidor-a-voz-não-pode).

### Redis para a conversa, Postgres para o que ela decidiu

O agente recebe sempre a mesma coisa: os **20 últimos turnos mais 1 resumo** de
tudo que veio antes deles. O custo em tokens por turno fica limitado por
construção, e nada é perdido, porque o corte é do que o agente segura e não do
que fica guardado. O resumo é reescrito pelo próprio agente quando 20 turnos
novos se acumulam, sem um segundo modelo no circuito.

Isso é o que é **quente**, e vive no Redis, que é onde uma lista com corte por
tamanho e uma chave com validade são operações nativas. O que a conversa
**decidiu** vive no Postgres. A régua que separa os dois é simples: vai para o
Redis quando perdê-lo custa contexto; vai para o Postgres quando perdê-lo custa
uma pergunta repetida ou dinheiro gasto duas vezes.

Três razões pelas quais o perfil da cozinha não podia ficar na conversa. Um
bloqueio é uma **relação**, não um valor: a lasanha saiu por causa do forno, e
quando o forno aparece os pratos voltam com um `UPDATE ... WHERE blocking_item =
'forno' RETURNING`. A janela de 20 turnos **descarta**, e um perfil descartado faz
a próxima consultoria recomeçar perguntando tudo. E *"o que ela ainda não
respondeu"* é uma **consulta**, não uma dedução: `unknown` é um estado guardado,
com as palavras dela ao lado. Decisões
[18](docs/decisoes.md#18-o-redis-guarda-a-conversa-20-turnos-mais-1-resumo) e
[19](docs/decisoes.md#19-o-postgres-guarda-os-dados-da-dona-maria); o esquema
inteiro está em [docs/modelo-de-dados.md](docs/modelo-de-dados.md).

### O preço da porção nasce da gramatura da receita

O enunciado define o custo como a soma de `quantidade usada × custo unitário`, e
a palavra que carrega o peso ali é **quantidade**. Uma estimativa por prato é um
chute com aparência de conta; a gramatura da receita é o que torna o número
conferível.

Então a receita entra na ferramenta como ela é escrita, ingrediente por
ingrediente, com quantidade e unidade: `100 g de carne moída`, `17 ml de azeite`,
`1 ovo`. O custo unitário sai do cruzamento das duas abas da planilha dela,
`preço pago ÷ quantidade comprada`, com a embalagem resolvida: um balde de 2 kg
por R$ 82,00 vira R$ 41,00 o quilo, não R$ 82,00 o balde.

Quando a receita da web vem por rendimento, *"1 kg de carne, serve 6"*, a divisão
acontece **na ferramenta**, com `recipe_yields`. Dividir por seis parece trivial,
e é exatamente o tipo de conta que sai da cabeça do modelo para poder ser
mostrada.

O que falta comprar é estimado sobre a mesma base, e separado em dois números que
não são o mesmo: a **fração** que a fornada consome entra no custo da porção, a
**embalagem inteira** entra na lista de compras. Ela não compra 40 g de leite
condensado, compra uma lata; e cobrar a lata inteira de uma fornada que usa uma
colherada infla o custo de todo prato que deixa sobra.

Daí saem, em Python e não no modelo, o piso `P ≥ CMV / 0,90`, o lucro
`0,90 × P − CMV` e os cenários de preço ancorados no mercado observado, sempre
dois ou três, para **ela** escolher. Decisões
[1](docs/decisoes.md#1-o-cálculo-vive-fora-do-modelo-de-linguagem),
[39](docs/decisoes.md#39-um-ingrediente-de-fora-tem-dois-custos-e-a-ferramenta-separa-os-dois)
e [50](docs/decisoes.md#50-a-conta-é-aberta-em-português-e-a-divisão-é-da-ferramenta).

### O estoque é finito, e só baixa quando ela aceita o prato

Ela tem **1,5 kg** de patinho. Não patinho à vontade. Um segundo prato que
calcula em cima da geladeira que o primeiro já esvaziou produz uma lista de
compras curta, e ela chega na cozinha com metade da carne que a fornada pede.

**O estoque é uma subtração, não um número guardado.** O que a planilha semeou,
menos o que os pratos já aceitos consumiram. A linha de `pantry_items` nunca é
reescrita; o consumo mora em `pantry_usage`, só-adição, uma linha por ingrediente
por prato.

```sql
-- o que ela ainda tem, em uma consulta
SELECT i.ingredient,
       i.stock_quantity - COALESCE(sum(u.quantity), 0) AS sobra
  FROM pantry_items i
  LEFT JOIN pantry_usage u ON u.ingredient_key = i.ingredient_key
 GROUP BY i.ingredient, i.stock_quantity;
```

Só-adição porque o que ela precisa ouvir não é o saldo, é para onde a carne foi.
*"Você tinha 1,5 kg, o escondidinho levou 560 g e sobraram 940 g"* é uma frase
que ela confere contra a própria geladeira; *"faltam 860 g"* parece erro de
planilha, e o que ela faz com um erro de planilha é duvidar do número em vez de
comprar a carne.

**E só baixa no aceite dela, nunca no cálculo.** Orçar um prato é uma pergunta;
colocá-lo no cardápio é uma decisão. O mesmo prato é orçado várias vezes, e às
vezes ela recusa no fim: se cada orçamento baixasse o estoque, a despensa
esvaziaria por conta de perguntas. Quem escreve é `menu_add_dish`, no instante em
que ela escolheu. As quantidades vêm da receita fechada, já resolvidas em unidade
base na hora do custo, para que aceitar o prato não precise resolver os nomes uma
segunda vez.

**E volta sozinho.** Tirar o prato do cardápio devolve o que ele tinha levado.
Reabrir a receita porque ela mudou de ideia também, porque o que aquela versão
consumia era de um prato que não vai mais ser feito. Nada disso depende de o
modelo lembrar de um segundo passo.

A fornada é o número dela: `portions` não tem valor padrão, e uma quantidade
diferente da que ela falou é recusada com a frase dela devolvida. Um padrão que
está errado sete vezes em oito é pior que um argumento faltando, porque a chamada
passa e ninguém percebe.

Aqui está a vantagem prática do Postgres, bem concreta: o estoque é um dado que o
operador precisa poder mexer, para repor o que ela comprou ou montar um cenário.
É um `UPDATE` de uma linha, conferível na hora com um `SELECT`. Decisões
[51](docs/decisoes.md#51-o-estoque-dela-é-finito-e-baixa-quando-o-prato-entra-no-cardápio)
e [52](docs/decisoes.md#52-a-fornada-é-o-número-dela-e-não-tem-valor-padrão).

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

`unknown` é uma pergunta, nunca um sim, e é isso que impede a sequência que o
enunciado manda evitar: comprar primeiro e descobrir depois. Um sim hesitante
também não é sim: um forno que ela tem *"mas queima embaixo"* volta como
pergunta, porque o detalhe que o desqualifica ficaria na nota, e a nota é o único
lugar que o portão não lê.

E um não nunca é definitivo. Quando um prato cai por falta de equipamento, ele é
**arquivado contra aquele equipamento**, não descartado:

```
ela não tem forno  →  lasanha ao forno bloqueada por 'forno'
                      parmegiana bloqueada por gosto
ela ganha um forno →  a lasanha volta sozinha, e ela é avisada
                      a parmegiana continua fora: gosto não é problema
                      esperando solução
```

A volta não depende de o modelo lembrar: gravar o `confirmed_yes` levanta os
bloqueios daquele item na mesma chamada. E se a receita de um prato aceito mudar
porque **ela** pediu, tudo que pendurava nela é refeito: buscar a receita, rodar
o portão, recalcular custo e preço. Decisões
[7](docs/decisoes.md#7-capacidades-têm-três-estados-e-silêncio-não-é-consentimento),
[30](docs/decisoes.md#30-o-prato-morto-é-fechado-pela-ferramenta-não-pelo-lembrete),
[35](docs/decisoes.md#35-um-sim-com-mas-dentro-não-é-um-sim) e
[43](docs/decisoes.md#43-a-receita-de-um-prato-fecha-uma-vez).

---

## O que pode melhorar

Quatro coisas, na ordem em que eu faria.

**Um servidor MCP de condução, para responder o que ela perguntou.** É a falha
da conversa lá em cima, e é de lógica de diálogo, não de conta. O
`conversation_state` diz onde a consultoria está; ninguém classifica o que a
**última frase dela** pediu, e por isso um *"dá pra fazer ou não?"* recebe uma
explicação e um *"me diz o custo logo"* recebe outro pedido de licença.

Um servidor `dialogue_*` com uma ferramenta que tipa o turno dela (pergunta
fechada, pedido de ação, resposta a uma pergunta pendente, desistência) e devolve
a forma da resposta devida dá ao portão de mensagem o que falta: ele mede se o
rascunho está empilhado e não mede se ele responde. Um pedido de ação já
concedido vira dívida: enquanto a ação não acontecer, perguntar de novo é
recusado. O mecanismo é o mesmo do veredito do prato morto, que é a garantia mais
sólida deste sistema.

**Perguntar em bloco, e por prioridade.** O portão pergunta um item por vez, e
`kitchen_register_requirement` não tem teto: cada variante de receita pode
acrescentar exigência, e nada impede uma sequência longa de perguntas antes de
ela ver um número. Não foi o que custou a conversa lá em cima, mas é risco real.
`kitchen_elicitation_gaps` já sabe quais respostas faltam e quais bloqueiam a
compra: falta ordenar por impacto e devolver o conjunto mínimo que destrava o
próximo passo, para ela responder três coisas de uma vez e ver a conta.

**Latência.** Um turno leva de sessenta a noventa segundos, e a maior parte é
busca na web. As frases de uma descoberta já correm em paralelo, com um prazo
sobre o conjunto: o que atrasa é descartado e dito, em vez de esperado, porque a
ferramenta responde a um cliente MCP que desiste em noventa segundos. O que falta
é cache: as mesmas buscas se repetem entre turnos da mesma consultoria, e um
cache por domínio e prato no Redis, com validade de horas, corta isso. Nada
disso muda o resultado, só o tempo que ela espera olhando a tela.

**Calibrar a nota com desfecho.** A confiança hoje **ordena** respostas: é
melhor que nada e não mede probabilidade de coisa nenhuma, e isso está escrito
onde alguém possa tropeçar. Calibrar exige registrar o que aconteceu depois (o
prato foi aceito? o preço se sustentou? a compra coube?) e mover os limiares com
esse dado. É o que transforma a nota de heurística ordenada em medida.

---

## O sistema em números

| | |
|---|---|
| **Servidores MCP** | 11, montados sob um único endpoint HTTP: `chat`, `pantry`, `dishes`, `recipes`, `kitchen`, `market`, `economy`, `budget`, `pricing`, `confidence`, `menu` |
| **Ferramentas** | 59, distribuídas nesses 11 servidores |
| **Decisões de arquitetura** | 53, cada uma com motivo e consequência |
| **Testes** | 277 na última rodada, em 15 suítes |
| **Modelo** | `claude-sonnet-5`, com OAuth de uma conta Anthropic Pro |
| **Armazenamento** | Redis 7 para a conversa, Postgres 17 para o que ela decidiu |

A distribuição das ferramentas por servidor: `recipes` e `kitchen` com 10 cada,
`menu` e `chat` com 7, `dishes` com 6, `pantry` com 5, `confidence` e `budget`
com 4, `pricing` com 3, `economy` com 2 e `market` com 1. A assimetria é do
problema: descobrir e qualificar receitas tem mais passos distintos do que
consultar um índice de inflação. A lista completa, com argumentos e o que cada
resultado significa, está em
[docs/referencia-mcp.md](docs/referencia-mcp.md).

---

## O que eu deixei de fora, e por quê

**Nenhum cálculo passa por modelo.** CMV, preço mínimo, lucro, saldo e projeção
de inflação são Python. Um modelo a quem se pede para multiplicar preços devolve
um número plausível, e plausível é indistinguível de correto até alguém gastar
dinheiro em cima.

**Nada de memória vetorial nem RAG.** A despensa tem 37 linhas. Busca semântica
sobre isso é infraestrutura para um problema que `SELECT` resolve, e traz uma
classe de erro nova: recuperar o ingrediente parecido em vez do certo.

**Nenhum segundo modelo como juiz.** O enunciado pede um agente, e dois
provedores no circuito é uma dependência e uma conta a mais. O avaliador é o
mesmo modelo sob uma régua mais dura, num turno próprio.

**Sessões simultâneas não são isoladas de verdade.** Correto para uma consultoria
por vez, que é o caso de uso; insuficiente para várias pessoas ao mesmo tempo.

**Não há teste automatizado de diálogo.** Cada execução custa uma chamada de
modelo e o julgamento do resultado é humano. A simulação é manual, e o que ela
encontra está em [docs/dialogos.md](docs/dialogos.md), inclusive o que continua
torto.

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [docs/arquitetura.md](docs/arquitetura.md) | Componentes, camadas, fluxogramas e diagramas de sequência |
| [docs/decisoes.md](docs/decisoes.md) | As 53 decisões de arquitetura, com motivo e consequência |
| [docs/dialogos.md](docs/dialogos.md) | Conversas reais: cinco que deram certo e quatro modos de falha |
| [docs/metricas.md](docs/metricas.md) | Como a confiança é calculada, o pipeline de afirmações, e as referências |
| [docs/modelo-de-dados.md](docs/modelo-de-dados.md) | Esquema do Postgres, chaves do Redis, normalização de unidades |
| [docs/referencia-mcp.md](docs/referencia-mcp.md) | As 59 ferramentas, os prompts e os recursos |
| [docs/operacao.md](docs/operacao.md) | Execução, credenciais, depuração, modos de falha |
| [docs/testes.md](docs/testes.md) | A suíte automatizada e o que a simulação manual cobre |

### Estrutura

```
bin/jacquinho          ponto de entrada de linha de comando
app/domain/            cálculo e regras, sem conhecer MCP
app/mcps/              uma classe por servidor MCP, mais a raiz de composição
hooks/                 fronteiras de turno: a fala dela, a resposta dela
hermes/SOUL.md         voz e quem fala primeiro, lido pelo agente
dockerfile/            imagem, compose, dependências, config do agente
```
