"""Etapa 1 do ETL — extração dos datasets prontos.

Baixa os CSVs originais para `data/raw/`, sem nenhuma alteração de conteúdo, e
registra a proveniência de cada arquivo em `data/raw/metadata.json`.

A regra do projeto é que `data/raw/` é imutável: nada aqui é editado à mão e
nenhuma limpeza acontece nesta etapa. Toda transformação vive em `transform.py`,
lendo daqui e escrevendo em `data/interim/` ou `data/processed/`.

Uso:
    python -m etl.extract              # baixa o que ainda falta
    python -m etl.extract --force      # rebaixa tudo, mesmo se já existir
    python -m etl.extract --check      # só verifica se a fonte mudou (sem gravar)
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import requests

from etl import provenance
from etl.paths import RAW_FJELSTUL, ROOT, ensure_dirs

# ---------------------------------------------------------------------------
# Fonte primária: Fjelstul World Cup Database (1930–2022 masc. e 1991–2019 fem.)
# ---------------------------------------------------------------------------

FJELSTUL_BASE = "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/"
FJELSTUL_LICENSE = "CC BY-SA 4.0"
FJELSTUL_ATTRIBUTION = (
    "Joshua C. Fjelstul, The World Cup Database — https://github.com/jfjelstul/worldcup"
)

# Subconjunto curado: as tabelas necessárias para o mapa e para as estatísticas
# do v1. As tabelas de eventos individuais (player_appearances, squads,
# substitutions, bookings, referees) somam ~9 MB e não entram no escopo atual —
# basta acrescentar o nome aqui se um dia forem necessárias.
FJELSTUL_DATASETS = [
    "tournaments.csv",  # um registro por edição da Copa
    "tournament_stages.csv",  # fases disputadas em cada edição
    "tournament_standings.csv",  # classificação final (1º ao 4º)
    "host_countries.csv",  # país-sede e desempenho do anfitrião
    "matches.csv",  # tabela central: uma linha por partida
    "teams.csv",  # seleções, com federação e confederação
    "stadiums.csv",  # sedes (sem lat/long — geocodificar na etapa 3)
    "goals.csv",  # um registro por gol, com autor e minuto
    "penalty_kicks.csv",  # cobranças em disputas por pênaltis
    "awards.csv",  # catálogo de prêmios (Bola de Ouro, Chuteira de Ouro...)
    "award_winners.csv",  # vencedores por edição
    "team_appearances.csv",  # desempenho de cada seleção por partida
    "groups.csv",  # grupos da fase de grupos
    "group_standings.csv",  # classificação dentro de cada grupo
    "qualified_teams.csv",  # seleções classificadas por edição
    "confederations.csv",  # CONMEBOL, UEFA, CAF...
]

USER_AGENT = (
    "atlas-copa-mundo/0.1 (projeto de portfólio de análise de dados; "
    "contato via GitHub)"
)

REQUEST_TIMEOUT = 30
REQUEST_DELAY = 0.5  # segundos entre downloads, para não martelar a origem


def download(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    force: bool,
) -> tuple[bool, str]:
    """Baixa `url` para `destination`.

    Devolve `(baixou, motivo)`. Se o arquivo já existe e `force` é False, o
    download é pulado — isso torna a execução repetida barata e evita tráfego
    desnecessário contra a fonte.

    A escrita é feita primeiro em um arquivo temporário e só então renomeada, para
    que uma interrupção no meio do download não deixe um CSV truncado em
    `data/raw/` parecendo válido.
    """
    if destination.exists() and not force:
        return False, "já existe (use --force para rebaixar)"

    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(response.content)
    temporary.replace(destination)
    return True, f"{len(response.content):,} bytes"


def extract_fjelstul(*, force: bool) -> int:
    """Baixa o subconjunto curado do Fjelstul. Devolve o número de falhas."""
    registry = provenance.load()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    failures = 0
    print(f"Fjelstul World Cup Database — {len(FJELSTUL_DATASETS)} arquivos")

    for index, filename in enumerate(FJELSTUL_DATASETS, start=1):
        url = FJELSTUL_BASE + filename
        destination = RAW_FJELSTUL / filename
        label = f"  [{index:2d}/{len(FJELSTUL_DATASETS)}] {filename:<26}"

        try:
            downloaded, reason = download(session, url, destination, force=force)
        except requests.RequestException as error:
            print(f"{label} FALHOU — {error}")
            failures += 1
            continue

        entry = provenance.record(
            registry,
            destination,
            source="fjelstul-worldcup",
            url=url,
            license_=FJELSTUL_LICENSE,
            attribution=FJELSTUL_ATTRIBUTION,
        )
        status = "OK " if downloaded else "pulado"
        print(f"{label} {status} {reason}  sha256:{entry['sha256'][:12]}")

        if downloaded:
            time.sleep(REQUEST_DELAY)

    provenance.save(registry)
    return failures


def check_fjelstul() -> int:
    """Compara o hash remoto com o registrado, sem gravar nada.

    Útil para descobrir se a fonte foi atualizada desde o último download —
    é o gancho natural para automatizar o pipeline com GitHub Actions depois.
    Devolve o número de arquivos divergentes.
    """
    registry = provenance.load()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    changed = 0
    for filename in FJELSTUL_DATASETS:
        key = (RAW_FJELSTUL / filename).relative_to(ROOT).as_posix()
        known = registry["files"].get(key)
        if known is None:
            print(f"  {filename:<26} ainda não baixado")
            changed += 1
            continue

        response = session.get(FJELSTUL_BASE + filename, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        remote = hashlib.sha256(response.content).hexdigest()
        if remote == known["sha256"]:
            print(f"  {filename:<26} inalterado")
        else:
            print(f"  {filename:<26} MUDOU na origem")
            changed += 1
        time.sleep(REQUEST_DELAY)

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebaixa os arquivos mesmo que já existam em data/raw/",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="apenas verifica se a fonte mudou desde o último download",
    )
    args = parser.parse_args()

    ensure_dirs()

    if args.check:
        changed = check_fjelstul()
        print(f"\n{changed} arquivo(s) divergente(s) da cópia local.")
        return 0

    failures = extract_fjelstul(force=args.force)

    if failures:
        print(f"\n{failures} arquivo(s) falharam. Rode de novo para tentar outra vez.")
        return 1

    print(f"\nExtração concluída. Proveniência em data/raw/metadata.json")
    print("Próximo passo: scraping da Copa 2026 (python -m etl.scrape_2026)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
