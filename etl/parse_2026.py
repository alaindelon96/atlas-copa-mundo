"""Etapa 1b (parte 2) — parsing do HTML da Copa de 2026.

Lê o HTML que o `scrape_2026.py` deixou em `data/raw/scraped/` e extrai dados
estruturados para `data/interim/`. **Não faz nenhuma requisição de rede** — roda
offline, o que o torna testável e rápido de iterar.

Saídas:
    data/interim/matches_2026.csv      104 partidas
    data/interim/venues_2026.csv       16 sedes
    data/interim/tournament_2026.csv   1 linha, dados do torneio

Cada página tem um papel definido, o que evita duplicatas na origem em vez de
removê-las depois: o artigo principal duplica as 32 partidas do mata-mata que
já estão na página do knockout. Aqui, o principal serve só para o infobox e as
sedes; os grupos entregam as 72 partidas de grupo; o knockout, as 32 restantes.

Notas de parsing (verificadas no HTML em cache, 08/08/2026):
- A fase vem do cabeçalho `h2` anterior à partida. Rastrear `h3` também
  quebraria: no mata-mata cada partida tem um `h3` com o próprio nome
  ("Canada vs Morocco"), que sobrescreveria a fase.
- Pênaltis não aparecem no `.fscore`; ficam no texto do box, depois da palavra
  "Penalties", entre as duas listas de cobradores.
- Os placares usam travessão (–, U+2013), não hífen.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from bs4 import BeautifulSoup, Tag

from etl.paths import INTERIM, RAW_SCRAPED, ensure_dirs

TOURNAMENT_ID = "WC-2026"
TOURNAMENT_NAME = "2026 FIFA Men's World Cup"

MAIN_PAGE = "2026_FIFA_World_Cup"
KNOCKOUT_PAGE = "2026_FIFA_World_Cup_knockout_stage"
GROUP_LETTERS = "ABCDEFGHIJKL"

# Travessão e hífen: aceitar os dois, para não quebrar se a Wikipédia mudar.
DASH = r"[–-]"

RE_ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
RE_SCORE = re.compile(rf"(\d+)\s*{DASH}\s*(\d+)")
RE_PENALTIES = re.compile(rf"Penalties.*?(\d+)\s*{DASH}\s*(\d+)", re.S)
RE_ATTENDANCE = re.compile(r"Attendance:\s*([\d,]+)")
RE_REFEREE = re.compile(r"Referee:\s*([^(]+?)\s*\(")
RE_REVISION = re.compile(r'"wgRevisionId"\s*:\s*(\d+)')


def text_of(node: Tag | None) -> str:
    """Texto normalizado de um nó, com espaços colapsados."""
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def load_page(page: str) -> tuple[BeautifulSoup, str, str | None]:
    """Carrega uma página do cache. Devolve (soup, html, revision_id)."""
    path = RAW_SCRAPED / f"{page}.html"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} não existe. Rode `python -m etl.scrape_2026` primeiro."
        )
    html = path.read_text(encoding="utf-8")
    revision = RE_REVISION.search(html)
    return BeautifulSoup(html, "lxml"), html, revision.group(1) if revision else None


def iter_matches_with_stage(soup: BeautifulSoup) -> Iterator[tuple[Tag, str | None]]:
    """Percorre o documento em ordem, associando cada partida ao seu `h2`.

    Só `h2` conta como fase — ver a nota no topo do módulo.
    """
    content = soup.select_one("div.mw-parser-output") or soup
    stage: str | None = None
    for element in content.find_all(["div", "h2"], recursive=True):
        if element.name == "h2":
            heading = element.get_text(strip=True)
            if heading:
                stage = heading
        elif "footballbox" in (element.get("class") or []):
            yield element, stage


def parse_match(box: Tag) -> dict[str, Any]:
    """Extrai um registro de partida de um `div.footballbox`."""
    full_text = " ".join(box.get_text(" ", strip=True).split())

    score_text = text_of(box.select_one(".fscore"))
    score_match = RE_SCORE.search(score_text)
    home_score = int(score_match.group(1)) if score_match else None
    away_score = int(score_match.group(2)) if score_match else None

    # O bloco da direita concentra sede, cidade, público e árbitro.
    right = text_of(box.select_one(".fright"))
    stadium, city = "", ""
    if right:
        head = RE_ATTENDANCE.split(right)[0]
        parts = [p.strip() for p in head.split(",", 1)]
        stadium = parts[0]
        if len(parts) > 1:
            city = parts[1].strip(" ,")

    attendance = RE_ATTENDANCE.search(right)
    referee = RE_REFEREE.search(right)

    extra_time = "a.e.t" in score_text
    penalties = RE_PENALTIES.search(full_text) if "Penalties" in full_text else None

    # A data legível por máquina fica no microformato `.bday` que o MediaWiki
    # emite dentro do `.fdate` ("June 28, 2026 (2026-06-28)"). Preferir o span
    # a aplicar regex no texto exibido: o texto varia com idioma e formatação.
    bday = box.select_one(".fdate .bday") or box.select_one(".bday")
    date_iso = RE_ISO_DATE.search(text_of(bday) or text_of(box.select_one(".fdate")))

    home = text_of(box.select_one(".fhome"))
    away = text_of(box.select_one(".faway"))

    return {
        "match_name": f"{home} vs {away}" if home and away else "",
        "match_date": date_iso.group(1) if date_iso else None,
        "match_time": text_of(box.select_one(".ftime")),
        "home_team_name": home,
        "away_team_name": away,
        "score": f"{home_score}–{away_score}" if score_match else "",
        "home_team_score": home_score,
        "away_team_score": away_score,
        "extra_time": int(extra_time),
        "penalty_shootout": int(bool(penalties)),
        "home_team_score_penalties": int(penalties.group(1)) if penalties else None,
        "away_team_score_penalties": int(penalties.group(2)) if penalties else None,
        "stadium_name": stadium,
        "city_name": city,
        "attendance": int(attendance.group(1).replace(",", "")) if attendance else None,
        "referee": referee.group(1).strip() if referee else "",
    }


def parse_page_matches(page: str, *, group_name: str = "") -> list[dict[str, Any]]:
    """Extrai todas as partidas de uma página do cache."""
    soup, _, revision = load_page(page)
    records = []
    for box, stage in iter_matches_with_stage(soup):
        record = parse_match(box)
        record["stage_name"] = "group stage" if group_name else (stage or "")
        record["group_name"] = group_name
        record["source_page"] = page
        record["source_revision"] = revision
        records.append(record)
    return records


def parse_matches() -> pd.DataFrame:
    """Monta as 104 partidas: 72 dos grupos + 32 do mata-mata."""
    records: list[dict[str, Any]] = []

    for letter in GROUP_LETTERS:
        page = f"2026_FIFA_World_Cup_Group_{letter}"
        records.extend(parse_page_matches(page, group_name=f"Group {letter}"))

    records.extend(parse_page_matches(KNOCKOUT_PAGE))

    frame = pd.DataFrame(records)
    frame.insert(0, "tournament_id", TOURNAMENT_ID)
    frame.insert(1, "tournament_name", TOURNAMENT_NAME)

    # Ordenar por data dá um match_id estável entre execuções.
    frame = frame.sort_values(["match_date", "match_time", "home_team_name"])
    frame = frame.reset_index(drop=True)
    frame.insert(2, "match_id", [f"M-2026-{i:03d}" for i in range(1, len(frame) + 1)])

    columns = [
        "tournament_id", "tournament_name", "match_id", "match_name",
        "stage_name", "group_name", "match_date", "match_time",
        "stadium_name", "city_name",
        "home_team_name", "away_team_name", "score",
        "home_team_score", "away_team_score",
        "extra_time", "penalty_shootout",
        "home_team_score_penalties", "away_team_score_penalties",
        "attendance", "referee", "source_page", "source_revision",
    ]
    return frame[columns]


def parse_venues() -> pd.DataFrame:
    """Extrai a tabela de sedes do artigo principal.

    A tabela é localizada pelas colunas que ela contém, não por índice: o
    artigo tem 95 tabelas e a posição delas muda a cada edição da página.
    """
    _, html, revision = load_page(MAIN_PAGE)
    tables = pd.read_html(io.StringIO(html))

    for table in tables:
        columns = {str(c) for c in table.columns}
        if any("Stadium" in c for c in columns) and any("Capacity" in c for c in columns):
            venues = table.copy()
            break
    else:
        raise ValueError("Tabela de sedes não encontrada no artigo principal.")

    rename = {}
    for column in venues.columns:
        name = str(column)
        if "City" in name:
            rename[column] = "city_raw"
        elif "Stadium" in name:
            rename[column] = "stadium_raw"
        elif "Capacity" in name:
            rename[column] = "capacity"
        elif "Number of matches" in name:
            rename[column] = "matches_raw"
    venues = venues.rename(columns=rename)
    venues = venues[[c for c in ["city_raw", "stadium_raw", "capacity", "matches_raw"]
                     if c in venues.columns]]

    # "Mexico City" / "Dallas (Arlington, Texas)" -> nome antes do parêntese.
    venues["city_name"] = (
        venues["city_raw"].astype(str).str.split("(").str[0].str.strip()
    )
    # "AT&T Stadium‡ (Dallas Stadium)" -> tirar apelido de patrocínio e marcadores.
    venues["stadium_name"] = (
        venues["stadium_raw"].astype(str)
        .str.split("(").str[0]
        .str.replace(r"[†‡*\[\]A-Z]?$", "", regex=True)
        .str.strip(" †‡*")
        .str.strip()
    )
    venues.insert(0, "tournament_id", TOURNAMENT_ID)
    venues["source_page"] = MAIN_PAGE
    venues["source_revision"] = revision

    return venues[["tournament_id", "city_name", "stadium_name", "capacity",
                   "city_raw", "stadium_raw", "source_page", "source_revision"]]


def parse_tournament() -> pd.DataFrame:
    """Extrai o infobox do artigo principal: campeão, vice, totais."""
    soup, _, revision = load_page(MAIN_PAGE)
    infobox = soup.select_one("table.infobox")
    if infobox is None:
        raise ValueError("Infobox não encontrado no artigo principal.")

    fields: dict[str, str] = {}
    for row in infobox.select("tr"):
        header, cell = row.find("th"), row.find("td")
        if header and cell:
            fields[text_of(header)] = text_of(cell)

    def number(key: str) -> int | None:
        raw = fields.get(key, "")
        found = re.search(r"[\d,]+", raw)
        return int(found.group().replace(",", "")) if found else None

    record = {
        "tournament_id": TOURNAMENT_ID,
        "tournament_name": TOURNAMENT_NAME,
        "year": 2026,
        "host_countries": fields.get("Host countries", ""),
        "winner": re.sub(r"\s*\(.*", "", fields.get("Champions", "")),
        "runner_up": fields.get("Runners-up", ""),
        "third_place": fields.get("Third place", ""),
        "fourth_place": fields.get("Fourth place", ""),
        "count_teams": number("Teams"),
        "count_venues": number("Venues"),
        "count_matches": number("Matches played"),
        "count_goals": number("Goals scored"),
        "attendance_total": number("Attendance"),
        "top_scorer": fields.get("Top scorer", ""),
        "best_player": fields.get("Best player", ""),
        "source_page": MAIN_PAGE,
        "source_revision": revision,
    }
    return pd.DataFrame([record])


def write(frame: pd.DataFrame, name: str) -> Path:
    path = INTERIM / name
    frame.to_csv(path, index=False, encoding="utf-8")
    print(f"  {name:<24} {len(frame):>4} linhas -> {path.relative_to(INTERIM.parent.parent)}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    ensure_dirs()
    print("Parsing do HTML em cache (nenhuma requisição de rede)")

    tournament = parse_tournament()
    matches = parse_matches()
    venues = parse_venues()

    write(tournament, "tournament_2026.csv")
    write(matches, "matches_2026.csv")
    write(venues, "venues_2026.csv")

    # Conferir o parsing contra os totais que o próprio infobox declara.
    print("\nConferência com o infobox:")
    expected_matches = tournament.at[0, "count_matches"]
    expected_goals = tournament.at[0, "count_goals"]
    expected_venues = tournament.at[0, "count_venues"]
    goals = int(matches[["home_team_score", "away_team_score"]].sum().sum())

    checks = [
        ("partidas", len(matches), expected_matches),
        ("gols", goals, expected_goals),
        ("sedes", len(venues), expected_venues),
    ]
    failed = 0
    for label, got, expected in checks:
        ok = got == expected
        failed += not ok
        print(f"  {'OK ' if ok else 'ERRO'} {label:<10} extraído={got:<6} infobox={expected}")

    if failed:
        print(f"\n{failed} verificação(ões) falharam — o parsing não bate com a fonte.")
        return 1

    print("\nParsing concluído e conferido contra a própria fonte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
