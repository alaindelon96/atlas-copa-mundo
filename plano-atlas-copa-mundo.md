# Atlas da Copa do Mundo — plano de projeto

> Documento vivo. Atualize conforme o projeto evoluir. Última revisão: 08/08/2026.
>
> **Status atual:** Etapas 1 a 4 concluídas — extração, scraping, limpeza, modelagem, geocodificação, validação e o mapa. Etapa 5 (Publicação) é o próximo passo: subir para o GitHub Pages.
>
> **Escopo:** Copa masculina — 23 edições, 1.068 partidas, 1930–2026. A Copa feminina é extraída e limpa, mas fica fora do modelo e do mapa (ver Etapa 3).
>
> Esquema do modelo: [`docs/schema.md`](docs/schema.md)
> Versão em inglês: [`plan-atlas-world-cup.md`](plan-atlas-world-cup.md) · Roadmap visual: [`docs/roadmap.html`](docs/roadmap.html)

## 1. Visão geral

**Objetivo:** construir um mapa interativo publicado na web mostrando o histórico da Copa do Mundo (1930–2026), como peça de portfólio de análise de dados, cobrindo o ciclo completo de ETL — da extração (incluindo web scraping) até a publicação.

**Por que esse projeto funciona bem como portfólio:** ele passa por praticamente todas as habilidades que um recrutador técnico procura — ingestão de dados de múltiplas fontes (API, CSV, scraping), reconciliação de dados sujos e inconsistentes ao longo de quase 100 anos, modelagem relacional, e um produto visual final que qualquer pessoa entende sem precisar ler código.

### Stack tecnológico (visão consolidada)

| Camada | Ferramenta principal | Alternativa | Por quê | Status |
|---|---|---|---|---|
| Extração — datasets prontos | `requests`, Kaggle API | — | Download direto de CSVs | ✅ implementado (`requests`) |
| Extração — web scraping | `requests` + `BeautifulSoup4` | `Scrapy` (se quiser mostrar arquitetura de spider) | Complementar dados da Copa 2026 | ✅ implementado (14 páginas) |
| Limpeza | `pandas`, `rapidfuzz` | `numpy` | Reconciliar nomes de seleções, tratar nulos | ✅ implementado (`etl/transform.py`) |
| Validação de dados | `pandera` | `great_expectations` | Garantir qualidade antes de modelar (bom diferencial de portfólio) | ✅ implementado (`etl/validate.py`) |
| Modelagem | `pandas`, schema documentado em Mermaid ERD | `dbdiagram.io` | Formalizar schema relacional | ✅ implementado (6 tabelas, [`docs/schema.md`](docs/schema.md)) |
| Geocodificação | `geopy` (Nominatim) | CSV manual de sedes | **Ver nota abaixo — não dá mais pra fazer manual** | ✅ implementado (252 sedes, cache versionado) |
| Visualização | Leaflet.js | Mapbox GL JS | Leve, gratuito, sem chave de API | ✅ implementado (`web/map.js`, 9 métricas) |
| Publicação | GitHub Pages | Netlify/Vercel | Grátis, integrado ao repositório | ⏳ não iniciado |
| Automação/CI | GitHub Actions | — | Rodar pipeline de ETL automaticamente (opcional, mas valoriza o portfólio) | ⏳ adiado para v2 |
| Testes | `pytest` | — | Testar funções de limpeza/transformação | ✅ 73 testes, todos offline |

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
- [x] ~~Baixar dataset complementar do Kaggle~~ → **não será baixado.** Ele só existia para o dado de público, que saiu do escopo (ver seção 7).
- [x] Salvar tudo em `data/raw/` sem alterações (preservar dado original)
- [x] Registrar data/hora e fonte de cada download em um `metadata.json`
- [x] Executar o scraping complementar da Copa de 2026 (ver seção 4) — 104 partidas, 16 sedes

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

### Etapa 2 — Limpeza ✅ CONCLUÍDA

- [x] Criar a coluna `competition` (`mens`/`womens`) a partir de `tournament_name`
- [x] Padronizar nomes de seleções via mapa de sucessão explícito + `rapidfuzz` para sinalizar candidatos
- [x] Tratar valores nulos — **escopo bem menor que o previsto**, os dados vieram limpos
- [x] Remover duplicatas entre as fontes — resolvido na origem, dando papel fixo a cada página
- [x] Normalizar nomes de fase (o Fjelstul tinha `quarter-final` E `quarter-finals`)
- [x] Cruzar (join) as fontes e resolver conflitos de informação
- [x] Salvar resultado em `data/processed/matches_clean.csv` — 1.352 partidas, 1930–2026
- [x] Escrever testes (`tests/test_transform.py` — 14 testes, todos offline)

**A decisão editorial, tomada em 08/08/2026:** a **Alemanha Ocidental conta como Alemanha**. A Alemanha passa a ter **4 títulos**, que é a contagem oficial da FIFA.

Foi a **única** pergunta de sucessão que muda um número de manchete: URSS, Iugoslávia, Tchecoslováquia, Alemanha Oriental e Zaire nunca venceram uma Copa. O tratamento delas afeta contagem de participações e rótulos no mapa, mas nenhum título.

**Três ideias sustentam esta etapa:**

1. **Rótulo e registro são perguntas diferentes.** O `reference/team_succession.csv` tem duas colunas separadas: `display_name` (como a seleção aparece hoje) e `merge_records` (se o histórico dela é creditado ao sucessor). A Alemanha Ocidental tem as duas; a URSS tem só a primeira.

   > ⚠️ **Corrigido na Etapa 3.** Esta seção afirmava que a URSS "mantém o registro próprio". A validação com `pandera` mostrou que não: `apply_succession` aplica o `display_name` a todo mundo, então os registros de **partida** sempre seguiram o rótulo — só a contagem de **títulos** respeita o `merge_records`. Como nenhuma das entidades com `merge_records=0` jamais venceu uma Copa, nenhum número de manchete estava errado; o que estava errado era a descrição. Confrontado com a escolha em 08/08/2026, o projeto **reafirmou o comportamento**: o rótulo manda. Ver Etapa 3 e [`docs/schema.md`](docs/schema.md).

