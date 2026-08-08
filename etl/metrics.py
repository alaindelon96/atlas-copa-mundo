"""Etapa 3 — métricas do mapa coroplético.

Transforma as tabelas modeladas (`etl.model`) no que o front-end consome:

    web/data/metrics.json    uma entrada por seleção, com as 6 métricas
    web/data/head2head.json  matriz de confrontos diretos

**Escopo: Copa masculina**, herdado de `etl.model` — este módulo não filtra
nada, ele lê as tabelas do modelo. Por isso nenhum dos dois JSONs tem dimensão
de competição: `head2head` é `{seleção: {adversário: {...}}}`, e não
`{competição: {seleção: ...}}`. O feminino segue no dado bruto e em
`matches_clean.csv`.

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

3. **A chave do mapa é `gu_a3`, não o nome.** Cada entrada carrega o código da
   unidade de mapa vinda de `reference/team_country.csv`; o Leaflet casa o
   GeoJSON por esse código. Casar por nome faria o front-end repetir — e
   divergir de — as decisões de nomenclatura tomadas no ETL.

Uso:
    python -m etl.model && python -m etl.metrics
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from etl.model import COMPETITION
from etl.paths import (INTERIM, PROCESSED, RAW_FJELSTUL, REFERENCE, ROOT,
                       WEB_DATA, ensure_dirs)

# Abaixo deste número de partidas, a média por partida não é comparável: uma
# seleção com 3 jogos passaria o Brasil por acidente amostral.
PER_MATCH_FLOOR = 10

GROUP_STAGES = {"group stage", "second group stage"}


def load_model() -> tuple[pd.DataFrame, pd.DataFrame]:
    """As tabelas do modelo. Este módulo não deriva nada que `etl.model` já deriva.

    A tabela longa `(partida, seleção)` e a coluna `result` — que resolve
    disputas por pênaltis — são produzidas uma vez, na modelagem. Recalculá-las
    aqui seria manter duas definições da mesma coisa em dois arquivos.
    """
    missing = [name for name in ("matches.csv", "team_matches.csv")
               if not (PROCESSED / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"{', '.join(missing)} não encontrado(s) — rode `python -m etl.model` antes.")
    return (pd.read_csv(PROCESSED / "matches.csv"),
            pd.read_csv(PROCESSED / "team_matches.csv"))


def map_units() -> dict[str, str]:
    """Seleção -> código da unidade de mapa, para o front-end casar o GeoJSON."""
    mapping = pd.read_csv(REFERENCE / "team_country.csv")
    return dict(zip(mapping.team_name, mapping.gu_a3))


def titles_by_team(editions: set[str]) -> dict[str, int]:
    """Títulos por seleção, com o mapa de sucessão aplicado.

    Vem de `tournament_standings.csv`, não das finais: a Copa de 1950 não teve
    final, e derivar campeão do `stage == "final"` perderia aquela edição em
    silêncio (ver `transform.titles_table`).

    O recorte não é uma regex sobre `tournament_name`: são os `tournament_id`
    que o modelo de fato contém. Assim o escopo é decidido em um lugar só
    (`etl.model.COMPETITION`) em vez de ser reinterpretado aqui.
    """
    succession = pd.read_csv(ROOT / "reference" / "team_succession.csv")
    merges = dict(zip(succession.historic_name, succession.merge_records))
    labels = dict(zip(succession.historic_name, succession.display_name))

    standings = pd.read_csv(RAW_FJELSTUL / "tournament_standings.csv")
    champions = standings[(standings.position == 1)
                          & standings.tournament_id.isin(editions)].team_name.tolist()

    modern = pd.read_csv(INTERIM / "tournament_2026.csv")
    champions.extend(modern.loc[modern.tournament_id.isin(editions), "winner"])

    counts: dict[str, int] = {}
    for raw in champions:
        name = labels[raw] if merges.get(raw, 0) == 1 else raw
        counts[name] = counts.get(name, 0) + 1
    return counts


def build_metrics(long: pd.DataFrame, matches: pd.DataFrame) -> list[dict]:
    """As seis métricas, por seleção."""
    titles = titles_by_team(set(matches.tournament_id))
    units = map_units()

    # "Partidas recebidas" é a única métrica que não olha para a seleção, e sim
    # para o país onde se jogou. Desde a geocodificação das sedes de 2026 ela
    # está completa — era a última coluna nula do modelo.
    received = matches.dropna(subset=["country_name"]).groupby("country_name").size()

    rows = []
    for team, block in long.groupby("team"):
        played = len(block)
        wins = int((block.result == "W").sum())
        draws = int((block.result == "D").sum())
        losses = int((block.result == "L").sum())
        goals = int(block.goals_for.sum())
        conceded = int(block.goals_against.sum())

        rows.append({
            "team": team,
            "gu_a3": units.get(team),
            "goals": goals,
            "conceded": conceded,
            "goal_difference": goals - conceded,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_pct": round(100 * wins / played, 1),
            "matches_played": played,
            "matches_received": int(received.get(team, 0)),
            "titles": titles.get(team, 0),
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
    matrix: dict[str, dict[str, dict[str, int]]] = {}
    for (team, opponent), block in long.groupby(["team", "opponent"]):
        matrix.setdefault(team, {})[opponent] = {
            "goals": int(block.goals_for.sum()),
            "conceded": int(block.goals_against.sum()),
            "matches": len(block),
            "wins": int((block.result == "W").sum()),
            "draws": int((block.result == "D").sum()),
            "losses": int((block.result == "L").sum()),
        }
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    ensure_dirs()
    try:
        matches, long = load_model()
    except FileNotFoundError as error:
        print(f"ERRO: {error}")
        return 1

    # Cada partida gera exatamente duas linhas na tabela longa.
    if len(long) != 2 * len(matches):
        print(f"ERRO: {len(long)} linhas longas para {len(matches)} partidas")
        return 1

    metrics = build_metrics(long, matches)
    head2head = build_head_to_head(long)

    for name, payload in (("metrics.json", {
        "generated_from": "data/processed/team_matches.csv",
        # O front-end não deve inferir o escopo contando linhas.
        "competition": COMPETITION,
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

    total_titles = sum(r["titles"] for r in metrics)
    checks.append(("títulos", total_titles, matches.tournament_id.nunique()))

    # V + E + D tem que fechar com as partidas jogadas
    wdl = sum(r["wins"] + r["draws"] + r["losses"] for r in metrics)
    checks.append(("V+E+D", wdl, 2 * len(matches)))

    # Uma seleção sem `gu_a3` existe nas métricas mas não pinta nada no mapa —
    # some da visualização sem gerar erro. Por isso é conferência, não aviso.
    with_unit = sum(1 for r in metrics if r["gu_a3"])
    checks.append(("entradas com gu_a3", with_unit, len(metrics)))

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

    print(f"\n{len(metrics)} seleções prontas para o mapa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
