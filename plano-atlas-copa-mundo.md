# Atlas da Copa do Mundo — plano de projeto

> Documento vivo. Atualize conforme o projeto evoluir. Última revisão: 07/08/2026.
>
> **Status atual:** Etapa 1 (Extração) concluída para a fonte principal. Etapa 2 (Limpeza) é o próximo passo.
> Versão em inglês: [`plan-atlas-world-cup.md`](plan-atlas-world-cup.md) · Roadmap visual: [`docs/roadmap.html`](docs/roadmap.html)

## 1. Visão geral

**Objetivo:** construir um mapa interativo publicado na web mostrando o histórico da Copa do Mundo (1930–2026), como peça de portfólio de análise de dados, cobrindo o ciclo completo de ETL — da extração (incluindo web scraping) até a publicação.

**Por que esse projeto funciona bem como portfólio:** ele passa por praticamente todas as habilidades que um recrutador técnico procura — ingestão de dados de múltiplas fontes (API, CSV, scraping), reconciliação de dados sujos e inconsistentes ao longo de quase 100 anos, modelagem relacional, e um produto visual final que qualquer pessoa entende sem precisar ler código.

### Stack tecnológico (visão consolidada)

| Camada | Ferramenta principal | Alternativa | Por quê | Status |
|---|---|---|---|---|
| Extração — datasets prontos | `requests`, Kaggle API | — | Download direto de CSVs | ✅ implementado (`requests`) |
| Extração — web scraping | `pandas.read_html` + `BeautifulSoup4` | `Scrapy` (se quiser mostrar arquitetura de spider) | Complementar dados da Copa 2026 | ⏳ não iniciado |
| Limpeza | `pandas`, `rapidfuzz` | `numpy` | Reconciliar nomes de seleções, tratar nulos | ⏳ próximo passo |
| Validação de dados | `pandera` | `great_expectations` | Garantir qualidade antes de modelar (bom diferencial de portfólio) | ⏳ instalado, não escrito |
| Modelagem | `pandas`, schema documentado em Mermaid ERD | `dbdiagram.io` | Formalizar schema relacional | ⏳ não iniciado |
| Geocodificação | `geopy` (Nominatim) | CSV manual de sedes | **Ver nota abaixo — não dá mais pra fazer manual** | ⏳ não iniciado |
| Visualização | Leaflet.js | Mapbox GL JS | Leve, gratuito, sem chave de API | ✅ **decidido: Leaflet** |
| Publicação | GitHub Pages | Netlify/Vercel | Grátis, integrado ao repositório | ⏳ não iniciado |
| Automação/CI | GitHub Actions | — | Rodar pipeline de ETL automaticamente (opcional, mas valoriza o portfólio) | ⏳ adiado para v2 |
| Testes | `pytest` | — | Testar funções de limpeza/transformação | ⏳ instalado, não escrito |

**Ambiente verificado:** Python 3.11.9, git 2.55.0, Windows 11. Todas as dependências instaladas e fixadas em `requirements.txt`.

## 2. Fontes de dados