2. **Fuzzy matching sugere, nunca decide.** O `rapidfuzz` só reporta nomes de 2026 sem correspondente histórico, para uma pessoa classificar. Resultado: quatro estreantes legítimos (Cabo Verde, Curaçao, Jordânia, Uzbequistão) — e **DR Congo não aparece na lista**, porque o mapa curado já resolveu para Zaire, de 1974. `fuzz.WRatio("Zaire", "DR Congo")` dá menos de 50.

3. **Campeão não sai da final.** A Copa de 1950 **não teve final** — foi decidida por um quadrangular. Contar campeões filtrando `stage == "final"` devolve 22 títulos para 23 edições e não dá erro nenhum. Por isso os campeões vêm de `tournament_standings.csv`, e o pipeline confere que a soma dos títulos bate com o número de edições.

**Ferramentas:** `pandas` para as transformações; `rapidfuzz` (fuzzy string matching) para as variações ortográficas. **Atenção:** fuzzy matching não resolve sucessão histórica (Zaire → DR Congo não têm similaridade textual) — o mapa curado é obrigatório.

**Ponto de atenção revisado:** a etapa continua sendo a mais delicada, mas por um motivo diferente do previsto — não é sujeira de dados, é **decisão editorial**. Você vai ter que escolher e defender: a Alemanha tem 4 títulos ou a Alemanha Ocidental tem 3 e a Alemanha 1? As duas respostas são defensáveis; o que não é defensável é não documentar qual você escolheu.

### Etapa 3 — Modelagem e geocodificação ✅ CONCLUÍDA

> ⚠️ **A decisão de 08/08/2026 sobre o desenho do mapa (ver Etapa 4) mudou a prioridade desta etapa.** O mapa é **coroplético** — pinta países inteiros — e não um mapa de marcadores. Coroplético precisa de **polígonos de país**, não de coordenadas de ponto. Geocodificar cidades deixou de ser o trabalho central e virou secundário.

- [x] **Construir `reference/team_country.csv`: as seleções → polígono no mapa-múndi** — o novo problema central desta etapa
- [x] Baixar um GeoJSON de países (Natural Earth), incluindo as **sub-regiões do Reino Unido**
- [x] Preencher `country_name` das 104 partidas de 2026 — **destravou a métrica "partidas recebidas"**
- [x] Desenhar o schema definitivo (diagrama ERD em Mermaid) — [`docs/schema.md`](docs/schema.md)
- [x] Validar o schema com `pandera` (regras de tipo, valores permitidos, nulos aceitáveis)
- [x] Gerar a tabela longa `(partida, seleção)` — uma linha por seleção por partida, base de todas as métricas
- [x] Gerar a matriz de confrontos diretos (seleção × adversário) para o modo de país selecionado
- [x] Exportar GeoJSON para o mapa + JSON para painéis
- [x] Geocodificar as sedes via `geopy`/Nominatim com cache — **as 252 sedes, não só as 2026**

**O que foi construído:**

| Arquivo | Papel |
|---|---|
| `etl/geocode.py` | 252 sedes → coordenada e país, via Nominatim, com cache versionado |
| `etl/geo.py` | GeoJSON do Natural Earth → `reference/team_country.csv` + `web/data/countries.geojson` |
| `etl/model.py` | As 6 tabelas do modelo em `data/processed/` |
| `etl/validate.py` | O contrato de cada tabela, em `pandera`, verificado contra o que está em disco |
| `docs/schema.md` | O ERD em Mermaid e o porquê de cada decisão do schema |

**Modelo:** 6 tabelas — `tournaments` (23), `tournament_hosts` (26), `teams` (83), `venues` (208), `matches` (1.068), `team_matches` (2.136).

**Escopo — decisão de 08/08/2026: só a Copa masculina.** O feminino é *extraído e limpo, mas não modelado*, e a distinção é o ponto: `data/raw/` e `data/processed/matches_clean.csv` seguem com as 284 partidas de 1991–2019 e com a coluna `competition` que as identifica; o que sai é o produto — modelo, métricas e mapa. O corte acontece em **um lugar só**, a constante `COMPETITION` em `etl/model.py`, e todo o resto herda. Por isso as tabelas do modelo não têm coluna `competition`: ela teria um único valor em 1.068 linhas, e uma coluna constante não informa nada — só sugere uma variação que não existe. Reincluir depois é mudar a constante e devolver a coluna; as sedes que só receberam Copa feminina já estão geocodificadas e em cache, então nada precisa ser refeito. Um teste em `tests/test_model.py` falha se alguém apagar o feminino mais atrás no pipeline, para a porta continuar aberta por construção e não por memória.

**Quatro coisas que o dado impôs (detalhe em [`docs/schema.md`](docs/schema.md)):**

1. **`map_units`, não `countries`.** O Natural Earth publica duas divisões do mundo. Só a `admin_0_map_units` separa Inglaterra, Escócia, País de Gales e Irlanda do Norte — o recorte que o futebol usa e que este projeto decidiu manter. O preço: a mesma divisão separa a **Bélgica** em Flandres, Valônia e Bruxelas, então o mapa seleção→polígono é **um-para-muitos** (88 polígonos para 86 seleções). As três regiões belgas recebem a mesma cor e a costura não aparece. Por isso a coluna se chama `gu_a3` e não `iso_a3`: `ENG` e `SCT` não são códigos ISO de país.

2. **País-sede virou tabela.** A fonte guarda o país-sede em uma coluna só e improvisa quando há mais de um — 2002 vira `"Korea, Japan"` (com vírgula, e "Korea" é um nome que não existe em nenhum outro lugar do dataset) e 2026 vira `"Canada Mexico United States"` (sem separador nenhum). Duas codificações ad hoc do mesmo um-para-muitos. No modelo, os países-sede são **derivados das sedes onde as partidas de fato ocorreram**; a string declarada virou conferência.

