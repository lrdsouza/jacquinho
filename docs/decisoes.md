# Decisões de arquitetura

![Registros](https://img.shields.io/badge/registros-28-6E56CF)
![Modelo](https://img.shields.io/badge/modelo-Claude%20Haiku%204.5-D97757)

Cada registro diz o que o sistema faz e por que é construído assim. Onde a
decisão tem consequência de infraestrutura — latência, escalabilidade,
observabilidade, elasticidade — ela fecha dizendo qual. Onde não tem, não
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

**Consequência.** Todo resultado que envolve dinheiro carrega a própria conta —
`0,20 x 14,00 = 2,80` — para que o agente possa mostrar o cálculo em vez de
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
requisições — tudo vive no Postgres ou no Redis — então ele escala
horizontalmente atrás de um mesmo endereço, sem afinidade de sessão. E como toda
chamada de ferramenta passa por um único processo HTTP, existe um log de acesso
só onde ver o que o agente de fato fez, em vez de reconstruir isso da
transcrição.

---

## 3. O procedimento vai com o servidor; a voz não pode

**Decisão.** Não há arquivos de skill. O **procedimento** vive nas descrições das
ferramentas, no campo `next_step` dos resultados e em quatro prompts MCP. A
**voz** — idioma, quem fala primeiro, postura — vive em `SOUL.md`, do lado do
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
with?"* — em inglês e sem abrir a consultoria. Assim que uma ferramenta era
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
no ar — não é preciso caçar que arquivo solto existia na máquina do agente
naquele dia.

---

## 4. Ferramentas MCP em vez de skills

**Decisão.** Tudo que pode ser verificado é uma ferramenta MCP. Só o que não pode
ser verificado — voz, postura, julgamento sobre o que dizer — fica como texto.
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
cozinha em três estados, o bloqueio que se desfaz quando a capacidade muda — são
transições com integridade. Texto não tem transação, nem `NUMERIC`, nem `CHECK`,
nem índice parcial.

*Uma skill não é testável sem um modelo.* A normalização de unidades, o casador
de ingredientes, o motor de consenso e o ciclo de bloqueio e liberação foram
todos verificados chamando funções, sem nenhuma conversa envolvida. Skill só se
avalia rodando diálogo, o que é lento, caro e não determinístico.

**Consequência.** A regra que ficou: **o que pode ser conferido vira ferramenta;
o que só pode ser dito continua texto.** E o texto que sobrou é pouco — voz e
quem fala primeiro, no `SOUL.md`, mais quatro prompts que carregam procedimento
de várias etapas.

**O outro lado.** Isso não é gratuito. Uma ferramenta custa esquema, validação e
um caminho de erro para cada argumento; uma skill custa um parágrafo. Para
comportamento que não tem certo e errado computável, a ferramenta é peso morto —
e foi exatamente esse o erro que a persona no MCP revelou. Onde não há o que
verificar, texto é a resposta certa.

**Observabilidade.** Toda chamada de ferramenta é uma requisição HTTP com linha de
log: dá para ver o que o agente fez, em que ordem, com que argumentos e o que
voltou. Uma skill "ter sido seguida" não é um evento observável — a única
evidência é a própria resposta, que é o que estava em dúvida.

**Elasticidade e portabilidade.** As ferramentas são um serviço, não um arquivo na
casa do agente. Escalam horizontalmente sem afinidade de sessão, e qualquer
cliente MCP as alcança — o comportamento não fica preso a um agente específico.

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
`forno`, não achava, e devolvia `unknown` — enquanto ler o perfil dava a
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
`NUMERIC`, não em ponto flutuante — dinheiro não acumula erro de arredondamento
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
`budget_commit_purchase` custam dinheiro ou vão para um cardápio. O middleware
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
as que carregam evidência — gate, CMV, consenso, mercado, inflação — e recalcula
a nota depois de cada uma, escrevendo uma linha no log. `jacquinho confidence`
lê esse log ao lado do chat. Nada depende de o agente lembrar.

Isso é a mesma regra da decisão sobre ferramentas contra skills, aplicada à
própria camada de confiança: o que pode ser conferido não fica como pedido.

**E é visível.** Toda avaliação devolve um `display.badge` que o agente cola no
fim da mensagem — `〔preço: confiança alta · CMV completo · 4 fontes〕`. Esse caminho
depende do modelo e portanto falha às vezes; o log não depende de nada.

**A confiança é da afirmação, não do pipeline.** A primeira versão pontuava toda
mensagem contra os cinco sinais — gate, CMV, consenso, mercado, inflação — e o
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
usa só os sinais daquele tipo, e os impedimentos também — um fato da despensa não
é barrado por falta de preço de mercado.

O efeito é que a nota volta a discriminar. Ler a despensa dá 1,00, porque a
planilha é determinística e ler é saber. Afirmar preço sem ter apurado nada dá
0,00 com três impedimentos. Antes, os dois davam zero.

**A escala é 0 a 1.** Uma nota de 0 a 100 lê como prova de escola e convida a
discutir um ponto para cima ou para baixo; 0 a 1 lê como o que é, um grau de
crença, e mantém os dois avaliadores na mesma régua. As bandas ficam em 0,75 e
0,50. O número aparece no log, para quem avalia a execução — o badge que ela
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
Guardar as exigências de cada receita é o que permite que uma única resposta —
ela não tem forno — elimine toda receita que precise de um, sem nova busca.

**Consequência.** Um prato que a cozinha dela não faz não é oferecido como
próxima opção. Candidatas bloqueadas são reportadas à parte com o que as
bloqueia, para que um impedimento duro nunca se esconda atrás de uma pergunta
em aberto.

**Escalabilidade da consulta.** Bloqueio não é apagado, é liberado, então o
histórico só cresce. A consulta quente — "o que ainda está aberto" — usa índice
parcial sobre `lifted_at IS NULL`, de modo que ela enxerga apenas os bloqueios em
vigor e não fica mais lenta conforme o histórico engorda.

---

## 18. O Redis guarda a conversa: 20 turnos mais 1 resumo

**Decisão.** O contexto que o agente segura é sempre a mesma coisa: os **20
últimos turnos** — na prática cerca de dez dela e dez do agente — mais **uma
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
janela mais o resumo mantêm as duas coisas — o texto recente literal, e a
memória do que ficou decidido.

**Consequência.** O resumo é instruído a guardar decisões, capacidades e
recusas com seus motivos, e a jogar fora conversa fiada. É o que uma retomada
precisa reler.

**Latência, escalabilidade e elasticidade.** A janela é uma lista Redis: gravar
é um `RPUSH`, ler é um `LRANGE` dos últimos vinte — operações de tempo
constante, fora do caminho do banco relacional. E o efeito que mais importa não
é de disco e sim de token: o contexto por turno fica **limitado por construção**,
então o custo de uma conversa cresce linearmente com o número de turnos, não com
o quadrado. Como o estado vive no Redis e não no processo, várias réplicas do
servidor MCP atendem a mesma conversa sem afinidade de sessão.

**Por que aqui e não no Postgres.** Isto é estado quente: reescrito a cada turno,
lido a cada turno, e sem valor depois de resumido. Os tickets de julgamento
seguem a mesma lógica e ficam no Redis com TTL de uma hora — um ticket
abandonado no meio de uma conversa deve expirar, não se acumular.

---

## 19. O Postgres guarda os dados da Dona Maria

**Decisão.** Tudo que é um registro sobre ela vive em Postgres: a despensa
aprendida (pesos de embalagem), o perfil da cozinha, o catálogo de restrições
que cresceu na conversa, o saldo do orçamento, as categorias de prato, o
catálogo de receitas com seus requisitos e bloqueios, o que ela achou de cada
prato, e o cardápio de lançamento. Dez tabelas. O volume de arquivos JSON que
existia antes deixou de existir.

**Motivo.** Nenhuma dessas coisas é cache. São fatos que sobrevivem a qualquer
sessão, e três propriedades disso pesam:

*São relacionais.* Um bloqueio existe **por causa de** uma capacidade. Quando a
capacidade muda — ela compra o fogão que não tinha —, todo prato que esperava
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
que capacidades foram confirmadas e quando — tudo com data e motivo, legível sem
reproduzir a conversa. É a diferença entre depurar o sistema e entrevistá-lo.

---

## 20. O modelo padrão é o Claude Haiku 4.5

**Decisão.** `model.default` é `claude-haiku-4-5`, com provedor `anthropic`,
fixado em `dockerfile/hermes-config.yaml`. A credencial é a de uma **conta
Anthropic no plano Pro**, autorizada por OAuth com `jacquinho login`, não uma
chave de API — o plano Pro não emite uma.

**Motivo.** Este agente faz muitas chamadas de ferramenta por turno e quase
nenhuma delas pede raciocínio profundo. A aritmética está em Python, as regras
são portões que devolvem `verdict` e `safe_to_shop`, e o trabalho do modelo é
rotear, perguntar e redigir em português claro. É a forma de trabalho em que o
modelo mais barato da família se sai bem, e uma consultoria inteira gasta dezenas
de chamadas.

**Consequência.** Subir é uma linha. `claude-sonnet-5` para julgamento mais forte
mantendo bom uso de ferramentas, `claude-opus-5` quando capacidade importar mais
que custo. Nada mais muda: os onze servidores MCP e as 55 ferramentas se
comportam de forma idêntica por baixo.

**Custo e latência.** Modelo menor também responde mais rápido, o que importa numa
conversa em que ela está com o celular na mão no meio da cozinha. E como o único
turno caro do fluxo é o do juiz, a decisão de modelo e a decisão de ordem —
determinístico primeiro, juiz depois — se reforçam.

**Nota sobre a credencial.** Uma assinatura não necessariamente libera a família
inteira de modelos. Rode `jacquinho hermes model` depois do login para ver o que
a conta oferece e ajuste a linha `default:` se o Haiku não estiver lá. Como o
comportamento inteiro vive nos servidores MCP, trocar de modelo não muda nenhuma
regra do sistema.

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
apontar para o mesmo Postgres e o mesmo Redis — não há nada para migrar junto.

---

## 22. A ferramenta é testada, não só exercitada

**Decisão.** Uma suíte de 140 testes automatizados sobre a camada de domínio e o
servidor, rodando em cerca de um segundo e meio com `jacquinho test`. O domínio
é testado sem banco: a única coisa que ele precisa de Postgres são linhas, e um
banco falso de vinte linhas devolve exatamente o que a semeadura teria escrito.

**Motivo.** Este projeto tem duas classes de risco. A primeira é o agente dizer
algo errado, e para isso existem o portão, a confiança e o juiz. A segunda é a
ferramenta simplesmente quebrar — e essa não tem nada a ver com modelo. Um
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
cardápio da camada MCP para o domínio — o teste não conseguia alcançá-lo sem
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
`dish`** — a aprovação caía numa trilha sem nome e o prato era recusado no
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
perde o fio e volta a oferecer o que ela já escolheu. Não por má vontade — nada
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

**Motivo.** Metade das ferramentas nunca era chamada numa conversa real — CMV,
mercado, feedback, memória. Instruir não bastou. A alavanca que já havia
funcionado para o portão foi estendida: cada exigência transforma uma sugestão
numa garantia, e só nas ferramentas que custam dinheiro ou vão para um cardápio.

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
ferramenta produziu, ou não é — e isso é decidível.

Não substitui o juiz: uma mensagem pode errar de formas que número nenhum
revela. Mas a falha específica que este sistema existe para impedir — um preço
que ninguém calculou — é pega aqui, deterministicamente e de graça.

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
não ouviu — já escritas.

**Motivo.** As checagens existiam e funcionavam. O portão sabia da sua parte, o
observador sabia do custo e do mercado, o middleware sabia o que recusaria, o
catálogo sabia o que não tinha sido perguntado. Cinco lugares, e nenhum
respondia a pergunta que o agente de fato tem antes de agir: *posso seguir?*

Estado espalhado é estado que ninguém consulta. Na prática o agente descobria o
que faltava sendo recusado, o que é aprender por tropeço.

**Consequência.** Duas distinções ficaram explícitas ao reunir tudo. Checagens
que **travam** o aceite — viabilidade, custo, avaliação — contra as que apenas
**informam** — mercado e inflação: um prato pode entrar no cardápio sem preço de
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
que fazer em seguida — usar o que já foi achado, ou perguntar a ela — em vez de
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

O `next_step` já mandava fechar o prato, com todas as letras. Não bastou —
instrução que o modelo pode pular não é garantia, que é a lição que se repete
neste documento inteiro. Então a gravação passou a fazer a checagem ela mesma.
`next_questions` ganhou a mesma verificação porque pedir a próxima pergunta é
precisamente o instante em que o agente ia mudar de assunto.

**Consequência.** O veredito chega como estrutura, não como conselho: prato,
`verdict: rejected`, `blocked_by`, e a frase a dizer. Dois testes cobrem os dois
caminhos. Honestamente: isso melhorou muito o comportamento e ainda não o tornou
certo — o modelo às vezes registra, respeita o bloqueio dali em diante e mesmo
assim não anuncia em voz alta que a lasanha ao forno saiu. Está anotado assim no
README e em [testes.md](testes.md), porque é o que os testes de diálogo mostram.

**Observabilidade.** O campo aparece na resposta da ferramenta e vai para o log;
dá para ver, depois da conversa, se a frase foi entregue e o agente a ignorou.
