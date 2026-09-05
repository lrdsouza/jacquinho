# Modelo de dados

A divisão entre os dois armazenamentos é por **tempo de vida**, não por
conveniência.

```mermaid
flowchart LR
    subgraph R["Redis — quente, reescrito a todo turno"]
        r1["chat:{sessão}:turns<br/><i>janela de 20</i>"]
        r2["chat:{sessão}:summary<br/><i>1 resumo corrente</i>"]
        r3["judgement:{ticket}<br/><i>TTL 1h</i>"]
    end
    subgraph P["Postgres — registros dela, duráveis"]
        p1["recipes · recipe_requirements<br/>recipe_blocks"]
        p2["kitchen_capabilities<br/>elicitation_items"]
        p3["budget_entries · package_sizes"]
        p4["dish_categories · dish_feedback<br/>menu_items · answer_assessments"]
    end
    R -.->|"some quando<br/>resumido ou expirado"| X["descartável"]
    P -.->|"decide o que o<br/>agente pode fazer"| Y["permanente"]
```


![Postgres](https://img.shields.io/badge/registros-Postgres%2017-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/estado%20quente-Redis%207-DC382D?logo=redis&logoColor=white)

## A planilha

Duas abas, cruzadas pelo nome do ingrediente.

| Aba | Colunas |
|---|---|
| `Despensa` | Ingrediente · Quantidade em estoque · Unidade |
| `Precos` | Ingrediente · Quantidade comprada · Unidade · Preço total pago (R$) |

O arquivo é montado somente para leitura. Nada é jamais escrito de volta nele.

### Normalização de unidades

Uma string de unidade pode ser uma unidade, ou a descrição de uma embalagem com
a quantidade dentro dela. As duas resolvem para uma unidade base por dimensão.

```mermaid
flowchart TD
    U["string de unidade"] --> E{"quantidade embutida?"}
    E -->|"'balde 2kg'"| P["embalagem<br/>fator = 2 kg"]
    E -->|"'un 500g'"| P2["embalagem<br/>fator = 0,5 kg"]
    E -->|não| S{"unidade conhecida?"}
    S -->|"'kg' 'L' 'un'"| B["unidade simples<br/>fator = 1"]
    S -->|não| X["UnknownUnitError"]
    P --> C["custo unitário = preço / (quantidade x fator)"]
    P2 --> C
    B --> C
```

| Dimensão | Unidade base |
|---|---|
| massa | kg |
| volume | L |
| contagem | un |

Um item precificado por peça avulsa sem peso declarado é marcado como
`priced_per_piece`. Ele serve para receitas que contam unidades. Uma receita que
peça massa ou volume de um item assim produz uma pergunta, e a resposta é
gravada para que o custo passe a ser calculável.

### Casamento de nomes

Os nomes são normalizados — minúsculas, acentos removidos, pontuação colapsada —
e casados por sobreposição de tokens significativos, com conectivos excluídos.
Abaixo do limiar não se devolve nada, e sugestões são oferecidas no lugar.

---

## Redis — o que é quente

Persistência append-only. Toda operação reporta indisponibilidade em vez de
falhar em silêncio.

| Chave | Tipo | Conteúdo |
|---|---|---|
| `chat:sessions` | conjunto | Identificadores de conversa conhecidos |
| `chat:{sessão}:turns` | lista | Turnos, limitados a 2000, os mais antigos descartados |
| `chat:{sessão}:summary` | string | O resumo corrente e quantos turnos ele cobre |
| `judgement:{ticket}` | string | Ticket de julgamento aberto, TTL de uma hora |

### A janela de 20 mais 1

O contexto entregue ao agente é sempre os **20 últimos turnos** — na prática cerca
de dez dela e dez do agente — mais **uma** mensagem de resumo representando tudo
antes deles.

```mermaid
sequenceDiagram
    participant A as Agente
    participant C as chat MCP
    A->>C: get_context(sessão)
    C-->>A: resumo + 20 turnos + needs_new_summary
    Note over A,C: quando 20 turnos novos se acumulam
    A->>C: turns_awaiting_summary
    C-->>A: resumo anterior + os turnos a absorver
    A->>A: escreve o resumo novo (turno próprio do Hermes)
    A->>C: save_summary(texto, covers_turns)
```

| Marco | Janela | Resumo cobre | Desde o resumo | Precisa novo |
|---:|---:|---:|---:|---|
| 10 turnos | 10 | 0 | 10 | não |
| 20 turnos | 20 | 0 | 20 | **sim** |
| 25 turnos | 20 | 20 | 5 | não |
| 40 turnos | 20 | 20 | 20 | **sim** |

Os turnos antigos continuam gravados: o corte é do que o agente segura, não do
que se guarda. `RPUSH` para gravar e `LRANGE` dos últimos vinte para ler são
operações de tempo constante, e o efeito que mais importa é que o custo em tokens
por turno fica limitado por construção.

O resumo é escrito pelo próprio Hermes, num turno separado. Nenhum segundo modelo
entra no circuito.

---

## Postgres — os registros dela

Onze tabelas, um dono para cada.

| Tabela | Dono | Conteúdo |
|---|---|---|
| `recipes` | `recipes` | Toda receita já aberta, com fonte e cobertura |
| `recipe_requirements` | `recipes` | O que cada receita exige: equipamento e técnica |
| `recipe_blocks` | `recipes` | Por que um prato saiu, e o que o traria de volta |
| `kitchen_capabilities` | `kitchen` | Capacidades em três estados, com as palavras dela |
| `elicitation_items` | `kitchen` | Restrições acrescentadas durante a conversa |
| `budget_entries` | `budget` | Compras fechadas; o saldo é derivado |
| `package_sizes` | `pantry` | Pesos descobertos para itens vendidos por peça |
| `dish_categories` | `dishes` | Categorias criadas durante a conversa |
| `dish_feedback` | `menu` | O que ela achou de cada prato |
| `menu_items` | `menu` | O cardápio de lançamento |
| `answer_assessments` | `confidence` | Cada resposta avaliada: tipo de afirmação, notas, badge e impedimentos |

### O bloqueio que se desfaz sozinho

```mermaid
erDiagram
    recipes ||--o{ recipe_requirements : "exige"
    recipes ||--o{ recipe_blocks : "está fora por"
    kitchen_capabilities ||--o{ recipe_blocks : "blocking_item aponta para"
    recipes { text slug PK, text dish, numeric pantry_coverage, bool accepted }
    recipe_requirements { text kind, text item }
    recipe_blocks { text reason, text blocking_item, bool conditional, timestamptz lifted_at }
    kitchen_capabilities { text category, text item, text state, text note }
```

Um bloqueio nunca é apagado — é **liberado**, com data e motivo. Quando uma
capacidade vira `confirmed_yes`, uma única instrução devolve os pratos que
esperavam por ela:

```sql
UPDATE recipe_blocks
   SET lifted_at = now(), lifted_because = %s
 WHERE lifted_at IS NULL AND conditional AND blocking_item = %s
RETURNING recipe_slug;
```

Só bloqueio **condicional** se auto-libera — falta de equipamento, técnica ou
orçamento. Gosto não: ela pode simplesmente não querer cozinhar aquilo, e isso
não é um problema esperando solução.

A consulta quente, "o que ainda está aberto", usa índice parcial sobre
`lifted_at IS NULL`, então enxerga apenas os bloqueios em vigor e não fica mais
lenta conforme o histórico cresce.

### Avaliações de resposta

A coluna `claim` guarda **o que a mensagem afirmava** — `pantry_fact`,
`dish_suggestion`, `feasibility`, `cost` ou `price` —, porque a nota só faz
sentido em relação a isso. É o que permite a pergunta que interessa depois:

```sql
SELECT dish, claim, final_score, badge
  FROM answer_assessments
 WHERE claim = 'price' AND band = 'baixa'
 ORDER BY assessed_at DESC;
```

Toda afirmação de preço que saiu com evidência fraca, sem reproduzir conversa.

### Perfil da cozinha

Ausência significa desconhecido, e desconhecido bloqueia. O `CHECK` na coluna
`state` recusa um valor inválido na porta do banco. A nota preserva as palavras
dela, porque o detalhe que depois importa costuma estar no jeito de falar.

### Saldo do orçamento

Entradas apenas inseridas, em `NUMERIC` — dinheiro não acumula erro de
arredondamento. O restante é derivado por `sum()`, nunca guardado, então não pode
se descolar das entradas, e duas sessões simultâneas não conseguem gastar o mesmo
dinheiro duas vezes.

---

## Categorias de prato

Uma categoria é um **E de OUs**: a despensa precisa de pelo menos um casamento
em cada grupo exigido.

```mermaid
flowchart LR
    subgraph dessert["Sobremesa"]
        G1["grupo 1<br/>açúcar · chocolate · cobertura<br/>chantilly · ninho · canela"]
        G2["grupo 2<br/>leite · ovos · farinha<br/>manteiga · amêndoa"]
    end
    G1 --> AND{"E"}
    G2 --> AND
    AND --> S["sustentada"]
```

Cinco categorias vêm embutidas — prato principal, entrada, acompanhamento,
sobremesa, lanche — e outras podem ser criadas e persistidas. As embutidas não
podem ser substituídas.

---

## Catálogo de restrições

26 itens em três categorias.

| Categoria | Itens |
|---|---|
| equipment | fogao, forno, panela_de_pressao, air_fryer, liquidificador, geladeira, freezer, batedeira, formas_e_assadeiras, microondas, processador, balanca, utensilios_basicos, embalagens |
| techniques | massa_fresca, molho_bechamel, pontos_de_carne, fritura, calda_e_caramelo, confeitar, porcionamento |
| constraints | tempo_por_cozinhada, gas, energia, espaco_geladeira, ajuda |

Cada item carrega a pergunta a fazer, por que importa, uma prioridade e as
palavras de receita que devem levantá-lo. Itens de prioridade 1 barram qualquer
recomendação.

---

## Indicadores econômicos

| Campo | Fonte |
|---|---|
| IPCA geral, 12 meses | IBGE SIDRA agregado 7060, variável 2265, categoria 7169 |
| IPCA alimentação no domicílio, 12 meses | O mesmo, categoria 7171 |
| Localidade | Código de área configurável, região metropolitana de São Paulo por padrão |

Os custos dos ingredientes são projetados com a série de alimentação no
domicílio, porque é a série que uma conta de supermercado segue. Os dois números
voltam com o período de referência e a idade dele, para que a defasagem seja
visível em vez de ignorada.
