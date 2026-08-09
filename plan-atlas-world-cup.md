# World Cup Atlas — project plan

> Living document. Update as the project evolves. Last revised: 2026-08-08.
>
> **Current status:** Stages 1 to 4 complete — extract, scrape, clean, model, geocode, validate and the map. Stage 5 (Publish) is next: shipping it to GitHub Pages.
>
> **Scope:** the men's World Cup — 23 editions, 1,068 matches, 1930–2026. The women's tournament is extracted and cleaned, but excluded from the model and the map (see Stage 3).
>
> Model schema: [`docs/schema.md`](docs/schema.md)
> Portuguese version: [`plano-atlas-copa-mundo.md`](plano-atlas-copa-mundo.md) · Visual roadmap: [`docs/roadmap.html`](docs/roadmap.html)

## 1. Overview

**Goal:** build an interactive web-published map showing the history of the FIFA World Cup (1930–2026), as a data-analysis portfolio piece covering the full ETL cycle — from extraction (including web scraping) through to publication.

**Why this works as a portfolio piece:** it exercises nearly every skill a technical recruiter looks for — ingesting data from multiple sources (API, CSV, scraping), reconciling messy and inconsistent data across almost 100 years, relational modelling, and a final visual product that anyone can understand without reading code.

### Technology stack (consolidated view)

| Layer | Primary tool | Alternative | Why | Status |
|---|---|---|---|---|
| Extract — ready-made datasets | `requests`, Kaggle API | — | Direct CSV download | ✅ implemented (`requests`) |
| Extract — web scraping | `requests` + `BeautifulSoup4` | `Scrapy` (to showcase spider architecture) | Fill the 2026 World Cup gap | ✅ implemented (14 pages) |
| Cleaning | `pandas`, `rapidfuzz` | `numpy` | Reconcile national-team names, handle nulls | ✅ implemented (`etl/transform.py`) |
| Data validation | `pandera` | `great_expectations` | Guarantee quality before modelling (strong portfolio differentiator) | ✅ implemented (`etl/validate.py`) |
| Modelling | `pandas`, schema documented as a Mermaid ERD | `dbdiagram.io` | Formalise the relational schema | ✅ implemented (6 tables, [`docs/schema.md`](docs/schema.md)) |
| Geocoding | `geopy` (Nominatim) | Manual venue CSV | **See note below — manual is no longer viable** | ✅ implemented (252 venues, versioned cache) |
| Visualisation | Leaflet.js | Mapbox GL JS | Lightweight, free, no API key | ✅ implemented (`web/map.js`, 9 metrics) |
| Publication | GitHub Pages | Netlify/Vercel | Free, integrated with the repository | ⏳ not started |
| Automation/CI | GitHub Actions | — | Run the ETL pipeline automatically (optional, but adds portfolio value) | ⏳ deferred to v2 |
| Testing | `pytest` | — | Test cleaning/transformation functions | ✅ 73 tests, all offline |

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
- [x] ~~Download the complementary Kaggle dataset~~ → **it will not be downloaded.** It existed only for attendance, which is now out of scope (see section 7).
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

### Stage 2 — Clean ✅ COMPLETE

- [x] Create the `competition` column (`mens`/`womens`) from `tournament_name`
- [x] Standardise team names via an explicit succession map + `rapidfuzz` to flag candidates
- [x] Handle null values — **much smaller scope than expected**, the data arrived clean
- [x] Remove duplicates across sources — solved at the source, by giving each page a fixed role
- [x] Normalise stage names (Fjelstul had both `quarter-final` and `quarter-finals`)
- [x] Join the sources and resolve information conflicts
- [x] Save the result to `data/processed/matches_clean.csv` — 1,352 matches, 1930–2026
- [x] Write tests (`tests/test_transform.py` — 14 tests, all offline)

**The editorial decision, taken 2026-08-08:** **West Germany counts as Germany.** Germany therefore has **4 titles**, which is FIFA's official count.

It was the **only** succession question that changes a headline number: the USSR, Yugoslavia, Czechoslovakia, East Germany and Zaire never won a World Cup. How they are treated affects appearance counts and map labels, but no title.

**Three ideas carry this stage:**

