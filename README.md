# Atlas Copa do Mundo — World Cup Atlas

An interactive map of every FIFA World Cup, 1930–2026, built as an end-to-end data
pipeline: extraction (including web scraping), reconciliation of almost a century of
inconsistent records, relational modelling, validation, and publication.

*Documentação de planejamento em português: [`plano-atlas-copa-mundo.md`](plano-atlas-copa-mundo.md)*

> ### Status: stage 5 of 5
> The pipeline runs end to end, **the map works**, and it is published —
> **[alaindelon96.github.io/atlas-copa-mundo](https://alaindelon96.github.io/atlas-copa-mundo/)**.
> Locally: `python -m http.server 8000 --directory web`. This README describes what is
> built, not what is planned — see [Roadmap](#roadmap).

---

## What this repository actually contains today

| | |
|---|---|
| **Working** | Extraction with cryptographic provenance, a Wikipedia scraper for 2026, a reconciled match table, a validated 6-table model, an interactive choropleth map with match detail, two-team comparison, a venue layer and shareable URLs — deployed to GitHub Pages by a workflow |
| **Data on hand** | `data/processed/` — 1,068 men's matches, 3,028 goals with scorer and minute, 23 tournaments, 83 teams, 208 geocoded venues, 1930–2026. Schema: [`docs/schema.md`](docs/schema.md) |
| **Not built yet** | Scheduled re-runs of the pipeline in CI — deferred to v2 |
| **Known gap** | Attendance exists only for 2026 (Fjelstul carries none) — and is deliberately not a feature |
| **Scope** | The men's World Cup. The women's data is extracted and cleaned but excluded from the model and the map — see [Scope](#scope) |

---

## Quickstart

The raw data is **not** in this repository. That is deliberate: it is reproducible
from the code, and reproducing it is verifiable. Clone, install, extract:

```bash
git clone https://github.com/alaindelon96/atlas-copa-mundo.git
```

```bash
pip install -r requirements.txt
```

```bash
python -m etl.extract
```

That downloads 16 CSVs (~1.9 MB) into `data/raw/fjelstul/` and writes a provenance
record to `data/raw/metadata.json`.

To check whether the upstream source has changed since your last download, without
overwriting anything:

```bash
python -m etl.extract --check
```

Then fetch and parse the 2026 tournament, which no dataset covers:

```bash
python -m etl.scrape_2026
```

```bash
python -m etl.parse_2026
```

**This has been verified**: a fresh clone followed by `python -m etl.extract`
reproduces all 16 files with SHA-256 hashes identical to the committed provenance
record. The data is not stored; it is *regenerable*, and the hashes prove the
regeneration is byte-identical.

Then build the model, validate it, and generate what the map loads:

```bash
python -m etl.transform && python -m etl.geocode --offline && python -m etl.geo
```

```bash
python -m etl.model && python -m etl.validate && python -m etl.metrics
```

`--offline` replays the committed geocoding cache and never touches the network. Drop it
only if you intend to re-query Nominatim — that is ~5 minutes at 1 request/second.

---

## How the pipeline works

Data flows in one direction only. Nothing ever writes backwards into a folder to its
left — that single constraint is what makes the whole thing reproducible.

```mermaid
flowchart LR
    A[Fjelstul DB<br/>16 CSV · 1930–2022]:::done --> R
    B[Wikipedia<br/>2026 · scraped]:::done --> R
    C[Natural Earth<br/>country polygons]:::done --> R
    R[("data/raw/<br/>immutable · hashed")]:::done --> I
    N[Nominatim<br/>venue coordinates]:::done --> I
    I[("data/interim/<br/>names reconciled · geocode cache")]:::done --> P
    P[("data/processed/<br/>6 tables · validated")]:::done --> W
    W[web/<br/>Leaflet choropleth]:::done -->|GitHub Actions| G
    G[GitHub Pages<br/>live site]:::done
    R -.provenance.-> M[metadata.json<br/>SHA-256 · when · licence]:::done

    classDef done fill:#DBEDE8,stroke:#0F7A6B,color:#16202B
```

### Stage 1 — Extract ✅

Downloads the source CSVs once, stores them untouched, and records exactly where each
came from.

| Module | Responsibility |
|---|---|
| [`etl/paths.py`](etl/paths.py) | Every path resolved from the repo root, so any module works regardless of the working directory |
| [`etl/provenance.py`](etl/provenance.py) | SHA-256, UTC timestamp, URL, licence and attribution for each file |
| [`etl/extract.py`](etl/extract.py) | The download itself |

Three decisions here are worth explaining, because they are the difference between a
script and a pipeline:

- **`data/raw/` is immutable.** Nothing in it is ever hand-edited, and it is
  `.gitignore`d — but `metadata.json` *is* committed. The data is disposable; the
  audit record is not.
- **Writes are atomic.** Each file lands as `.part` and is renamed only on success. An
  interrupted download cannot leave a truncated CSV that looks valid.
- **Everything is hashed.** `--check` compares the remote hash against the recorded one
  without overwriting, so you can detect upstream changes. This is the hook that makes
  scheduled automation possible later.

### Stage 1b — Scrape 2026 ✅

No published dataset covers the 2026 tournament, so it comes from Wikipedia.
Scraping and parsing are **separate modules**, deliberately:

| Module | Responsibility |
|---|---|
| [`etl/scrape_2026.py`](etl/scrape_2026.py) | Fetches raw HTML into `data/raw/scraped/`. Nothing is interpreted. |
| [`etl/parse_2026.py`](etl/parse_2026.py) | Reads that cached HTML and extracts data. **Makes no network requests.** |

Splitting them means a parsing bug can be fixed and re-run instantly without
touching Wikipedia again, the parser is testable offline, and the cached HTML is
evidence of what the page said at collection time.

**Compliance**, since scraping has rules worth following:

- Wikipedia's `robots.txt` disallows `/w/` and `/api/` for generic agents but
  permits articles at `/wiki/<Title>` — which is what this fetches. The REST API
  would *not* have been allowed.
- Identifiable user-agent with contact details, per Wikimedia policy.
- One second between requests.
- The **revision ID** of every page is recorded. Wikipedia changes constantly, so
  naming the article is not sufficient attribution — see
  [`LICENSE-DATA.md`](LICENSE-DATA.md).

The 104 matches are spread across 14 pages: 12 group pages (6 matches each) plus
the knockout stage (32). The parser verifies itself against the article's own
declared totals and **refuses to succeed if they disagree**:

```
OK  partidas   extraído=104    infobox=104
OK  gols       extraído=308    infobox=308
OK  sedes      extraído=16     infobox=16
```

Attendance independently sums to 6,810,966 across 104 matches — matching the
infobox exactly, average included.

### Stage 2 — Clean and reconcile ✅

Merges both sources into `data/processed/matches_clean.csv` — 1,352 matches, 1930–2026.

```bash
python -m etl.transform
```

Three ideas carry this stage:

**Label and record are different questions.** [`reference/team_succession.csv`](reference/team_succession.csv)
has two separate columns: `display_name` (how the team is shown today) and
`merge_records` (whether its history is credited to the successor). West Germany gets
both — it becomes Germany *and* its titles count. The USSR gets only the first.

> **Corrected in stage 3.** That last sentence used to end "…and keeps its own record."
> `pandera` showed it was not true: `apply_succession` applies `display_name` to
> everyone, so **match** records always followed the label — only the **title** count
> respects `merge_records`. No headline number was wrong, because no entity treated this
> way ever won a World Cup; the description was. Faced with the choice, the project
> reaffirmed the behaviour — the label governs — and made the consequence visible instead
> of hiding it. See [Stage 3](#stage-3--model-geocode-and-validate-) and
> [`docs/schema.md`](docs/schema.md).

**Fuzzy matching suggests; it never decides.** `rapidfuzz` reports names in 2026 that
have no historical counterpart, for a human to classify. It is deliberately not allowed
to merge anything, and the data shows why:

```
Cape Verde       closest: Cuba    60.0   debut?
Curaçao          closest: Cuba    67.5   debut?
Jordan           closest: Iran    67.5   debut?
Uzbekistan       closest: Iran    60.0   debut?
```

Four genuine World Cup debutants — and **DR Congo is absent from that list**, because
the curated map already resolved it to Zaire, which played in 1974. `fuzz.WRatio("Zaire",
"DR Congo")` scores under 50. The only real succession between the two sources is
precisely the one string similarity could never find.

**Champions do not come from finals.** The 1950 World Cup had no final — it was decided
by a final round-robin group. Deriving champions by filtering `stage == "final"` returns
22 titles for 23 tournaments and raises no error. So champions come from the source's own
standings table instead, and the pipeline asserts that titles sum to the number of
editions.

Stage 2 also normalises stage names, which were inconsistent *within* Fjelstul itself —
`quarter-final` (32 rows) alongside `quarter-finals` (70).

### Stage 3 — Model, geocode and validate ✅

```bash
python -m etl.geocode --offline && python -m etl.geo
```

```bash
python -m etl.model && python -m etl.validate && python -m etl.metrics
```

Six tables in `data/processed/` — `tournaments`, `tournament_hosts`, `teams`, `venues`,
`matches`, `team_matches` — plus the two JSONs and the GeoJSON the front-end loads. The
ERD and the reasoning behind every schema decision are in [`docs/schema.md`](docs/schema.md).

Note the order: `etl.geo` writes the `reference/team_country.csv` that `etl.model` reads.

**Geocoding.** All 252 venues in the data resolved through Nominatim at 1 request/second, with the
responses cached on disk *and committed*. `--offline` replays that cache and never touches
the network — reproducing the pipeline should not cost a free public service five minutes
of traffic. The query descends in steps (`stadium, city, country` → `city, country` →
`stadium, city`) and the step that answered is kept in `venues.match_level`, because 51 of
the 252 coordinates point at a city centre rather than a pitch, and a marker layer needs to
know that.

This is what filled `country_name` for the 104 matches of 2026, which the Wikipedia tables
never carried. That unblocked "matches received" — and added **Canada** as the 19th country
ever to host a men's World Cup match.

**Country polygons.** The map shades countries, so it needs shapes, not points. The base is
Natural Earth's `admin_0_map_units` rather than `admin_0_countries`, and the difference
decides the project: only `map_units` separates England, Scotland, Wales and Northern
Ireland, which is the split football uses. The price is that the same division splits
**Belgium** into Flanders, Wallonia and Brussels — so `reference/team_country.csv` is
one-to-many, 88 polygons for 86 teams. The three Belgian regions take the same colour and
the seam does not show.

**Validation.** `etl/validate.py` declares each table's contract in `pandera` and checks
what is *on disk*, without recomputing it. It earned its place immediately. The checks the
scripts already ran verify **totals** — "do the goals add up?" — and are therefore blind to
row-level error. Declarative validation found two sentinels no sum would ever flag:

| Column | Fjelstul writes | Wikipedia writes | Rows |
|---|---|---|---|
| penalty score, no shootout | `0` and `0` | blank | 1,205 |
| `group_name`, knockout stage | `"not applicable"` | blank | 332 |

Neither breaks anything, and that is the problem. `0` is a valid score, and a `groupby` on
group would happily return a "group" called `not applicable` holding 332 knockout matches.
Both are real nulls now.

It also caught something sharper: **the project's own documentation was wrong.** Stage 2
claimed that teams with `merge_records=0` kept separate records. They did not — only the
title count respected that flag; match records always followed the display label. No
headline number was affected (none of those entities ever won a World Cup), but Russia
shows 53 matches of which 22 are Russia's. Faced with the choice, the project kept the
behaviour — **the label wins** — and made the consequence loud instead of hidden:

> **1974, East Germany 1–0 West Germany** becomes `Germany × Germany`. Germany books one
> win and one loss, one goal for and one against; every total still balances. `etl.validate`
> prints the case on every run and a test locks it, so nobody "fixes" an editorial decision
> by accident.

### Stage 4 — The map ✅

```bash
python -m http.server 8000 --directory web
```

Then open http://localhost:8000. The page needs a real HTTP server: opening
`index.html` off disk trips the browser's origin policy and the JSON fetch fails — the
page tells you so if it happens.

| File | Role |
|---|---|
| `web/index.html` | The shell: a full-window map with the panels floating over it |
| `web/map.js` | Aggregates, classifies, paints — and checks itself against the pipeline |
| `web/style.css` | Chrome inherited from `docs/panorama.html` + the two colour ramps |
| `web/vendor/` | Leaflet 1.9.4 and 83 flag SVGs, vendored rather than pulled from a CDN |
| `web/data/` | Everything the page fetches — 2.0 MB, of which `countries.geojson` is 1.7 MB |
| `etl/color.py` | Turns a shirt colour into a sequential ramp, in OKLab |
| `reference/team_colors.csv` | Each team's curated colour, with the exceptions reasoned |

**The year slider cost a rule, so the rule became a check.** Every other number on the
map is pre-computed in Python, on the principle that a wrong number is always an ETL
bug. A free year range breaks that — 23 editions give 276 possible ranges, so the
browser has to do the arithmetic. Rather than quietly duplicating the metric
definitions in JavaScript, the duplication is made loud: `etl.metrics.aggregate_timeline`
is the reference implementation, `web/map.js` mirrors it, and **the page re-runs the
full 1930–2026 range on load and compares it to `metrics.json` team by team**. Diverge,
and a red banner says the numbers cannot be trusted. A Python test locks the other side.

**The map is painted in the selected team's shirt colour.** Pick Brazil and the world
turns yellow; Italy, azzurro; the Netherlands, orange. The rule is precise: **the home
shirt of the last World Cup that team actually played**, curated by hand in
[`reference/team_colors.csv`](reference/team_colors.csv). For 48 of the 83 teams that is
2026, so it rarely bites; it bites for the nine who have not played since before 1998 —
Cuba's 1938 red, Israel's 1970 blue, Kuwait's 1982 blue.

The `last_cup` column is **checked against the model on every run**, so a team playing
again cannot leave the colour quietly describing a kit that is no longer their last. That
check caught two curation errors the first time it ran: Italy (last played 2014, not
2026) and Peru (2018).

Sixteen sides play in white or black, which cannot carry a ramp — white has no hue, and
black becomes the same grey that means "no data". Those fall back to the chromatic colour
that identifies them, marked `identity` and reasoned row by row. The Dutch East Indies are
the sharpest case: they played 1938 in white, so the row uses modern Indonesia's red — the
label the record appears under.

`etl/color.py` turns each of those colours into a nine-step ramp in **OKLab**, a
perceptually uniform space — interpolating yellow to white in sRGB detours through dirty
beige. Lightness carries the data and moves monotonically, which is what keeps the ramp
readable without colour vision; when a step falls outside sRGB, chroma gives way rather
than the RGB channels, because clamping a channel would drag the hue and land the yellow
on orange. The **global view keeps one ramp on purpose**: the eye reads darkness as
quantity, so giving every country its own colour would make a dark-blue Italy look like
more than a brighter Brazil with a bigger number.

**Three further colour decisions the data forced:**

- **The scale is continuous, with a square root.** Brazil has 247 goals and half the
  teams have fewer than ten; a linear continuous scale crushes almost everyone into the
  first tenth of the ramp. The root opens the bottom out without inverting any ordering.
  What it distorts is proportion — so the legend marks real values at `sqrt(v/max)`, and
  the marks visibly bunch up on the right.
- **Goal difference gets a diverging ramp** (red ↔ blue) with two *fixed* poles, even
  when a team is selected. It is the only metric with a negative side, and if the
  positive pole followed the team's colour, "negative" would change colour with every
  country.
- **Zero and "no data" are different colours.** China, Trinidad and Tobago, and Zaire in
  1974 have never scored a World Cup goal. That is a fact worth showing, not an absence
  — which is why the weakest step of every ramp keeps a trace of the hue instead of
  fading to the no-data grey.

### Stage 4b — Four features the existing data already paid for ✅

None of these needed a new source. The design reference was **SofaScore**, whose team page
is built on a match list with a W/D/L marker per row, a form summary and a compare button.

| Feature | What it fixes |
|---|---|
| **State in the URL** | The view becomes a link. Without it, "Brazil against Sweden between 1958 and 1970" is a set of instructions for a human to execute by hand. It also gives the browser's back button a meaning on a page that never changes page. |
| **Match detail** | The map said *how many* and never *which*. Click a fixture and the matches behind the number open up: date, edition, stage, score, venue, result marker. New payload `web/data/matches.json`, 58 KB, all 1,068 matches. |
| **Two-team comparison** | Head-to-head only answers for teams that have met. A side-by-side comparison works for teams that never have — and says so explicitly instead of showing zeros. Each row declares its direction, because in goals conceded the winner is the *lower* number. |
| **Venue layer** | Returns the 252 venues stage 3 geocoded and the map never used. The choropleth aggregates to the country; the layer shows **where**. The count respects the year filter — 208 venues over the full range, 16 in 2026. |

**Three decisions the data forced:**

- **Penalties do not produce draws — not in the detail list either.** `etl.model` resolves
  the 39 shootouts into a win and a loss. The JavaScript has to apply the same rule, or the
  list shows "D" directly beneath a panel saying 82 wins. A test recomputes the totals from
  `matches.json` and compares them to `metrics.json` — the map's self-check, one level down.
- **The two venue lists must stay in the same order.** The front-end takes a match's venue
  index and uses it to find the coordinate in the layer. The first version sorted the layer
  by match count and broke that **silently**, because both lists stay the same length. It is
  a contract now, asserted in the ETL and in a test.
- **The URL stores only what differs from the default**, so an untouched view gives back a
  clean `#` rather than a paragraph of redundant parameters, and `replaceState` keeps every
  slider step out of the history.

Two silent bugs surfaced on the way and became fixes: `badge()` escaped the single quote but
not the double one in the flag's `onerror`, which closed the attribute early and leaked `'">`
as text next to the team name — live since the flags commit; and `styleFor()` still asked for
two CSS variables that the restyle had removed, so the selected country came through unfilled.

### Stage 4c — Top scorers, and the assumption that fell ✅

**Stage 3 concluded that player-level data would have a hole in 2026, and cut the project's
features down to "match statistics only".** The conclusion was right about Fjelstul, which
stops at 2022, and wrong about what was already on disk: the pages `scrape_2026.py` had
downloaded carry the scorers, with minutes. All 104 match boxes were checked — **308 minute
marks**, exactly the total the article declares, and the 7 matches with no name listed are
all 0–0. The hole never existed; a parser was missing.

| | |
|---|---|
| Fjelstul, 1930–2022 | 2,720 goals with scorer, minute, penalty and own-goal flags |
| Wikipedia, 2026 | 308, parsed from HTML already sitting in `data/raw/scraped/` |
| **Total** | **3,028** — the same number the model's scorelines already produced |

That meeting is what makes the table **checkable** rather than plausible: it does not invent
a count of its own, it reproduces one the model already produced by another route — and the
check is per match, not just on the total.

- **An own goal is credited to the team that gained it**, as in the scoreline; `player_team`
  holds the team of whoever kicked it. If `team` were the player's team, two sides would have
  each other's number in the same match.
- **Reading by list item lost 6 goals in 302.** Most columns wrap each scorer in an `<li>` —
  but not all, and one carried two players in loose text. The parser now walks the minutes and
  treats the text between them as a change of player, which holds in both formats. What caught
  the error was the check against the declared total, not the parser checking itself.
- **Player names are not comparable across the sources.** Fjelstul writes the string
  `"not applicable"` in the first-name field of anyone who has only one — the Brazilian Ronaldo
  among them. Top scorer per edition is safe; a career summed across the two sources is not,
  and the project does not promise it.

On screen: each match's scorers in the detail view (the 1958 final comes out with Vavá, Pelé
and Zagallo at the right minutes), a scorer list for the selected team (Ronaldo 15, Pelé 12 for
Brazil; Mbappé 10 in 2026), and a **play button on the slider** that walks the window across the
editions keeping the chosen width — which is why it skips 1942 and 1946, which never happened.

### Stage 5 — Publish ✅

The site is static, so there is no server to break and hosting costs nothing:

**[alaindelon96.github.io/atlas-copa-mundo](https://alaindelon96.github.io/atlas-copa-mundo/)**

Deployment is [`.github/workflows/pages.yml`](.github/workflows/pages.yml) — a push to `main`
runs `pytest`, and **only if the suite passes** does it upload `web/` as the Pages artifact.
That ordering is the point: the 82 tests exist to stop a wrong number reaching a reader, so
they gate the deploy rather than merely reporting after it.

The workflow publishes `web/` **as it stands in the repository** — it does not re-run the
pipeline. The generated payloads under `web/data/` are committed, so what deploys is exactly
what a clone renders locally, and rebuilding the numbers stays a deliberate act
(`python -m etl.metrics`) rather than a side effect of a push. Re-running the whole ETL on a
schedule is the natural next step and is deferred to v2 — `etl.extract --check` already exists
for precisely that hook.

## Tests

```bash
pytest
```

82 tests, all offline. They pin the decisions and the traps — the succession ruling, the
men's/women's split, stage normalisation, the 1950 case, the fact that fuzzy matching
scores Zaire against DR Congo below 50, the four British teams staying four polygons, the
two sentinel nulls, the 3,028 goals reconciling per match against the scorelines, the venue
lists staying in the same order, shootouts never becoming draws, and a hand-checked sample of
coordinates (a valid schema cannot tell Wembley in London from Wembley in the Atlantic). If
someone edits the succession map without realising the consequence, a test fails with the
reason attached.

One of the 82 reads `data/raw/`, which is not in the repository — the champions come from
the source's own standings table rather than from `stage == "final"`, so that check has
nowhere else to look. It skips in a clone that has not run `python -m etl.extract`, and the
deploy workflow runs the extraction so that it never skips there.

The suite also **gates the deploy** — see [stage 5](#stage-5--publish-).

---

## What the data revealed

Four things surfaced on first inspection that changed the original plan. They are the
most interesting part of this project so far.

**1. `tournament_id` does not separate the men's and women's tournaments.**
All 30 editions use the same `WC-<year>` pattern — `WC-1991` is the women's tournament,
`WC-1994` the men's. Only `tournament_name` distinguishes them. Because the years never
overlap and the ID is genuinely unique, grouping by ID silently blends two competitions
and raises no error. An explicit `competition` column is the first thing stage 2 will add.

**2. There is no attendance data — for 1930–2022.** `matches.csv` has 36 columns and
none is attendance, though `stadium_capacity` is complete across all 240 stadiums.
Wikipedia, by contrast, carries per-match attendance, so 2026 has it and the earlier
tournaments do not. Still an open decision — see below.

**3. Geocoding cannot be done by hand.** The plan assumed "a few cities". It is 240
stadiums across 202 cities. That is `geopy`/Nominatim with an on-disk cache, not a
spreadsheet.

**4. The data is clean — so the hard problem is a different one.** Zero nulls in dates,
venues, scores and capacities. The work is therefore not repair but **historical
reconciliation**:

| In the data | Today | Change | Solvable by fuzzy matching? |
|---|---|---|---|
| West Germany / East Germany | Germany | Reunification, 1990 | Partly |
| Soviet Union | Russia | Dissolution, 1991 | **No** |
| Yugoslavia → Serbia and Montenegro | Serbia | Staged dissolution | Partly |
| Czechoslovakia | Czech Republic | Split, 1993 | Partly |
| Dutch East Indies | Indonesia | Independence, 1949 | **No** |
| Zaire | DR Congo | Renaming, 1997 | **No** |

This is precisely where `rapidfuzz` alone fails: *Zaire* and *DR Congo* share no textual
similarity. The solution is a curated succession map for the political changes, with
fuzzy matching reserved for spelling variants — and the reasoning documented, because
the choice is editorial rather than technical.

**5. In the 2026 data, city names are not a usable join key.** Match records give the
municipality the stadium physically sits in; the venues table gives the metro area it
is marketed under. Joining on city matches **8 of 16**; joining on stadium name matches
**16 of 16**.

| Match record says | Venue table says |
|---|---|
| Inglewood | Los Angeles |
| East Rutherford | New York/New Jersey |
| Santa Clara | San Francisco Bay Area |
| Zapopan | Guadalajara |
| Arlington | Dallas |

Neither is wrong — they answer different questions. This matters directly for the map,
because the marker coordinate should be the *stadium*, not the metro centroid.

---

## Layout

```
etl/                     pipeline modules (paths, provenance, extract)
data/raw/                immutable source data — gitignored
data/raw/metadata.json   provenance ledger — committed
data/interim/            partial transformations — disposable
data/processed/          final tables, ready for the front-end
web/                     Leaflet map — the published site
web/data/                what the page fetches: countries.geojson + 7 JSON payloads
.github/workflows/       pytest, then deploy web/ to GitHub Pages
docs/roadmap.html        visual roadmap (bilingual PT/EN)
tests/                   pytest suite for transformation logic
```

---

## Scope

**This project covers the men's World Cup — 23 editions, 1,068 matches, 1930–2026.**

The women's tournament is *extracted and cleaned, but not modelled*. That distinction
is the point:

| Layer | Women's data |
|---|---|
| `data/raw/` | Present — the source ships both in the same files |
| `data/processed/matches_clean.csv` | Present — 284 matches, 1991–2019, tagged by the `competition` column |
| The model, the metrics, the map | Excluded |

The cut happens in exactly one place: the `COMPETITION` constant in
[`etl/model.py`](etl/model.py). Everything downstream inherits it. That is why the
model tables carry no `competition` column — it would hold a single value across
1,068 rows, and a constant column tells you nothing while implying a variation that
is not there.

Re-adding the women's tournament later means changing that constant and putting the
column back. The cleaning stage, the succession map and the geocoding cache already
cover it, so nothing has to be re-derived — the venues that only ever hosted women's
matches are geocoded and sitting in the cache. A test in
[`tests/test_model.py`](tests/test_model.py) fails if anyone strips the women's rows
further upstream, so the option stays open by construction rather than by memory.

---

## Open decisions

None outstanding. The last one — stadium capacity — closed when the venue layer shipped in
[stage 4b](#stage-4b--four-features-the-existing-data-already-paid-for-) *without* it: the
layer sizes each circle by how many matches the venue held, which is a fact of the record
and needs no era attached. Capacity stays out for the reason below.

### Settled: the features are match statistics — plus who scored

Decided 2026-08-08, **amended 2026-08-09**. The original ruling cut player data on the
grounds that 2026 would leave a hole in it. That was wrong, and
[stage 4c](#stage-4c--top-scorers-and-the-assumption-that-fell-) is the correction: the
scorers were already in the scraped HTML, and the 3,028 goals reconcile per match against
the scorelines the model had already derived. Scorers ship.

What the original ruling got right, and what still holds: every metric the map *colours by*
is derived from what happened in the games — goals, goals conceded, goal difference,
wins/draws/losses, win rate, matches played, matches hosted, titles, participations, first
and last year — plus the same figures head-to-head against any single opponent. Scorers are
a list, not a metric: they name the players behind a number the map already shows.

**Attendance and stadium capacity are out.** Not blocked, not pending — out. That closes
what had been the project's longest-running open question, and it closes it by narrowing
scope rather than by picking a side.

Both would have needed an apology attached to every number:

| Field | Why it was awkward |
|---|---|
| Attendance | Exists for 104 of 1,068 matches. Wikipedia has 2026; Fjelstul has nothing. Kaggle would reach 2018 and leave 2022 blank. |
| Stadium capacity | Complete, but **time-varying**. The Azteca held 115,000 in 1970 and holds 80,824 in 2026 — a 34,176 gap in one column that can only carry one value. |

Match statistics have neither problem: they are complete for all 1,068 matches, they mean
the same thing in 1930 and 2026, and they need no footnote.

The `attendance` column stays in `matches.csv`, because it is a real fact the source
gives and dropping it would throw away the only place it exists. It simply feeds no
metric. Capacity was never joined in — that is a deliberate omission, not an oversight.

## The map

**Settled 2026-08-08: a choropleth world map with two selectors.** Stage 4b added three
more controls without changing that shape.

| Control | Options |
|---|---|
| **Metric** | Goals · Goals conceded · Goal difference · Wins · Win rate · Matches played · Matches received · Titles · Participations |
| **Country** | None (global view) or one specific team |
| **Compare with** | A second team, side by side — works even for two that never met |
| **Layers** | Venues on or off, sized by matches held |
| **Reading** | Totals or per match (10-match floor) |
| **Years** | Any range across the 23 editions, 1930–2026, with a play button that walks it edition by edition |

Every one of those is in the URL hash, so any view is a link. Clicking a fixture opens the
matches behind the number, scorers and minutes included.

Selecting a country **recolours the map by head-to-head**. *Brazil + Goals* shades every
country by how many goals Brazil scored against it — Sweden brightest at 21 in 7 matches,
and Mexico conceding 13 across 5 matches without ever scoring.

Two rulings behind it:

- **The UK stays four regions.** England, Scotland, Wales and Northern Ireland are four
  distinct teams. Merging them would invent a national side that has never existed and
  credit it with 168 goals nobody scored.
- **Totals and per-match both ship, behind a toggle.** Raw counts on a choropleth mostly
  redraw qualification frequency — Germany 248 and Brazil 247 are near-tied because both
  played ~120 matches. Per match, Hungary leads at 2.72 and disappears from the raw top
  ten. The switch between those two readings is the point.

This design lives entirely at **match level**, which is the one dimension both sources
cover completely — so unlike player- or confederation-based features, it has no 2026 gap.

**Settled — West Germany counts as Germany** (2026-08-08). Germany therefore has **4
titles**, matching FIFA's official count. This was the only succession question that
changes a headline number: the USSR, Yugoslavia, Czechoslovakia, East Germany and Zaire
never won a World Cup, so their treatment affects appearance counts and map labels but
no title. The full ruling is in
[`reference/team_succession.csv`](reference/team_succession.csv), one row per case with
the reasoning.

---

## Roadmap

| Stage | Status |
|---|---|
| 1 · Extract ready-made datasets | ✅ Done |
| 1b · Scrape the 2026 tournament | ✅ Done |
| 2 · Clean and reconcile names | ✅ Done |
| 3 · Model, validate, geocode | ✅ Done |
| 4 · Build the Leaflet map | ✅ Done |
| 4b · URL state, match detail, comparison, venue layer | ✅ Done |
| 4c · Top scorers, 1930–2026 | ✅ Done |
| 5 · Publish to GitHub Pages | ✅ Done |
| v2 · Re-run the pipeline on a schedule | ⬜ Deferred |

A bilingual visual roadmap with the reasoning behind each stage is in
[`docs/roadmap.html`](docs/roadmap.html).

### 2026, verified

The planning documents had recorded — from outside the project, unverified — that the
2026 tournament ended on 19 July 2026 with Spain beating Argentina. The scraper has now
confirmed it against the source:

| | |
|---|---|
| **Champions** | Spain (2nd title) |
| **Runners-up** | Argentina |
| **Final** | 1–0, 19 July 2026, MetLife Stadium — 80,663 present |
| **Third / fourth** | England / France |
| **Format** | 48 teams, 3 host countries, 16 venues, 104 matches |
| **Top scorer** | Kylian Mbappé (10 goals) |

The 2026 tournament breaks two schema assumptions that held for 1930–2022: `host_country`
is no longer a single value, and there is one knockout round more than in any previous
edition. Both need handling in stage 3.

---

## Licensing and attribution

This repository is under **two** licences, because the code and the data have different
origins.

| | Licence | |
|---|---|---|
| **Code** (`etl/`, `web/`, `tests/`) | MIT | [`LICENSE`](LICENSE) |
| **Data** (`data/`, `web/data/`) | CC BY-SA 4.0 | [`LICENSE-DATA.md`](LICENSE-DATA.md) |

The data licence is not a choice. The source is published under CC BY-SA 4.0, whose
ShareAlike term requires derived data to carry the same licence.

> GitHub's sidebar detects a single licence and will display **MIT**. That label
> applies to the code only — the data is CC BY-SA 4.0 regardless of what the sidebar
> says.

### Required attribution

World Cup data for **1930–2022** comes from the **Fjelstul World Cup Database**:

- **Author:** Joshua C. Fjelstul, Ph.D.
- **Copyright:** © 2023 Joshua C. Fjelstul, Ph.D.
- **Licence:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode)
- **Source:** https://www.github.com/jfjelstul/worldcup

> Fjelstul, Joshua C. "The Fjelstul World Cup Database v.1.2.0." July 19, 2023.
> https://www.github.com/jfjelstul/worldcup.

**Modifications:** the files in `data/raw/fjelstul/` are byte-for-byte identical to the
source — 16 of the 29 published tables were retrieved, none altered. A full modification
record is maintained in [`LICENSE-DATA.md`](LICENSE-DATA.md), as the licence requires.

The database is provided by its author as-is, with no warranties of any kind.

Data for **2026** comes from the English **Wikipedia**, also under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode). Because
Wikipedia articles change continuously, naming the article is not sufficient
attribution — the 14 exact revision IDs used are listed in
[`LICENSE-DATA.md`](LICENSE-DATA.md), recorded per file in
[`data/raw/metadata.json`](data/raw/metadata.json), and carried per row in the parsed
output's `source_revision` column.

Country polygons come from **Natural Earth** (`ne_50m_admin_0_map_units`), which is in the
**public domain** and therefore imposes no obligation — the attribution below is the one
its makers ask for, and is carried in the published `web/data/countries.geojson`:

> Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com

Venue coordinates come from **Nominatim / OpenStreetMap**, whose data is licensed under the
[ODbL](https://opendatacommons.org/licenses/odbl/) — © OpenStreetMap contributors. The
cached responses are committed at `data/interim/geocode_cache.json` so that reproducing the
pipeline costs the service nothing.

### Built with

[pandas](https://pandas.pydata.org/) ·
[pandera](https://pandera.readthedocs.io/) ·
[rapidfuzz](https://github.com/rapidfuzz/RapidFuzz) ·
[geopy](https://geopy.readthedocs.io/) ·
[requests](https://requests.readthedocs.io/) ·
[Leaflet](https://leafletjs.com/)

Leaflet 1.9.4 is **vendored** into `web/vendor/` rather than loaded from a CDN, so a
clone renders the map offline and the version in git is the version on screen. It keeps
its own BSD 2-Clause licence, reproduced at
[`web/vendor/LEAFLET-LICENSE.txt`](web/vendor/LEAFLET-LICENSE.txt) — neither this
repository's MIT code licence nor its CC BY-SA data licence applies to it.