| Fonte | Cobertura | Formato | Licença | Observação |
|---|---|---|---|---|
| [Fjelstul World Cup Database](https://github.com/jfjelstul/worldcup) | 1930–2022 (masc.) + 1991–2019 (fem.) | CSV / pacote R | CC-BY-SA 4.0 — pode redistribuir com atribuição ao autor, e o trabalho derivado precisa manter a mesma licença | ✅ **BAIXADO.** Mais completo: partidas, sedes, grupos, classificações, premiações. Base do projeto. |
| [FIFA World Cup All Goals 1930-2022 (Kaggle, jahaidulislam)](https://www.kaggle.com/datasets/jahaidulislam/fifa-world-cup-all-goals-1930-2022-dataset) | 1930–2022 | CSV | CC0 1.0 — domínio público, sem restrições | ⚠️ **Provavelmente desnecessário** — o Fjelstul já traz 3.637 gols com autor, minuto, pênalti e gol contra. |
| [FIFA World Cup 1930-2022 All Match Dataset (Kaggle, jahaidulislam)](https://www.kaggle.com/datasets/jahaidulislam/fifa-world-cup-1930-2022-all-match-dataset) | 1930–2022 | CSV | Não confirmado — checar selo de licença na página do Kaggle antes de usar | Placares resumidos por partida. |
| [wcmatches (Kaggle, evangower)](https://www.kaggle.com/datasets/evangower/fifa-world-cup) | 1930–2018 | CSV | CC0 — domínio público | 🎯 **Passou a ser importante:** é a fonte candidata para o dado de **público**, que o Fjelstul não tem (ver seção 2.1). |
| Wikipédia — "2026 FIFA World Cup" e páginas relacionadas | 2026 | HTML (via scraping) | CC BY-SA 4.0 — exige atribuição | Único jeito de cobrir 2026, via scraping (ver seção 4). |

**Licenças — resumo prático:** os datasets CC0 podem ser usados e republicados livremente. O Fjelstul e a Wikipédia (ambos CC-BY-SA 4.0) exigem atribuição ao autor/fonte e que os dados processados publicados no seu repositório carreguem a mesma licença — isso já está registrado em `data/raw/metadata.json` e precisa ir para o README.

### 2.1 O que a exploração dos dados revelou (07/08/2026)

Depois de baixar e inspecionar os CSVs, quatro coisas mudam o plano original:

**1. `tournament_id` NÃO separa masculino de feminino — é uma armadilha.**
As 30 edições usam o mesmo padrão `WC-<ano>` (`WC-1991` é a Copa feminina, `WC-1994` a masculina). Só a coluna `tournament_name` distingue (`"1991 FIFA Women's World Cup"`). Se você agrupar por `tournament_id` achando que é só masculino, vai misturar as duas competições silenciosamente. **Decisão:** criar uma coluna explícita `competition` (`mens`/`womens`) logo na limpeza, derivada do `tournament_name`.

| | Edições | Período | Partidas |
|---|---|---|---|
| Masculino | 22 | 1930–2022 | 964 |
| Feminino | 8 | 1991–2019 | 284 |
| **Total** | **30** | **1930–2022** | **1.248** |

Não há sobreposição de anos entre as duas, e `tournament_id` é único — por isso o erro passa despercebido.

**2. Não existe dado de público no Fjelstul.** A tabela `matches.csv` tem 36 colunas e nenhuma delas é público/attendance. O plano original previa "público total" nos popups do mapa. **Duas saídas:** (a) buscar o dado no `wcmatches` do Kaggle, aceitando que ele só cobre até 2018; (b) tirar o público do escopo v1 e usar a **capacidade do estádio**, que o Fjelstul tem completa (0 nulos em 240 estádios). Decisão pendente.

**3. Geocodificação não pode ser manual.** O plano dizia "poucas cidades — pode ser manual". São **240 estádios em 202 cidades** (193 estádios / 165 cidades se ficarmos só no masculino). Fazer à mão é inviável. **Decisão:** `geopy`/Nominatim com cache em disco, respeitando o limite de 1 requisição/segundo (~3 min de execução, uma única vez).

**4. Os dados estão muito mais limpos do que o esperado.** Zero nulos em `match_date`, `match_time`, `stadium_id`, `city_name` e nos placares. Zero nulos em `stadium_capacity`. Isso é ótimo, mas **muda a narrativa do portfólio**: o trabalho de limpeza não vai ser "consertar dados quebrados", e sim **reconciliação histórica** — que é um problema mais interessante de contar.

**O problema real de limpeza (e é um bom problema):** os nomes de seleções que mudaram ao longo de quase 100 anos, todos presentes no dataset:

| Nome histórico | Entidade atual | Tipo de mudança |
|---|---|---|
| West Germany / East Germany | Germany | Reunificação (1990) |
| Soviet Union | Russia | Dissolução (1991) |
| Yugoslavia → Serbia and Montenegro → Serbia | Serbia | Dissolução em etapas |
| Czechoslovakia | Czech Republic | Separação (1993) |
| Dutch East Indies | Indonesia | Independência (1949) |
| Zaire | DR Congo | Renomeação (1997) |

É exatamente aqui que o `rapidfuzz` **não** resolve sozinho: "Zaire" e "DR Congo" não têm nenhuma semelhança textual. Vai precisar de um **mapa de sucessão explícito** (um dicionário curado, versionado no repositório) + `rapidfuzz` para as variações ortográficas menores. Documentar essa distinção é um ótimo ponto no README.

## 3. Metodologia de ETL

### Etapa 1 — Extração ✅ CONCLUÍDA (fonte principal)

- [x] Criar `etl/extract.py`
- [x] Baixar CSVs do Fjelstul (via GitHub raw) — 16 tabelas, ~1,9 MB
- [ ] Baixar dataset complementar do Kaggle — **só se a decisão sobre público exigir** (ver 2.1)
- [x] Salvar tudo em `data/raw/` sem alterações (preservar dado original)
- [x] Registrar data/hora e fonte de cada download em um `metadata.json`
- [ ] Executar o scraping complementar da Copa de 2026 (ver seção 4)

**O que foi construído:**

| Arquivo | Papel |
|---|---|
| `etl/paths.py` | Todos os caminhos resolvidos a partir da raiz do repo — nenhum caminho relativo frágil espalhado pelos scripts |
| `etl/provenance.py` | Registro de proveniência: SHA-256, timestamp UTC, URL, licença e atribuição de cada arquivo baixado |
| `etl/extract.py` | Download dos 16 CSVs, com escrita atômica, delay entre requisições e user-agent identificável |

**Decisões de implementação (e o porquê — bom material pro README):**

- **Escrita atômica:** cada arquivo é gravado como `.part` e só depois renomeado. Se o download cair no meio, você não fica com um CSV truncado em `data/raw/` parecendo válido.
- **SHA-256 de tudo:** permite rodar `python -m etl.extract --check` e descobrir se a fonte mudou desde o último download, sem baixar por cima. É o gancho natural pra automatizar com GitHub Actions depois.
- **`data/raw/` é imutável:** nada ali é editado à mão, e `.gitignore` não versiona os dados brutos (são reproduzíveis com um comando) — mas **versiona o `metadata.json`**, que é o registro de auditoria.
- **Subconjunto curado:** foram baixadas 16 das 29 tabelas do Fjelstul. As 13 de fora (`player_appearances`, `squads`, `substitutions`, `bookings`, arbitragem) somam ~9 MB de dados a nível de evento individual, fora do escopo do mapa. Adicionar uma delas é acrescentar uma linha na lista.

**Como rodar:**

```bash
python -m etl.extract
```

```bash
python -m etl.extract --check
```

### Etapa 2 — Limpeza ⏳ PRÓXIMO PASSO

- [ ] Criar a coluna `competition` (`mens`/`womens`) a partir de `tournament_name` — **fazer isso primeiro** (ver 2.1)
- [ ] Padronizar nomes de seleções via mapa de sucessão explícito + `rapidfuzz` para variações ortográficas
- [ ] Tratar valores nulos — **escopo bem menor que o previsto**, os dados vieram limpos
- [ ] Remover duplicatas entre as fontes (incluindo os dados raspados de 2026)
- [ ] Validar tipos de dados (datas, números de gols, IDs)
- [ ] Cruzar (join) as fontes e resolver conflitos de informação
- [ ] Salvar resultado em `data/processed/matches_clean.csv`

**Ferramentas:** `pandas` para as transformações; `rapidfuzz` (fuzzy string matching) para as variações ortográficas. **Atenção:** fuzzy matching não resolve sucessão histórica (Zaire → DR Congo não têm similaridade textual) — o mapa curado é obrigatório.

**Ponto de atenção revisado:** a etapa continua sendo a mais delicada, mas por um motivo diferente do previsto — não é sujeira de dados, é **decisão editorial**. Você vai ter que escolher e defender: a Alemanha tem 4 títulos ou a Alemanha Ocidental tem 3 e a Alemanha 1? As duas respostas são defensáveis; o que não é defensável é não documentar qual você escolheu.

### Etapa 3 — Modelagem

Schema proposto (formato tabular relacional):

- `tournaments`: ano, sede (país/cidade), campeão, vice, número de seleções, **`competition`**
- `matches`: torneio, fase, data, mandante, visitante, placar, sede, ~~público~~ (ver 2.1)
- `teams`: nome atual, nomes históricos (para reconciliar mudanças)
- `venues`: cidade, país, latitude, longitude (para o mapa), capacidade

- [ ] Desenhar o schema definitivo (diagrama ERD em Mermaid)
- [ ] Validar o schema com `pandera` (regras de tipo, valores permitidos, nulos aceitáveis)
- [ ] Geocodificar as 202 cidades-sede via `geopy`/Nominatim **com cache em disco** (ver 2.1)
- [ ] Gerar métricas derivadas: total de gols por torneio, capacidade média, número de títulos por seleção
- [ ] Exportar em formato consumível pelo front-end (GeoJSON para o mapa + JSON para tabelas/gráficos)

**Ferramentas:** `pandas` para agregações; `geopy` para geocodificação; `pandera` para validação declarativa do schema.

### Etapa 4 — Visualização

- [x] ~~Escolher biblioteca de mapa~~ → **Leaflet.js decidido** (leve, gratuito, sem chave de API)
- [ ] Marcadores nas sedes de cada Copa, com popup (campeão, artilheiro, capacidade)
- [ ] Camada opcional: trajetória histórica das seleções campeãs
- [ ] Filtro por década/era
- [ ] Alternância masculino/feminino (viabilizada pela coluna `competition`)
- [ ] Painel lateral ou seção com estatísticas gerais (ex: ranking de campeões)

**Ferramentas:** Leaflet.js (JS puro) para o mapa; opcionalmente `folium` em Python para prototipar rápido.

### Etapa 5 — Publicação

- [ ] Estruturar como site estático (`web/index.html` + assets)
- [ ] Testar localmente
- [ ] Publicar via GitHub Pages
- [ ] (Opcional) configurar GitHub Actions para rodar o pipeline de ETL automaticamente
- [x] Escrever README do repositório explicando o processo de ETL (bom para portfólio)
- [x] **Incluir atribuição CC-BY-SA ao Fjelstul** (obrigação de licença, não é opcional) — atribuição da Wikipédia fica pendente até o scraping existir

**Licenciamento (feito em 07/08/2026):** o repositório tem **duas** licenças, porque código e dados têm origens diferentes. Código sob MIT (`LICENSE`); dados sob CC-BY-SA 4.0 (`LICENSE-DATA.md`), porque a cláusula ShareAlike da fonte obriga. O `LICENSE-DATA.md` também mantém o **registro de modificações** exigido pela licença — hoje: nenhuma alteração nos dados brutos, apenas seleção de 16 das 29 tabelas.

## 4. Web scraping — complemento da Copa de 2026

Nenhuma fonte pronta cobre o torneio de 2026. A melhor forma de complementar é raspar os dados diretamente da Wikipédia, que mantém tabelas estruturadas de resultados por partida, artilheiros e sedes.

> ⚠️ **A ser verificado pelo scraping:** a nota anterior deste documento registrava que a Copa de 2026 terminou em 19/07/2026 com título da Espanha sobre a Argentina. **Esse dado ainda não foi confirmado por nenhuma fonte dentro do projeto.** Trate como hipótese até o scraping rodar — e, quando rodar, deixe o dado raspado ser a verdade, não a anotação.

**Fonte alvo:** páginas da Wikipédia sobre a Copa de 2026 (ex: "2026 FIFA World Cup", "2026 FIFA World Cup final", páginas de cada grupo/fase). Conteúdo sob CC BY-SA 4.0 — exige atribuição.

**Nota de escopo:** 2026 é o primeiro torneio com **48 seleções e 3 países-sede** (EUA, Canadá, México). Isso quebra duas premissas do schema: `host_country` como valor único, e o conjunto de fases (há uma fase a mais que em 2022). Prever isso agora evita retrabalho.

**Ferramentas recomendadas, por nível de complexidade:**

| Ferramenta | Quando usar | Vantagem para o portfólio |
|---|---|---|
| `pandas.read_html()` | Tabelas HTML simples e bem formatadas (é o caso da maioria das tabelas de resultados na Wikipédia) | Solução rápida e direta — mostra pragmatismo |
| `requests` + `BeautifulSoup4` | Quando precisa extrair dados que não estão em uma `<table>` limpa, ou combinar texto com tabela | Mostra domínio de parsing HTML manual |
| `Scrapy` | Se quiser estruturar como um spider reaproveitável, com rate limiting e cache embutidos | Mostra arquitetura mais robusta |

**Recomendação prática:** comece com `pandas.read_html()` para validar rápido se as tabelas saem limpas; se precisar de mais controle, evolua para `BeautifulSoup4`. `Scrapy` é overkill para poucas dezenas de páginas.

**Boas práticas a aplicar (e destacar no README):**
- [ ] Respeitar o `robots.txt` do domínio-alvo
- [ ] Colocar um user-agent identificável e um delay entre requisições
- [ ] Cachear o HTML baixado localmente em `data/raw/scraped/`, para não raspar de novo a cada execução
- [ ] Separar claramente "scraping" (baixar o HTML bruto) de "parsing" (extrair os dados) — são responsabilidades diferentes e ajudam a testar cada parte isoladamente
- [ ] Dar atribuição à Wikipédia no README, conforme exigido pela licença CC BY-SA

## 5. Estrutura de repositório

Inspirada na convenção [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/). ✅ = já existe no disco.

```
atlas-copa-mundo/
├── data/
│   ├── raw/              ✅ dados originais, nunca editados manualmente
│   │   ├── fjelstul/     ✅ 16 CSVs baixados
│   │   ├── kaggle/       ✅ (vazio — pendente da decisão sobre público)
│   │   ├── scraped/      ✅ (vazio — HTML bruto da Wikipédia)
│   │   └── metadata.json ✅ registro de proveniência (versionado no git)
│   ├── interim/          ✅ dados intermediários (limpeza parcial)
│   └── processed/        ✅ dados finais, prontos para o front-end
├── etl/
│   ├── paths.py          ✅ caminhos centralizados
│   ├── provenance.py     ✅ hash + timestamp + licença
│   ├── extract.py        ✅ download dos datasets prontos
│   ├── scrape_2026.py    ⏳ próximo
│   ├── transform.py      ⏳
│   ├── validate.py       ⏳ regras do pandera
│   └── load.py           ⏳
├── notebooks/            ✅
├── tests/                ✅
├── web/                  ✅
│   ├── index.html        ⏳
│   ├── map.js            ⏳
│   └── data/             ✅
├── docs/
│   └── roadmap.html      ✅ roadmap visual
├── .github/workflows/    ✅ (vazio — GitHub Actions adiado)
├── plano-atlas-copa-mundo.md    ✅ este documento
├── plan-atlas-world-cup.md      ✅ versão em inglês
├── .gitignore            ✅
├── README.md             ⏳
└── requirements.txt      ✅ versões fixadas e testadas
```

## 6. Cronograma sugerido (ajustável)

| Semana | Foco | Status |
|---|---|---|
| 1 | Extração dos datasets prontos + scraping da Copa 2026 | 🔵 em andamento — extração feita, scraping pendente |
| 2 | Limpeza e reconciliação de nomes | ⬜ |
| 3 | Modelagem, validação e geocodificação | ⬜ |
| 4 | Visualização (mapa funcional) | ⬜ |
| 5 | Refinamento visual + publicação + README | ⬜ |

## 7. Decisões

### Resolvidas

| Decisão | Escolha | Por quê |
|---|---|---|
| Leaflet ou Mapbox | **Leaflet** | Não precisa de chave de API — o mapa continua funcionando pra quem clonar o repositório, sem cadastro. Para marcadores + popups, os recursos extras do Mapbox não se pagam. |
| Dataset feminino no v1 | **Extrair sempre, exibir com filtro** | Vem nos mesmos arquivos, custo zero. Separar por uma coluna `competition` e deixar o front-end filtrar é mais barato do que descartar agora e reprocessar depois. |
| GitHub Actions | **Adiado para v2** | O `--check` do `extract.py` já deixa o gancho pronto. Automatizar antes de ter pipeline completo é otimização prematura. |
| Quantas tabelas do Fjelstul baixar | **16 de 29** | As 13 restantes são dados de evento individual (~9 MB), fora do escopo de um mapa. Fácil de reverter. |

### Em aberto

- [ ] **Público (attendance):** buscar no `wcmatches` do Kaggle (só até 2018) ou trocar por capacidade do estádio no v1? — *bloqueia o conteúdo dos popups do mapa*
- [ ] **Sucessão de seleções:** Alemanha Ocidental conta como Alemanha na contagem de títulos? URSS conta como Rússia? — *bloqueia a Etapa 2; é decisão editorial, não técnica*
- [ ] Confirmar licença do "FIFA World Cup 1930-2022 All Match Dataset" (Kaggle) — *só importa se ele for realmente usado*
- [ ] Decidir entre `pandas.read_html`, `BeautifulSoup4` ou `Scrapy` para o scraping de 2026 (recomendação: começar pelo `read_html`)
- [x] ~~Criar o repositório remoto no GitHub e dar `git push`~~ → publicado em https://github.com/alaindelon96/atlas-copa-mundo

## 8. Notas de progresso

- **27/07/2026** — plano inicial criado.
- **27/07/2026** — confirmado que a Copa de 2026 terminou (Espanha campeã); documento reestruturado com stack tecnológico e etapa de web scraping. *(Ver ressalva na seção 4: esse dado ainda não foi verificado por nenhuma fonte dentro do projeto.)*
- **07/08/2026** — ambiente verificado (Python 3.11.9, git 2.55.0); dependências instaladas e fixadas.
- **07/08/2026** — estrutura de repositório criada; `.gitignore` e `requirements.txt` escritos.
- **07/08/2026** — **Etapa 1 concluída para a fonte principal:** `etl/paths.py`, `etl/provenance.py` e `etl/extract.py` implementados; 16 CSVs do Fjelstul baixados (~1,9 MB) com proveniência SHA-256 em `data/raw/metadata.json`.
- **07/08/2026** — exploração dos dados revelou quatro pontos que mudam o plano: (1) `tournament_id` não separa masculino de feminino; (2) não há dado de público; (3) são 202 cidades para geocodificar, não "poucas"; (4) os dados estão limpos — o desafio real é reconciliação histórica de nomes, não sujeira. Detalhes na seção 2.1.
- **07/08/2026** — scraping de 2026 ainda não iniciado.