3. **O `pandera` pagou por si em duas linhas.** As conferências que cada script já fazia checam **totais** ("os gols somam?"), e por isso são cegas para erro de linha. A validação declarativa achou dois sentinels que nenhuma soma acusaria: o Fjelstul grava `0–0` no placar de pênaltis de **1.205 partidas sem disputa** (um 0 é um placar válido), e escreve a string `"not applicable"` em `group_name` nas **332 partidas de mata-mata** — um `groupby` por grupo devolveria um "grupo" chamado `not applicable`, sem erro. Ambos viraram nulo de verdade.

4. **A geocodificação achou o que o dataset já dizia.** Nas 8 sedes inglesas de 1966, o Nominatim devolve `United Kingdom` onde o dataset diz `England` — a mesma fronteira que a escolha por `map_units` resolve do outro lado. Onde o dataset tem país, ele prevalece; o Nominatim entra como conferência. Onde não tinha (2026), ele preencheu.

**A decisão editorial reafirmada em 08/08/2026: o rótulo manda.** Quem é rotulado como Alemanha soma como Alemanha. A consequência aparece uma vez em 1.352 partidas e o modelo a expõe em vez de escondê-la: **M-1974-20, Alemanha Oriental 1–0 Alemanha Ocidental**, vira `Germany × Germany`. A Alemanha soma uma vitória e uma derrota, um gol feito e um sofrido — todos os totais continuam fechando e nenhum título muda. `etl.validate` imprime o caso a cada execução e `tests/test_model.py` o trava, para que a escolha continue visível e ninguém a "conserte" sem saber que está mexendo numa decisão editorial.

**Ferramentas:** `pandas` para agregações; `pandera` para validação declarativa; `geopy`/Nominatim para as sedes.

**Como rodar:**

```bash
python -m etl.geocode --offline && python -m etl.geo
```

```bash
python -m etl.model && python -m etl.validate && python -m etl.metrics
```

O `--offline` usa o cache versionado em `data/interim/geocode_cache.json` e não toca na rede. Sem ele, são ~5 minutos de requisições ao Nominatim, a 1 por segundo — o cache é versionado por educação com um serviço público e gratuito, mesmo raciocínio do `metadata.json`.

### Etapa 4 — Visualização

**Desenho definido em 08/08/2026: mapa-múndi coroplético com dois seletores.**

Não é um mapa de marcadores em sedes — é um mapa que **pinta países** segundo uma métrica escolhida. Dois controles:

| Controle | Opções |
|---|---|
| **Métrica** | Gols · Vitórias/Derrotas · Partidas recebidas · Partidas jogadas · Títulos · Participações |
| **País** | Nenhum (visão global) ou uma seleção específica |

**O modo de país selecionado é a ideia mais forte do projeto.** Ao escolher *Brasil + Gols*, o mapa **repinta segundo os confrontos diretos**: cada país fica colorido pelo número de gols que o Brasil fez contra ele. A Suécia acende mais forte (21 gols em 7 jogos), e o painel resume os 247 gols do Brasil em 119 partidas, 23 participações, 82V–15E–22D.

- [x] ~~Escolher biblioteca de mapa~~ → **Leaflet.js decidido** (leve, gratuito, sem chave de API)
- [x] ~~Desenho do mapa~~ → **coroplético com seletor de métrica e de país**
- [x] ~~Reino Unido~~ → **sub-regiões separadas.** Inglaterra, Escócia, País de Gales e Irlanda do Norte são quatro seleções distintas e continuam quatro regiões distintas no mapa. Somar as quatro criaria uma "seleção do Reino Unido" que nunca existiu, com 168 gols que ninguém marcou.
- [x] ~~Contagem bruta ou por jogo~~ → **as duas, com alternância.** Contagem bruta sozinha reproduz "quem se classificou mais vezes": a Alemanha tem 248 gols e o Brasil 247 porque os dois jogaram ~120 partidas. Por jogo, a **Hungria lidera com 2,72** e some do top 10 bruto. A alternância entre as duas leituras *é* o insight.
- [x] Escala sequencial de uma cor só para a métrica (nunca arco-íris) — **contínua**, e na cor da seleção escolhida
- [x] Piso de 10 partidas no modo "por jogo", para uma seleção de 3 jogos não ultrapassar o Brasil
- [x] ~~Filtro por década/era~~ → **slider de faixa de anos**, sobre as 23 edições
- [x] Painel lateral com o resumo da seleção escolhida e a tabela de confrontos

**O que foi construído:**

| Arquivo | Papel |
|---|---|
| `web/index.html` | A casca: o mapa ocupando a janela inteira e os painéis flutuando por cima |
| `web/map.js` | Agrega, classifica e pinta — e faz a autoconferência contra o `metrics.json` |
| `web/style.css` | Cromo cartográfico herdado do `panorama.html` + as duas rampas de cor do dado |
| `web/vendor/leaflet.*` | Leaflet 1.9.4 versionado no repositório, não via CDN |
| `web/vendor/flags/` | 83 bandeiras em SVG (circle-flags, MIT), uma por seleção |
| `web/data/timeline.json` | A tabela longa em forma compacta (37 KB) — o que o slider agrega |
| `etl/color.py` | Cor de camisa → rampa sequencial, em OKLab |
| `reference/team_colors.csv` | A cor curada de cada uma das 83 seleções, com o porquê das exceções |
| `web/data/colors.json` | As 83 rampas prontas, nos dois modos |

**Quatro decisões desta etapa:**

1. **O filtro temporal é um slider de faixa, e ele quebrou a regra "o front-end não agrega".** Década seria pré-computável; faixa livre não é — 23 edições dão 276 faixas possíveis. Então `timeline.json` leva a tabela longa em forma colunar (2.136 linhas, 37 KB — menor que o `head2head.json`, porque os nomes viraram índices) e o JavaScript soma.

   A regra não foi abandonada, **virou conferência**: `etl.metrics.aggregate_timeline` é a implementação de referência em Python, o `map.js` a espelha, e a página **refaz a faixa completa ao carregar e compara com o `metrics.json`, seleção por seleção**. Divergiu, aparece um aviso vermelho no topo dizendo que os números não são confiáveis. A duplicação de lógica existe — o que não existe é ela ser silenciosa. Um teste em Python trava o outro lado.