1. **Label and record are different questions.** `reference/team_succession.csv` has two separate columns: `display_name` (how the team is shown today) and `merge_records` (whether its history is credited to the successor). West Germany gets both; the USSR gets only the first.

   > ⚠️ **Corrected in Stage 3.** This section claimed the USSR "keeps its own record". `pandera` validation showed otherwise: `apply_succession` applies `display_name` to everyone, so **match** records always followed the label — only the **title** count respects `merge_records`. Since no entity with `merge_records=0` ever won a World Cup, no headline number was wrong; the description was. Presented with the choice on 2026-08-08, the project **reaffirmed the behaviour**: the label wins. See Stage 3 and [`docs/schema.md`](docs/schema.md).

2. **Fuzzy matching suggests; it never decides.** `rapidfuzz` only reports 2026 names with no historical counterpart, for a human to classify. Result: four genuine debutants (Cape Verde, Curaçao, Jordan, Uzbekistan) — and **DR Congo is absent from that list**, because the curated map already resolved it to Zaire, of 1974. `fuzz.WRatio("Zaire", "DR Congo")` scores under 50.

3. **Champions do not come from finals.** The 1950 World Cup had **no final** — it was decided by a final round-robin group. Counting champions by filtering `stage == "final"` returns 22 titles for 23 editions and raises no error at all. So champions come from `tournament_standings.csv`, and the pipeline asserts that titles sum to the number of editions.

**Tools:** `pandas` for the transformations; `rapidfuzz` (fuzzy string matching) for spelling variants. **Careful:** fuzzy matching does not solve historical succession (Zaire → DR Congo have no textual similarity) — the curated map is mandatory.

**Revised watch-out:** this stage remains the most delicate, but for a different reason than expected — it is not data dirtiness, it is **editorial judgement**. You will have to choose and defend: does Germany have 4 titles, or does West Germany have 3 and Germany 1? Both answers are defensible; what is not defensible is failing to document which one you chose.

### Stage 3 — Model and geocoding ✅ DONE

> ⚠️ **The 2026-08-08 decision on the map design (see Stage 4) changed this stage's priority.** The map is a **choropleth** — it shades whole countries — not a marker map. A choropleth needs **country polygons**, not point coordinates. Geocoding cities is no longer the central job; it dropped to secondary.

- [x] **Build `reference/team_country.csv`: teams → a shape on the world map** — this stage's new central problem
- [x] Fetch a country GeoJSON (Natural Earth), including the **UK subunits**
- [x] Fill `country_name` for the 104 matches of 2026 — it **unblocked the "matches received" metric**
- [x] Draw the final schema (Mermaid ERD diagram) — [`docs/schema.md`](docs/schema.md)
- [x] Validate the schema with `pandera` (type rules, allowed values, acceptable nulls)
- [x] Build the long `(match, team)` table — one row per team per match, the basis of every metric
- [x] Build the head-to-head matrix (team × opponent) for the selected-country mode
- [x] Export GeoJSON for the map + JSON for the panels
- [x] Geocode the venues via `geopy`/Nominatim with a cache — **all 252, not just 2026's**

**What was built:**

| File | Role |
|---|---|
| `etl/geocode.py` | 252 venues → coordinate and country, via Nominatim, with a versioned cache |
| `etl/geo.py` | Natural Earth GeoJSON → `reference/team_country.csv` + `web/data/countries.geojson` |
| `etl/model.py` | The 6 model tables in `data/processed/` |
| `etl/validate.py` | Each table's contract, in `pandera`, checked against what is on disk |
| `docs/schema.md` | The Mermaid ERD and the reason behind every schema decision |

**Model:** 6 tables — `tournaments` (23), `tournament_hosts` (26), `teams` (83), `venues` (208), `matches` (1,068), `team_matches` (2,136).

**Scope — decided 2026-08-08: the men's World Cup only.** The women's tournament is *extracted and cleaned, but not modelled*, and that distinction is the point: `data/raw/` and `data/processed/matches_clean.csv` still carry the 284 matches of 1991–2019 and the `competition` column that tags them; what drops out is the product — model, metrics and map. The cut happens in **one place**, the `COMPETITION` constant in `etl/model.py`, and everything downstream inherits it. That is why the model tables carry no `competition` column: it would hold a single value across 1,068 rows, and a constant column tells you nothing while implying a variation that is not there. Re-adding it later means changing that constant and putting the column back; the venues that only ever hosted women's matches are already geocoded and cached, so nothing has to be re-derived. A test in `tests/test_model.py` fails if anyone strips the women's rows further upstream, so the option stays open by construction rather than by memory.

**Four things the data forced (details in [`docs/schema.md`](docs/schema.md)):**

