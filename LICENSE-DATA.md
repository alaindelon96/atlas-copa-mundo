# Data licence — CC BY-SA 4.0

The **data** in this repository is licensed differently from the **code**.
See [`LICENSE`](LICENSE) for the code (MIT).

Everything in `data/` and `web/data/` is derived from sources published under the
**Creative Commons Attribution-ShareAlike 4.0 International licence**, so under that
licence's ShareAlike term this repository's derived data carries the same licence:

> **CC BY-SA 4.0** — https://creativecommons.org/licenses/by-sa/4.0/legalcode

Per section 3(a)(1) of that licence, a hyperlink to the licence text is sufficient
attribution of the licence itself; the full legal text is therefore linked rather
than reproduced here.

---

## Source 1 — The Fjelstul World Cup Database

All match, tournament, team, venue, goal and award data in this repository
originates from the Fjelstul World Cup Database.

- **Author:** Joshua C. Fjelstul, Ph.D.
- **Copyright:** © 2023 Joshua C. Fjelstul, Ph.D.
- **Licence:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode)
- **Source:** https://www.github.com/jfjelstul/worldcup

**Citation:**

> Fjelstul, Joshua C. "The Fjelstul World Cup Database v.1.2.0." July 19, 2023.
> https://www.github.com/jfjelstul/worldcup.

### Modifications made to this source

The CC BY-SA 4.0 licence requires that modifications be indicated. As of
**2026-08-08**:

| Location | Modified? | Detail |
|---|---|---|
| `data/raw/fjelstul/` | **No** | Byte-for-byte identical to the source. SHA-256 of every file is recorded in [`data/raw/metadata.json`](data/raw/metadata.json) and is independently verifiable against the origin. |
| Subset selection | **Yes** | 16 of the 29 published tables were retrieved; the other 13 were not. No table was altered. The list is in [`etl/extract.py`](etl/extract.py). |
| `data/processed/`, `web/data/` | **Yes — derived works** | Detailed below. |

The derived data published in `data/processed/` and `web/data/` applies these
transformations to the source. Nothing is edited in place; every change adds a
column or a table, and the original values are preserved alongside:

| Transformation | Detail |
|---|---|
| Men's/women's split | An explicit `competition` column derived from `tournament_name`. The source's `tournament_id` does not distinguish them. |
| Scope filter | The published model and map cover the **men's** tournament only (1,068 of the 1,352 matches). The women's data is retained unmodified in `data/processed/matches_clean.csv`; it is excluded from the derived tables, not deleted. |
| Historical name reconciliation | National-team names mapped to modern labels (West Germany, Soviet Union, Yugoslavia, Czechoslovakia, Zaire, Dutch East Indies…) via the curated map in [`reference/team_succession.csv`](reference/team_succession.csv). The names as recorded at the time are preserved in the `home_team_raw` / `away_team_raw` columns. |
| Stage-name normalisation | The source itself carries both `quarter-final` and `quarter-finals`; these were collapsed to one spelling. |
| Sentinel values converted to nulls | Penalty scores recorded as `0–0` for the 1,205 matches with no shootout, and the string `"not applicable"` in `group_name` for 332 knockout matches, became true nulls. |
| Host country as a table | `tournaments.host_country` (a single column, holding `"Korea, Japan"` for 2002) was replaced by a `tournament_hosts` table derived from the venues where matches took place. |
| Venue coordinates added | Latitude/longitude from Nominatim (OpenStreetMap, ODbL). This is added data, not altered data — see the note on mixed licensing below. |
| Country polygons added | `web/data/countries.geojson` is Natural Earth (public domain) with a `team` property joined on. It contains no Fjelstul data. |
| Aggregation | `web/data/metrics.json` and `head2head.json` are statistics computed from the match table. `web/data/timeline.json` is the same match table rewritten losslessly in columnar form (names replaced by indices) so the map's year-range slider can re-aggregate it in the browser. |

**Editorial decision, stated because it is a choice and not a cleanup:** where a
historic team resolves to a modern label, the **label governs the records**. West
Germany's matches count as Germany's. The one visible consequence is that the 1974
match East Germany 1–0 West Germany appears as `Germany × Germany`. Title counts
follow the same rule and are unchanged by it, since no entity treated this way ever
won the tournament. The reasoning is in [`docs/schema.md`](docs/schema.md).

**Mixed licensing note:** `data/processed/venues.csv` combines venue names from
Fjelstul (CC BY-SA 4.0) with coordinates from OpenStreetMap (ODbL). Both licences
are share-alike, and both are honoured: reuse of that file must credit both sources
and carry the corresponding terms.

The database is provided by its author as-is and as-available, with no
representations or warranties of any kind. That disclaimer is passed through here
unchanged.

---

## Source 2 — Wikipedia (2026 tournament)

Data for the 2026 tournament — which no published dataset covers — is derived from
the English Wikipedia, whose text is published under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode).