2. **A rampa é a cor da seleção escolhida.** Escolher o Brasil pinta o mapa de amarelo, a Itália de azzurro, a Holanda de laranja. As cores são curadas à mão em [`reference/team_colors.csv`](reference/team_colors.csv), na mesma lógica do `team_succession.csv`: é decisão editorial, então fica versionada com o porquê.

   A regra é **a camisa principal da última Copa que a seleção disputou** — não "a cor do país", nem o uniforme atual. Para 48 das 83 a última Copa é 2026, então a distinção quase não morde; ela morde nas **nove** que não jogam desde antes de 1998 (Cuba 1938, Índias Orientais Neerlandesas 1938, Israel 1970, Kuwait e El Salvador 1982, Hungria e Irlanda do Norte 1986, Emirados 1990, Bolívia 1994). A coluna `last_cup` é **conferida contra o modelo** a cada execução: se uma seleção voltar a jogar, a linha fica desatualizada e o pipeline para. A conferência já pagou por si — pegou dois erros de curadoria na primeira execução, Itália (última em 2014, não 2026) e Peru (2018).

   A exceção continua sendo a camisa branca ou preta, que não têm matiz para sustentar uma rampa e cujo cinza colidiria com o cinza de "sem dado": nesses **16 casos** (Alemanha, Inglaterra, Polônia, Peru, Nova Zelândia…) entra a cor cromática que identifica a seleção, marcada `identity` e justificada linha a linha.

   **A visão global não faz isso**, e a diferença importa: sem país escolhido, a rampa é uma só. Dar a cada país a sua própria cor deixaria o mapa bonito e ilegível, porque o olho lê escuridão como quantidade — uma Itália azul-escura pareceria "mais" que um Brasil amarelo vivo com número maior.

3. **Uma cor de camisa não é uma rampa — `etl/color.py` transforma uma na outra.** O trabalho acontece em **OKLab/OKLCH**, espaço perceptualmente uniforme: interpolar do amarelo `#FFDF00` até o branco em sRGB passa por bege sujo. A claridade percorre a banda do modo linearmente (é ela que carrega o dado, e é ela que mantém a rampa legível para quem não distingue matizes); o croma sobe junto sem passar do croma da própria cor. Quando um passo não cabe em sRGB — amarelo escuro e saturado não existe —, o que cede é o **croma**, nunca os canais RGB: clampar canal moveria o matiz e o amarelo chegaria laranja na ponta.

   Isso roda no **Python**, não no navegador: as rampas saem prontas em `web/data/colors.json` (19 KB, 83 seleções × 2 modos × 9 passos) e o JavaScript só interpola entre passos vizinhos. Portar OKLab para o `map.js` seria uma segunda implementação para manter em sincronia.

4. **Escala contínua, com raiz quadrada.** Não há mais classes. A raiz não é enfeite — sem ela o mapa some: a distribuição é muito torta (o Brasil tem 247 gols, metade das seleções tem menos de 10), e uma escala linear contínua empurra quase todo mundo para o primeiro décimo da rampa. A raiz abre o pé da distribuição **sem inverter nenhuma ordem**; o que ela distorce é a proporção, e por isso a legenda virou uma barra com os valores marcados em `sqrt(v/máx)`. As marcas se apertam à direita — essa compressão visível *é* o aviso de que a escala não é linear.

5. **O saldo de gols mantém dois polos fixos.** Ele é a única métrica com lado negativo, então usa rampa divergente (vermelho ↔ azul) — e ela **não** segue a cor da seleção escolhida. Se o lado positivo virasse amarelo com o Brasil e vermelho com a Espanha, "negativo" mudaria de cor a cada troca de país e o mapa deixaria de ter um lado.

6. **Zero e "sem dado" são cores diferentes.** Três seleções nunca marcaram um gol em Copa — China, Trinidad e Tobago e o Zaire de 1974 — e isso é um fato, não uma ausência. Por isso o passo mais fraco de cada rampa carrega um traço do matiz em vez de ser acromático: se fosse cinza, seria o mesmo cinza de quem nunca jogou.

**O que o mapa mostra hoje:** 9 métricas em escala contínua na cor da camisa da seleção, 85 polígonos pintados de 264, seletor de país com modo de confronto direto, alternância total/por partida, faixa de anos de 1930 a 2026 e um painel que é também a *table view* exigida pela regra de acessibilidade (a informação nunca fica só na cor).

**Ferramentas:** Leaflet.js com camada GeoJSON de países; `pandas` para pré-computar as métricas.

**Como rodar:**

```bash
python -m http.server 8000 --directory web
```

A página precisa de um servidor HTTP: abrir o `index.html` direto do disco esbarra na política de origem do navegador e o `fetch` dos JSONs falha. A própria página diz isso se acontecer.

**Por que este desenho combina com o nosso dado:** ele vive inteiramente no **nível de partida** — placar, seleções, sede. É exatamente a dimensão que as duas fontes têm completa. Features de jogador, confederação ou escalação teriam buraco em 2026 (ver seção 2.1); esta não tem.

### Etapa 4b — Quatro funcionalidades novas