1. **`map_units`, not `countries`.** Natural Earth publishes two divisions of the world. Only `admin_0_map_units` separates England, Scotland, Wales and Northern Ireland — the split football uses, and the one this project decided to keep. The price: the same division splits **Belgium** into Flanders, Wallonia and Brussels, so the team→polygon map is **one-to-many** (88 polygons for 86 teams). The three Belgian regions get the same colour and the seam does not show. Hence the column is `gu_a3`, not `iso_a3`: `ENG` and `SCT` are not ISO country codes.

2. **Host country became a table.** The source keeps the host in a single column and improvises when there is more than one — 2002 becomes `"Korea, Japan"` (with a comma, and "Korea" is a name that appears nowhere else in the dataset) and 2026 becomes `"Canada Mexico United States"` (no separator at all). Two ad-hoc encodings of the same one-to-many. In the model, hosts are **derived from the venues where matches actually took place**; the declared string became a cross-check.

3. **`pandera` paid for itself in two lines.** The checks each script already ran verify **totals** ("do the goals add up?"), and are therefore blind to row-level error. Declarative validation found two sentinels no sum would catch: Fjelstul writes `0–0` as the penalty score of **1,205 matches with no shootout** (0 is a valid score), and the literal string `"not applicable"` in `group_name` for the **332 knockout matches** — a `groupby` on group would happily return a "group" called `not applicable`. Both became real nulls.

4. **Geocoding found what the dataset already said.** For the 8 English venues of 1966, Nominatim returns `United Kingdom` where the dataset says `England` — the same border the `map_units` choice resolves from the other side. Where the dataset has a country it wins; Nominatim is only a cross-check. Where it had none (2026), Nominatim filled it in.

**The editorial decision reaffirmed on 2026-08-08: the label wins.** Whoever is labelled Germany counts as Germany. The consequence shows up once in 1,352 matches, and the model exposes it rather than hiding it: **M-1974-20, East Germany 1–0 West Germany**, becomes `Germany × Germany`. Germany books one win and one loss, one goal scored and one conceded — every total still balances and no title count changes. `etl.validate` prints the case on every run and `tests/test_model.py` locks it, so the choice stays visible and nobody "fixes" it without realising they are touching an editorial decision.

**Tools:** `pandas` for aggregations; `pandera` for declarative validation; `geopy`/Nominatim for the venues.

**How to run:**

```bash
python -m etl.geocode --offline && python -m etl.geo
```

```bash
python -m etl.model && python -m etl.validate && python -m etl.metrics
```

`--offline` uses the cache versioned at `data/interim/geocode_cache.json` and never touches the network. Without it, that is ~5 minutes of requests to Nominatim at 1 per second — the cache is versioned out of courtesy to a free public service, the same reasoning as `metadata.json`.

### Stage 4 — Visualise

**Design settled 2026-08-08: a choropleth world map with two selectors.**

Not a map of venue markers — a map that **shades countries** by a chosen metric. Two controls:

| Control | Options |
|---|---|
| **Metric** | Goals · Wins/Losses · Matches received · Matches played · Titles · Participations |
| **Country** | None (global view) or one specific team |

**The selected-country mode is the project's strongest idea.** Choosing *Brazil + Goals* **recolours the map by head-to-head**: every country is shaded by how many goals Brazil scored against it. Sweden burns brightest (21 goals in 7 matches), and the panel summarises Brazil's 247 goals in 119 matches, 23 participations, 82W–15D–22L.

- [x] ~~Choose a map library~~ → **Leaflet.js decided** (lightweight, free, no API key)
- [x] ~~Map design~~ → **choropleth with a metric selector and a country selector**
- [x] ~~United Kingdom~~ → **separate subunits.** England, Scotland, Wales and Northern Ireland are four distinct teams and stay four distinct regions. Merging them would invent a "UK national team" that has never existed, credited with 168 goals nobody scored.
- [x] ~~Raw counts or per-match~~ → **both, behind a toggle.** Raw counts alone just reproduce "who qualified most often": Germany has 248 goals and Brazil 247 because both played ~120 matches. Per match, **Hungary leads at 2.72** and vanishes from the raw top 10. Switching between the two readings *is* the insight.
- [x] Single-hue sequential scale for the metric (never a rainbow) — **continuous**, in the selected team's colour
- [x] A 10-match floor in per-match mode, so a 3-match team can't outrank Brazil
- [x] ~~Filter by decade/era~~ → **a year-range slider** across the 23 editions
- [x] Side panel with the selected team's summary and its head-to-head table

