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

# Um gol na caixa de partida: minuto, acréscimo opcional e uma marca opcional
# logo depois. A marca gruda no minuto que a precede, não na linha inteira —
# "Fulano 12', 45' (pen.)" é um gol normal e um de pênalti, não dois de pênalti.
RE_GOAL = re.compile(r"(\d+)(?:\s*\+\s*(\d+))?\s*'\s*(?:\(\s*(pen\.|o\.g\.)\s*\))?")


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


def player_pages(cell: Tag) -> dict[str, str]:
    """Nome exibido -> título do artigo, para os links de uma coluna de gols.

    **A caixa de partida abrevia o nome, mas o link não.** O que a coluna mostra
    é o nome curto ("Mbappé", "Quiñones"), e é só isso que sobra depois de ler o
    texto; o `title` da âncora traz o nome inteiro que o artigo tem:

        <a href="/wiki/Kylian_Mbappé"  title="Kylian Mbappé">Mbappé</a>
        <a href="/wiki/Julián_Quiñones" title="Julián Quiñones">Quiñones</a>

    Vale a pena insistir no link em vez de tentar completar o sobrenome depois,
    porque o artigo não é só um nome mais longo — **é a identidade que a fonte
    declara**. Quem decide se o "Ronaldo" de 2026 é o brasileiro ou o português
    é a Wikipédia, no destino do link, e não uma regra nossa de comparar strings.

    Os 308 gols de 2026 têm link, todos os 190 nomes distintos — mas um nome sem
    âncora não é erro (a Wikipédia deixa sem link quem não tem artigo), e nesse
    caso `parse_goals` fica com o nome curto mesmo.
    """
    pages: dict[str, str] = {}
    for anchor in cell.select("a[title]"):
        title = " ".join(str(anchor.get("title", "")).split())
        shown = " ".join(anchor.get_text(" ", strip=True).split())
        if shown and title:
            pages.setdefault(shown, title)
    return pages


def parse_goals(box: Tag) -> list[dict[str, Any]]:
    """Os gols de uma partida, a partir das duas colunas de artilheiros.

    **Esta função existe porque uma suposição do projeto estava errada.** A Etapa
    3 concluiu que dado de jogador teria buraco em 2026 e cortou o escopo para
    "só estatística de jogo". Mas as páginas que o `scrape_2026.py` já baixou
    trazem os artilheiros com minuto: 104 caixas de partida, 308 marcas de
    minuto — exatamente o total que o próprio artigo declara — e as 7 partidas
    sem nome listado são todas 0–0. O buraco nunca existiu; o parser é que não
    olhava.

    O texto de uma coluna encadeia jogadores e minutos:

        Manzambi 74' , 90'                 -> dois gols do mesmo jogador
        Xhaka 90+7' ( pen. )               -> acréscimo e pênalti
        Manai 75' ( o.g. )                 -> gol contra
        Dembélé 7' , 20' , 32' Doué 90+4'  -> dois jogadores na mesma coluna

    **A leitura é pelo texto, não pela lista.** A maioria das colunas embrulha
    cada jogador num `<li>`, mas nem todas — e confiar no `<li>` perdia 6 gols
    em 302, todos em colunas que a Wikipédia deixou como texto solto. O que vale
    em qualquer um dos dois formatos é a alternância: um nome, os minutos dele,
    o próximo nome. Então o parser anda pelos minutos e trata o texto entre dois
    deles como troca de jogador — vazio ou só pontuação significa "mesmo
    jogador".

    **Gol contra fica na coluna de quem ganhou o gol**, que é como a Wikipédia
    (e o placar) contam — por isso `team_side` é o lado da coluna, e o nome do
    jogador é de quem marcou contra. Sem essa distinção a soma dos gols não
    fecharia com o placar.

    O `player_page` que sai junto é o artigo apontado pelo link daquele nome (ver
    `player_pages`): o nome curto é o que a coluna mostra, o artigo é quem ele é.
    """
    goals: list[dict[str, Any]] = []

    for side, selector in (("home", "td.fhgoal"), ("away", "td.fagoal")):
        cell = box.select_one(selector)
        if cell is None:
            continue

        pages = player_pages(cell)
        items = cell.select("li")
        lines = items if items else [cell]

        for item in lines:
            text = " ".join(item.get_text(" ", strip=True).split())
            first = RE_GOAL.search(text)
            if not first:
                continue

            player = text[:first.start()].strip(" ,;·")
            cursor = 0
            for match in RE_GOAL.finditer(text):
                between = text[cursor:match.start()].strip(" ,;·")
                if between:
                    player = between
                cursor = match.end()

                marker = match.group(3) or ""
                goals.append({
                    "team_side": side,
                    "player_name": player,
                    "player_page": pages.get(player, ""),
                    "minute_regulation": int(match.group(1)),
                    "minute_stoppage": int(match.group(2)) if match.group(2) else None,
                    "penalty": int(marker == "pen."),
                    "own_goal": int(marker == "o.g."),
                })
    return goals


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
        # Os gols viajam junto com a partida até o `match_id` existir — ele só é
        # atribuído depois da ordenação, em `parse_matches`. O nome da coluna não
        # começa com underscore porque o `itertuples` renomeia essas para `_13`.
        record["goal_events"] = parse_goals(box)
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
    return frame[columns], build_goals(frame)


def build_goals(matches: pd.DataFrame) -> pd.DataFrame:
    """Espalha os gols que viajaram com cada partida numa tabela própria.

    O `team_side` vira nome de seleção aqui, onde a partida ainda está à mão —
    depois disso a coluna não teria como ser resolvida sem um join de volta.

    As duas colunas de nome saem lado a lado de propósito: `player_name` é o que
    a caixa de partida exibiu e `player_page`, o artigo para onde ela apontou.
    Guardar as duas mantém este arquivo fiel à página — quem escolhe rótulo e
    identidade é o `etl.model`, e essa escolha fica revisável sem re-raspar nada.
    """
    rows: list[dict[str, Any]] = []
    for match in matches.itertuples():
        for order, goal in enumerate(match.goal_events or [], start=1):
            rows.append({
                "tournament_id": TOURNAMENT_ID,
                "match_id": match.match_id,
                "match_date": match.match_date,
                "goal_order": order,
                "team_name": (match.home_team_name if goal["team_side"] == "home"
                              else match.away_team_name),
                "opponent_name": (match.away_team_name if goal["team_side"] == "home"
                                  else match.home_team_name),
                "home_away": goal["team_side"],
                "player_name": goal["player_name"],
                "player_page": goal["player_page"],
                "minute_regulation": goal["minute_regulation"],
                "minute_stoppage": goal["minute_stoppage"],
                "penalty": goal["penalty"],
                "own_goal": goal["own_goal"],
                "source_page": match.source_page,
                "source_revision": match.source_revision,
            })
    return pd.DataFrame(rows)


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
    matches, goals_frame = parse_matches()
    venues = parse_venues()

    write(tournament, "tournament_2026.csv")
    write(matches, "matches_2026.csv")
    write(venues, "venues_2026.csv")
    write(goals_frame, "goals_2026.csv")

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
        # Os artilheiros extraídos têm que dar o mesmo total que os placares. É a
        # conferência que separa "achei nomes" de "achei todos os gols": um
        # jogador esquecido numa linha some sem erro nenhum.
        ("gols com autor", len(goals_frame), expected_goals),
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