Inspiradas no **SofaScore**, cuja página de seleção é construída em cima de uma lista de partidas com marcador V/E/D por linha, um resumo de forma e um botão de comparação — e no [copa2026.goodstart.com.br](https://copa2026.goodstart.com.br/) para a casca. As quatro nascem do dado que já existia; nenhuma exigiu fonte nova.

| Funcionalidade | O que resolve |
|---|---|
| **Estado na URL** | A visão vira link. Sem isso, "Brasil contra a Suécia entre 1958 e 1970" é um roteiro para a pessoa executar à mão. |
| **Detalhamento de partidas** | O mapa dizia *quanto* e nunca *quais*. Agora o número abre: clique num confronto e vêm as partidas, com data, edição, fase, placar e sede. |
| **Comparação de duas seleções** | Confronto direto só responde sobre quem se enfrentou. A comparação lado a lado funciona também para quem nunca se cruzou. |
| **Camada de sedes** | Devolve as 252 sedes que a Etapa 3 geocodificou e o mapa nunca usou. O coroplético agrega ao país; a camada mostra **onde**. |

**Três decisões que o dado impôs:**

1. **Pênaltis não geram empate — nem no detalhamento.** `etl.model` resolve as 39 disputas em vitória e derrota, porque tratar o tempo normal como final criaria empates que não aconteceram. O JavaScript precisa aplicar a mesma regra, senão a lista mostra "E" logo abaixo de um painel que diz 82 vitórias. Um teste refaz a conta a partir do `matches.json` e compara com o `metrics.json` — mesmo padrão da autoconferência do mapa, um nível abaixo.

2. **As duas listas de sede têm que estar na mesma ordem.** O front-end pega o índice de sede de uma partida e usa esse índice para achar a coordenada na camada. A primeira versão ordenava a camada por número de partidas e quebrava isso **em silêncio**, porque as duas listas continuam do mesmo tamanho. Virou contrato conferido no ETL e em teste.

3. **A URL guarda só o que difere do padrão.** Uma visão inicial devolve `#` limpo em vez de um parágrafo de parâmetros redundantes, e o `replaceState` evita que cada passo do slider vire uma entrada no histórico.

**Novos arquivos:** `web/data/matches.json` (58 KB, as 1.068 partidas) e `web/data/venues.json` (15 KB, as 208 sedes com partida).

### Etapa 5 — Publicação

- [x] Estruturar como site estático (`web/index.html` + assets)
- [x] Testar localmente
- [ ] Publicar via GitHub Pages
- [ ] (Opcional) configurar GitHub Actions para rodar o pipeline de ETL automaticamente
- [x] Escrever README do repositório explicando o processo de ETL (bom para portfólio)
- [x] **Incluir atribuição CC-BY-SA ao Fjelstul** (obrigação de licença, não é opcional) — atribuição da Wikipédia fica pendente até o scraping existir

**Licenciamento (feito em 07/08/2026):** o repositório tem **duas** licenças, porque código e dados têm origens diferentes. Código sob MIT (`LICENSE`); dados sob CC-BY-SA 4.0 (`LICENSE-DATA.md`), porque a cláusula ShareAlike da fonte obriga. O `LICENSE-DATA.md` também mantém o **registro de modificações** exigido pela licença — hoje: nenhuma alteração nos dados brutos, apenas seleção de 16 das 29 tabelas.

## 4. Web scraping — complemento da Copa de 2026

Nenhuma fonte pronta cobre o torneio de 2026. A melhor forma de complementar é raspar os dados diretamente da Wikipédia, que mantém tabelas estruturadas de resultados por partida, artilheiros e sedes.

> ✅ **VERIFICADO em 08/08/2026.** A nota anterior estava correta: a Copa de 2026 terminou em 19/07/2026, com a Espanha batendo a Argentina por 1–0 no MetLife Stadium, diante de 80.663 pessoas (2º título espanhol). Terceiro lugar: Inglaterra; quarto: França. Artilheiro: Kylian Mbappé (10 gols). O dado agora vem do scraping, não da anotação.

**Resultado do scraping (14 páginas, revisões registradas):**

| | |
|---|---|
| Partidas | 104 (72 de grupo + 32 de mata-mata) |
| Gols | 308 (2,96 por partida) |
| Público total | 6.810.966 (média de 65.490) |
| Sedes | 16 estádios, 3 países |
| Seleções | 48 |

As três conferências do parser batem exatamente com os totais que o próprio artigo declara — partidas, gols e sedes. O parser **falha** se não baterem.

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
│   │   ├── kaggle/       ✅ (vazio — e vai continuar: público saiu do escopo)
│   │   ├── scraped/      ✅ (vazio — HTML bruto da Wikipédia)
│   │   └── metadata.json ✅ registro de proveniência (versionado no git)
│   │   └── naturalearth/ ✅ GeoJSON de polígonos de país
│   ├── interim/          ✅ dados intermediários + o cache do Nominatim (versionado)
│   └── processed/        ✅ as 6 tabelas do modelo, prontas para o front-end
├── etl/
│   ├── paths.py          ✅ caminhos centralizados
│   ├── provenance.py     ✅ hash + timestamp + licença
│   ├── extract.py        ✅ download dos datasets prontos
│   ├── scrape_2026.py    ✅ baixa o HTML da Wikipédia
│   ├── parse_2026.py     ✅ extrai partidas/sedes do HTML
│   ├── transform.py      ✅ limpeza e reconciliação histórica
│   ├── geocode.py        ✅ 252 sedes via Nominatim, com cache
│   ├── geo.py            ✅ polígonos de país + mapa seleção→polígono
│   ├── model.py          ✅ as 6 tabelas do modelo
│   ├── validate.py       ✅ regras do pandera
│   └── metrics.py        ✅ JSONs que o mapa consome
├── reference/            ✅ tabelas curadas à mão (sucessão, seleção→polígono, cores)
├── notebooks/            ✅
├── tests/                ✅ 36 testes, todos offline
├── web/                  ✅
│   ├── index.html        ✅ a página do mapa
│   ├── map.js            ✅ agrega, classifica, pinta e se autoconfere
│   ├── style.css         ✅ cromo cartográfico + as duas rampas de cor
│   ├── vendor/           ✅ Leaflet 1.9.4 versionado (sem CDN)
│   └── data/             ✅ metrics.json, head2head.json, timeline.json, colors.json, countries.geojson
├── docs/
│   ├── schema.md         ✅ ERD do modelo (Mermaid)
│   ├── panorama.html     ✅ panorama dos dados
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
| 1 | Extração dos datasets prontos + scraping da Copa 2026 | ✅ concluída |
| 2 | Limpeza e reconciliação de nomes | ✅ concluída |
| 3 | Modelagem, validação e geocodificação | ✅ concluída |
| 4 | Visualização (mapa funcional) | ✅ concluída |
| 5 | Refinamento visual + publicação + README | 🔵 próximo passo |

## 7. Decisões

### Resolvidas

| Decisão | Escolha | Por quê |
|---|---|---|
| Leaflet ou Mapbox | **Leaflet** | Não precisa de chave de API — o mapa continua funcionando pra quem clonar o repositório, sem cadastro. Para marcadores + popups, os recursos extras do Mapbox não se pagam. |
| Dataset feminino no v1 | **Extrair e limpar sempre; ficar fora do modelo** | Revisto em 08/08/2026. A extração e a limpeza continuam cobrindo as duas competições — custo zero, e o dado fica pronto. O que mudou é o produto: o modelo, o mapa e os JSONs cobrem só a Copa masculina. O recorte é uma constante em `etl/model.py`, então reincluir o feminino é um diff pequeno, não um reprocessamento. |
| GitHub Actions | **Adiado para v2** | O `--check` do `extract.py` já deixa o gancho pronto. Automatizar antes de ter pipeline completo é otimização prematura. |
| Quantas tabelas do Fjelstul baixar | **16 de 29** | As 13 restantes são dados de evento individual (~9 MB), fora do escopo de um mapa. Fácil de reverter. |

### Em aberto

- [x] ~~**Público (attendance)**~~ → **RESOLVIDO em 08/08/2026 por redução de escopo: público e capacidade ficam de fora.** As features do mapa são só estatísticas de jogo — gols, gols sofridos, saldo, V/E/D, aproveitamento, partidas jogadas, partidas recebidas, títulos, participações, e os mesmos números em confronto direto. Público existe em 104 de 1.068 partidas; capacidade é completa mas **varia no tempo** (o Azteca tinha 115.000 em 1970 e tem 80.824 em 2026 — 34.176 de diferença numa coluna que só cabe um valor). Estatística de jogo não tem nenhum dos dois problemas: é completa nas 1.068 partidas e significa a mesma coisa em 1930 e em 2026. A coluna `attendance` continua em `matches.csv` porque é um fato que a fonte dá; ela só não alimenta métrica nenhuma. Capacidade nunca foi juntada — omissão deliberada, não esquecimento.
- [x] ~~**Sucessão de seleções**~~ → **RESOLVIDO em 08/08/2026: a Alemanha Ocidental conta como Alemanha (4 títulos).** As dissoluções (URSS, Iugoslávia, Tchecoslováquia) recebem rótulo moderno **e somam nos registros de partida do sucessor** — `merge_records` governa só a contagem de títulos, e como nenhuma delas venceu, nenhum título muda. Regras e ressalvas em `reference/team_succession.csv`; consequências em [`docs/schema.md`](docs/schema.md).
- [ ] Confirmar licença do "FIFA World Cup 1930-2022 All Match Dataset" (Kaggle) — *só importa se ele for realmente usado*
- [x] ~~Decidir entre `pandas.read_html`, `BeautifulSoup4` ou `Scrapy`~~ → **`requests` + `BeautifulSoup4`**, com scraping e parsing em módulos separados.
- [x] ~~Criar o repositório remoto no GitHub e dar `git push`~~ → publicado em https://github.com/alaindelon96/atlas-copa-mundo

## 8. Notas de progresso

- **27/07/2026** — plano inicial criado.
- **27/07/2026** — confirmado que a Copa de 2026 terminou (Espanha campeã); documento reestruturado com stack tecnológico e etapa de web scraping. *(Ver ressalva na seção 4: esse dado ainda não foi verificado por nenhuma fonte dentro do projeto.)*
- **07/08/2026** — ambiente verificado (Python 3.11.9, git 2.55.0); dependências instaladas e fixadas.
- **07/08/2026** — estrutura de repositório criada; `.gitignore` e `requirements.txt` escritos.
- **07/08/2026** — **Etapa 1 concluída para a fonte principal:** `etl/paths.py`, `etl/provenance.py` e `etl/extract.py` implementados; 16 CSVs do Fjelstul baixados (~1,9 MB) com proveniência SHA-256 em `data/raw/metadata.json`.
- **07/08/2026** — exploração dos dados revelou quatro pontos que mudam o plano: (1) `tournament_id` não separa masculino de feminino; (2) não há dado de público; (3) são 202 cidades para geocodificar, não "poucas"; (4) os dados estão limpos — o desafio real é reconciliação histórica de nomes, não sujeira. Detalhes na seção 2.1.
- **08/08/2026** — repositório publicado em https://github.com/alaindelon96/atlas-copa-mundo; README, `LICENSE` (MIT, código) e `LICENSE-DATA.md` (CC-BY-SA 4.0, dados) escritos.
- **08/08/2026** — **Etapa 1b concluída: scraping da Copa de 2026.** `robots.txt` da Wikipédia verificado (artigos em `/wiki/` são permitidos; `/w/` e `/api/` não). `etl/scrape_2026.py` baixou 14 páginas com o `revision_id` de cada uma; `etl/parse_2026.py` extraiu 104 partidas, 16 sedes e o registro do torneio, conferindo tudo contra os totais do próprio artigo.
- **08/08/2026** — **Etapa 2 concluída** e decisão de sucessão tomada (Alemanha Ocidental = Alemanha, 4 títulos). `data/processed/matches_clean.csv` com 1.352 partidas; 14 testes passando.
- **08/08/2026** — panorama dos dados gerado (`docs/panorama.html`) para escolher features a partir do dado. Revelou a assimetria central: 2026 só existe no nível de partida.
- **08/08/2026** — **desenho do mapa definido: coroplético com seletor de métrica e de país**, com modo de confronto direto. Decidido: Reino Unido em sub-regiões separadas; alternância entre contagem bruta e por jogo. Isso **muda a prioridade da Etapa 3**: o trabalho central passa a ser mapear as 83 seleções para polígonos de país, e não geocodificar cidades.
- **08/08/2026** — dois achados novos: (1) a Wikipédia **tem público por partida** (6.810.966 no total em 2026), enquanto o Fjelstul não tem nenhum — o que muda a decisão em aberto sobre público; (2) no dado de 2026, `city_name` **não serve como chave de join** (casa 8 de 16), porque a partida registra o município e a tabela de sedes registra a região metropolitana — `stadium_name` casa 16 de 16.
- **08/08/2026** — **Etapa 3 concluída: modelagem, geocodificação e validação.** `etl/geocode.py` resolveu as 252 sedes no Nominatim (cache versionado, ~5 min uma vez só) e preencheu o `country_name` que faltava em 2026 — a métrica "partidas recebidas" ficou completa e o Canadá entrou como 19º país a receber partida de Copa masculina. `etl/geo.py` baixou o Natural Earth e mapeou as 86 seleções em 88 polígonos. `etl/model.py` gerou as 6 tabelas de `data/processed/`, e `etl/validate.py` declarou o contrato de cada uma em `pandera`. 36 testes passando.
- **08/08/2026** — **o `pandera` achou dois sentinels que nenhuma soma acusaria:** o Fjelstul grava `0–0` no placar de pênaltis de 1.205 partidas sem disputa, e a string `"not applicable"` em `group_name` nas 332 partidas de mata-mata. Os dois viraram nulo de verdade no modelo. É a diferença entre conferir totais e conferir linhas.
- **08/08/2026** — **a validação também expôs uma afirmação errada do próprio plano.** A Etapa 2 dizia que as entidades com `merge_records=0` (URSS, Iugoslávia, Tchecoslováquia…) mantinham registros separados; na prática, só a contagem de títulos as respeita — os registros de partida sempre seguiram o rótulo. Nenhum número de manchete estava errado (nenhuma delas venceu uma Copa), mas a Rússia mostra 53 partidas das quais 22 são dela. Confrontado com a escolha, o projeto **manteve o comportamento — o rótulo manda** —, e a consequência (Alemanha × Alemanha em 1974) passou a ser impressa a cada validação e travada em teste, em vez de ficar escondida.
- **08/08/2026** — dois achados menores da geocodificação: (1) nas 8 sedes inglesas de 1966 o Nominatim devolve `United Kingdom` onde o dataset diz `England` — a mesma fronteira que a escolha por `map_units` resolve do outro lado; (2) o Natural Earth divide a **Bélgica** em três unidades de mapa, exatamente como divide o Reino Unido em quatro — o que obrigou o mapa seleção→polígono a ser um-para-muitos.
- **08/08/2026** — **escopo reduzido à Copa masculina.** O modelo passou de 1.352 para 1.068 partidas, 86 para 83 seleções e 252 para 208 sedes; a coluna `competition`, que agora teria um valor só, saiu das tabelas do modelo, e os JSONs do mapa perderam a dimensão de competição (`head2head` virou `{seleção: {adversário}}`). O dado feminino **não foi apagado**: as 284 partidas de 1991–2019 seguem em `data/raw/` e em `matches_clean.csv`, e as sedes que só receberam Copa feminina seguem geocodificadas em cache. O corte é a constante `COMPETITION` em `etl/model.py` — um lugar só —, e um teste falha se alguém apagar o feminino mais atrás no pipeline.
- **08/08/2026** — **features definidas: só estatística de jogo.** Fecha a pergunta em aberto mais antiga do projeto — público ou capacidade — por **redução de escopo**, sem escolher um lado: os dois ficam de fora. O mapa expõe gols, gols sofridos, saldo, V/E/D, aproveitamento, partidas jogadas, partidas recebidas, títulos, participações e os mesmos números em confronto direto. O motivo é que os dois candidatos exigiriam uma ressalva colada em cada número: público existe em 104 de 1.068 partidas, e capacidade é completa mas varia no tempo (Azteca: 115.000 em 1970, 80.824 em 2026). Nenhuma linha de código mudou — as métricas já eram essas. O que mudou foi o registro: a coluna `attendance` fica em `matches.csv` como fato da fonte, sem alimentar métrica, e a capacidade **nunca** entra no modelo, por decisão e não por esquecimento. O dataset `wcmatches` do Kaggle deixa de ser necessário.
- **08/08/2026** — **Etapa 4 concluída: o mapa existe.** `web/index.html`, `web/map.js` e `web/style.css`, com Leaflet 1.9.4 versionado no repositório em vez de CDN. Nove métricas, seletor de país com modo de confronto direto, alternância total/por partida, slider de faixa de anos e painel lateral. Todos os números documentados no plano se reproduzem na tela: Alemanha 248 gols e Brasil 247 no total, Hungria 2,72 por partida, Brasil 247 gols em 119 partidas com 82–15–22, e Brasil × Suécia 21 gols em 7 jogos. 44 testes passando.
- **08/08/2026** — **a escolha do slider de anos custou a regra "o front-end não agrega nada" — e a troca foi documentada, não escondida.** Filtro por década seria pré-computável; faixa livre não é (276 faixas possíveis). Então a agregação foi para o navegador, com uma contrapartida: `timeline.json` (a tabela longa em forma colunar, 37 KB), uma implementação de referência em Python (`aggregate_timeline`), o `map.js` espelhando-a, e a **página refazendo a faixa completa ao carregar para comparar com o `metrics.json` seleção por seleção** — com aviso na tela se divergir. Um teste em Python trava o lado de lá. É a mesma ideia do `pandera` na Etapa 3: a conferência que pega erro de linha, não só de total.
- **08/08/2026** — **três decisões de cor que o dado impôs.** (1) O **saldo de gols** ganhou rampa divergente (vermelho ↔ cinza ↔ azul) enquanto as outras oito métricas usam a sequencial de um matiz: saldo é a única com lado negativo, e uma rampa sequencial colocaria −20 e +20 nos dois extremos de uma escala sem lado. (2) As classes são por **quantil** — o Brasil tem 247 gols e metade das seleções tem menos de 10, então intervalo igual daria quatro países escuros e o resto branco. (3) **Zero e "sem dado" são cores diferentes**: China, Trinidad e Tobago e o Zaire de 1974 nunca marcaram um gol em Copa, e isso é um fato, não uma ausência.
- **08/08/2026** — **duas melhorias no coroplético: escala contínua e a cor da seleção.** As classes por quantil saíram: a escala virou **contínua**, com raiz quadrada no valor — sem a raiz, uma escala linear amontoaria quase todas as seleções no primeiro décimo da rampa, porque o Brasil tem 247 gols e metade delas tem menos de 10. A raiz abre o pé da distribuição sem inverter nenhuma ordem, e a legenda virou uma barra com os valores marcados em `sqrt(v/máx)`: as marcas se apertam à direita, e essa compressão visível é o aviso de que a escala não é linear. E a rampa passou a ser **a cor da seleção escolhida** — Brasil amarelo, Itália azzurro, Holanda laranja —, gerada em OKLab por `etl/color.py` a partir de `reference/team_colors.csv`. A visão global continua com uma rampa só, de propósito: o olho lê escuridão como quantidade, então dar a cada país a sua cor faria uma Itália azul-escura parecer 'mais' que um Brasil amarelo com número maior. 58 testes.
- **08/08/2026** — **a curadoria das cores encostou num problema que o dado não tinha.** Doze seleções jogam de branco ou preto — Alemanha, Inglaterra, Polônia, Nova Zelândia, Senegal… — e nenhuma das duas serve de matiz: branco não tem croma para sustentar uma rampa, e preto vira um cinza que colide com o cinza de 'sem dado'. A regra ficou: a cor da camisa principal; quando ela é acromática, a cor cromática que identifica a seleção, marcada como `identity` e justificada linha a linha. Pelo mesmo motivo, o passo mais fraco de toda rampa carrega um traço do matiz em vez de ser cinza — senão 'jogou e não marcou' teria a mesma cor de 'nunca jogou'.
- **08/08/2026** — **interface repaginada e a regra das cores ficou mais exigente.** O cromo foi para um cinza-quase-preto azulado com cartões arredondados, controles em pílula, tipografia sem serifa mais pesada e um acento verde-esmeralda vivo — inspirado no [copa2026.goodstart.com.br](https://copa2026.goodstart.com.br/), que resolve o mesmo problema (mapa da Copa) com mapa imersivo e navegação em pílulas. O acento **não** é azul de propósito: azul é a rampa da visão global, e um botão azul ao lado de um mapa azul seria lido como parte da escala.
- **08/08/2026** — **as cores das seleções passaram a ser a camisa da última Copa disputada**, e não uma 'cor do país' genérica. A tabela ganhou a coluna `last_cup`, conferida contra o modelo — que pegou dois erros na primeira execução (Itália joga desde 2014, não 2026; Peru desde 2018). Só nove seleções não jogam desde antes de 1998, e são elas que exigiram pesquisa: Cuba jogou 1938 de vermelho, e as Índias Orientais Neerlandesas jogaram 1938 **de branco** — sem matiz para uma rampa, então essa linha cai na exceção e usa o vermelho da Indonésia moderna, que é o rótulo sob o qual o registro aparece. As rampas também ficaram mais vibrantes: o croma agora pode passar do croma da cor original e é o gamut do sRGB que corta, então cada passo fica tão saturado quanto aquela claridade permite — sem mexer em claridade nem matiz.
- **08/08/2026** — **o mapa virou a página.** O layout deixou de ser um documento com o mapa dentro de um cartão: agora o mapa ocupa a janela inteira e os controles, a legenda e o painel flutuam por cima em vidro fosco, como no [copa2026.goodstart.com.br](https://copa2026.goodstart.com.br/). O detalhe que faz isso funcionar é `pointer-events` — a camada que posiciona os cartões não recebe ponteiro, só os cartões recebem; sem isso o espaço vazio entre eles engoliria o arrasto e metade da tela deixaria de ser mapa. O cabeçalho com título e resumo saiu: o mapa é o título. O `h1` continua na página para leitor de tela, e a atribuição CC BY-SA — que é obrigação de licença — saiu do controle de 10px do Leaflet para um bloco "Fontes e licenças" no cartão da legenda, onde as três fontes aparecem por extenso. Um botão devolve a janela inteira ao mapa, escondendo os painéis.
- **09/08/2026** — **os pontos coloridos das tabelas viraram bandeiras — e o caminho até elas foi mais interessante que o resultado.** A primeira versão usou emoji, que não custa byte nenhum: `iso_a2` saiu do próprio Natural Earth (o mesmo `ISO_A2_EH` que resolve os `-99` de Noruega e Portugal), e as três seleções britânicas com emoji vieram de sequências de tag. Só que **o Windows não tem nenhuma bandeira nas fontes do sistema**: `🇧🇷` vira as letras "BR" e as britânicas viram uma bandeira preta lisa, igual para as três. Uma conferência em canvas media 16,88 px contra 17,42 px de duas letras soltas e confirmava que o navegador não compunha — ou seja, metade dos visitantes (e o dono do projeto) nunca veria bandeira nenhuma.
- **09/08/2026** — **a troca por SVG resolveu dois problemas de uma vez.** O conjunto vendorizado desenha igual em qualquer sistema e **tem a Irlanda do Norte**, que o Unicode nunca criou como emoji e que por isso era a única seleção condenada a ficar sem bandeira. A escolha do conjunto também foi medida: o primeiro candidato pesava 723 KB, com dez brasões (Sérvia sozinha, 177 KB) somando 87% do total para um detalhe invisível a 16 px; o conjunto adotado faz o mesmo trabalho em **146 KB**. Um `onerror` volta ao ponto colorido se algum arquivo faltar, e o ETL falha se algum SVG não existir no disco — porque ícone quebrado não gera erro em lugar nenhum.
- **09/08/2026** — **quatro funcionalidades novas, todas do dado que já existia:** estado na URL (a visão vira link), detalhamento de partidas (o número abre e mostra as linhas que o formam), comparação de duas seleções (funciona inclusive para quem nunca se enfrentou) e camada de sedes (devolve as 252 sedes geocodificadas na Etapa 3 que o mapa nunca usou). A referência de desenho foi o SofaScore, cuja página de seleção é construída em cima de uma lista de partidas com marcador V/E/D por linha.
- **09/08/2026** — **dois erros silenciosos apareceram durante a construção, e os dois viraram teste.** (1) A camada de sedes saía ordenada por número de partidas, enquanto o detalhamento indexa sedes na ordem do CSV — as duas listas continuavam do mesmo tamanho, então nada acusava, mas a contagem de um estádio seria plotada na coordenada de outro. (2) O `badge()` escapava aspas simples e não duplas no `onerror` da bandeira, o que encerrava o atributo no meio e vazava `'">` como texto ao lado do nome da seleção — bug que já estava no ar desde o commit das bandeiras.
