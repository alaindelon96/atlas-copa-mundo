# World Cup Atlas — project plan

> Living document. Update as the project evolves. Last revised: 2026-08-07.
>
> **Current status:** Stage 1 (Extract) complete for the primary source. Stage 2 (Clean) is next.
> Portuguese version: [`plano-atlas-copa-mundo.md`](plano-atlas-copa-mundo.md) · Visual roadmap: [`docs/roadmap.html`](docs/roadmap.html)

## 1. Overview

**Goal:** build an interactive web-published map showing the history of the FIFA World Cup (1930–2026), as a data-analysis portfolio piece covering the full ETL cycle — from extraction (including web scraping) through to publication.

**Why this works as a portfolio piece:** it exercises nearly every skill a technical recruiter looks for — ingesting data from multiple sources (API, CSV, scraping), reconciling messy and inconsistent data across almost 100 years, relational modelling, and a final visual product that anyone can understand without reading code.

### Technology stack (consolidated view)

| Layer | Primary tool | Alternative | Why | Status |
|---|---|---|---|---|
| Extract — ready-made datasets | `requests`, Kaggle API | — | Direct CSV download | ✅ implemented (`requests`) |
| Extract — web scraping | `pandas.read_html` + `BeautifulSoup4` | `Scrapy` (to showcase spider architecture) | Fill the 2026 World Cup gap | ⏳ not started |
| Cleaning | `pandas`, `rapidfuzz` | `numpy` | Reconcile national-team names, handle nulls | ⏳ next step |
| Data validation | `pandera` | `great_expectations` | Guarantee quality before modelling (strong portfolio differentiator) | ⏳ installed, not written |
| Modelling | `pandas`, schema documented as a Mermaid ERD | `dbdiagram.io` | Formalise the relational schema | ⏳ not started |
| Geocoding | `geopy` (Nominatim) | Manual venue CSV | **See note below — manual is no longer viable** | ⏳ not started |
| Visualisation | Leaflet.js | Mapbox GL JS | Lightweight, free, no API key | ✅ **decided: Leaflet** |
| Publication | GitHub Pages | Netlify/Vercel | Free, integrated with the repository | ⏳ not started |
| Automation/CI | GitHub Actions | — | Run the ETL pipeline automatically (optional, but adds portfolio value) | ⏳ deferred to v2 |
| Testing | `pytest` | — | Test cleaning/transformation functions | ⏳ installed, not written |

**Verified environment:** Python 3.11.9, git 2.55.0, Windows 11. All dependencies installed and pinned in `requirements.txt`.

## 2. Data sources