- **Author:** Wikipedia contributors
- **Licence:** [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/legalcode)
- **Source:** https://en.wikipedia.org

Wikipedia articles change continuously, so naming the article is not sufficient
attribution — the **exact revision** must be identified. These are the revisions
retrieved on **2026-08-08** and used to produce the 2026 data:

| Article | Revision ID | Permanent link |
|---|---|---|
| 2026 FIFA World Cup | `1368037326` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368037326) |
| 2026 FIFA World Cup Group A | `1368129117` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368129117) |
| 2026 FIFA World Cup Group B | `1368282937` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368282937) |
| 2026 FIFA World Cup Group C | `1368283749` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368283749) |
| 2026 FIFA World Cup Group D | `1368284732` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368284732) |
| 2026 FIFA World Cup Group E | `1368284951` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368284951) |
| 2026 FIFA World Cup Group F | `1368285128` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368285128) |
| 2026 FIFA World Cup Group G | `1368285341` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368285341) |
| 2026 FIFA World Cup Group H | `1368285642` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368285642) |
| 2026 FIFA World Cup Group I | `1368283456` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368283456) |
| 2026 FIFA World Cup Group J | `1368286276` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368286276) |
| 2026 FIFA World Cup Group K | `1368286465` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368286465) |
| 2026 FIFA World Cup Group L | `1368283601` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368283601) |
| 2026 FIFA World Cup knockout stage | `1368128792` | [permalink](https://en.wikipedia.org/w/index.php?oldid=1368128792) |

These revision IDs are also recorded per-file in
[`data/raw/metadata.json`](data/raw/metadata.json), and carried per-row in the
`source_page` and `source_revision` columns of the parsed output — so any single
figure in the 2026 data can be traced back to the exact article revision it came
from.

### Modifications made to this source

The article HTML in `data/raw/scraped/` is stored unmodified. Data was extracted
from it — match results, venues and tournament totals restructured into tabular
form — but no source text was altered. Prose, references and formatting were
discarded rather than changed.

---

## Original work in this repository

Two files are **not** derived from any source above — they are curated by hand for this
project and are covered by the repository's own licences:

- [`reference/team_colors.csv`](reference/team_colors.csv) — each national team's map
  colour. The rule is the home shirt of the last World Cup that team played (the
  `last_cup` column, checked against the model); where that shirt is white or black —
  neither can carry a sequential ramp — the chromatic colour that identifies the side,
  marked `identity` with the reasoning in the row. These are editorial judgements about
  kit colour, not facts from any dataset above, and they are approximations of a shirt
  rather than verified brand values.
- [`web/data/colors.json`](web/data/colors.json) — the ramps generated from that table by
  [`etl/color.py`](etl/color.py).

---

## Third-party code bundled in this repository

The map depends on Leaflet, and this repository **vendors** it at
`web/vendor/leaflet.js` and `web/vendor/leaflet.css` instead of loading it from a
CDN. That is a deliberate choice — a clone keeps working offline, and the version
that renders the map is the version recorded in git — but it means redistributing
someone else's code, which carries its own obligation:

- **Leaflet 1.9.4** — © 2010–2023 Volodymyr Agafonkin, © 2010–2011 CloudMade
- **Licence:** BSD 2-Clause, reproduced in full at
  [`web/vendor/LEAFLET-LICENSE.txt`](web/vendor/LEAFLET-LICENSE.txt)
- **Source:** https://github.com/Leaflet/Leaflet

The files are byte-for-byte as published on unpkg; neither was modified. Leaflet is
**not** covered by this repository's MIT licence or by the CC BY-SA 4.0 data
licence — it keeps its own.

The map also vendors **83 national flag SVGs** at `web/vendor/flags/`, one per team:

- **circle-flags** — © HatScripts
- **Licence:** MIT, reproduced at
  [`web/vendor/flags/LICENSE.md`](web/vendor/flags/LICENSE.md)
- **Source:** https://github.com/HatScripts/circle-flags

Only the 83 files this map actually uses were retrieved, unmodified; the set is
selected by the `iso_a2` column of
[`reference/team_country.csv`](reference/team_country.csv), which comes from Natural
Earth. This set was chosen over flag emoji because emoji flags depend on system fonts
and **Windows ships none**, and over a larger flag set because its coats of arms cost
723 KB against 146 KB here for detail invisible at 16px. It also carries `gb-nir`,
which Unicode has never defined as an emoji — so Northern Ireland has a flag.

Country outlines come from **Natural Earth**, which is public domain; the map
credits it in the attribution control, as its terms request rather than require.

---

## What this means if you reuse this repository

You may copy, redistribute, remix and build on this data, including commercially,
provided you:

1. **Give attribution** — credit Joshua C. Fjelstul as above, link the licence, and
   link the original source.
2. **Indicate changes** — state what you altered.
3. **Share alike** — license anything you build from it under CC BY-SA 4.0.
