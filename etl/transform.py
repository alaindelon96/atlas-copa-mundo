"""Etapa 2 do ETL — limpeza e reconciliação.

Junta as duas fontes (Fjelstul 1930–2022 e Wikipédia 2026) em uma tabela única
de partidas, resolvendo o problema central do projeto: os países mudaram ao
longo de quase 100 anos, e os nomes no dado refletem o mundo de cada época.

Três decisões estruturam este módulo:

1. **`competition` explícito.** No Fjelstul, `tournament_id` NÃO separa
   masculino de feminino: `WC-1991` é a Copa feminina e `WC-1994` a masculina.
   Só `tournament_name` distingue. Agrupar por `tournament_id` misturaria as duas
   sem gerar erro nenhum — por isso a coluna vem primeiro.

2. **Sucessão é curada, não adivinhada.** O mapa vive em
   `reference/team_succession.csv`, editável sem tocar em código. `rapidfuzz`
   **não** é usado para decidir sucessão — é usado para *sinalizar* nomes
   parecidos para revisão humana. O motivo está no próprio dado: a única
   sucessão real entre as duas fontes é "Zaire" → "DR Congo", que tem
   similaridade textual zero. Fuzzy matching nunca acharia, e se achasse algo
   seria por acidente.

3. **Rótulo e registro são coisas diferentes.** `display_name` é como a seleção
   aparece hoje; `merge_records` diz se o histórico dela soma no sucessor. A
   Alemanha Ocidental tem os dois (vira Alemanha e soma os títulos). A URSS tem
   só o primeiro: aparece como Rússia no mapa, mas mantém os registros próprios.

Uso:
    python -m etl.transform
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
from rapidfuzz import fuzz, process

from etl.paths import INTERIM, PROCESSED, RAW_FJELSTUL, ROOT, ensure_dirs

SUCCESSION_CSV = ROOT / "reference" / "team_succession.csv"

# As duas fontes nomeiam as fases de formas diferentes, e o próprio Fjelstul é
# inconsistente consigo mesmo: convivem "quarter-final" (32x) e "quarter-finals"
# (70x), "semi-final" (16x) e "semi-finals" (38x). Normalizar aqui evita que
# qualquer agrupamento por fase, mais adiante, quebre em silêncio.
STAGE_CANONICAL = {
    "group stage": "group stage",
    "second group stage": "second group stage",
    "final round": "final round",
    "round of 32": "round of 32",
    "round of 16": "round of 16",
    "quarter-final": "quarter-finals",
    "quarter-finals": "quarter-finals",
    "quarterfinals": "quarter-finals",
    "semi-final": "semi-finals",
    "semi-finals": "semi-finals",
    "semifinals": "semi-finals",
    "third-place match": "third-place match",
    "match for third place": "third-place match",
    "final": "final",
}

# Colunas finais da tabela de partidas unificada.
OUTPUT_COLUMNS = [
    "tournament_id", "tournament_name", "competition", "year",
    "match_id", "stage_name", "stage", "group_name",
    "match_date", "stadium_name", "city_name", "country_name",
    "home_team_raw", "away_team_raw",
    "home_team", "away_team",
    "home_team_score", "away_team_score",
    "extra_time", "penalty_shootout",
    "home_team_score_penalties", "away_team_score_penalties",
    "attendance", "source",
]


def load_succession() -> pd.DataFrame:
    """Carrega o mapa de sucessão curado."""
    if not SUCCESSION_CSV.exists():
        raise FileNotFoundError(f"{SUCCESSION_CSV} não encontrado.")
    return pd.read_csv(SUCCESSION_CSV)


def apply_succession(names: pd.Series, succession: pd.DataFrame) -> pd.Series:
    """Traduz nomes históricos para o rótulo atual.

    Aplica `display_name` a todo mundo que está no mapa — inclusive quem tem
    `merge_records=0`, porque rotular no mapa e somar estatística são perguntas
    diferentes. Quem soma ou não é decidido depois, por quem consome a coluna.
    """
    lookup = dict(zip(succession.historic_name, succession.display_name))
    return names.map(lambda name: lookup.get(name, name))


def load_fjelstul() -> pd.DataFrame:
    """Carrega e normaliza as partidas de 1930–2022."""
    matches = pd.read_csv(RAW_FJELSTUL / "matches.csv")

    # A armadilha central do dataset — ver nota 1 no topo do módulo.
    competition = matches.tournament_name.str.extract(r"(Men's|Women's)")[0]
    matches["competition"] = competition.map({"Men's": "mens", "Women's": "womens"})

    if matches.competition.isna().any():
        unknown = matches.loc[matches.competition.isna(), "tournament_name"].unique()
        raise ValueError(f"Torneios sem competição identificada: {list(unknown)}")

    matches["year"] = matches.match_date.str[:4].astype(int)
    matches["attendance"] = pd.NA  # o Fjelstul não tem público
    matches["source"] = "fjelstul"
    matches["home_team_raw"] = matches.home_team_name
    matches["away_team_raw"] = matches.away_team_name

    return matches


def load_2026() -> pd.DataFrame:
    """Carrega as partidas de 2026 e as põe no mesmo formato."""
    matches = pd.read_csv(INTERIM / "matches_2026.csv")

    matches["competition"] = "mens"
    matches["year"] = 2026
    matches["source"] = "wikipedia"
    matches["home_team_raw"] = matches.home_team_name
    matches["away_team_raw"] = matches.away_team_name

    # O Fjelstul traz o país da sede; a Wikipédia não, nesta tabela.
    # Fica em branco e será preenchido na etapa 3, junto da geocodificação.
    matches["country_name"] = pd.NA

    return matches


def report_unmatched(
    combined: pd.DataFrame,
    succession: pd.DataFrame,
) -> list[tuple[str, str, float]]:
    """Sinaliza nomes de 2026 que não existem no histórico.

    Este é o papel honesto do `rapidfuzz` aqui: sugerir candidatos para revisão
    humana, nunca aplicar sozinho. Um nome novo pode ser (a) uma estreia
    legítima na Copa ou (b) uma sucessão que faltou mapear — e só uma pessoa
    sabe distinguir os dois casos.
    """
    historic = set(combined.loc[combined.source == "fjelstul", "home_team"]) | set(
        combined.loc[combined.source == "fjelstul", "away_team"]
    )
    modern = set(combined.loc[combined.source == "wikipedia", "home_team"]) | set(
        combined.loc[combined.source == "wikipedia", "away_team"]
    )

    suggestions = []
    for name in sorted(modern - historic):
        match = process.extractOne(name, sorted(historic), scorer=fuzz.WRatio)
        suggestions.append((name, match[0], match[1]) if match else (name, "", 0.0))
    return suggestions


def transform() -> pd.DataFrame:
    """Constrói a tabela unificada de partidas."""
    succession = load_succession()
    print(f"Mapa de sucessão: {len(succession)} regras em {SUCCESSION_CSV.name}")

    fjelstul = load_fjelstul()
    print(f"  Fjelstul  {len(fjelstul):>5} partidas  1930–2022")

    modern = load_2026()
    print(f"  Wikipédia {len(modern):>5} partidas  2026")

    combined = pd.concat([fjelstul, modern], ignore_index=True)

    combined["home_team"] = apply_succession(combined.home_team_raw, succession)
    combined["away_team"] = apply_succession(combined.away_team_raw, succession)

    combined["stage"] = combined.stage_name.str.strip().str.lower().map(STAGE_CANONICAL)
    if combined.stage.isna().any():
        unknown = sorted(combined.loc[combined.stage.isna(), "stage_name"].unique())
        raise ValueError(f"Fases não mapeadas em STAGE_CANONICAL: {unknown}")

    combined = combined.sort_values(["match_date", "match_id"]).reset_index(drop=True)
    return combined[OUTPUT_COLUMNS]


def titles_table(succession: pd.DataFrame) -> pd.DataFrame:
    """Conta títulos masculinos, respeitando `merge_records`.

    **Não** deriva o campeão das finais, e o motivo é histórico: a Copa de 1950
    não teve final. O título foi decidido por um quadrangular final — o
    "Maracanaço" é a última rodada desse grupo, não uma decisão. Quem contasse
    campeões filtrando `stage == "final"` perderia 1950 sem perceber, porque o
    resultado não daria erro: daria 22 títulos em vez de 23.

    Por isso a fonte aqui é `tournament_standings.csv`, que já traz a
    classificação final oficial de cada edição e resolve 1950 corretamente.

    Uma seleção que aparece no mapa com outro rótulo mas com `merge_records=0`
    mantém a contagem própria — é aqui que a diferença entre rótulo e registro
    deixa de ser teórica.
    """
    standings = pd.read_csv(RAW_FJELSTUL / "tournament_standings.csv")
    competition = standings.tournament_name.str.extract(r"(Men's|Women's)")[0]
    standings["competition"] = competition.map({"Men's": "mens", "Women's": "womens"})

    champions = standings[
        (standings.competition == "mens") & (standings.position == 1)
    ].team_name.tolist()

    # 2026 vem da Wikipédia, não do Fjelstul.
    modern = pd.read_csv(INTERIM / "tournament_2026.csv")
    champions.extend(modern.winner.tolist())

    merges = dict(zip(succession.historic_name, succession.merge_records))
    labels = dict(zip(succession.historic_name, succession.display_name))

    # Só soma no sucessor se o mapa de sucessão disser que soma.
    attributed = [labels[name] if merges.get(name, 0) == 1 else name for name in champions]

    counts = pd.Series(attributed).value_counts().reset_index()
    counts.columns = ["team", "titles"]
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    ensure_dirs()
    matches = transform()
    succession = load_succession()

    destination = PROCESSED / "matches_clean.csv"
    matches.to_csv(destination, index=False, encoding="utf-8")
    print(f"\n{len(matches)} partidas -> {destination.relative_to(ROOT)}")

    print("\nPor competição:")
    for competition, count in matches.competition.value_counts().items():
        years = matches[matches.competition == competition].year
        print(f"  {competition:<8} {count:>5} partidas   {years.min()}–{years.max()}")

    print("\nNomes de 2026 ausentes no histórico (rapidfuzz sugere, você decide):")
    for name, closest, score in report_unmatched(matches, succession):
        verdict = "REVISAR" if score >= 80 else "estreia?"
        print(f"  {name:<16} mais próximo: {closest:<22} {score:5.1f}  {verdict}")

    print("\nFases normalizadas:")
    for stage, count in matches.stage.value_counts().items():
        print(f"  {stage:<20} {count:>5}")

    titles = titles_table(succession)
    print("\nTítulos masculinos (aplicando o mapa de sucessão):")
    for _, row in titles.iterrows():
        print(f"  {row.team:<16} {row.titles}")

    # Cada edição masculina tem exatamente um campeão: a soma tem que fechar.
    editions = matches[matches.competition == "mens"].tournament_id.nunique()
    total = int(titles.titles.sum())
    print(f"\n  soma dos títulos = {total}   edições masculinas = {editions}", end="  ")
    if total != editions:
        print("ERRO — não fecham")
        return 1
    print("OK")

    return 0


if __name__ == "__main__":
    sys.exit(main())
