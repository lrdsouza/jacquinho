# Referência MCP

![Ferramentas](https://img.shields.io/badge/ferramentas-54-success)
![Prompts](https://img.shields.io/badge/prompts-4-6E56CF)
![Recursos](https://img.shields.io/badge/recursos-1-0A7EA4)

Onze servidores montados sob prefixo em um único endpoint HTTP. Toda ferramenta
é chamada como `prefixo_nome`. Os resultados são JSON, e a maioria carrega um
campo `next_step` nomeando o que deve vir em seguida — o procedimento viaja com
o dado.

## Índice


- [`chat`](#chat) — 7 ferramentas · A transcrição, como janela de 20 turnos mais um resumo.
- [`pantry`](#pantry) — 4 ferramentas · A planilha como custos unitários normalizados.
- [`dishes`](#dishes) — 6 ferramentas · Categorias de prato e descoberta por concordância entre fontes.
- [`recipes`](#recipes) — 10 ferramentas · Montagem de buscas, cobertura da despensa e o catálogo de receitas.
- [`kitchen`](#kitchen) — 9 ferramentas · Elicitação de restrições e o gate de viabilidade.
- [`market`](#market) — 1 ferramenta · Preços de delivery observados para pratos comparáveis.
- [`economy`](#economy) — 2 ferramentas · Inflação regional, índice geral e alimentação no domicílio.
- [`budget`](#budget) — 4 ferramentas · O orçamento de complementos como saldo gastável.
- [`pricing`](#pricing) — 2 ferramentas · CMV e cenários de preço ancorados no mercado.
- [`confidence`](#confidence) — 4 ferramentas · Quanto a evidência sustenta o que vai ser dito.
- [`menu`](#menu) — 5 ferramentas · A opinião dela sobre cada prato e o cardápio de lançamento.

- [Prompts](#prompts)
- [Recursos](#recursos)
- [Convenções de resultado](#convenções-de-resultado)


---

## `chat`

**A transcrição, como janela de 20 turnos mais um resumo.** O contexto é sempre os 20 últimos turnos mais uma mensagem que resume tudo antes deles.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `chat_save_turn` | Registra um turno. | `session`, `role`, `content`, `tags` | Grave as palavras dela literalmente. |
| `chat_recent_history` | Lê os últimos turnos. | `session`, `limit` |  |
| `chat_search_history` | Acha o que ela já disse sobre algo. | `session`, `term`, `limit` | Sem sensibilidade a acento. Use antes de perguntar qualquer coisa. |
| `chat_list_sessions` | Lista as conversas guardadas. | nenhum |  |
| `chat_get_context` | O contexto a segurar: 20 turnos mais o resumo. | `session` | Avisa em `needs_new_summary` quando o resumo precisa ser reescrito. |
| `chat_turns_awaiting_summary` | Os turnos que o resumo novo precisa absorver. | `session` | Vem com o resumo anterior e a instrução do que preservar. |
| `chat_save_summary` | Grava o resumo reescrito. | `session`, `summary`, `covers_turns` |  |

---

## `pantry`

**A planilha como custos unitários normalizados.** Cruza as duas abas e resolve embalagens, para que "balde 2kg por R$ 82,00" vire R$ 41,00/kg. É a única fonte de custo de ingrediente no sistema.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `pantry_list_ingredients` | Lista os 37 ingredientes com custo unitário normalizado. | nenhum | Custos por kg/L/un, palavras-chave de busca e pendências de unidade. |
| `pantry_find_ingredient` | Procura um ingrediente. | `name` | Tolera acento, caixa e parênteses; devolve sugestões quando não acha, nunca um quase-acerto. |
| `pantry_reseed_from_spreadsheet` | Recarrega a despensa da planilha para o banco. | `force` | A aplicação lê o Postgres; a planilha só semeia. |
| `pantry_record_package_size` | Registra quanto pesa uma embalagem vendida por peça. | `ingredient`, `quantity`, `unit` | Depois de perguntar a ela. Sem isso não dá para custear "200 g de cobertura" comprada por unidade. |

---

## `dishes`

**Categorias de prato e descoberta por concordância entre fontes.** Decide que tipos de prato a despensa sustenta antes de gastar busca com eles, e só promove prato em que domínios independentes concordam.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `dishes_list_categories` | Lista as categorias, embutidas ou criadas na conversa. | nenhum | Cinco embutidas mais as que foram criadas. |
| `dishes_create_category` | Cria uma categoria nova. | `key`, `label`, `search_terms`, `required_groups` | Grupos são E de OUs: a despensa precisa de um casamento em cada grupo. |
| `dishes_delete_category` | Remove uma categoria criada antes. | `key` | As embutidas não podem ser removidas. |
| `dishes_survey_categories` | Confere todas as categorias contra a despensa de uma vez. | nenhum | Use cedo: diz que tipos de prato estão sequer na mesa. |
| `dishes_assess_category` | Percorre a despensa ingrediente por ingrediente para uma categoria. | `category` | Mostra qual ingrediente satisfaz qual exigência, com estoque e custo. |
| `dishes_discover_dishes` | Acha pratos em que várias fontes recentes concordam. | `category`, `constraints`, `min_sources`, `freshness`, `queries` | Janela padrão de cinco anos. `source_count` 1 é pista, não achado. |

---

## `recipes`

**Montagem de buscas, cobertura da despensa e o catálogo de receitas.** A busca sai dos ingredientes dela, e toda receita aberta entra no catálogo com o que exige da cozinha.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `recipes_build_search_queries` | Monta buscas web a partir dos ingredientes da despensa. | `constraints`, `limit` | Casa proteína com acompanhamento e ignora temperos. |
| `recipes_search_recipes` | Busca receitas reais na web. | `query`, `limit` | Brave quando há chave, senão DuckDuckGo. Erro vira instrução de perguntar a ela, não número inventado. |
| `recipes_check_pantry_coverage` | Mede quanto de uma receita a despensa cobre. | `ingredients` | Marca receitas apoiadas nos ingredientes caros. |
| `recipes_save_candidate` | Põe uma receita no catálogo com suas exigências. | `dish`, `source_url`, `source_title`, `ingredients`, `required_equipment`, `required_techniques`, `pantry_coverage`, `notes` | Salve até as que não vai mostrar agora: viram a próxima opção. |
| `recipes_list_candidates` | O catálogo, com exigências e bloqueios. | `only_open` | Separa o que está bloqueado e por quê. |
| `recipes_block_candidate` | Tira um prato da mesa e registra o motivo. | `dish`, `reason`, `blocking_item`, `note` | Bloqueio que nomeia capacidade se libera sozinho depois. Bloqueio por gosto, não. |
| `recipes_revisit_blocks` | Traz de volta os pratos que esperavam por uma capacidade. | `capability`, `because` | Chame sempre que uma capacidade virar `confirmed_yes`. |
| `recipes_unblock_candidate` | Libera todos os bloqueios de um prato, à mão. | `dish`, `because` | Para quando ela muda de ideia. |
| `recipes_block_history` | Todo bloqueio já colocado num prato. | `dish` | Com data, motivo e o que liberou. |
| `recipes_next_candidate` | A melhor opção aberta que a cozinha dela faz. | nenhum | Prato bloqueado não é oferecido; vai separado em `ruled_out_by_kitchen`. |

---

## `kitchen`

**Elicitação de restrições e o gate de viabilidade.** O coração: ela nunca compra para um prato que não consegue fazer. Exigências saem do texto da receita, e nada é presumido.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `kitchen_check_feasibility` | Confere se ela consegue produzir o prato. | `equipment_needed`, `techniques_needed` | Veredito `approved`, `needs_answers` ou `rejected`. |
| `kitchen_record_capability` | Guarda o que ela respondeu sobre a cozinha. | `category`, `item`, `state`, `note` | Ao virar `confirmed_yes`, aponta para `recipes_revisit_blocks`. |
| `kitchen_read_kitchen_profile` | Tudo que se sabe de equipamentos, técnicas e limites. | nenhum | Vazio significa não perguntado, não ausente. |
| `kitchen_next_questions` | As coisas mais úteis ainda não perguntadas. | `limit` | Ordenadas por prioridade; itens de prioridade 1 barram recomendação. |
| `kitchen_elicitation_coverage` | Quanto do catálogo ela já respondeu. | nenhum | Percentual e o que falta. |
| `kitchen_elicitation_gaps` | Confere exigências de um prato contra as respostas dela. | `requirements` | `safe_to_shop` falso significa que nada é comprado ainda. |
| `kitchen_elicitation_catalogue` | O catálogo completo de restrições. | nenhum | 26 itens embutidos mais os registrados. |
| `kitchen_analyse_recipe_requirements` | Lê da receita o que ela exige e roda o gate. | `dish`, `recipe_text`, `extra_requirements` | Cada detecção traz as palavras da receita que a levantaram. |
| `kitchen_register_requirement` | Acrescenta uma restrição que o catálogo não tinha. | `key`, `category`, `question`, `why_it_matters`, `priority`, `triggers` | Persistida: o próximo prato não redescobre. |

---

## `market`

**Preços de delivery observados para pratos comparáveis.** Preço não sai de multiplicador sobre custo. Sai do que a concorrência cobra, na cidade dela, no último mês.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `market_research_dish_prices` | Coleta preços reais de delivery. | `dish`, `city`, `limit`, `freshness` | Devolve cada observação com a fonte, a faixa mín/mediana/máx e confiança por fontes distintas. |

---

## `economy`

**Inflação regional, índice geral e alimentação no domicílio.** O custo dela segue alimentação no domicílio, não o índice geral, e na região dela, não no Brasil.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `economy_current_indicators` | Lê o IPCA oficial mais recente. | nenhum | Vem com período de referência e idade; IPCA sai com defasagem. |
| `economy_restate_cost` | Recoloca um custo pago no passado a preços de hoje. | `cost`, `cost_basis_age_months` | A idade é entrada, não palpite: a planilha não diz quando ela comprou. |

---

## `budget`

**O orçamento de complementos como saldo gastável.** R$ 80,00 que diminuem. O saldo é derivado do banco, nunca guardado.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `budget_get_status` | Mostra total, comprometido e restante. | nenhum | Com a lista de compras fechadas. |
| `budget_check_purchase` | Testa se uma lista cabe, sem gastar. | `amount` | Devolve o quanto falta quando não cabe. |
| `budget_commit_purchase` | Gasta contra o orçamento. | `dish`, `description`, `amount` | Só depois que ela concordou. Recusa estourar. |
| `budget_release_purchase` | Devolve o dinheiro de um prato abandonado. | `entry_id` |  |

---

## `pricing`

**CMV e cenários de preço ancorados no mercado.** Toda a aritmética de custo e preço, fora do modelo.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `pricing_calculate_cmv` | Custeia uma porção, separando o que ela tem do que falta. | `dish`, `lines`, `portions` | Devolve `open_questions` em vez de chutar quando a unidade da receita não bate com a da compra. |
| `pricing_price_scenarios` | Monta cenários de preço. | `cmv_per_portion`, `market` | Sem faixa de mercado devolve só o preço mínimo. Cada cenário projeta o lucro em doze meses com a inflação de alimentos. |

---

## `confidence`

**Quanto a evidência sustenta o que vai ser dito.** Nada que ela vá agir em cima sai sem passar por aqui.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `confidence_assess_answer` | Pontua o quanto a evidência sustenta o rascunho. | `dish`, `draft_answer`, `evidence`, `claim`, `mode` | `claim` diz o que a mensagem afirma — `pantry_fact`, `dish_suggestion`, `feasibility`, `cost` ou `price` — e só a evidência daquele tipo é pontuada. Nota determinística na hora; em híbrido e llm devolve também um ticket de julgamento. |
| `confidence_submit_judgement` | Devolve o veredito do julgamento e fecha o relatório. | `ticket`, `verdict`, `confidence`, `unsupported_claims`, `issues` | No híbrido a nota final é a menor das duas. Ticket é de uso único. |
| `confidence_audit_figures` | Confere cada número da mensagem contra o que as ferramentas devolveram. | `message`, `evidence` | Sem modelo: uma cifra ou veio de uma ferramenta ou não veio. Pega o preço inventado. |
| `confidence_recent_assessments` | Toda resposta que foi avaliada, mais recente primeiro. | `limit` | O rastro por trás dos badges: rascunho, as duas notas, banda e impedimentos. |

---

## `menu`

**A opinião dela sobre cada prato e o cardápio de lançamento.** Onde a consultoria termina.

| Ferramenta | O que faz | Argumentos | Notas |
|---|---|---|---|
| `menu_record_feedback` | Registra o que ela achou de um prato. | `dish`, `likes_cooking`, `comment`, `impediments` | Um "não gosto" encerra o assunto e aponta para o bloqueio e a próxima opção. |
| `menu_list_feedback` | Tudo que ela já disse sobre pratos. | nenhum | Separado em aprovados e recusados. |
| `menu_add_dish` | Coloca um prato aceito no cardápio. | `dish`, `category`, `cmv`, `price`, `confidence_band`, `notes` | Só depois do gate, do CMV completo, do preço ancorado e da escolha dela. |
| `menu_remove_dish` | Tira um prato do cardápio. | `dish` |  |
| `menu_build_launch_menu` | O cardápio: cada prato com custo, preço e lucro. | nenhum | Marca os que entraram com evidência fraca. |

---

## Prompts

| Prompt | Argumentos | Para quê |
|---|---|---|
| `open_conversation` | nenhum | Abre a conversa e roteia o que ela disser primeiro |
| `check_specific_dish` | `dish` | Ela chegou com um prato em mente |
| `suggest_from_pantry` | nenhum | Ela quer que o agente proponha |
| `evaluate_dish` | `dish`, `source_url` | Leva um prato das exigências até um preço escolhido |

## Recursos

| URI | Conteúdo |
|---|---|
| `pantry://ingredients` | Retrato navegável da despensa com custos unitários normalizados |

## Convenções de resultado

| Campo | Significado |
|---|---|
| `next_step` | A ferramenta que deve vir em seguida, ou o que perguntar a ela |
| `open_questions` | Um número não pôde ser calculado; pergunte em vez de estimar |
| `blocking_issues` | A resposta não pode ser enviada como está |
| `safe_to_shop` | Falso significa que nada é comprado para este prato ainda |
| `caveat` / `warning` | Um limite do dado que precisa ser dito em voz alta |
| `available` | Falso significa que um armazenamento ou fonte não foi alcançado |
| `conversation_state` | Onde a conversa está: prato em jogo, portão, próximo passo. Vem em **toda** resposta |
| `display.badge` | A linha de confiança a colar no fim da mensagem, como veio |

Além das ferramentas, um middleware no servidor pontua a trilha de evidências
depois de cada chamada e escreve o resultado no log. Isso roda independentemente
de o agente chamar `confidence_assess_answer`; veja `jacquinho confidence`.

O tipo de afirmação em jogo é inferido da ferramenta que acabou de rodar — quem
leu a despensa vai falar da despensa, quem calculou cenário vai falar de preço:

| Afirmação | Repousa sobre | Ferramentas que a colocam em jogo |
|---|---|---|
| `pantry_fact` | a planilha | `pantry_*` |
| `dish_suggestion` | planilha e concordância entre fontes | `dishes_*`, `recipes_search_recipes`, `recipes_next_candidate` |
| `feasibility` | o gate | `kitchen_check_feasibility`, `kitchen_elicitation_gaps`, `kitchen_analyse_recipe_requirements` |
| `cost` | planilha, gate e CMV | `pricing_calculate_cmv` |
| `price` | gate, CMV, mercado e inflação | `pricing_price_scenarios`, `market_*`, `economy_*` |

Três ferramentas — `pricing_price_scenarios`, `menu_add_dish` e
`budget_commit_purchase` — são **recusadas** pelo mesmo middleware enquanto o
gate não tiver aprovado nesta sessão.

Um resultado vazio é uma resposta de verdade. As ferramentas que não acham nada
dizem isso e nomeiam o que fazer a respeito; nenhuma devolve um substituto
plausível.
