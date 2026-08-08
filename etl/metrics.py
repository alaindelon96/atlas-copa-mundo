"""Etapa 3 (parte 1) — métricas do mapa coroplético.

Transforma `data/processed/matches_clean.csv` no que o front-end consome:

    web/data/metrics.json    uma entrada por seleção, com as 6 métricas
    web/data/head2head.json  matriz de confrontos diretos

O desenho do mapa (decidido em 08/08/2026) tem dois seletores — métrica e país
— e o modo de país repinta o mapa por confronto direto. Ambos os arquivos são
pré-computados aqui porque o front-end não faz nenhuma agregação: se um número
estiver errado no mapa, o bug está neste arquivo, não no JavaScript.

Duas decisões do projeto estão implementadas aqui:

1. **Total e por partida, os dois.** Contagem bruta num coroplético reproduz
   sobretudo "quem se classificou mais vezes": a Alemanha tem 248 gols e o
   Brasil 247 porque os dois jogaram ~120 partidas. Por partida, a Hungria
   lidera com 2,72 e nem aparece no top 10 bruto. Por isso toda métrica sai nas
   duas formas, com piso de `PER_MATCH_FLOOR` partidas na versão por partida.

2. **O Reino Unido são quatro seleções.** Inglaterra, Escócia, País de Gales e
   Irlanda do Norte entram separadas, como estão no dado. A junção viraria uma
   "seleção do Reino Unido" que nunca existiu.

Uso:
    python -m etl.metrics
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from etl.paths import INTERIM, PROCESSED, RAW_FJELSTUL, ROOT, WEB_DATA, ensure_dirs

# Abaixo deste número de partidas, a média por partida não é comparável: uma
# seleção com 3 jogos passaria o Brasil por acidente amostral.
PER_MATCH_FLOOR = 10

GROUP_STAGES = {"group stage", "second group stage"}


def to_long(matches: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (partida, seleção).

    A tabela de partidas tem duas seleções por linha; quase toda métrica quer o
    contrário. Empilhar mandante e visitante uma vez aqui evita repetir a mesma
    dobra em cada agregação — e evita o erro clássico de contar só os mandantes.
    """
    shared = ["tournament_id", "competition", "year", "stage", "country_name",
              "stadium_name", "city_name", "penalty_shootout"]
    home = matches.rename(columns={
        "home_team": "team", "away_team": "opponent",
        "home_team_score": "gf", "away_team_score": "ga",
        "home_team_score_penalties": "pf", "away_team_score_penalties": "pa"})
    away = matches.rename(columns={
        "away_team": "team", "home_team": "opponent",
        "away_team_score": "gf", "home_team_score": "ga",
        "away_team_score_penalties": "pf", "home_team_score_penalties": "pa"})
    cols = shared + ["team", "opponent", "gf", "ga", "pf", "pa"]
    return pd.concat([home[cols], away[cols]], ignore_index=True)


def outcome(row: pd.Series) -> str:
    """V, E ou D — resolvendo disputas por pênaltis.

    No mata-mata um 1–1 não é empate: alguém avançou. Tratar o placar do tempo
    normal como resultado final daria empates que não existiram e tiraria
    vitórias reais de quem passou nos pênaltis.
    """
    if row.gf > row.ga:
        return "W"
    if row.gf < row.ga:
        return "L"
    if row.penalty_shootout == 1:
        return "W" if row.pf > row.pa else "L"
    return "D"


def titles_by_team() -> dict[str, dict[str, int]]:
    """Títulos por seleção e competição, com o mapa de sucessão aplicado.

    Vem de `tournament_standings.csv`, não das finais: a Copa de 1950 não teve
    final, e derivar campeão do `stage == "final"` perderia aquela edição em
    silêncio (ver `transform.titles_table`).
    """
    succession = pd.read_csv(ROOT / "reference" / "team_succession.csv")
    merges = dict(zip(succession.historic_name, succession.merge_records))
    labels = dict(zip(succession.historic_name, succession.display_name))

    standings = pd.read_csv(RAW_FJELSTUL / "tournament_standings.csv")
    comp = standings.tournament_name.str.extract(r"(Men's|Women's)")[0]
    standings["competition"] = comp.map({"Men's": "mens", "Women's": "womens"})
    champions = standings[standings.position == 1][["competition", "team_name"]]

    modern = pd.read_csv(INTERIM / "tournament_2026.csv")
    champions = pd.concat([champions, pd.DataFrame(
        {"competition": ["mens"] * len(modern), "team_name": modern.winner})])

    counts: dict[str, dict[str, int]] = {}
    for competition, raw in champions.itertuples(index=False):
        name = labels[raw] if merges.get(raw, 0) == 1 else raw
        counts.setdefault(competition, {}).setdefault(name, 0)
        counts[competition][name] += 1
    return counts


