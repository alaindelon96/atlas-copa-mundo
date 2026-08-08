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
**2026-08-07**:

| Location | Modified? | Detail |
|---|---|---|
| `data/raw/fjelstul/` | **No** | Byte-for-byte identical to the source. SHA-256 of every file is recorded in [`data/raw/metadata.json`](data/raw/metadata.json) and is independently verifiable against the origin. |
| Subset selection | **Yes** | 16 of the 29 published tables were retrieved; the other 13 were not. No table was altered. The list is in [`etl/extract.py`](etl/extract.py). |
| `data/interim/`, `data/processed/`, `web/data/` | **Not yet produced** | When these are generated, the transformations applied will be recorded here and in the commit history. |

Planned modifications, not yet applied: normalising national-team names across
historical successions (e.g. West Germany, Soviet Union, Yugoslavia, Zaire),
adding an explicit men's/women's `competition` column, geocoding venues to
latitude/longitude, and deriving aggregate statistics.

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

## What this means if you reuse this repository

You may copy, redistribute, remix and build on this data, including commercially,
provided you:

1. **Give attribution** — credit Joshua C. Fjelstul as above, link the licence, and
   link the original source.
2. **Indicate changes** — state what you altered.
3. **Share alike** — license anything you build from it under CC BY-SA 4.0.