**What was built:**

| File | Role |
|---|---|
| `web/index.html` | The shell: the map filling the window, with the panels floating over it |
| `web/map.js` | Aggregates, classifies and paints — and self-checks against `metrics.json` |
| `web/style.css` | Cartographic chrome inherited from `panorama.html` + the two data ramps |
| `web/vendor/leaflet.*` | Leaflet 1.9.4 vendored into the repo, not loaded from a CDN |
| `web/vendor/flags/` | 83 flag SVGs (circle-flags, MIT), one per team |
| `web/data/timeline.json` | The long table in compact form (37 KB) — what the slider aggregates |
| `etl/color.py` | Shirt colour → sequential ramp, in OKLab |
| `reference/team_colors.csv` | The curated colour of each of the 83 teams, with the exceptions reasoned |
| `web/data/colors.json` | The 83 ramps, ready, in both modes |

**Four decisions from this stage:**

1. **The time filter is a range slider, and it broke the "the front-end aggregates nothing" rule.** A decade selector would be pre-computable; a free range is not — 23 editions give 276 possible ranges. So `timeline.json` carries the long table in columnar form (2,136 rows, 37 KB — smaller than `head2head.json`, because the names became indices) and the JavaScript sums.

   The rule was not abandoned, it **became a check**: `etl.metrics.aggregate_timeline` is the reference implementation in Python, `map.js` mirrors it, and the page **re-runs the full range on load and compares it to `metrics.json`, team by team**. On a divergence a red warning appears at the top saying the numbers cannot be trusted. The duplicated logic exists — what does not exist is it being silent. A Python test locks the other side.

2. **The ramp is the selected team's colour.** Pick Brazil and the map turns yellow; Italy, azzurro; the Netherlands, orange. The colours are curated by hand in [`reference/team_colors.csv`](reference/team_colors.csv), on the same logic as `team_succession.csv`: it is an editorial decision, so it is versioned with its reasoning.

   The rule is **the home shirt of the last World Cup that team played** — not "the country's colour", nor the current kit. For 48 of the 83 that last cup is 2026, so the distinction rarely bites; it bites for the **nine** who have not played since before 1998 (Cuba 1938, the Dutch East Indies 1938, Israel 1970, Kuwait and El Salvador 1982, Hungary and Northern Ireland 1986, the UAE 1990, Bolivia 1994). The `last_cup` column is **checked against the model** on every run: if a team plays again, the row goes stale and the pipeline stops. That check paid for itself immediately — it caught two curation errors on the first run, Italy (last played 2014, not 2026) and Peru (2018).

   The exception is still a white or black shirt, which has no hue to carry a ramp and whose grey would collide with the "no data" grey: in those **16 cases** (Germany, England, Poland, Peru, New Zealand…) the chromatic colour that identifies the side steps in, marked `identity` and reasoned row by row.

   **The global view does not do this**, and the difference matters: with no country selected there is one ramp. Giving every country its own colour would make the map handsome and unreadable, because the eye reads darkness as quantity — a dark-blue Italy would look like "more" than a bright-yellow Brazil with a bigger number.

3. **A shirt colour is not a ramp — `etl/color.py` turns one into the other.** The work happens in **OKLab/OKLCH**, a perceptually uniform space: interpolating from Brazil's `#FFDF00` to white in sRGB detours through dirty beige. Lightness walks the mode's band linearly (it is what carries the data, and what keeps the ramp readable for someone who cannot separate hues); chroma rises with it, never past the team colour's own. When a step will not fit in sRGB — dark saturated yellow does not exist — what gives is the **chroma**, never the RGB channels: clamping a channel moves the hue, and the yellow would arrive orange at the dark end.

   This runs in **Python**, not the browser: the ramps ship ready in `web/data/colors.json` (19 KB, 83 teams × 2 modes × 9 steps) and the JavaScript only interpolates between neighbouring steps. Porting OKLab into `map.js` would be a second implementation to keep in sync.

4. **A continuous scale, with a square root.** There are no classes any more. The root is not decoration — without it the map disappears: the distribution is badly skewed (Brazil 247 goals, half the teams under 10), and a linear continuous scale crushes almost everyone into the first tenth of the ramp. The root opens up the bottom of the distribution **without inverting any ordering**; what it distorts is proportion, which is why the legend became a bar with values marked at `sqrt(v/max)`. The marks bunch up on the right — that visible compression *is* the warning that the scale is not linear.