def build_metrics(long: pd.DataFrame, matches: pd.DataFrame) -> list[dict]:
    """As seis métricas, por seleção e competição."""
    titles = titles_by_team()

    # "Partidas recebidas" é a única métrica que não olha para a seleção, e sim
    # para o país onde se jogou. As 104 partidas de 2026 ainda estão sem
    # country_name, então a métrica sai incompleta e o JSON diz isso.
    received = (matches.dropna(subset=["country_name"])
                .groupby(["competition", "country_name"]).size())

    rows = []
    for (competition, team), block in long.groupby(["competition", "team"]):
        played = len(block)
        wins = int((block.res == "W").sum())
        draws = int((block.res == "D").sum())
        losses = int((block.res == "L").sum())
        goals = int(block.gf.sum())
        conceded = int(block.ga.sum())

        rows.append({
            "team": team,
            "competition": competition,
            "goals": goals,
            "conceded": conceded,
            "goal_difference": goals - conceded,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_pct": round(100 * wins / played, 1),
            "matches_played": played,
            "matches_received": int(received.get((competition, team), 0)),
            "titles": titles.get(competition, {}).get(team, 0),
            "participations": int(block.year.nunique()),
            "first_year": int(block.year.min()),
            "last_year": int(block.year.max()),
            # versões por partida — None abaixo do piso, para o front-end poder
            # apagar a seleção do mapa em vez de mostrar média não comparável
            "goals_per_match": round(goals / played, 3) if played >= PER_MATCH_FLOOR else None,
            "conceded_per_match": round(conceded / played, 3) if played >= PER_MATCH_FLOOR else None,
            "wins_per_match": round(wins / played, 3) if played >= PER_MATCH_FLOOR else None,
        })
    return sorted(rows, key=lambda r: (-r["goals"], r["team"]))


def build_head_to_head(long: pd.DataFrame) -> dict:
    """Matriz seleção × adversário — o que o modo de país selecionado pinta."""
    matrix: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    grouped = long.groupby(["competition", "team", "opponent"])
    for (competition, team, opponent), block in grouped:
        entry = {
            "goals": int(block.gf.sum()),
            "conceded": int(block.ga.sum()),
            "matches": len(block),
            "wins": int((block.res == "W").sum()),
            "draws": int((block.res == "D").sum()),
            "losses": int((block.res == "L").sum()),
        }
        matrix.setdefault(competition, {}).setdefault(team, {})[opponent] = entry
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    ensure_dirs()
    matches = pd.read_csv(PROCESSED / "matches_clean.csv")
    long = to_long(matches)
    long["res"] = long.apply(outcome, axis=1)

    # Cada partida gera exatamente duas linhas na tabela longa.
    if len(long) != 2 * len(matches):
        print(f"ERRO: {len(long)} linhas longas para {len(matches)} partidas")
        return 1

    metrics = build_metrics(long, matches)
    head2head = build_head_to_head(long)

    for name, payload in (("metrics.json", {
        "generated_from": "data/processed/matches_clean.csv",
        "per_match_floor": PER_MATCH_FLOOR,
        "matches_received_complete": bool(matches.country_name.notna().all()),
        "teams": metrics,
    }), ("head2head.json", head2head)):
        path = WEB_DATA / name
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        size = path.stat().st_size
        print(f"  {name:<16} {size:>9,} bytes -> {path.relative_to(ROOT)}")

    # ---- conferências contra o dado de origem ----
    print("\nConferências:")
    checks: list[tuple[str, object, object]] = []

    total_goals = sum(r["goals"] for r in metrics)
    expected_goals = int((matches.home_team_score + matches.away_team_score).sum())
    checks.append(("gols somados", total_goals, expected_goals))

    total_played = sum(r["matches_played"] for r in metrics)
    checks.append(("participações em partidas", total_played, 2 * len(matches)))

    mens_titles = sum(r["titles"] for r in metrics if r["competition"] == "mens")
    mens_editions = matches[matches.competition == "mens"].tournament_id.nunique()
    checks.append(("títulos masculinos", mens_titles, mens_editions))

    # V + E + D tem que fechar com as partidas jogadas
    wdl = sum(r["wins"] + r["draws"] + r["losses"] for r in metrics)
    checks.append(("V+E+D", wdl, 2 * len(matches)))

    failed = 0
    for label, got, expected in checks:
        ok = got == expected
        failed += not ok
        print(f"  {'OK ' if ok else 'ERRO'} {label:<26} {got:<8} esperado {expected}")

    if failed:
        print(f"\n{failed} conferência(s) falharam.")
        return 1

    incomplete = matches.country_name.isna().sum()
    if incomplete:
        print(f"\nAVISO: 'partidas recebidas' está incompleta — {incomplete} partidas "
              f"sem country_name (2026). Preencher na geocodificação.")

    print(f"\n{len(metrics)} entradas seleção×competição prontas para o mapa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