| Source | Coverage | Format | Licence | Note |
|---|---|---|---|---|
| [Fjelstul World Cup Database](https://github.com/jfjelstul/worldcup) | 1930–2022 (men) + 1991–2019 (women) | CSV / R package | CC-BY-SA 4.0 — redistributable with attribution to the author; derivative work must keep the same licence | ✅ **DOWNLOADED.** Most complete: matches, venues, groups, standings, awards. Project backbone. |
| [FIFA World Cup All Goals 1930-2022 (Kaggle, jahaidulislam)](https://www.kaggle.com/datasets/jahaidulislam/fifa-world-cup-all-goals-1930-2022-dataset) | 1930–2022 | CSV | CC0 1.0 — public domain, no restrictions | ⚠️ **Probably redundant** — Fjelstul already carries 3,637 goals with scorer, minute, penalty and own-goal flags. |
| [FIFA World Cup 1930-2022 All Match Dataset (Kaggle, jahaidulislam)](https://www.kaggle.com/datasets/jahaidulislam/fifa-world-cup-1930-2022-all-match-dataset) | 1930–2022 | CSV | Unconfirmed — check the licence badge on the Kaggle page before use | Summary scores per match. |
| [wcmatches (Kaggle, evangower)](https://www.kaggle.com/datasets/evangower/fifa-world-cup) | 1930–2018 | CSV | CC0 — public domain | 🎯 **Now important:** it is the candidate source for **attendance**, which Fjelstul lacks (see 2.1). |
| Wikipedia — "2026 FIFA World Cup" and related pages | 2026 | HTML (via scraping) | CC BY-SA 4.0 — attribution required | The only way to cover 2026, via scraping (see section 4). |

**Licences — practical summary:** the CC0 datasets can be used and republished freely. Fjelstul and Wikipedia (both CC-BY-SA 4.0) require attribution to the author/source, and the processed data published in your repository must carry the same licence — this is already recorded in `data/raw/metadata.json` and needs to reach the README.

### 2.1 What exploring the data revealed (2026-08-07)

After downloading and inspecting the CSVs, four things change the original plan:

**1. `tournament_id` does NOT separate men's from women's — this is a trap.**
All 30 editions use the same `WC-<year>` pattern (`WC-1991` is the women's tournament, `WC-1994` the men's). Only the `tournament_name` column distinguishes them (`"1991 FIFA Women's World Cup"`). If you group by `tournament_id` assuming it is men-only, you will silently blend the two competitions. **Decision:** create an explicit `competition` column (`mens`/`womens`) during cleaning, derived from `tournament_name`.

| | Editions | Period | Matches |
|---|---|---|---|
| Men's | 22 | 1930–2022 | 964 |
| Women's | 8 | 1991–2019 | 284 |
| **Total** | **30** | **1930–2022** | **1,248** |

There is no year overlap between the two, and `tournament_id` is unique — which is exactly why the mistake goes unnoticed.

**2. There is no attendance data in Fjelstul.** The `matches.csv` table has 36 columns and none is attendance. The original plan promised "total attendance" in the map popups. **Two ways out:** (a) source it from Kaggle's `wcmatches`, accepting that it only covers through 2018; (b) drop attendance from v1 scope and use **stadium capacity**, which Fjelstul has complete (0 nulls across 240 stadiums). Decision pending.

**3. Geocoding cannot be manual.** The plan said "few cities — could be manual". It is **240 stadiums across 202 cities** (193 stadiums / 165 cities if we stay men-only). Doing that by hand is not realistic. **Decision:** `geopy`/Nominatim with an on-disk cache, respecting the 1 request/second limit (~3 minutes of runtime, once).

**4. The data is far cleaner than expected.** Zero nulls in `match_date`, `match_time`, `stadium_id`, `city_name` and the scorelines. Zero nulls in `stadium_capacity`. That is great news, but it **changes the portfolio narrative**: the cleaning work will not be "fix broken data", it will be **historical reconciliation** — a more interesting story to tell.

**The real cleaning problem (and it is a good one):** national-team names that changed over almost 100 years, all present in the dataset:

| Historic name | Current entity | Kind of change |
|---|---|---|
| West Germany / East Germany | Germany | Reunification (1990) |
| Soviet Union | Russia | Dissolution (1991) |
| Yugoslavia → Serbia and Montenegro → Serbia | Serbia | Staged dissolution |
| Czechoslovakia | Czech Republic | Split (1993) |
| Dutch East Indies | Indonesia | Independence (1949) |
| Zaire | DR Congo | Renaming (1997) |

This is precisely where `rapidfuzz` **cannot** solve it alone: "Zaire" and "DR Congo" share no textual similarity. You will need an **explicit succession map** (a curated dictionary, versioned in the repo) plus `rapidfuzz` for the minor spelling variants. Documenting that distinction is an excellent README point.

## 3. ETL methodology

### Stage 1 — Extract ✅ COMPLETE (primary source)

- [x] Create `etl/extract.py`
- [x] Download Fjelstul CSVs (via GitHub raw) — 16 tables, ~1.9 MB
- [ ] Download the complementary Kaggle dataset — **only if the attendance decision requires it** (see 2.1)
- [x] Save everything to `data/raw/` unaltered (preserve the original data)
- [x] Record timestamp and source of every download in a `metadata.json`
- [x] Run the complementary 2026 World Cup scraping (see section 4) — 104 matches, 16 venues

**What was built:**

| File | Role |
|---|---|
| `etl/paths.py` | All paths resolved from the repo root — no fragile relative paths scattered across scripts |
| `etl/provenance.py` | Provenance ledger: SHA-256, UTC timestamp, URL, licence and attribution for every downloaded file |
| `etl/extract.py` | Downloads the 16 CSVs, with atomic writes, inter-request delay and an identifiable user-agent |

**Implementation decisions (and the reasoning — good README material):**

- **Atomic writes:** each file is written as `.part` and only then renamed. If a download drops midway, you are not left with a truncated CSV in `data/raw/` that looks valid.
- **SHA-256 on everything:** lets you run `python -m etl.extract --check` to discover whether the source changed since the last download, without overwriting. It is the natural hook for automating with GitHub Actions later.
- **`data/raw/` is immutable:** nothing there is hand-edited, and `.gitignore` does not version the raw data (it is reproducible with one command) — but it **does version `metadata.json`**, which is the audit record.
- **Curated subset:** 16 of Fjelstul's 29 tables were downloaded. The 13 left out (`player_appearances`, `squads`, `substitutions`, `bookings`, refereeing) total ~9 MB of individual-event data, outside the scope of a map. Adding one back is a one-line change.

**How to run:**

```bash
python -m etl.extract
```

```bash
python -m etl.extract --check
```

### Stage 2 — Clean ⏳ NEXT STEP

- [ ] Create the `competition` column (`mens`/`womens`) from `tournament_name` — **do this first** (see 2.1)
- [ ] Standardise team names via an explicit succession map + `rapidfuzz` for spelling variants
- [ ] Handle null values — **much smaller scope than expected**, the data arrived clean
- [ ] Remove duplicates across sources (including the scraped 2026 data)
- [ ] Validate data types (dates, goal counts, IDs)
- [ ] Join the sources and resolve information conflicts
- [ ] Save the result to `data/processed/matches_clean.csv`

**Tools:** `pandas` for the transformations; `rapidfuzz` (fuzzy string matching) for spelling variants. **Careful:** fuzzy matching does not solve historical succession (Zaire → DR Congo have no textual similarity) — the curated map is mandatory.

**Revised watch-out:** this stage remains the most delicate, but for a different reason than expected — it is not data dirtiness, it is **editorial judgement**. You will have to choose and defend: does Germany have 4 titles, or does West Germany have 3 and Germany 1? Both answers are defensible; what is not defensible is failing to document which one you chose.

### Stage 3 — Model

Proposed schema (relational tabular form):

- `tournaments`: year, host (country/city), champion, runner-up, number of teams, **`competition`**
- `matches`: tournament, stage, date, home, away, score, venue, ~~attendance~~ (see 2.1)
- `teams`: current name, historic names (to reconcile changes)
- `venues`: city, country, latitude, longitude (for the map), capacity

- [ ] Draw the final schema (Mermaid ERD diagram)
- [ ] Validate the schema with `pandera` (type rules, allowed values, acceptable nulls)
- [ ] Geocode the 202 host cities via `geopy`/Nominatim **with an on-disk cache** (see 2.1)
- [ ] Generate derived metrics: total goals per tournament, average capacity, titles per team
- [ ] Export in a front-end-consumable format (GeoJSON for the map + JSON for tables/charts)

**Tools:** `pandas` for aggregations; `geopy` for geocoding; `pandera` for declarative schema validation.

### Stage 4 — Visualise

- [x] ~~Choose a map library~~ → **Leaflet.js decided** (lightweight, free, no API key)
- [ ] Markers at each World Cup's venues, with popups (champion, top scorer, capacity)
- [ ] Optional layer: historic trajectory of championship-winning teams
- [ ] Filter by decade/era
- [ ] Men's/women's toggle (enabled by the `competition` column)
- [ ] Side panel or section with overall statistics (e.g. champions ranking)

**Tools:** Leaflet.js (vanilla JS) for the map; optionally `folium` in Python for rapid prototyping.

### Stage 5 — Publish

- [ ] Structure as a static site (`web/index.html` + assets)
- [ ] Test locally
- [ ] Publish via GitHub Pages
- [ ] (Optional) configure GitHub Actions to run the ETL pipeline automatically
- [x] Write the repository README explaining the ETL process (good for the portfolio)
- [x] **Include CC-BY-SA attribution to Fjelstul** (a licence obligation, not optional) — Wikipedia attribution pending until the scraper exists

**Licensing (done 2026-08-07):** the repository carries **two** licences, because the code and the data have different origins. Code under MIT (`LICENSE`); data under CC-BY-SA 4.0 (`LICENSE-DATA.md`), because the source's ShareAlike term requires it. `LICENSE-DATA.md` also maintains the **modification record** the licence demands — currently: no alteration to the raw data, only a selection of 16 of the 29 tables.

## 4. Web scraping — filling the 2026 World Cup gap

No ready-made source covers the 2026 tournament. The best way to fill the gap is to scrape directly from Wikipedia, which maintains structured tables of match results, top scorers and venues.

> ✅ **VERIFIED on 2026-08-08.** The earlier note was correct: the 2026 World Cup ended on 2026-07-19, with Spain beating Argentina 1–0 at MetLife Stadium in front of 80,663 people (Spain's 2nd title). Third place: England; fourth: France. Top scorer: Kylian Mbappé (10 goals). This now comes from the scraped data, not the note.

**Scraping result (14 pages, revisions recorded):**

| | |
|---|---|
| Matches | 104 (72 group + 32 knockout) |
| Goals | 308 (2.96 per match) |
| Total attendance | 6,810,966 (65,490 average) |
| Venues | 16 stadiums, 3 countries |
| Teams | 48 |

All three of the parser's self-checks match the article's own declared totals exactly — matches, goals and venues. The parser **fails** if they disagree.

**Target source:** Wikipedia pages on the 2026 World Cup (e.g. "2026 FIFA World Cup", "2026 FIFA World Cup final", per-group/stage pages). Content under CC BY-SA 4.0 — attribution required.

**Scope note:** 2026 is the first tournament with **48 teams and 3 host countries** (USA, Canada, Mexico). That breaks two schema assumptions: `host_country` as a single value, and the set of stages (there is one more round than in 2022). Anticipating this now avoids rework.

**Recommended tools, by complexity level:**

| Tool | When to use | Portfolio benefit |
|---|---|---|
| `pandas.read_html()` | Simple, well-formed HTML tables (which is most Wikipedia results tables) | Fast and direct — shows pragmatism |
| `requests` + `BeautifulSoup4` | When you need data not in a clean `<table>`, or must combine prose with a table | Shows command of manual HTML parsing |
| `Scrapy` | If you want a reusable spider with built-in rate limiting and caching | Shows more robust architecture |

**Practical recommendation:** start with `pandas.read_html()` to check quickly whether the tables come out clean; if you need more control, move up to `BeautifulSoup4`. `Scrapy` is overkill for a few dozen pages.

**Best practices to apply (and highlight in the README):**
- [ ] Respect the target domain's `robots.txt`
- [ ] Use an identifiable user-agent and a delay between requests
- [ ] Cache downloaded HTML locally in `data/raw/scraped/`, to avoid re-scraping on every run
- [ ] Cleanly separate "scraping" (fetching raw HTML) from "parsing" (extracting the data) — different responsibilities, and it makes each part testable in isolation
- [ ] Credit Wikipedia in the README, as the CC BY-SA licence requires

## 5. Repository structure

Inspired by the [Cookiecutter Data Science](https://cookiecutter-data-science.drivendata.org/) convention. ✅ = already on disk.

```
atlas-copa-mundo/
├── data/
│   ├── raw/              ✅ original data, never hand-edited
│   │   ├── fjelstul/     ✅ 16 CSVs downloaded
│   │   ├── kaggle/       ✅ (empty — pending the attendance decision)
│   │   ├── scraped/      ✅ (empty — raw Wikipedia HTML)
│   │   └── metadata.json ✅ provenance ledger (versioned in git)
│   ├── interim/          ✅ intermediate data (partial cleaning)
│   └── processed/        ✅ final data, ready for the front-end
├── etl/
│   ├── paths.py          ✅ centralised paths
│   ├── provenance.py     ✅ hash + timestamp + licence
│   ├── extract.py        ✅ ready-made dataset download
│   ├── scrape_2026.py    ⏳ next
│   ├── transform.py      ⏳
│   ├── validate.py       ⏳ pandera rules
│   └── load.py           ⏳
├── notebooks/            ✅
├── tests/                ✅
├── web/                  ✅
│   ├── index.html        ⏳
│   ├── map.js            ⏳
│   └── data/             ✅
├── docs/
│   └── roadmap.html      ✅ visual roadmap
├── .github/workflows/    ✅ (empty — GitHub Actions deferred)
├── plano-atlas-copa-mundo.md    ✅ Portuguese plan
├── plan-atlas-world-cup.md      ✅ this document
├── .gitignore            ✅
├── README.md             ⏳
└── requirements.txt      ✅ pinned, tested versions
```

## 6. Suggested timeline (adjustable)

| Week | Focus | Status |
|---|---|---|
| 1 | Extract ready-made datasets + scrape the 2026 World Cup | 🔵 in progress — extraction done, scraping pending |
| 2 | Cleaning and name reconciliation | ⬜ |
| 3 | Modelling, validation and geocoding | ⬜ |
| 4 | Visualisation (working map) | ⬜ |
| 5 | Visual polish + publication + README | ⬜ |

## 7. Decisions

### Resolved

| Decision | Choice | Why |
|---|---|---|
| Leaflet or Mapbox | **Leaflet** | No API key needed — the map keeps working for anyone who clones the repo, with no sign-up. For markers + popups, Mapbox's extra features do not pay for themselves. |
| Women's dataset in v1 | **Always extract, expose behind a filter** | It ships in the same files, at zero cost. Splitting on a `competition` column and letting the front-end filter is cheaper than discarding now and reprocessing later. |
| GitHub Actions | **Deferred to v2** | `extract.py --check` already leaves the hook in place. Automating before the pipeline is complete is premature optimisation. |
| How many Fjelstul tables to download | **16 of 29** | The remaining 13 are individual-event data (~9 MB), outside a map's scope. Easy to reverse. |

### Open

- [ ] **Attendance:** source it from Kaggle's `wcmatches` (only through 2018), or swap it for stadium capacity in v1? — *blocks the map popup content*
- [ ] **Team succession:** does West Germany count as Germany in the title count? Does the USSR count as Russia? — *blocks Stage 2; this is an editorial call, not a technical one*
- [ ] Confirm the licence of the "FIFA World Cup 1930-2022 All Match Dataset" (Kaggle) — *only matters if it is actually used*
- [ ] Decide between `pandas.read_html`, `BeautifulSoup4` and `Scrapy` for the 2026 scraping (recommendation: start with `read_html`)
- [x] ~~Create the remote repository on GitHub and `git push`~~ → published at https://github.com/alaindelon96/atlas-copa-mundo

## 8. Progress notes

- **2026-07-27** — initial plan created.
- **2026-07-27** — noted that the 2026 World Cup had finished (Spain champions); document restructured with the technology stack and a web-scraping stage. *(See the caveat in section 4: this fact has not yet been verified by any source inside the project.)*
- **2026-08-07** — environment verified (Python 3.11.9, git 2.55.0); dependencies installed and pinned.
- **2026-08-07** — repository structure created; `.gitignore` and `requirements.txt` written.
- **2026-08-07** — **Stage 1 complete for the primary source:** `etl/paths.py`, `etl/provenance.py` and `etl/extract.py` implemented; 16 Fjelstul CSVs downloaded (~1.9 MB) with SHA-256 provenance in `data/raw/metadata.json`.
- **2026-08-07** — data exploration surfaced four points that change the plan: (1) `tournament_id` does not separate men's from women's; (2) there is no attendance data; (3) there are 202 cities to geocode, not "a few"; (4) the data is clean — the real challenge is historical name reconciliation, not dirtiness. Details in section 2.1.
- **2026-08-08** — repository published at https://github.com/alaindelon96/atlas-copa-mundo; README, `LICENSE` (MIT, code) and `LICENSE-DATA.md` (CC-BY-SA 4.0, data) written.
- **2026-08-08** — **Stage 1b complete: 2026 World Cup scraped.** Wikipedia's `robots.txt` verified (articles under `/wiki/` are permitted; `/w/` and `/api/` are not). `etl/scrape_2026.py` fetched 14 pages recording each one's `revision_id`; `etl/parse_2026.py` extracted 104 matches, 16 venues and the tournament record, checking everything against the article's own totals.
- **2026-08-08** — two new findings: (1) Wikipedia **does carry per-match attendance** (6,810,966 total in 2026) where Fjelstul carries none — which reshapes the open attendance decision; (2) in the 2026 data, `city_name` is **not a usable join key** (matches 8 of 16), because match records give the municipality and the venues table gives the metro area — `stadium_name` matches 16 of 16.
