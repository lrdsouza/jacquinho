# Decisões de arquitetura

![Registros](https://img.shields.io/badge/registros-46-6E56CF)
![Modelo](https://img.shields.io/badge/modelo-Claude%20Sonnet%205-D97757)

Cada registro diz o que o sistema faz e por que é construído assim. Onde a
decisão tem consequência de infraestrutura (latência, escalabilidade,
observabilidade, elasticidade) ela fecha dizendo qual. Onde não tem, não
inventa uma.

---

## 1. O cálculo vive fora do modelo de linguagem

**Decisão.** Custos unitários, CMV, preço mínimo, cenários de preço, aritmética
de orçamento e projeções de inflação são calculados em Python e devolvidos como
dados estruturados. Nunca se pede um número ao modelo.

**Motivo.** Um modelo a quem se pede para multiplicar preços de mercado devolve
um número plausível, e plausível é indistinguível de correto até alguém gastar
dinheiro em cima. Aritmética em código é auditável, testável e idêntica em toda
execução.

**Consequência.** Todo resultado que envolve dinheiro carrega a própria conta,
`0,20 x 14,00 = 2,80`, para que o agente possa mostrar o cálculo em vez de
afirmar um total.

**Latência e observabilidade.** Uma multiplicação em Python custa microssegundos;
o mesmo número pedido ao modelo custa um turno inteiro, com a rede no meio.
Tirar aritmética do modelo remove latência do caminho crítico e, mais importante,
torna todo número rastreável: entradas, fórmula e saída aparecem no resultado da
ferramenta, então uma margem errada é depurável sem reproduzir uma conversa.

---

## 2. Um endpoint HTTP, onze servidores montados

**Decisão.** Onze classes de servidor MCP são montadas sob prefixos em uma única
instância FastMCP, servida sobre HTTP.

**Motivo.** Separação de responsabilidades sem espalhamento operacional: um
container, um healthcheck, uma URL na configuração do agente, e mesmo assim cada
área continua sendo sua própria classe, com suas instruções e seus testes.

HTTP em vez de stdio é estrutural. Um servidor stdio é subprocesso do processo
que o lança, o que forçaria a camada de cálculo a morar dentro do container do
agente. Como serviço HTTP ele é iniciável, depurável e alcançável de forma
independente, sem agente nenhum.

**Elasticidade e observabilidade.** O servidor MCP não guarda estado entre
requisições, porque tudo vive no Postgres ou no Redis, então ele escala
horizontalmente atrás de um mesmo endereço, sem afinidade de sessão. E como toda
chamada de ferramenta passa por um único processo HTTP, existe um log de acesso
só onde ver o que o agente de fato fez, em vez de reconstruir isso da
transcrição.

---

## 3. O procedimento vai com o servidor; a voz não pode

**Decisão.** Não há arquivos de skill. O **procedimento** vive nas descrições das
ferramentas, no campo `next_step` dos resultados e em quatro prompts MCP. A
**voz** (idioma, quem fala primeiro, postura) vive em `SOUL.md`, do lado do
agente.

**Motivo.** Uma regra escrita onde não pode ser imposta se descola do código que
deveria impô-la, e é por isso que o procedimento acompanha o servidor: mudar a
regra e mudar a verificação andam no mesmo commit.

A voz é o caso em que isso não funciona, e a razão é do protocolo. O Hermes trata
texto que chega por MCP como **dado não confiável**, não como instrução: existe um
scanner de injeção sobre esse texto, e as `instructions` de um servidor MCP não
entram no system prompt. Uma persona escrita ali simplesmente não chega ao
modelo.

O sintoma foi exato: a um "oi" o agente respondia *"Oi! What can I help you
with?"*, em inglês e sem abrir a consultoria. Assim que uma ferramenta era
chamada ele voltava ao trilho, porque aí o procedimento chegava pela descrição da
ferramenta. Faltava só o que só o system prompt entrega.

**Consequência.** `SOUL.md` é lido automaticamente de `HERMES_HOME`, sem chave de
configuração, e carrega o mínimo que precisa estar no system prompt: fale
português, fale primeiro, e siga o `next_step` das ferramentas. As regras que
podem ser impostas continuam sendo impostas no servidor, onde uma verificação as
acompanha.

**Observabilidade.** A versão do comportamento continua sendo a tag da imagem para
o procedimento, e o `SOUL.md` é versionado no repositório junto dela.

**Observabilidade.** A versão do comportamento é a tag da imagem. Para saber que
regras estavam valendo numa conversa de semana passada basta a versão que estava
no ar, e não é preciso caçar que arquivo solto existia na máquina do agente
naquele dia.

---

## 4. Ferramentas MCP em vez de skills

**Decisão.** Tudo que pode ser verificado é uma ferramenta MCP. Só o que não pode
ser verificado (voz, postura, julgamento sobre o que dizer) fica como texto.
O projeto não tem nenhuma skill.

**Motivo.** Uma skill é instrução: texto que o modelo lê e, se tudo correr bem,
segue. Uma ferramenta é execução: código que roda e devolve um valor que o modelo
não produziu. A diferença aparece exatamente onde este trabalho não pode falhar.

*Uma instrução pode ser ignorada; um resultado não pode ser inventado.* Uma skill
que diz "sempre calcule o CMV a partir dos custos unitários" é um pedido.
`pricing_calculate_cmv` devolve um número que o modelo não escreveu. Quando ela
vai gastar dinheiro em cima, essa distinção é o projeto inteiro.

*Uma skill não recusa.* `safe_to_shop: false` é um portão que devolve uma recusa
legível por máquina. Uma skill só consegue *dizer* "não deixe ela comprar ainda";
a ferramenta consegue **não entregar o número** até o portão fechar. O
`price_scenarios` leva isso ao limite: sem faixa de mercado observada ele não
devolve preço de venda nenhum, por mais que se peça.

*Uma skill não guarda estado.* O saldo do orçamento que diminui, o perfil da
cozinha em três estados, o bloqueio que se desfaz quando a capacidade muda: são
transições com integridade. Texto não tem transação, nem `NUMERIC`, nem `CHECK`,
nem índice parcial.

*Uma skill não é testável sem um modelo.* A normalização de unidades, o casador
de ingredientes, o motor de consenso e o ciclo de bloqueio e liberação foram
todos verificados chamando funções, sem nenhuma conversa envolvida. Skill só se
avalia rodando diálogo, o que é lento, caro e não determinístico.

**Consequência.** A regra que ficou: **o que pode ser conferido vira ferramenta;
o que só pode ser dito continua texto.** E o texto que sobrou é pouco: voz e
quem fala primeiro, no `SOUL.md`, mais quatro prompts que carregam procedimento
de várias etapas.

**O outro lado.** Isso não é gratuito. Uma ferramenta custa esquema, validação e
um caminho de erro para cada argumento; uma skill custa um parágrafo. Para
comportamento que não tem certo e errado computável, a ferramenta é peso morto,
e foi exatamente esse o erro que a persona no MCP revelou. Onde não há o que
verificar, texto é a resposta certa.

**Observabilidade.** Toda chamada de ferramenta é uma requisição HTTP com linha de
log: dá para ver o que o agente fez, em que ordem, com que argumentos e o que
voltou. Uma skill "ter sido seguida" não é um evento observável, e a única
evidência é a própria resposta, que é o que estava em dúvida.

**Elasticidade e portabilidade.** As ferramentas são um serviço, não um arquivo na
casa do agente. Escalam horizontalmente sem afinidade de sessão, e qualquer
cliente MCP as alcança, então o comportamento não fica preso a um agente específico.

---

## 5. Unidades da planilha são embalagens, e precisam ser resolvidas

**Decisão.** Uma string de unidade é analisada em busca de quantidade embutida
antes de ser tratada como unidade. `balde 2kg` é uma embalagem de dois quilos,
`un 500g` é meio quilo, e todo custo é expresso por quilo, litro ou unidade.

**Motivo.** Dividir preço por quantidade sem ler a embalagem produz um custo por
balde, que não pode ser aplicado a uma receita que pede vinte gramas. O erro é
silencioso e cai direto na margem.

**Consequência.** Um item precificado por peça avulsa sem peso declarado é
sinalizado, e pedir gramas dele produz uma pergunta em vez de um número.

---

## 6. O casamento de ingredientes recusa quase-acertos

**Decisão.** Nomes são casados sem sensibilidade a acento ou caixa, com
conectivos excluídos da pontuação, e um casamento abaixo do limiar devolve nada
em vez do candidato mais próximo.

**Motivo.** Contar conectivos faz nomes sem relação parecerem semelhantes, e
dizer a ela que já tem um ingrediente que não tem é pior do que perguntar. Um
falso negativo custa uma pergunta. Um falso positivo custa um item faltando na
lista de compras.

---

## 7. Capacidades têm três estados, e silêncio não é consentimento

**Decisão.** Toda capacidade da cozinha é `confirmed_yes`, `confirmed_no` ou
`unknown`. Só `confirmed_yes` permite que um prato avance.

**Motivo.** Dois estados forçam perguntas não respondidas a cair em uma das
respostas, e a que elas caem é invariavelmente o sim. O risco inteiro que se
está administrando é ela comprar ingredientes para um prato que não consegue
produzir.

**As chaves são canônicas, não texto livre.** A primeira versão aceitava qualquer
string em `item`, e o agente gravava `forno de 45l`. O portão então procurava
`forno`, não achava, e devolvia `unknown`, enquanto ler o perfil dava a
resposta. O atalho ficava melhor que o caminho certo, e o agente naturalmente
pegava o atalho. Agora `record_capability` resolve o que chega para uma chave do
catálogo (`forno de 45l` → `forno`, o detalhe indo para `note`) e recusa o que
não mapeia, apontando para `register_requirement`. Um portão que não encontra o
que foi gravado não é um portão.

**Observabilidade.** `unknown` é uma lacuna contável, não uma ausência silenciosa.
`elicitation_coverage` devolve a fração do catálogo já respondida, o que
transforma "o agente perguntou o suficiente?" numa métrica em vez de uma
impressão.

---

## 8. As exigências são lidas da receita, não recordadas

**Decisão.** O que uma receita exige é extraído do texto dela por marcadores de
equipamento e técnica, e cada detecção carrega as palavras que a levantaram.

**Motivo.** Exigências recordadas são o que o prato costuma precisar. Exigências
extraídas são o que esta receita diz precisar. As palavras de evidência também
permitem ao agente explicar por que está perguntando, que é a diferença entre
uma conversa e um interrogatório.

**Consequência.** Existe um argumento `extra_requirements` para o que se enxerga
e o texto não explicita. Ele acrescenta exigências; nunca remove.

---

## 9. Exigência não reconhecida bloqueia

**Decisão.** Uma exigência que não mapeia para nenhum item do catálogo é tratada
como pergunta em aberto e bloqueia a compra, e pode ser incorporada ao catálogo.

**Motivo.** Esta é a classe mais perigosa de exigência, porque é exatamente
aquilo sobre o que ninguém nunca perguntou a ela. Tratar exigência desconhecida
como satisfeita reintroduz precisamente a falha que o catálogo existe para
evitar.

**Consequência.** O catálogo cresce com o uso. Itens registrados persistem e se
levantam sozinhos em receitas posteriores.

---

## 10. Um prato precisa de concordância entre fontes independentes

**Decisão.** A descoberta roda várias formulações de busca, agrupa resultados
por domínio registrável e promove um nome de prato apenas quando ele aparece em
domínios distintos suficientes e toca um ingrediente da despensa.

**Motivo.** Uma página é uma opinião. Várias páginas do mesmo site continuam
sendo uma opinião, e é por isso que o agrupamento é por domínio e não por
resultado. Exigir um ingrediente da despensa mantém a concordância ancorada no
que ela de fato consegue cozinhar.

**Consequência.** Uma expressão feita inteiramente de palavras da despensa é um
ingrediente, não um prato, e é descartada. A confiança nos dados de mercado
segue a mesma regra: conta fontes distintas, não observações.

**Latência.** Concordância custa. Uma descoberta dispara várias buscas em vez de
uma, e a rede domina o tempo da chamada. É uma troca deliberada de latência por
confiabilidade, e por isso o número de formulações é parâmetro da ferramenta:
quem chama decide quanto tempo está disposto a gastar por quanta certeza.

---

## 11. A recência é dividida pelo que se está perguntando

**Decisão.** A descoberta de pratos guarda cinco anos. Qualquer coisa sobre
dinheiro guarda um mês. A inflação usa a última publicação oficial e informa a
idade dela.

**Motivo.** São perguntas diferentes. Uma técnica de quatro anos atrás continua
válida; um preço de cardápio de quatro anos atrás é desinformação.

**Consequência.** Nenhum buscador expressa uma janela de cinco anos, então essa
janela não envia filtro nenhum ao provedor e é imposta inteiramente por
pós-filtragem. O pós-filtro é deliberadamente conservador: só rejeita resultados
que declaram um ano anterior ao corte, e páginas sem data passam.

Apertar a busca de preços para um mês frequentemente não devolve nada. Esse é o
comportamento correto, e a ferramenta diz o que fazer a respeito: alargar a
janela e **rotular** a referência como mais antiga, quantificando a diferença
com o índice de inflação. Uma referência antiga rotulada é útil. Uma sem rótulo
não é.

---

## 12. Nenhum preço de venda sem mercado observado

**Decisão.** `price_scenarios` sempre devolve o preço mínimo. Não devolve preço
de venda nenhum sem uma faixa de mercado observada, e os cenários são ancorados
no mínimo, na mediana e no máximo observados.

**Motivo.** Um multiplicador sobre o custo é um palpite com casa decimal. O
custo determina o piso; só o mercado determina o preço.

**Consequência.** Uma âncora abaixo do preço mínimo é reportada como inviável,
que é como o agente aprende a dizer que um prato não compete por preço, em vez
de propor um prejuízo em silêncio.

---

## 13. O lucro é expresso em moeda de hoje

**Decisão.** Todo cenário projeta no que a margem se transforma em doze meses se
os custos dos ingredientes acompanharem a inflação de alimentos e o preço de
cardápio ficar parado, e que preço sustentaria a margem.

**Motivo.** A inflação não reduz um percentual de margem; ela eleva custos
enquanto um preço impresso fica parado. Comparar uma razão de margem contra uma
taxa de inflação compara grandezas diferentes e não significa nada. Projetar o
custo para frente é a comparação que tem conteúdo.

**Consequência.** O índice de alimentação no domicílio é usado para os custos
dos ingredientes em vez do índice geral, porque é a série que a conta de
supermercado dela segue. O índice regional é usado porque é onde ela vende.

---

## 14. O orçamento é um saldo

**Decisão.** O orçamento de complementos é estado guardado que diminui conforme
as compras são fechadas, sobrevive a reinicializações e recusa estourar.

**Motivo.** Um orçamento escrito como constante é relido como cheio a cada
prato. Do segundo prato em diante isso é simplesmente errado, e o erro se
acumula em silêncio.

**Consequência.** A estimativa de custo consulta o saldo vivo em vez do valor
inicial, então o segundo prato é avaliado contra o que de fato sobrou.

**Consistência.** O saldo é derivado por `sum()` no banco, nunca guardado, então
não pode divergir das entradas. As compras são linhas apenas inseridas, em
`NUMERIC`, não em ponto flutuante, porque dinheiro não acumula erro de arredondamento
aqui, e duas sessões simultâneas não conseguem gastar o mesmo dinheiro duas
vezes.

---

## 15. A confiança combina dois avaliadores, de forma conservadora

**Decisão.** Uma nota determinística ponderada sobre a trilha de evidências,
mais um turno de julgamento que lê o rascunho da resposta contra essa mesma
evidência. No modo híbrido a nota final é a menor das duas.

**Motivo.** Os dois falham de maneiras diferentes. A nota determinística não
pode ser persuadida, mas só enxerga aquilo para que foi construída. O juiz lê a
redação de fato e pega afirmações que nada sustenta, mas pode ser convencido.
Ficar com a menor nota significa que uma resposta vale o que diz o revisor menos
convencido.

**Consequência.** Discordância acima de um limiar é reportada explicitamente, e
impedimentos anulam a nota por completo: gate aberto, CMV incompleto ou faixa de
mercado ausente barram a resposta em qualquer nota.

**E três ferramentas são recusadas, não apenas desaconselhadas.** Conselho errado
se corrige na conversa seguinte; `pricing_price_scenarios`, `menu_add_dish` e
`budget_reserve_purchase` mexem no dinheiro dela ou vão para um cardápio. O middleware
recusa essas três enquanto o portão de viabilidade não tiver aprovado nesta
sessão, com a mensagem que fecha o atalho: *"ler o perfil da cozinha não conta:
ler não é verificar."* É a diferença entre pedir ao agente que não pule uma etapa
e ele não conseguir pular.

**Latência.** O julgamento custa um turno inteiro do modelo, e é o item mais caro
do fluxo. Por isso a nota determinística volta na hora e sozinha basta para
barrar: uma resposta que já falhou nela nunca chega a pagar o turno do juiz.

**A confiança não pode depender de o agente pedir.** A primeira versão era uma
ferramenta que o agente devia chamar antes de falar. Medido numa conversa real:
onze chamadas ao MCP, **zero avaliações**. Um modelo pequeno com cinquenta e duas
ferramentas não lembra de chamar mais uma antes de cada mensagem, e uma
instrução que pode ser pulada não é garantia.

Então o servidor virou observador. Um middleware intercepta toda chamada, guarda
as que carregam evidência (gate, CMV, consenso, mercado, inflação) e recalcula
a nota depois de cada uma, escrevendo uma linha no log. `jacquinho confidence`
lê esse log ao lado do chat. Nada depende de o agente lembrar.

Isso é a mesma regra da decisão sobre ferramentas contra skills, aplicada à
própria camada de confiança: o que pode ser conferido não fica como pedido.

**E é visível.** Toda avaliação devolve um `display.badge` que o agente cola no
fim da mensagem: `〔preço: confiança alta · CMV completo · 4 fontes〕`. Esse caminho
depende do modelo e portanto falha às vezes; o log não depende de nada.

**A confiança é da afirmação, não do pipeline.** A primeira versão pontuava toda
mensagem contra os cinco sinais (gate, CMV, consenso, mercado, inflação) e o
resultado era 0,00 na conversa inteira. Faz sentido: "você tem 37 ingredientes"
não precisa de preço de mercado. Marcar isso como zero não dizia nada sobre a
frase e tudo sobre um medidor apontado para o lugar errado.

Cada mensagem afirma um tipo de coisa, e cada tipo se apoia em evidência
diferente:

| Afirmação | Repousa sobre |
|---|---|
| o que ela tem | a planilha |
| sugestão de prato | a planilha e a concordância entre fontes |
| se ela consegue fazer | o gate |
| custo | a planilha, o gate e o CMV |
| preço | o gate, o CMV, o mercado e a inflação |

O tipo em jogo é inferido da ferramenta que acabou de rodar: quem leu a despensa
vai falar da despensa; quem calculou cenário vai falar de preço. A nota então
usa só os sinais daquele tipo, e os impedimentos também: um fato da despensa não
é barrado por falta de preço de mercado.

O efeito é que a nota volta a discriminar. Ler a despensa dá 1,00, porque a
planilha é determinística e ler é saber. Afirmar preço sem ter apurado nada dá
0,00 com três impedimentos. Antes, os dois davam zero.

**A escala é 0 a 1.** Uma nota de 0 a 100 lê como prova de escola e convida a
discutir um ponto para cima ou para baixo; 0 a 1 lê como o que é, um grau de
crença, e mantém os dois avaliadores na mesma régua. As bandas ficam em 0,75 e
0,50. O número aparece no log, para quem avalia a execução. O badge que ela
recebe continua sem número, porque citar decimal de heurística é falsa precisão.
Se o juiz responder `80` querendo dizer `0,80`, o valor é normalizado em vez de
virar uma confiança de oitenta.

Duas escolhas dentro do badge. Ele lista os sinais **mais frágeis primeiro**,
porque um marcador que enumera o que deu certo e omite o que não deu lê como
tranquilização. E ele não mostra percentual: um número dá falsa precisão a uma
heurística, enquanto "poucas fontes de preço" diz o que de fato se sabe.

**Observabilidade.** Cada avaliação é gravada em `answer_assessments` com o
rascunho, as duas notas, a banda e os impedimentos. Dá para procurar depois toda
resposta que saiu com banda baixa, sem reproduzir nenhuma conversa.

---

## 16. O turno de julgamento é uma troca explícita

**Decisão.** Pedir um julgamento emite um ticket que carrega a rubrica e as
evidências. O julgamento é feito como turno próprio e devolvido por uma segunda
ferramenta. Tickets são de uso único.

**Motivo.** Chamadas ao modelo iniciadas pelo servidor não estão disponíveis
neste transporte, então o turno de julgamento é devolvido para fora. E é
melhor assim: o turno de julgamento aparece na transcrição, o que torna um
julgamento pulado ou contrariado visível, em vez de algo em que se confia.

**Consequência.** O juiz é um turno restrito do mesmo modelo que conduz a
conversa. Nenhum segundo provedor é introduzido.

---

## 17. A recusa alimenta uma lista de candidatas

**Decisão.** Toda receita aberta é salva com sua fonte, ingredientes,
equipamentos exigidos e técnicas exigidas. As recusas registram um motivo
tipado. A próxima opção sai da lista, ordenada pelo que ela respondeu. A web só
é consultada de novo quando a lista esvazia.

**Motivo.** Sem uma lista, a busca é amnésica e toda recusa recomeça do zero.
Guardar as exigências de cada receita é o que permite que uma única resposta,
"ela não tem forno", elimine toda receita que precise de um, sem nova busca.

**Consequência.** Um prato que a cozinha dela não faz não é oferecido como
próxima opção. Candidatas bloqueadas são reportadas à parte com o que as
bloqueia, para que um impedimento duro nunca se esconda atrás de uma pergunta
em aberto.

**Escalabilidade da consulta.** Bloqueio não é apagado, é liberado, então o
histórico só cresce. A consulta quente, "o que ainda está aberto", usa índice
parcial sobre `lifted_at IS NULL`, de modo que ela enxerga apenas os bloqueios em
vigor e não fica mais lenta conforme o histórico engorda.

---

## 18. O Redis guarda a conversa: 20 turnos mais 1 resumo

**Decisão.** O contexto que o agente segura é sempre a mesma coisa: os **20
últimos turnos**, na prática cerca de dez dela e dez do agente, mais **uma
única mensagem de resumo** que representa tudo o que veio antes. Quando 20
turnos novos se acumulam desde o último resumo, o resumo é reescrito para
absorvê-los. Os turnos antigos continuam gravados; o corte é do que o agente
segura, não do que se guarda.

```
 10 turnos | janela=10 | resumo cobre= 0 | desde=10 | precisa resumo=não
 20 turnos | janela=20 | resumo cobre= 0 | desde=20 | precisa resumo=SIM
      -> resumo gravado cobrindo 20 turnos
 25 turnos | janela=20 | resumo cobre=20 | desde= 5 | precisa resumo=não
 40 turnos | janela=20 | resumo cobre=20 | desde=20 | precisa resumo=SIM

contexto final: 1 resumo + 20 turnos, de msg21 a msg40
```

O resumo é escrito pelo próprio Hermes, num turno separado: `chat_get_context`
avisa quando é devido, `chat_turns_awaiting_summary` entrega o que falta cobrir
junto do resumo anterior, e `chat_save_summary` grava a versão nova. Nenhum
segundo modelo entra no circuito.

**Motivo.** Uma conversa de cozinha é longa e repetitiva. Reenviar tudo a cada
turno cresce sem limite, e cortar sem resumir perde justamente o que importa:
que ela não tem forno, que recusou fritura, que já gastou sessenta reais. A
janela mais o resumo mantêm as duas coisas: o texto recente literal, e a
memória do que ficou decidido.

**Consequência.** O resumo é instruído a guardar decisões, capacidades e
recusas com seus motivos, e a jogar fora conversa fiada. É o que uma retomada
precisa reler.

**Latência, escalabilidade e elasticidade.** A janela é uma lista Redis: gravar
é um `RPUSH`, ler é um `LRANGE` dos últimos vinte, operações de tempo
constante, fora do caminho do banco relacional. E o efeito que mais importa não
é de disco e sim de token: o contexto por turno fica **limitado por construção**,
então o custo de uma conversa cresce linearmente com o número de turnos, não com
o quadrado. Como o estado vive no Redis e não no processo, várias réplicas do
servidor MCP atendem a mesma conversa sem afinidade de sessão.

**Por que aqui e não no Postgres.** Isto é estado quente: reescrito a cada turno,
lido a cada turno, e sem valor depois de resumido. Os tickets de julgamento
seguem a mesma lógica e ficam no Redis com TTL de uma hora, porque um ticket
abandonado no meio de uma conversa deve expirar, não se acumular.

---

## 19. O Postgres guarda os dados da Dona Maria

**Decisão.** Tudo que é um registro sobre ela vive em Postgres: a despensa
aprendida (pesos de embalagem), o perfil da cozinha, o catálogo de restrições
que cresceu na conversa, o saldo do orçamento, as categorias de prato, o
catálogo de receitas com seus requisitos e bloqueios, o que ela achou de cada
prato, e o cardápio de lançamento. Treze tabelas. O volume de arquivos JSON que
existia antes deixou de existir.

**Motivo.** Nenhuma dessas coisas é cache. São fatos que sobrevivem a qualquer
sessão, e três propriedades disso pesam:

*São relacionais.* Um bloqueio existe **por causa de** uma capacidade. Quando a
capacidade muda, quando ela compra o fogão que não tinha, todo prato que esperava
por aquilo precisa voltar sozinho. Isso é um `UPDATE ... WHERE blocking_item =
%s RETURNING`, uma linha de SQL. Em chave-valor seria varredura e reconstrução
em Python.

*Não podem ser despejadas.* O Redis é um armazenamento com política de
expiração. Perder o perfil da cozinha dela significa perguntar tudo de novo;
perder o saldo do orçamento significa deixá-la gastar duas vezes.

*Precisam ser consultáveis sem o agente.* "Que pratos foram recusados por falta
de forno?" é uma consulta, e responder isso não deveria exigir subir um modelo.

**Consequência.** O tipo `NUMERIC` guarda dinheiro sem erro de arredondamento, e
as restrições `CHECK` recusam um estado de capacidade inválido na porta do
banco, não na camada que o escreveu.

**Observabilidade.** Todo o estado da consultoria é inspecionável com `psql`. Por
que um prato saiu, o que o trouxe de volta, quanto do orçamento foi para quê,
que capacidades foram confirmadas e quando, tudo com data e motivo, legível sem
reproduzir a conversa. É a diferença entre depurar o sistema e entrevistá-lo.

**A régua que decide onde a próxima coisa vai.** Vai para o Redis quando perdê-la
custa contexto; vai para o Postgres quando perdê-la custa uma pergunta repetida
ou dinheiro gasto duas vezes. Foi por ela que os utensílios ficaram no Postgres,
e é por ela que a fala capturada pelos hooks ficou no Redis: é conversa, e o
Postgres só a consulta no instante em que confere uma citação.

---

## 20. O modelo padrão é o Claude Sonnet 5

**Decisão.** `model.default` é `claude-sonnet-5`, com provedor `anthropic`,
fixado em `dockerfile/hermes-config.yaml`. A credencial é a de uma **conta
Anthropic no plano Pro**, autorizada por OAuth com `jacquinho login`, não uma
chave de API, porque o plano Pro não emite uma.

**Motivo.** A escolha começou no modelo mais barato da família, e pela razão
certa: a aritmética está em Python, as regras são portões que devolvem `verdict`
e `safe_to_shop`, e o trabalho do modelo é rotear, perguntar e redigir em
português claro. Nada disso pede raciocínio profundo, e uma consultoria inteira
gasta dezenas de chamadas.

O que a simulação mostrou é que o gargalo não é profundidade, é **condução**.
São 58 ferramentas e cadeias de vários passos, e o modelo mais barato perdia o
fio: chamava a ferramenta certa com o prato errado, esquecia de nomear o `dish`,
repetia busca. Cada tropeço desses custa mais chamadas do que o modelo mais caro
teria custado.

**Consequência.** Trocar é uma linha. `claude-haiku-4-5` se custo pesar mais que
condução, `claude-opus-5` quando capacidade importar mais que custo. Nada mais
muda: os onze servidores MCP e as 58 ferramentas se comportam de forma idêntica
por baixo, porque o comportamento não mora no modelo.

**Custo e latência.** O único turno caro do fluxo é o do juiz, e é por isso que a
ordem importa: o avaliador determinístico roda primeiro e de graça, e o juiz só
entra depois. A decisão de modelo e a decisão de ordem se reforçam.

**Nota sobre a credencial.** Uma assinatura não necessariamente libera a família
inteira de modelos. Rode `jacquinho hermes model` depois do login para ver o que
a conta oferece e ajuste a linha `default:` se o Sonnet não estiver lá.

---

## 21. A imagem constrói apenas a camada de cálculo

**Decisão.** A imagem do projeto contém os servidores MCP e suas dependências,
sobre uma base Python enxuta e sem cadeia de compilação. O agente roda a partir
da imagem publicada dele e recebe a customização do projeto por montagem.

**Motivo.** A imagem do agente carrega um ambiente de execução cuidadosamente
montado, incluindo uma camada de armazenamento da qual a memória dele depende.
Reconstruir aquilo do zero troca algo correto por algo aproximado.

**Consequência.** A imagem do projeto fica pequena, reconstrói em segundos, e a
planilha é montada somente para leitura, de modo que nenhum dado dela jamais é
gravado em uma camada.

**Elasticidade.** Imagem pequena sobe rápido. Como o servidor MCP não guarda
estado no disco dele, subir uma réplica é puxar cerca de duzentos megabytes e
apontar para o mesmo Postgres e o mesmo Redis, e não há nada para migrar junto.

---

## 22. A ferramenta é testada, não só exercitada

**Decisão.** Uma suíte de 140 testes automatizados sobre a camada de domínio e o
servidor, rodando em cerca de um segundo e meio com `jacquinho test`. O domínio
é testado sem banco: a única coisa que ele precisa de Postgres são linhas, e um
banco falso de vinte linhas devolve exatamente o que a semeadura teria escrito.

**Motivo.** Este projeto tem duas classes de risco. A primeira é o agente dizer
algo errado, e para isso existem o portão, a confiança e o juiz. A segunda é a
ferramenta simplesmente quebrar, e essa não tem nada a ver com modelo. Um
`AttributeError` numa consulta de despensa vira "não achei o ingrediente", que é
indistinguível de "ela não tem".

**Consequência.** Quase todo teste existe porque um bug existiu primeiro: o
conectivo que fazia `farinha de rosca` casar com `farinha de trigo`, o `400.0`
que virava fator zero e sumia com o ingrediente, a banda extraída fatiando a
string do badge. Um teste que não teria pego bug nenhum é peso morto; estes
pegariam todos de novo.

A planilha usada nos testes é a real. Fixture que mente é pior que fixture
nenhuma: se a normalização quebrar para `balde 2kg`, ninguém quer descobrir com
um arquivo inventado que não tem baldes.

**Observabilidade.** O primeiro efeito prático foi mover o arredondamento de
cardápio da camada MCP para o domínio, porque o teste não conseguia alcançá-lo sem
subir um servidor, o que era o próprio sintoma de estar no lugar errado.

---

## 23. As falhas da métrica são corrigidas onde dá, e escritas onde não dá

**Decisão.** As seis falhas conhecidas da camada de confiança foram atacadas, e
cada uma tem o estado registrado: corrigida, parcial ou explicitada. As que
permanecem estão escritas com o motivo.

| Falha | Estado |
|---|---|
| O observador não lê a mensagem | Mitigada: o cardápio exige avaliação |
| Afirmação inferida da última ferramenta | Corrigida: declarada tem precedência |
| Degraus arbitrários | Explicitados como ordinais, não calibrados |
| Sessão global | Parcial: trilha por sessão e prato, chave ainda fixa |
| Trilha só cresce | Corrigida: por prato, despensa compartilhada |
| `pantry` binário | Corrigida: cobertura vira a nota |

**Motivo.** Uma métrica cujos limites não estão documentados vira número mágico:
alguém lê 0,85 e acredita que significa 85% de alguma coisa. Não significa. Os
degraus ordenam respostas corretamente e o valor absoluto não é probabilidade de
nada, e isso precisa estar escrito ao lado do número.

**Consequência.** Duas correções vieram de tentar corrigir, não de planejar. A
trilha por prato revelou que `kitchen_check_feasibility` **não tinha argumento
`dish`**: a aprovação caía numa trilha sem nome e o prato era recusado no
cardápio sem explicação. E o isolamento por sessão revelou que `ctx.session_id`
é um UUID novo a cada requisição: cada chamada caía numa trilha própria e nada
acumulava.

**Observabilidade.** O que sobrou está em `docs/metricas.md` com o residual de
cada falha, não como lista de desejos mas como limite conhecido do que a nota
mede.

---

---

## 24. O estado da conversa viaja em toda resposta de ferramenta

**Decisão.** Todo resultado de ferramenta carrega um bloco `conversation_state`:
que prato está em jogo, se o portão passou, se o CMV foi calculado, se o mercado
foi pesquisado, e qual é a próxima ação.

**Motivo.** Nove turnos de conversa real mostraram o defeito dominante: o agente
perde o fio e volta a oferecer o que ela já escolheu. Não por má vontade: nada
à frente dele dizia onde as coisas estavam. Dizer uma vez, num texto que ele
pode não reler, não é o mesmo que dizer em toda chamada.

**Consequência.** É a mesma regra do projeto inteiro aplicada à condução: o que
pode ser conferido não fica como pedido. O middleware já mantinha a trilha por
prato; anexá-la ao resultado custou nada e ataca o defeito onde ele acontece.

**Observabilidade.** A injeção fica **fora** do bloco que engole exceções do
observador. Se o estado não puder ser anexado o agente perde o fio, e uma falha
silenciada aí é exatamente como isso passa despercebido.

---

## 25. As ferramentas exigem umas às outras

**Decisão.** Uma cadeia de pré-condições verificadas pelo middleware: preço exige
portão aprovado **e** CMV completo para aquele prato; cardápio exige, além
disso, que uma avaliação tenha ocorrido.

**Motivo.** Metade das ferramentas nunca era chamada numa conversa real. CMV,
mercado, feedback, memória. Instruir não bastou. A alavanca que já havia
funcionado para o portão foi estendida: cada exigência transforma uma sugestão
numa garantia, e só nas ferramentas que mexem no dinheiro dela ou vão para um cardápio.

**Consequência.** O caminho certo passou a ser o único caminho, em vez do mais
trabalhoso. Foi isso que fez o agente pular o portão antes: ler o perfil dava
resposta e rodar o portão dava trabalho.

---

## 26. Os números da mensagem são conferidos sem modelo

**Decisão.** `confidence_audit_figures` extrai toda cifra e todo percentual da
mensagem e verifica se cada um aparece no que as ferramentas devolveram.

**Motivo.** O observador pontua a evidência e nunca lê a frase; o juiz lê a
frase mas precisa ser invocado. Entre os dois havia algo que nenhum fazia e que
não precisa de modelo nenhum: uma cifra na mensagem ou é um número que uma
ferramenta produziu, ou não é, e isso é decidível.

Não substitui o juiz: uma mensagem pode errar de formas que número nenhum
revela. Mas a falha específica que este sistema existe para impedir, um preço
que ninguém calculou, é pega aqui, deterministicamente e de graça.

**Consequência.** A busca é recursiva sobre o payload inteiro, não por campo
nomeado: um verificador que precisa ser avisado de cada campo novo fica obsoleto
no dia em que uma ferramenta ganha um.

---

## 27. A configuração do agente é montada somente para leitura

**Decisão.** `hermes-config.yaml` é montado `:ro`.

**Motivo.** O Hermes reescreve esse arquivo ao registrar coisas como flags de
onboarding, e a reescrita **apaga todos os comentários e reverte qualquer edição
feita no repositório**. Foi descoberto ao trocar o modelo: a mudança parecia
aplicada e não estava.

**Consequência.** O repositório volta a ser a única fonte de verdade da fiação.
O resto do estado do Hermes continua no volume, que segue gravável.

---

## 28. O rastreamento de restrições tem estado, e um lugar para consultá-lo

**Decisão.** `menu_acceptance_check` devolve, para um prato, cada checagem que
separa ele do cardápio, com o estado de cada uma e as perguntas que ela ainda
não ouviu, já escritas.

**Motivo.** As checagens existiam e funcionavam. O portão sabia da sua parte, o
observador sabia do custo e do mercado, o middleware sabia o que recusaria, o
catálogo sabia o que não tinha sido perguntado. Cinco lugares, e nenhum
respondia a pergunta que o agente de fato tem antes de agir: *posso seguir?*

Estado espalhado é estado que ninguém consulta. Na prática o agente descobria o
que faltava sendo recusado, o que é aprender por tropeço.

**Consequência.** Duas distinções ficaram explícitas ao reunir tudo. Checagens
que **travam** o aceite (viabilidade, custo, avaliação) contra as que apenas
**informam** (mercado e inflação): um prato pode entrar no cardápio sem preço de
mercado, mas um preço não pode ser dito sem ele, e antes isso estava implícito
em dois conjuntos diferentes do middleware. E as lacunas voltam como a pergunta
pronta, não como o nome do item, porque o agente não deveria precisar inventar
como perguntar sobre air fryer.

**Observabilidade.** É a mesma informação que o middleware usa para recusar,
exposta antes da recusa. A ferramenta e o portão não podem discordar: leem a
mesma trilha.

---

## 29. A busca tem um teto por sessão

**Decisão.** `dishes_discover_dishes` aceita cinco chamadas por sessão. A sexta
é recusada pelo middleware, não desencorajada pela descrição.

**Motivo.** Numa conversa gravada o agente chamou a busca vinte vezes seguidas e
não respondeu nada à Dona Maria. Não foi capricho do modelo: o `next_step` da
ferramenta convidava a tentar de novo quando o consenso vinha fraco, e consenso
fraco é o caso comum. Cada chamada tornava a próxima mais atraente, e a única
saída do laço era o modelo decidir sozinho que já bastava.

Um teto resolve isso de um jeito que nenhuma redação resolve. A recusa carrega o
que fazer em seguida, seja usar o que já foi achado ou perguntar a ela, em vez de
um erro seco.

**Consequência.** Cinco buscas cobrem com folga o que a conversa precisa; se um
dia não cobrirem, o número está numa constante e não espalhado por descrições. O
custo é que uma sessão muito longa pode encostar no teto legitimamente. Preferi
isso a uma sessão que trava.

**Observabilidade.** `jacquinho confidence` mostra a trilha inteira; as buscas
aparecem contadas, e o teto aparece como recusa, não como silêncio.

---

## 30. O prato morto é fechado pela ferramenta, não pelo lembrete

**Decisão.** Gravar um `confirmed_no` roda o portão do prato em discussão ali
mesmo e devolve o veredito como dado: `dish_now_ruled_out`, com o item que
bloqueia e a frase pronta. Pedir a próxima pergunta faz o mesmo.

**Motivo.** É o pior desfecho possível da conversa e aconteceu de verdade: a
Dona Maria diz "não tenho forno", o agente grava, e segue perguntando outra
coisa. Ela entregou exatamente a informação que mata a lasanha e não ouviu nada
sobre a lasanha.

O `next_step` já mandava fechar o prato, com todas as letras. Não bastou:
instrução que o modelo pode pular não é garantia, que é a lição que se repete
neste documento inteiro. Então a gravação passou a fazer a checagem ela mesma.
`next_questions` ganhou a mesma verificação porque pedir a próxima pergunta é
precisamente o instante em que o agente ia mudar de assunto.

**Consequência.** O veredito chega como estrutura, não como conselho: prato,
`verdict: rejected`, `blocked_by`, e a frase a dizer. Dois testes cobrem os dois
caminhos. Honestamente: isso melhorou muito o comportamento e ainda não o tornou
certo. O modelo às vezes registra, respeita o bloqueio dali em diante e mesmo
assim não anuncia em voz alta que a lasanha ao forno saiu. Está anotado assim no
README e em [testes.md](testes.md), porque é o que os testes de diálogo mostram.

**Observabilidade.** O campo aparece na resposta da ferramenta e vai para o log;
dá para ver, depois da conversa, se a frase foi entregue e o agente a ignorou.

---

## 31. O veredito é uma dívida da conversa, não um lembrete

**Decisão.** Quando um prato morre, ou volta, a sessão passa a dever a ela
essa frase. Todas as ferramentas que significam seguir em frente são recusadas
até que `kitchen_announce_verdict` receba o texto que ela vai ler, e esse texto
é conferido: precisa nomear o prato dela e o que decidiu aquilo.

**Motivo.** É o pior turno que este agente já produziu, e nenhum número estava
errado: ela diz "não tenho forno", o servidor arquiva certo, e a resposta fala
de outra coisa. Ela entregou o fato que matou o prato dela e não ouviu nada
sobre o prato dela.

Três tentativas, todas por redação. Um `next_step` mandando fechar o prato com
todas as letras. Depois a frase pronta devolvida em `dish_now_ruled_out.say_now`.
Depois a mesma checagem em `next_questions`, porque pedir a próxima pergunta é o
instante em que ele mudava de assunto. Melhorou nas três, acertou em nenhuma:
redação é conselho, e conselho o modelo pode pular. É a mesma lição que este
documento repete desde a decisão 1.

**Consequência.** Ler nunca é recusado: despensa, perfil, histórico e o próprio
portão seguem abertos, porque conferir antes de falar é o que ele deveria estar
fazendo ali. O que fecha é buscar outro prato, custear, precificar, comprar,
entrar no cardápio e fazer a próxima pergunta.

A conferência da frase é deliberadamente pequena: nome do prato, motivo, e
tamanho de frase inteira. O nome curto conta, porque ela chama de "a lasanha" e o
agente também. E a palavra que bloqueia é descontada do nome do prato antes da
comparação, senão dizer "forno" passaria por ter nomeado "lasanha ao forno".

Isso não garante que a frase conferida seja de fato enviada a ela; o servidor
não vê a mensagem final. O que garante é que ela foi escrita, com o prato e o
motivo dentro, antes de qualquer outra coisa acontecer, e na simulação isso foi
suficiente, o que as três redações anteriores nunca foram.

**Observabilidade.** A dívida aparece em `conversation_state.deve_a_ela`, em toda
resposta de ferramenta, e a recusa diz exatamente o que falta dizer.

---

## 32. Um "confirmado" é uma afirmação sobre o que ela disse

**Decisão.** `kitchen_record_capability` exige `her_words` para `confirmed_yes` e
`confirmed_no`, e procura essa citação nas falas guardadas dela antes de aceitar.
Sem conversa guardada, nada pode ser confirmado. `unknown` não exige citação.

**Motivo.** Numa simulação com o banco zerado, o agente decidiu sozinho que ela
tinha forno, fogão, sabia montar camadas e gratinar, sem perguntar nada. O
portão aprovou em cima disso e precificou uma lasanha inteira, com margem e
tudo, para uma cozinha que não a assa. O portão funcionou perfeitamente: ele
confere o perfil, e o perfil dizia sim.

O problema era de onde vinha o sim. O único registro do que ela tinha dito
morava no contexto do modelo, e o servidor não tinha como discordar. "Silêncio
não é consentimento" estava escrito na descrição da ferramenta desde o começo, o
que o tornava exatamente o tipo de regra que este projeto já aprendeu a não
confiar.

**Consequência.** A conversa passa a ser gravada de verdade. Antes o Redis
ficava vazio numa consultoria inteira, e a janela de contexto documentada não
descrevia nada. A gravação vira dependência de uma coisa que o agente quer
fazer, e por isso acontece.

Continua sendo possível inventar a citação junto com a resposta. A diferença é
que agora inventar é um ato explícito, escrito, e auditável: a nota gravada
carrega `ela: "…"` ao lado do estado, e quem revisar lê a origem da afirmação
junto com ela.

**Observabilidade.** `her_words_verified` volta em toda gravação, e é `false`
quando a citação não pôde ser conferida, com o Redis fora do ar, por exemplo. A
consultoria continua; a confiança na linha é que fica menor, e dita.

---

## 33. Os limites do turno são do runtime, não do modelo

**Decisão.** Dois hooks de shell do Hermes ligam a fronteira do turno ao
servidor. `pre_llm_call` traz a mensagem dela antes de o modelo ler;
`post_llm_call` traz a resposta depois que o laço de ferramentas termina. Os
dois scripts vivem em `hooks/`, falam HTTP com rotas próprias do servidor, e
falham abertos.

**Motivo.** Duas garantias tinham o mesmo buraco no meio: tudo neste servidor
roda porque o modelo decidiu chamar alguma coisa.

*A citação.* Um `confirmed_yes` é uma afirmação sobre o que ela disse, conferida
contra a transcrição, que até aqui era escrita pelo próprio agente. Citação
conferida contra transcrição escrita por quem cita não é conferência. O agente
podia gravar a fala e depois citar a si mesmo.

*A entrega.* O servidor decidia que o prato morreu, entregava a frase, recusava
tudo que significasse seguir em frente, e nunca via a mensagem que chega a ela.
Garantia de que a frase foi **escrita**, nunca de que foi **enviada**.

**Consequência.** As falas capturadas ficam num balde próprio, marcadas
`source: hook`, e passam a valer mais: existindo qualquer fala capturada, só
elas contam para conferir uma citação. A dívida do veredito ganhou dois
estágios: a ferramenta *rascunha* (e isso reabre as portas dentro do turno), o
fim do turno *quita*, olhando o texto que ela recebeu. Se não recebeu, a dívida
reabre e o turno seguinte começa fechado.

Um hook de shell não pode reescrever a mensagem em voo; só um plugin em Python
pode, e um servidor escrevendo direto para ela seria uma garantia pior que a
recusa de esquecer. Então **não dá para desdizer um turno ruim; dá para recusar
esquecê-lo**, e é isso que está prometido, sem exagero.

Nem todo turno de "usuário" é ela: o Hermes roda uma passagem de curadoria que
fala na cadeira dela. Capturada, viraria prova de algo que a Dona Maria teria
dito. É filtrada pelos mesmos prefixos que o próprio Hermes usa internamente.

**Observabilidade.** `jacquinho.verdict` registra, por turno, se o veredito
chegou a ela e o que faltou. É a única métrica do sistema medida sobre a
mensagem, e não sobre a intenção.

---

## 34. Um veredito não é devido duas vezes

**Decisão.** Cada veredito entregue fica registrado por sessão. Repetir o mesmo
, mesmo prato e mesmo motivo, não abre dívida nova.

**Motivo.** Apareceu rodando a consultoria inteira. Ela já tinha ouvido que a
lasanha ao forno estava fora, aceitado a de panela e pedido o custo. Aí
mencionou que também não frita por imersão. Aquele `confirmed_no` disparou a
recheca do prato "em jogo", que ainda era a lasanha ao forno, e o agente lhe
deu o discurso do forno de novo, no meio da conta que ela tinha pedido.

Dizer de novo o que ela já ouviu é o mesmo defeito de nunca ter dito: a
mensagem não é sobre onde a conversa está.

**Consequência.** A dívida é sobre um par (prato, motivo), não sobre um evento.
O registro é da sessão, não do banco: se ela voltar semanas depois, ouvir de
novo por que a lasanha está fora é gentileza, não repetição.

---

## 35. Um "sim" com "mas" dentro não é um sim

**Decisão.** `confirmed_yes` é recusado quando as palavras dela carregam
hesitação: "mas", "às vezes", "mais ou menos", "quebrado", "acho que". Volta
como pergunta, e o item continua `unknown`.

**Motivo.** Ela disse *"meu forno acende mas não esquenta direito, às vezes
queima embaixo"*. Foi gravado `confirmed_yes`, com o detalhe na nota, e a nota
é o único lugar que o portão não lê. Dali em diante o portão liberaria qualquer
prato de forno para uma cozinha cujo forno queima o fundo, e ela compraria os
ingredientes. Era a falha central do desafio de volta, numa forma nova: o portão
funcionava, o dado é que estava mentindo.

Três estados não têm onde guardar "tem, mais ou menos".

**Consequência.** É uma lista de palavras, e listas de palavras erram. O que a
torna aceitável aqui é a assimetria: `unknown` bloqueia compra, então um falso
positivo custa uma pergunta a mais e um falso negativo custaria os ingredientes
dela. Errar para o lado da pergunta é barato; para o outro lado, não.

O conserto de verdade é um quarto estado, "tem, mas não dá para contar com
isso", que muda o contrato do portão em todo lugar que o lê. Isso merece uma
passagem própria, não um remendo pendurado nesta. Está escrito aqui em vez de
ficar implícito no código.

**Observabilidade.** A recusa devolve `hedges` com as marcas que encontrou, e
elas aparecem no log ao lado da tentativa.

---

## 36. O agente não compra nada, e o orçamento é uma reserva

**Decisão.** `budget_commit_purchase` virou `budget_reserve_purchase`, e passou
a exigir `her_words`, conferidas na transcrição capturada como qualquer
capacidade da cozinha. O que a tabela guarda é o que **ela decidiu** gastar, não
o que foi gasto.

**Motivo.** Numa consultoria gravada, o agente disse a ela: *"Já comprei a massa
de lasanha e os temperos que faltavam por R$ 30,85, dentro do seu orçamento de
R$ 80."* Ele não comprou. Não tem carteira, não tem cartão, não vai ao mercado.

Não foi um deslize de redação. A ferramenta se chamava `commit_purchase`, a
descrição dizia *"spend against the budget"*, e o argumento que faltava era
justamente aquele que tornaria a decisão dela: a ferramenta não pedia nada da
Dona Maria para tirar dinheiro do orçamento da Dona Maria. Um modelo lendo
"gastar" escreve "gastei", e está sendo coerente com o que leu.

O dano de acreditar nessa frase é concreto. Ela pode não ir ao mercado, achando
que já está feito; pode não conferir preço, achando que já foi pago; e o custo
por marmita, calculado sobre uma referência de mercado, passa a parecer um valor
apurado.

**Consequência.** Três mudanças, e a primeira é a que importa: o nome e a
descrição passam a dizer o que a coisa é. Depois, a exigência da citação, que
usa a mesma máquina da decisão 32 e por isso não custou nada de novo. E a
resposta da ferramenta devolve a frase no tempo certo, no futuro: *"a massa e os
temperos saem por uns R$ 30,85, e sobram R$ 49,15"*.

A reserva continua sendo estado necessário. Sem ela, o segundo prato seria
calculado sobre os oitenta reais uma segunda vez. O que mudou não é a
contabilidade, é de quem é a decisão.

Faltava teste nesse caminho, e foi por isso que a redação envelheceu sem ninguém
notar. Agora tem dois: reservar sem a palavra dela é recusado, e reservar com a
palavra dela devolve a instrução de nunca dizer que comprou.

**Observabilidade.** `budget_get_status` fala em `reserved_for_her_to_buy`, e
cada linha de `budget_entries` carrega a descrição do que **ela** vai comprar.
Quem ler o banco depois não confunde uma intenção com um recibo.

---

## 37. As cifras da mensagem são conferidas sozinhas, no fim do turno

**Decisão.** O fim do turno extrai todo R$ e todo % da resposta e compara com
**todos** os números que qualquer ferramenta produziu na sessão. O que não bate
sai no log como `jacquinho.figures`. Para isso o observador passou a guardar as
cifras de toda chamada, não só os seis compartimentos da trilha de evidências.

**Motivo.** Fechando um estrogonofe a R$ 19,90 sobre CMV de R$ 12,64, o agente
disse a ela *"deixando R$ 7,26 no seu bolso"*. O valor certo é R$ 5,27, gravado
em `menu_items` na mesma chamada: 19,90 menos os 10% da plataforma dá 17,91,
menos 12,64 dá 5,27. O modelo subtraiu custo de preço em prosa e esqueceu a
taxa, num turno em que ele mesmo já tinha dito 5,27 uma mensagem antes.

`confidence_audit_figures` faz exatamente essa conferência desde o começo, e não
foi chamado. É a mesma história da decisão 15: uma ferramenta que o agente deve
lembrar de chamar é uma ferramenta que não roda quando mais importa.

A trilha de evidências não servia como referência porque tem seis
compartimentos, e nem preço nem cardápio alimentam algum deles. Os números que
ela usa para decidir eram justamente os invisíveis.

**Consequência.** A conferência é grosseira de propósito: pergunta se a cifra
existe em algum resultado de ferramenta, não se está no lugar certo da frase.
Não pega um número certo usado errado. Pega o número que ninguém calculou, que é
a falha que custa dinheiro a ela.

Como todo o resto que mora na fronteira do turno, isto não desfaz a mensagem. O
que muda é que o erro deixa de ser invisível.

**Observabilidade.** Uma linha por turno sujo, com a cifra e o trecho onde ela
aparece. Turno limpo não gera linha.

---

## 38. Recusar um prato por gosto arquiva o prato

**Decisão.** `menu_record_feedback` com `likes_cooking` falso bloqueia o prato
ali mesmo, com o motivo nas palavras dela, criando a entrada no catálogo se ela
não existir. O bloqueio é `disliked`, que é o único não condicional.

**Motivo.** Ela disse que parmegiana dá muito trabalho e nunca fica boa. O
agente respondeu "anotado, nem entra na conversa" e não escreveu nada:
`dish_feedback` e `recipe_blocks` vazios ao fim da conversa. Vinte turnos
depois, a janela do Redis rola e a parmegiana volta a ser uma ideia nova.

A causa está escrita neste documento umas cinco vezes: o `next_step` pedia uma
**segunda** chamada, `recipes_reject_candidate`, e segunda chamada é chamada que
se pula. É o mesmo conserto do prato bloqueado por equipamento na decisão 30, e
foi preciso repetir porque o defeito não estava no prato bloqueado, estava no
padrão.

**Consequência.** O prato que ela recusou fica arquivado como recusado, e não
volta quando ela comprar um forno, porque gosto não é impedimento esperando
solução. Repetir a recusa não empilha bloqueio.

O que continua aberto: isso só grava se o agente chamar `menu_record_feedback`.
Quando ela recusa um prato que ninguém propôs, nada obriga o registro. Fechar
esse caso pediria ler intenção na mensagem dela, que é julgamento de modelo e
não checagem, e por isso está escrito em [testes.md](testes.md) em vez de
resolvido pela metade.

---

## 39. Um ingrediente de fora tem dois custos, e a ferramenta separa os dois

**Decisão.** `pricing_calculate_cmv` aceita `researched_prices`: para cada
ingrediente que a despensa não tem, o preço de **uma embalagem**, quanto vem
nela e a unidade. A ferramenta divide em dois números que não são o mesmo: a
fração que a receita consome, que entra no CMV, e as embalagens inteiras que ela
precisa comprar, que entram na lista de compras.

**Motivo.** Antes, um ingrediente fora da despensa caía em `not_found` e ficava
**fora do CMV**, com o cálculo marcado incompleto. Não havia caminho de volta:
nenhum argumento aceitava um preço pesquisado. Então o modelo fazia a conta na
mensagem, e o resultado apareceu numa consultoria gravada: uma lata de leite
condensado, um pacote de chocolate em pó e um de granulado somaram R$ 29,86, e
esse número foi tratado como o custo do lote. Não é. É o que ela paga no caixa;
o brigadeiro come uma colherada de cada um.

A mesma conta feita direito dá R$ 0,98 por brigadeiro. A diferença entre os dois
números é a diferença entre um preço de venda que fecha e um que não fecha.

**Consequência.** As duas pontas ficam certas ao mesmo tempo. A lista de compras
arredonda para cima, porque ela não compra 40 g de leite condensado, compra uma
lata: 400 g de necessidade sobre latas de 395 g dão **duas** latas, e a sobra
vem dita, com unidade. O CMV carrega só o que a fornada consome.

Sem `researched_prices` o comportamento antigo continua: o ingrediente volta em
`not_found`, o CMV fica incompleto e nada é precificado. Preferi manter isso a
deixar a ferramenta estimar, porque um preço inventado é exatamente o que este
sistema existe para não produzir.

**Observabilidade.** Cada linha carrega a divisão escrita:
`7,89 / 0,395 = 19,9747 por kg; 0,015 x 19,9747 = 0,30`.

---

## 40. O fechamento fala do dia, não da marmita

**Decisão.** `menu_expected_return` recebe quantas porções de cada prato saem da
fornada e devolve receita, taxa da plataforma, custo dos ingredientes, lucro e
percentual, mais a frase pronta em `say_it_like_this`.

**Motivo.** O cardápio respondia "quanto sobra numa marmita". A pergunta que ela
faz é se o dia valeu a pena, e essa precisa da quantidade, que é dela.

**Consequência.** Três percentuais, e a escolha de qual vai na frase importa
mais que o cálculo. A primeira versão liderava com **retorno sobre o custo de
produção** e imprimiu *"um retorno de 1556%"* para um brigadeiro. É
aritmeticamente verdadeiro e inútil: a base é a colherada que a fornada
consome, não o que ela paga no caixa.

A frase passou a liderar com **margem sobre a venda**, que não pode passar de
100 e por isso continua acreditável e comparável entre pratos: *"57 centavos de
cada real vendido"*. Retorno sobre custo e retorno sobre desembolso continuam na
resposta, rotulados, com um campo `careful_with` dizendo por que não citá-los.

Os dois custos ficam separados de propósito: o que a comida custa, incluindo o
que ela já tinha, e o que ainda precisa sair do bolso dela. Somar os dois conta
duas vezes a despensa que ela já pagou.

**Observabilidade.** Percentual sobre base inexistente volta `None`, não zero:
uma porcentagem sobre nada não é infinito, é uma pergunta sobre dado faltando.

---

## 41. O portão sozinho basta para arquivar o prato

**Decisão.** Quando não há exigências lidas de uma receita, o arquivamento do
prato morto usa os impedimentos que o próprio `check_feasibility` devolveu.

**Motivo.** O arquivamento dependia de o agente ter passado por
`kitchen_analyse_recipe_requirements`. Numa gravação ele foi direto ao
`check_feasibility`: anunciou a lasanha morta corretamente, e `recipe_blocks`
ficou **vazio**. A frase saiu certa e a garantia não existiu. No dia em que ela
ganhasse um forno, não havia o que voltar.

É a diferença entre uma garantia e um caminho feliz: dependia de qual das duas
ferramentas o modelo escolheu, e as duas são legítimas.

**Consequência.** O veredito do portão e a leitura da receita passam a alimentar
o mesmo arquivamento, com a leitura da receita ganhando quando existe, porque é
mais específica. Dois testes de domínio cobrem os dois caminhos.

---

## 42. Uma promessa é o que ela ouviu, não o que a ferramenta calculou

**Decisão.** `pricing_calculate_cmv` compara o resultado com o último CMV que
**chegou até ela**, e não com o último que a ferramenta produziu. A fronteira do
turno marca quais custos apareceram na mensagem entregue; só esses contam como
promessa.

**Motivo.** A primeira versão desta decisão comparava com o histórico da
ferramenta, e produziu um defeito pior que o silêncio que ela existia para
corrigir. Numa conversa nova, na primeira vez que o agente falou de dinheiro, a
mensagem abriu assim:

> *"Antes de mais nada: preciso corrigir um número. Eu tinha te dito que a
> lasanha de panela custava R$ 9,90 por marmita."*

Ele nunca disse isso. Dentro de um turno o prato é custeado várias vezes
enquanto o agente resolve a receita, e só o último número é falado. Comparar com
o histórico da ferramenta fez o agente **inventar uma lembrança da conversa** e
pedir desculpa por um preço que ela nunca viu.

Silêncio sobre uma mudança é ruim. Uma memória falsa da conversa é pior: ela
corrói exatamente a coisa que o resto do sistema existe para proteger, que é ela
poder confiar no que ele diz ter dito.

**Consequência.** Só o que passou pela fronteira do turno vira promessa, o que
significa que a mesma máquina que já servia para conferir cifras e entregar
veredito agora também define o que foi prometido. Um CMV calculado e não
mencionado não gera correção nenhuma.

**Observabilidade.** `cmv_told` fica na trilha da sessão, ao lado do `cmv`
calculado, e a diferença entre os dois é literalmente a diferença entre o que
ele sabe e o que ela sabe.

---

## 43. A receita de um prato fecha uma vez

**Decisão.** A primeira vez que um prato é custeado por completo, a lista de
ingredientes daquele prato é gravada em `recipe_costing` e passa a valer. Uma
chamada seguinte com lista diferente é **recusada**, com a receita fechada e o
custo dela devolvidos. Só `pricing_reopen_recipe` reabre, e ele exige as
palavras dela.

**Motivo.** Numa consultoria o custo da mesma lasanha andou sozinho: R$ 9,90,
depois R$ 8,18, depois R$ 7,15. As três contas estavam certas. A aritmética
nunca foi o problema: os **insumos** eram, porque o agente compunha uma lista de
ingredientes um pouco diferente a cada chamada, e nada no sistema podia dizer
qual daquelas listas *era* o prato.

A decisão 42 detecta a mudança e manda explicá-la a ela. Isso é o segundo melhor
resultado. O melhor é o número não andar: **um prato tem uma receita**, e se ela
mudar, quem mudou foi a Dona Maria.

**Consequência.** A receita vira um fato atômico do prato, do mesmo jeito que uma
capacidade da cozinha é um fato dela. Ordem de ingredientes e caixa alta não
contam como diferença, porque não mudam o custo; ingrediente que entra, sai ou
muda de quantidade, sim.

Reabrir é um evento da conversa, não uma decisão do modelo. Ela diz *"tira a
cebola"*, *"põe frango no lugar"*, e a reabertura carrega essa fala, conferida
na transcrição capturada como qualquer outra citação. Se ela desiste do prato,
o caminho é outro e já existia: `menu_record_feedback` arquiva. Se ela quer
outro prato, o outro prato tem outro nome e portanto outra receita, sem precisar
de nada.

Depois de reabrir, tudo que pendurava na receita antiga é refeito: buscar a
receita, rodar o portão, custear, precificar. Os números velhos não são mais
daquele prato, e o `next_step` diz isso.

O custo é rigidez: se o agente errou a lista na primeira vez, corrigir exige
falar com ela em vez de silenciosamente recalcular. Isso é intencional. Ele
errar sozinho e consertar sozinho é indistinguível, do lado dela, de ele estar
chutando.

**Observabilidade.** `recipe_costing` guarda a lista, as porções, o custo e
quando fechou, mais o motivo de cada reabertura nas palavras dela. Dá para
reconstruir, depois, por que o custo de um prato mudou entre duas conversas.

---

## 44. Confiança por afirmação: o que é Pydantic e o que não é

**Decisão.** A confiança é calculada por **afirmação** (`Claim`), com pesos por
sinal, em Python simples. Pydantic valida as **entradas das ferramentas**, não a
conta da confiança.

**Motivo.** São dois problemas diferentes e vale não confundi-los.

*A afirmação.* Pontuar toda mensagem contra o pipeline inteiro estava errado:
"você tem 37 ingredientes" é lido da planilha e é tão certo quanto qualquer
coisa aqui, e marcá-lo 0,00 por falta de preço de mercado não diz nada sobre a
frase. Daí `Claim`, com `REQUIRES` mapeando cada tipo de afirmação aos sinais que
ela de fato precisa: um fato da despensa precisa da despensa; um preço precisa
de portão, custo, mercado e inflação.

*A forma dos dados.* `RecipeLine`, `PurchasedItem`, `MarketReference`,
`DishPortions` e `EvidenceBundle` são modelos Pydantic, e existem para que o
modelo não consiga mandar uma quantidade negativa ou uma unidade ausente. Isso é
validação de **forma**, na porta de entrada.

O que faltava não era validação de forma. Era **identidade**: nada dizia que a
receita de um prato é uma coisa só, e é por isso que o custo andava. Um
`BaseModel` a mais no argumento não impediria a segunda chamada de trazer uma
lista diferente e igualmente válida. O que impede é a decisão 43, que dá à
receita um lugar durável e um dono.

**Consequência.** As três peças ficam com papéis separados e verificáveis:
Pydantic recusa entrada malformada, `RecipeLock` recusa insumo trocado, e
`Claim` decide quais sinais uma frase precisa ter para valer. Nenhuma delas
cobre o buraco das outras duas, e é por isso que as três existem.


---

## 45. A confiança de uma mensagem é a soma das afirmações dela

**Decisão.** Toda mensagem entregue passa por um pipeline determinístico de
quatro passos, na fronteira do turno: decompor em afirmações atômicas, descartar
as que não são conferíveis, conferir cada uma contra as ferramentas da sessão, e
compará-las com o que ela já ouviu. O resultado é uma nota por mensagem, com as
afirmações listadas. Os tipos são modelos Pydantic.

**Motivo.** Havia duas meias-medidas e um buraco entre elas. O observador
pontuava a **trilha de evidências** e nunca olhava a frase. A auditoria de
cifras olhava a frase e fazia uma pergunta só de cada número: alguma ferramenta
produziu isto?

As duas passaram na conversa em que o custo saiu como R$ 9,90, depois R$ 8,18,
depois R$ 7,15. Todos os três vieram de ferramenta, todos "com lastro". Ninguém
estava perguntando se a mensagem **contradizia o que ela já tinha ouvido**.

**O desenho segue o que a literatura de verificação de fatos convergiu**, com uma
adaptação que muda tudo. Decompor a resposta em afirmações atômicas e verificar
uma a uma é o método do FActScore e do SAFE. Filtrar para as **verificáveis** é a
correção que o VeriScore fez em cima disso: conselho, sugestão e pergunta não
podem estar certos ou errados, e pontuá-los mede o avaliador, não a mensagem.
Comparar contra turnos anteriores é o que os avaliadores multi-turno chamam de
*commitment*, e o detector mais confiável deles é justamente o de discordância
numérica, porque compara valores simbólicos em vez de similaridade de texto.

A adaptação: nesses trabalhos a evidência é a web aberta, então a extração
precisa de um modelo e a verificação precisa de busca. Aqui a evidência são os
resultados das próprias ferramentas desta sessão. Um preço saiu de
`pricing_price_scenarios` ou não saiu, e isso é decidível com aritmética. Por
isso o pipeline inteiro é determinístico, roda em toda mensagem, e não custa
nenhuma chamada de modelo.

**A identidade da afirmação vem da ferramenta, não da frase.** Essa foi a
correção mais importante durante a construção. Classificar o tipo pelas palavras
ao redor do número parecia razoável e não era: *"sobram R$ 63,91 dos seus
R$ 80"* é o orçamento, e todas as pistas que o classificariam como lucro estão
presentes. Um tipo errado é pior que nenhum, porque inventa uma contradição
entre um lucro e um saldo que nunca falaram da mesma coisa. Hoje o tipo vem de
quem produziu o valor: o CMV é o que `calculate_cmv` devolveu, o preço é o que
foi para o cardápio. A leitura da frase serve para saber **quais** desses
valores ela de fato ouviu.

**Consequência.** Uma contradição zera a mensagem, sem média ponderada: ouvir
dois custos diferentes para o mesmo prato não é oitenta por cento certo. Uma
cifra sem lastro baixa a nota proporcionalmente. Uma mensagem sem nada
conferível vale 1,00, porque uma pergunta não pode estar errada.

Mudança que **ela** pediu não é contradição. `pricing_reopen_recipe` autoriza a
revisão daquele prato, e o valor novo passa como `revised`. Sem isso o sistema
puniria o agente por fazer a coisa certa, e o que ele aprenderia é a esconder a
mudança.

**Consequência de escopo.** O ledger é por sessão, em memória. O que sobrevive
entre sessões é o registro em Postgres, que é a fonte real; reconstruir o ledger
a partir dele na abertura da conversa é um passo pequeno e ainda não foi dado.

**Observabilidade.** `jacquinho.claims`, uma linha por mensagem que afirme algo:
nota, quantas afirmações foram conferidas, quantas contradizem. Contradição sai
em `warning` com o texto da divergência. Mensagem sem nada a conferir não gera
linha.

---

## 46. A lista de compras é derivada, não escolhida

**Decisão.** O que falta comprar e quanto custa saem de `calculate_cmv` e ficam
gravados junto com a receita fechada. `budget_reserve_purchase` **recusa** um
valor que não seja esse.

**Motivo.** Numa consultoria, uma mensagem dizia que a massa de lasanha era a
única coisa faltando e custava R$ 6,95. A mensagem de fechamento reservou
R$ 12,00 "da massa de lasanha e orégano". O orégano apareceu do nada e o total
nunca foi explicado.

O `amount` era um parâmetro livre da ferramenta. Um parâmetro livre num lugar
onde existe resposta certa é um convite a inventar, e o modelo aceitou.

**E há um furo mais fundo aqui, que este caso expôs.** A conferência de cifras
pergunta se alguma ferramenta produziu o número. `budget_reserve_purchase`
recebia o `12.00` **do modelo** e o devolvia no resultado, então o número
aparecia como "produzido por ferramenta". Argumento ecoado não é evidência, e
tratá-lo como tal transforma a checagem em raciocínio circular.

A lição vale além deste caso: **uma ferramenta só serve de evidência para os
valores que ela calcula**, não para os que recebe. Onde existe resposta certa
derivável, o argumento não deveria existir.

**Consequência.** A lista de compras vira o mesmo tipo de fato que a receita: o
que o prato pede menos o que ela tem. Acrescentar orégano à lista é acrescentar
orégano à receita, e isso passa por `pricing_reopen_recipe` com as palavras
dela, como qualquer mudança de prato.

A recusa devolve a lista apurada e o total certo, então o caminho de volta é
imediato. O custo é o de sempre nesta base: rigidez. Se a receita esqueceu um
tempero de verdade, corrigir exige falar com ela, e isso é intencional.

**Observabilidade.** `recipe_costing.shopping` guarda a lista item a item com
quantas embalagens e quanto sobra, ao lado de `shopping_cost`. Na verificação
depois da correção, os três lugares batem: a mensagem, a receita e o lançamento
do orçamento, todos R$ 10,39 para um item.