5. **Goal difference keeps two fixed poles.** It is the only metric with a negative side, so it uses a diverging ramp (red ↔ blue) — and that ramp does **not** follow the selected team's colour. If the positive side turned yellow for Brazil and red for Spain, "negative" would change colour with every country and the map would stop having a side.

6. **Zero and "no data" are different colours.** Three teams have never scored a World Cup goal — China, Trinidad and Tobago, and Zaire in 1974 — and that is a fact, not an absence. So the weakest step of every ramp carries a trace of the hue instead of being achromatic: were it grey, it would be the same grey as never having played.

**What the map shows today:** 9 metrics on a continuous scale in the selected team's shirt colour, 85 of 264 polygons painted, a country selector with head-to-head mode, a total/per-match toggle, a 1930–2026 year range, and a panel that doubles as the *table view* the accessibility rule demands (the information is never carried by colour alone).

**Tools:** Leaflet.js with a GeoJSON country layer; `pandas` to pre-compute the metrics.

**How to run:**

```bash
python -m http.server 8000 --directory web
```

The page needs an HTTP server: opening `index.html` straight off disk hits the browser's origin policy and the JSON `fetch` fails. The page says so itself if that happens.

**Why this design suits our data:** it lives entirely at **match level** — scoreline, teams, venue. That is precisely the dimension both sources have complete. Player, confederation or squad features would break in 2026 (see 2.1); this one does not.

### Stage 4b — Four new features

