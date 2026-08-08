"""Etapa 1b do ETL — scraping da Copa de 2026 (Wikipédia).

Nenhuma base pronta cobre o torneio de 2026, então os dados vêm da Wikipédia.

Este módulo faz **apenas o scraping**: baixa o HTML bruto e guarda em
`data/raw/scraped/`. A extração dos dados de dentro desse HTML é
responsabilidade do `parse_2026.py`. A separação é deliberada:

- corrigir um bug de parsing não exige bater na Wikipédia de novo;
- o parsing fica testável offline, a partir do HTML em cache;
- o HTML em cache é a prova do que a página dizia no momento da coleta.

Conformidade (verificada em 08/08/2026):
- O `robots.txt` da Wikipédia proíbe `/w/` e `/api/` para agentes genéricos,
  mas **não** proíbe artigos em `/wiki/<Título>` — que é o que baixamos aqui.
- User-agent identificável com forma de contato, conforme a política da
  Wikimedia.
- 1 segundo de intervalo entre requisições.
- O `revision_id` de cada página é registrado: a licença CC BY-SA exige
  atribuir a revisão exata, e artigos mudam.

Uso:
    python -m etl.scrape_2026            # baixa o que ainda não está em cache
    python -m etl.scrape_2026 --force    # rebaixa tudo
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests

from etl import provenance
from etl.paths import RAW_SCRAPED, ensure_dirs

WIKI_BASE = "https://en.wikipedia.org/wiki/"
WIKI_LICENSE = "CC BY-SA 4.0"
WIKI_ATTRIBUTION = (
    "Wikipedia contributors, English Wikipedia — https://en.wikipedia.org "
    "(CC BY-SA 4.0)"
)

# A Wikimedia pede um user-agent que identifique o cliente e ofereça contato.
USER_AGENT = (
    "atlas-copa-mundo/0.1 (portfolio data project; "
    "https://github.com/alaindelon96/atlas-copa-mundo)"
)

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 1.0

# As 104 partidas de 2026 não estão em uma página só. São 12 grupos de 4
# seleções (6 partidas cada = 72) mais o mata-mata (32). Verificado em
# 08/08/2026: 72 + 32 = 104, que bate com o infobox do artigo principal.
GROUP_LETTERS = "ABCDEFGHIJKL"

PAGES: list[str] = [
    "2026_FIFA_World_Cup",  # infobox do torneio + tabela de sedes
    *[f"2026_FIFA_World_Cup_Group_{letter}" for letter in GROUP_LETTERS],
    "2026_FIFA_World_Cup_knockout_stage",
]

REVISION_PATTERN = re.compile(r'"wgRevisionId"\s*:\s*(\d+)')


def revision_id(html: str) -> str | None:
    """Extrai o ID da revisão embutido na configuração JS do MediaWiki.

    É o identificador que a CC BY-SA pede para atribuir uma versão específica
    do artigo, e o único jeito de dizer com precisão *qual* texto foi usado.
    """
    match = REVISION_PATTERN.search(html)
    return match.group(1) if match else None


def cache_path(page: str) -> Path:
    return RAW_SCRAPED / f"{page}.html"


def fetch(
    session: requests.Session,
    page: str,
    *,
    force: bool,
) -> tuple[bool, str, str | None]:
    """Baixa uma página e grava no cache.

    Devolve `(baixou, motivo, revision_id)`. Como no `extract.py`, a escrita é
    atômica: grava em `.part` e só então renomeia, para nunca deixar um HTML
    truncado no cache parecendo íntegro.
    """
    destination = cache_path(page)

    if destination.exists() and not force:
        html = destination.read_text(encoding="utf-8")
        return False, "em cache (use --force para rebaixar)", revision_id(html)

    response = session.get(WIKI_BASE + page, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    html = response.text

    temporary = destination.with_suffix(".html.part")
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(destination)

    return True, f"{len(response.content):,} bytes", revision_id(html)


def scrape(*, force: bool) -> int:
    """Baixa todas as páginas. Devolve o número de falhas."""
    registry = provenance.load()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    failures = 0
    print(f"Wikipédia — Copa do Mundo de 2026 — {len(PAGES)} páginas")

    for index, page in enumerate(PAGES, start=1):
        label = f"  [{index:2d}/{len(PAGES)}] {page:<38}"

        try:
            downloaded, reason, revision = fetch(session, page, force=force)
        except requests.RequestException as error:
            print(f"{label} FALHOU — {error}")
            failures += 1
            continue

        provenance.record(
            registry,
            cache_path(page),
            source="wikipedia",
            url=WIKI_BASE + page,
            license_=WIKI_LICENSE,
            attribution=WIKI_ATTRIBUTION,
            extra={"revision_id": revision, "page_title": page.replace("_", " ")},
        )

        status = "OK " if downloaded else "cache"
        print(f"{label} {status} {reason:<34} rev:{revision}")

        if downloaded:
            time.sleep(REQUEST_DELAY)

    provenance.save(registry)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebaixa as páginas mesmo que já estejam em cache",
    )
    args = parser.parse_args()

    ensure_dirs()
    failures = scrape(force=args.force)

    if failures:
        print(f"\n{failures} página(s) falharam. Rode de novo para tentar outra vez.")
        return 1

    print("\nHTML bruto em data/raw/scraped/ — nada foi interpretado ainda.")
    print("Próximo passo: python -m etl.parse_2026")
    return 0


if __name__ == "__main__":
    sys.exit(main())