Inspired by **SofaScore**, whose team page is built on a match list with a W/D/L marker per row, a form summary and a compare action — and by [copa2026.goodstart.com.br](https://copa2026.goodstart.com.br/) for the shell. All four come from data that already existed; none needed a new source.

| Feature | What it solves |
|---|---|
| **State in the URL** | A view becomes a link. Without it, "Brazil against Sweden between 1958 and 1970" is a set of instructions to carry out by hand. |
| **Match drill-down** | The map said *how many* and never *which*. Now the number opens: click a fixture and the matches appear, with date, edition, stage, score and venue. |
| **Compare two teams** | Head-to-head only answers for sides that have met. A side-by-side works for those who never have. |
| **Venue layer** | Returns the 252 venues Stage 3 geocoded and the map never used. The choropleth aggregates to the country; the layer shows **where**. |

**Three decisions the data forced:**

1. **Shootouts produce no draw — not in the drill-down either.** `etl.model` resolves the 39 shootouts into wins and losses, because treating normal time as final would invent draws that never happened. The JavaScript must apply the same rule, or the list shows "D" directly under a panel claiming 82 wins. A test redoes the count from `matches.json` and compares it to `metrics.json` — the map's self-check pattern, one level down.

2. **The two venue lists must share an order.** The front-end takes a match's venue index and uses it to find the coordinate in the layer. The first version sorted the layer by match count and broke that **silently**, because both lists stay the same length. It is now a contract checked in the ETL and in a test.

3. **The URL stores only what differs from the default.** An initial view yields a clean `#` rather than a paragraph of redundant parameters, and `replaceState` keeps each slider step from becoming a history entry.

**New files:** `web/data/matches.json` (58 KB, the 1,068 matches) and `web/data/venues.json` (15 KB, the 208 venues with matches).

### Stage 5 — Publish

- [x] Structure as a static site (`web/index.html` + assets)
- [x] Test locally
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
│   │   ├── kaggle/       ✅ (empty — and staying that way: attendance is out of scope)
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
│   ├── index.html        ✅ the map page
│   ├── map.js            ✅ aggregates, classifies, paints, self-checks
│   ├── style.css         ✅ cartographic chrome + the two data ramps
│   ├── vendor/           ✅ Leaflet 1.9.4, vendored (no CDN)
│   └── data/             ✅ + timeline.json
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
| 1 | Extract ready-made datasets + scrape the 2026 World Cup | ✅ complete |
| 2 | Cleaning and name reconciliation | ✅ complete |
| 3 | Modelling, validation and geocoding | ✅ complete |
| 4 | Visualisation (working map) | ✅ complete |
| 5 | Visual polish + publication + README | 🔵 next step |

## 7. Decisions

### Resolved

| Decision | Choice | Why |
|---|---|---|
| Leaflet or Mapbox | **Leaflet** | No API key needed — the map keeps working for anyone who clones the repo, with no sign-up. For markers + popups, Mapbox's extra features do not pay for themselves. |
| Women's dataset in v1 | **Always extract and clean; keep it out of the model** | Revised 2026-08-08. Extraction and cleaning still cover both competitions — zero cost, and the data stays ready. What changed is the product: the model, the map and the JSONs cover the men's tournament only. The cut is a constant in `etl/model.py`, so re-adding the women's tournament is a small diff, not a reprocessing job. |
| GitHub Actions | **Deferred to v2** | `extract.py --check` already leaves the hook in place. Automating before the pipeline is complete is premature optimisation. |
| How many Fjelstul tables to download | **16 of 29** | The remaining 13 are individual-event data (~9 MB), outside a map's scope. Easy to reverse. |

### Open

- [x] ~~**Attendance**~~ → **SETTLED 2026-08-08 by narrowing scope: attendance and capacity are both out.** The map's features are match statistics only — goals, goals conceded, goal difference, W/D/L, win rate, matches played, matches hosted, titles, participations, and the same figures head-to-head. Attendance exists for 104 of 1,068 matches; capacity is complete but **time-varying** (the Azteca held 115,000 in 1970 and holds 80,824 in 2026 — a 34,176 gap in a column that fits one value). Match statistics have neither problem: complete across all 1,068 matches, and meaning the same thing in 1930 and 2026. The `attendance` column stays in `matches.csv` because it is a fact the source provides; it simply feeds no metric. Capacity was never joined in — a deliberate omission, not an oversight.
- [x] ~~**Team succession**~~ → **SETTLED 2026-08-08: West Germany counts as Germany (4 titles).** The dissolutions (USSR, Yugoslavia, Czechoslovakia) get a modern label **and fold into the successor's match records** — `merge_records` governs only the title count, and since none of them ever won, no title changes. Rules and caveats in `reference/team_succession.csv`; consequences in [`docs/schema.md`](docs/schema.md).
- [ ] Confirm the licence of the "FIFA World Cup 1930-2022 All Match Dataset" (Kaggle) — *only matters if it is actually used*
- [x] ~~Decide between `pandas.read_html`, `BeautifulSoup4` and `Scrapy`~~ → **`requests` + `BeautifulSoup4`**, with scraping and parsing in separate modules.
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
- **2026-08-08** — **Stage 2 complete** and the succession decision taken (West Germany = Germany, 4 titles). `data/processed/matches_clean.csv` holds 1,352 matches; 14 tests passing.
- **2026-08-08** — data panorama generated (`docs/panorama.html`) to pick features from the data rather than the plan. It surfaced the central asymmetry: 2026 exists only at match level.
- **2026-08-08** — **map design settled: a choropleth with a metric selector and a country selector**, plus a head-to-head mode. Ruled: the UK stays as separate subunits; totals and per-match both ship behind a toggle. This **changes Stage 3's priority**: the central job becomes mapping the 83 teams to country polygons, not geocoding cities.
- **2026-08-08** — two new findings: (1) Wikipedia **does carry per-match attendance** (6,810,966 total in 2026) where Fjelstul carries none — which reshapes the open attendance decision; (2) in the 2026 data, `city_name` is **not a usable join key** (matches 8 of 16), because match records give the municipality and the venues table gives the metro area — `stadium_name` matches 16 of 16.
- **2026-08-08** — **Stage 3 complete: modelling, geocoding and validation.** `etl/geocode.py` resolved all 252 venues on Nominatim (versioned cache, ~5 minutes once) and filled the `country_name` missing for 2026 — the "matches received" metric became complete and Canada entered as the 19th country to host a men's World Cup match. `etl/geo.py` fetched Natural Earth and mapped the 86 teams onto 88 polygons. `etl/model.py` produced the 6 tables in `data/processed/`, and `etl/validate.py` declared each one's contract in `pandera`. 36 tests passing.
- **2026-08-08** — **`pandera` found two sentinels no sum would catch:** Fjelstul writes `0–0` as the penalty score of 1,205 matches with no shootout, and the string `"not applicable"` in `group_name` for the 332 knockout matches. Both became real nulls in the model. That is the difference between checking totals and checking rows.
- **2026-08-08** — **validation also exposed a false claim in the plan itself.** Stage 2 said entities with `merge_records=0` (USSR, Yugoslavia, Czechoslovakia…) kept separate records; in practice only the title count respects it — match records always followed the label. No headline number was wrong (none of them ever won), but Russia shows 53 matches of which 22 are its own. Presented with the choice, the project **kept the behaviour — the label wins** — and the consequence (Germany × Germany in 1974) is now printed on every validation run and locked by a test, instead of staying hidden.
- **2026-08-08** — two smaller geocoding findings: (1) for the 8 English venues of 1966, Nominatim returns `United Kingdom` where the dataset says `England` — the same border the `map_units` choice resolves from the other side; (2) Natural Earth splits **Belgium** into three map units, exactly as it splits the UK into four — which forced the team→polygon map to be one-to-many.
- **2026-08-08** — **scope narrowed to the men's World Cup.** The model went from 1,352 to 1,068 matches, 86 to 83 teams and 252 to 208 venues; the `competition` column, now single-valued, left the model tables, and the map JSONs lost the competition dimension (`head2head` became `{team: {opponent}}`). The women's data was **not deleted**: the 284 matches of 1991–2019 remain in `data/raw/` and in `matches_clean.csv`, and the venues that only ever hosted women's matches remain geocoded in the cache. The cut is the `COMPETITION` constant in `etl/model.py` — one place — and a test fails if anyone strips the women's rows further upstream.
- **2026-08-08** — **features settled: match statistics only.** Closes the project's longest-running open question — attendance or capacity — by **narrowing scope** rather than picking a side: both are out. The map exposes goals, goals conceded, goal difference, W/D/L, win rate, matches played, matches hosted, titles, participations, and the same figures head-to-head. The reason is that either candidate would need a caveat attached to every number: attendance covers 104 of 1,068 matches, and capacity is complete but time-varying (Azteca: 115,000 in 1970, 80,824 in 2026). No code changed — those were already the metrics. What changed is the record: the `attendance` column stays in `matches.csv` as a fact from the source, feeding no metric, and capacity **never** enters the model, by decision rather than by oversight. Kaggle's `wcmatches` dataset is no longer needed.

- **2026-08-08** — **Stage 4 complete: the map exists.** `web/index.html`, `web/map.js` and `web/style.css`, with Leaflet 1.9.4 vendored into the repo instead of a CDN. Nine metrics, a country selector with head-to-head mode, a total/per-match toggle, a year-range slider and a side panel. Every figure documented in this plan reproduces on screen: Germany 248 goals and Brazil 247 in raw counts, Hungary 2.72 per match, Brazil 247 goals in 119 matches at 82W–15D–22L, and Brazil × Sweden 21 goals in 7. 44 tests passing.
- **2026-08-08** — **choosing the year slider cost the "the front-end aggregates nothing" rule — and the trade was documented, not hidden.** A decade filter would be pre-computable; a free range is not (276 possible ranges). So aggregation moved into the browser, with a counterpart: `timeline.json` (the long table in columnar form, 37 KB), a reference implementation in Python (`aggregate_timeline`), `map.js` mirroring it, and the **page re-running the full range on load to compare against `metrics.json` team by team** — with an on-screen warning if they diverge. A Python test locks the other side. It is the same idea as `pandera` in Stage 3: the check that catches a wrong row, not just a wrong total.
- **2026-08-08** — **three colour decisions the data forced.** (1) **Goal difference** got a diverging ramp (red ↔ grey ↔ blue) while the other eight metrics use the single-hue sequential one: goal difference is the only metric with a negative side, and a sequential ramp would put −20 and +20 at the two ends of a scale with no sides. (2) Classes are by **quantile** — Brazil has 247 goals and half the teams have fewer than 10, so equal intervals would give four dark countries and a white rest. (3) **Zero and "no data" are different colours**: China, Trinidad and Tobago and Zaire in 1974 never scored a World Cup goal, and that is a fact, not an absence.
- **2026-08-08** — **two improvements to the choropleth: a continuous scale and the team's colour.** The quantile classes are gone: the scale is now **continuous**, with a square root on the value — without the root, a linear scale would crush nearly every team into the first tenth of the ramp, because Brazil has 247 goals and half of them have fewer than 10. The root opens up the bottom of the distribution without inverting any ordering, and the legend became a bar with values marked at `sqrt(v/max)`: the marks bunch up on the right, and that visible compression is the warning that the scale is not linear. And the ramp is now **the selected team's colour** — Brazil yellow, Italy azzurro, the Netherlands orange — generated in OKLab by `etl/color.py` from `reference/team_colors.csv`. The global view deliberately keeps a single ramp: the eye reads darkness as quantity, so giving each country its own colour would make a dark-blue Italy look like 'more' than a bright-yellow Brazil with a bigger number. 58 tests.
- **2026-08-08** — **curating the colours hit a problem the data never had.** Twelve teams play in white or black — Germany, England, Poland, New Zealand, Senegal… — and neither works as a hue: white has no chroma to carry a ramp, and black becomes a grey that collides with the 'no data' grey. The rule settled as: the home shirt colour; where that is achromatic, the chromatic colour that identifies the side, marked `identity` and reasoned row by row. For the same reason the weakest step of every ramp carries a trace of the hue rather than being grey — otherwise 'played and never scored' would look identical to 'never played'.
- **2026-08-08** — **the interface was restyled and the colour rule got stricter.** The chrome moved to a near-black blue-cast surface with rounded cards, pill controls, heavier sans typography and a vivid emerald accent — taking cues from [copa2026.goodstart.com.br](https://copa2026.goodstart.com.br/), which solves the same problem (a World Cup map) with an immersive map and pill navigation. The accent is deliberately **not** blue: blue is the global-view ramp, and a blue button beside a blue map would read as part of the scale.
- **2026-08-08** — **team colours are now the shirt from the last World Cup each side played**, not a generic 'country colour'. The table gained a `last_cup` column, checked against the model — which caught two errors on the first run (Italy has not played since 2014, Peru since 2018). Only nine teams have not played since before 1998, and those are the ones that needed research: Cuba played 1938 in red, and the Dutch East Indies played 1938 **in white** — no hue to carry a ramp, so that row falls to the exception and uses modern Indonesia's red, which is the label the record appears under. The ramps also got more vibrant: chroma may now exceed the source colour's own and it is the sRGB gamut that clips, so each step is as saturated as that lightness allows — with lightness and hue untouched.
- **2026-08-08** — **the map became the page.** The layout stopped being a document with the map in a card: the map now fills the window and the controls, legend and side panel float over it in frosted glass, as on [copa2026.goodstart.com.br](https://copa2026.goodstart.com.br/). The detail that makes it work is `pointer-events` — the layer positioning the cards takes no pointer, only the cards do; without that the empty space between them would swallow the drag and half the screen would stop being a map. The header with the title and standfirst is gone: the map is the title. The `h1` stays for screen readers, and the CC BY-SA attribution — a licence obligation — moved out of Leaflet's 10px control into a "Fontes e licenças" block on the legend card, where all three sources are named in full. A button hides the panels and hands the whole window back to the map.
- **2026-08-09** — **the coloured dots in the tables became flags — and the route there was more interesting than the result.** The first version used emoji, which costs no bytes: `iso_a2` came from Natural Earth itself (the `ISO_A2_EH` field, which resolves the `-99`s that `ISO_A2` writes for Norway and Portugal), and the three British sides with emoji came from tag sequences. But **Windows ships no flag glyphs at all**: `🇧🇷` renders as the letters "BR" and the British ones as a plain black flag, identical for all three. A canvas check measured 16.88px against 17.42px for two loose letters and confirmed the browser was not composing — meaning half the visitors, the project's own author included, would never see a flag.
- **2026-08-09** — **switching to SVG solved two problems at once.** The vendored set renders identically on every system and **includes Northern Ireland**, which Unicode has never defined as an emoji and which was therefore the one team condemned to have no flag. The choice of set was measured too: the first candidate weighed 723 KB, with ten coats of arms (Serbia alone at 177 KB) making up 87% of it for detail invisible at 16px; the adopted set does the same job in **146 KB**. An `onerror` falls back to the coloured dot if a file is missing, and the ETL fails if any SVG is absent from disk — because a broken icon raises no error anywhere.
- **2026-08-09** — **four new features, all from data that already existed:** state in the URL (a view becomes a link), match drill-down (the number opens and shows the rows behind it), comparing two teams (works even for sides that never met) and a venue layer (returns the 252 venues geocoded in Stage 3 that the map never used). The design reference was SofaScore, whose team page is built on a match list with a W/D/L marker per row.
- **2026-08-09** — **two silent bugs surfaced while building, and both became tests.** (1) The venue layer was sorted by match count while the drill-down indexes venues in CSV order — both lists stayed the same length, so nothing complained, but one stadium's count would have been plotted at another's coordinates. (2) `badge()` escaped single but not double quotes in the flag's `onerror`, ending the attribute early and leaking `'">` as text beside the team name — a bug live since the flags commit.
