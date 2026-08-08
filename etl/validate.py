"""Etapa 3 — validação do modelo com `pandera`.

Declara o contrato de cada tabela de `data/processed/` — tipos, faixas de
valores, unicidade, o que pode ser nulo — e o verifica de uma vez:

    python -m etl.validate

Por que isto existe além das conferências que cada script já faz:

As conferências dentro de `etl.model` e `etl.metrics` checam **totais** ("os
gols somam?", "V+E+D fecha?"). São ótimas para pegar erro de agregação, e cegas
para erro de linha: um placar negativo, uma latitude de 500 graus ou um ano
1830 passariam por todas elas somando certo. O `pandera` cobre o outro lado —
cada linha, cada coluna — e o faz de forma **declarativa**: o schema abaixo é
legível como documentação do modelo, o que uma bateria de `assert` espalhada
não seria.

E há uma diferença de papel que importa para quem for ler este repositório: os
scripts validam o que produzem no momento em que produzem; este módulo valida o
que está **em disco**, sem reprocessar nada. É o que se roda antes de publicar,
ou num CI, para responder "os arquivos que estão no repositório hoje são
válidos?".
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd
from pandera.errors import SchemaErrors
from pandera.pandas import Check, Column, DataFrameSchema

from etl.paths import PROCESSED, ROOT

# Faixas conhecidas do domínio. A primeira Copa foi em 1930; a margem até 2100
# é para o modelo não precisar ser editado quando 2030 entrar.
YEAR_RANGE = Check.in_range(1930, 2100)

STAGES = Check.isin([
    "group stage", "second group stage", "final round", "round of 32",
    "round of 16", "quarter-finals", "semi-finals", "third-place match", "final",
])

RESULTS = Check.isin(["W", "D", "L"])

CONFEDERATIONS = Check.isin(["UEFA", "CONMEBOL", "CONCACAF", "CAF", "AFC", "OFC"])

BOOLEAN_FLAG = Check.isin([0, 1])

# Um placar de Copa nunca passou de 10 (Hungria 10–1 El Salvador, 1982). O teto
# em 20 não é o recorde: é o limiar acima do qual o número quase certamente veio
# de um erro de parsing, não de uma goleada.
SCORE_RANGE = Check.in_range(0, 20)


SCHEMAS: dict[str, DataFrameSchema] = {
    "tournaments.csv": DataFrameSchema({
        "tournament_id": Column(str, unique=True),
        "year": Column(int, YEAR_RANGE),
        "matches": Column(int, Check.gt(0)),
        "goals": Column(int, Check.gt(0)),
        "venues": Column(int, Check.gt(0)),
        "start_date": Column(str),
        "end_date": Column(str),
        "count_teams": Column(int, Check.in_range(12, 64)),
        "champion": Column(str),
        "runner_up": Column(str),
    }, strict=True, name="tournaments"),

    "tournament_hosts.csv": DataFrameSchema({
        "tournament_id": Column(str),
        "host_country": Column(str),
    }, strict=True, unique=["tournament_id", "host_country"], name="tournament_hosts"),

    "teams.csv": DataFrameSchema({
        "team_name": Column(str, unique=True),
        # A chave do mapa. Se ela virar nula, a seleção existe nas métricas e
        # não pinta nada no mapa — falha silenciosa, por isso nullable=False.
        "gu_a3": Column(str, Check.str_length(3, 3)),
        "geounit_name": Column(str),
        "map_units": Column(int, Check.in_range(1, 5)),
        "confederation": Column(str, CONFEDERATIONS),
        "first_year": Column(int, YEAR_RANGE),
        "last_year": Column(int, YEAR_RANGE),
        "participations": Column(int, Check.gt(0)),
        "matches_played": Column(int, Check.gt(0)),
    }, strict=True, name="teams"),

    "venues.csv": DataFrameSchema({
        "venue_id": Column(str, unique=True),
        "stadium_name": Column(str),
        "city_name": Column(str),
        "country_name": Column(str),
        "country_code": Column(str, Check.str_length(2, 2), nullable=True),
        # Coordenadas fora da faixa pegam o erro clássico de latitude e
        # longitude trocadas — que não quebra nada, só põe o estádio no oceano.
        "latitude": Column(float, Check.in_range(-90, 90)),
        "longitude": Column(float, Check.in_range(-180, 180)),
        "matches_hosted": Column(int, Check.gt(0)),
        "first_year": Column(int, YEAR_RANGE),
        "last_year": Column(int, YEAR_RANGE),
        "match_level": Column(str, Check.isin(
            ["stadium+country", "city+country", "stadium", "city"])),
    }, strict=True, unique=["stadium_name", "city_name"], name="venues"),

    "matches.csv": DataFrameSchema({
        "match_id": Column(str, unique=True),
        "tournament_id": Column(str),
        "year": Column(int, YEAR_RANGE),
        "stage": Column(str, STAGES),
        # Só a fase de grupos tem grupo; o mata-mata não tem, e isso é legítimo.
        # O `isin` existe para o sentinel `"not applicable"` do Fjelstul nunca
        # voltar a passar por um nome de grupo válido.
        "group_name": Column(str, Check.str_startswith("Group"), nullable=True),
        "match_date": Column(str, Check.str_matches(r"^\d{4}-\d{2}-\d{2}$")),
        "venue_id": Column(str),
        "country_name": Column(str),
        "home_team": Column(str),
        "away_team": Column(str),
        "home_team_score": Column(int, SCORE_RANGE),
        "away_team_score": Column(int, SCORE_RANGE),
        "extra_time": Column(int, BOOLEAN_FLAG),
        "penalty_shootout": Column(int, BOOLEAN_FLAG),
        # Placar de pênaltis só existe quando houve disputa — a regra cruzada
        # que garante isso está em `cross_checks`, fora do schema de coluna.
        "home_team_score_penalties": Column(float, nullable=True),
        "away_team_score_penalties": Column(float, nullable=True),
        # Público: a Wikipédia tem para 2026, o Fjelstul não tem para nenhuma
        # edição. A coluna é majoritariamente nula por origem, não por erro.
        "attendance": Column(float, Check.gt(0), nullable=True),
        "home_team_raw": Column(str),
        "away_team_raw": Column(str),
        "source": Column(str, Check.isin(["fjelstul", "wikipedia"])),
    }, strict=True, name="matches"),

    "team_matches.csv": DataFrameSchema({
        "match_id": Column(str),
        "tournament_id": Column(str),
        "year": Column(int, YEAR_RANGE),
        "stage": Column(str, STAGES),
        "match_date": Column(str),
        "venue_id": Column(str),
        "country_name": Column(str),
        "penalty_shootout": Column(int, BOOLEAN_FLAG),
        "team": Column(str),
        "opponent": Column(str),
        "goals_for": Column(int, SCORE_RANGE),
        "goals_against": Column(int, SCORE_RANGE),
        "pens_for": Column(float, nullable=True),
        "pens_against": Column(float, nullable=True),
        "home_away": Column(str, Check.isin(["home", "away"])),
        "result": Column(str, RESULTS),
        # A chave é `(partida, lado)`, e não `(partida, seleção)` — e a exceção
        # que obriga isso é uma só, em 1974: Alemanha Oriental 1–0 Alemanha
        # Ocidental. Pela decisão do projeto o rótulo manda, então as duas viram
        # "Germany" e a Alemanha aparece duas vezes na mesma partida. Não é
        # corrupção: ela some com 1 vitória e 1 derrota, 1 gol feito e 1 sofrido,
        # e todos os totais continuam fechando. Ver `soft_checks`.
    }, strict=True, unique=["match_id", "home_away"], name="team_matches"),
}


def cross_checks(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Regras que envolvem mais de uma coluna ou mais de uma tabela.

    O `pandera` valida cada coluna contra o seu contrato; integridade
    referencial e regras condicionais não cabem ali. São essas as invariantes
    que fazem o modelo ser um modelo, e não seis CSVs soltos na mesma pasta.
    """
    errors: list[str] = []
    matches = tables["matches.csv"]
    long = tables["team_matches.csv"]

    def foreign_key(child: pd.DataFrame, column: str,
                    parent: pd.DataFrame, key: str, label: str) -> None:
        orphans = set(child[column]) - set(parent[key])
        if orphans:
            errors.append(f"{label}: {len(orphans)} valor(es) órfão(s), "
                          f"ex.: {sorted(orphans)[:3]}")

    foreign_key(matches, "venue_id", tables["venues.csv"], "venue_id",
                "matches.venue_id -> venues")
    foreign_key(matches, "tournament_id", tables["tournaments.csv"], "tournament_id",
                "matches.tournament_id -> tournaments")
    foreign_key(matches, "home_team", tables["teams.csv"], "team_name",
                "matches.home_team -> teams")
    foreign_key(matches, "away_team", tables["teams.csv"], "team_name",
                "matches.away_team -> teams")
    foreign_key(long, "match_id", matches, "match_id",
                "team_matches.match_id -> matches")
    foreign_key(tables["tournament_hosts.csv"], "tournament_id",
                tables["tournaments.csv"], "tournament_id",
                "tournament_hosts.tournament_id -> tournaments")

    # Placar de pênaltis existe se, e somente se, houve disputa de pênaltis.
    shootout = matches.penalty_shootout == 1
    has_pens = matches.home_team_score_penalties.notna()
    if (shootout & ~has_pens).any():
        errors.append(f"matches: {int((shootout & ~has_pens).sum())} disputa(s) de "
                      "pênaltis sem placar de pênaltis")
    if (~shootout & has_pens).any():
        errors.append(f"matches: {int((~shootout & has_pens).sum())} placar(es) de "
                      "pênaltis sem disputa registrada")

    # A janela de anos de cada seleção tem que ser coerente.
    teams = tables["teams.csv"]
    if (teams.first_year > teams.last_year).any():
        errors.append("teams: first_year depois de last_year")

    # Toda edição tem pelo menos um país-sede.
    hosted = set(tables["tournament_hosts.csv"].tournament_id)
    orphan_editions = set(tables["tournaments.csv"].tournament_id) - hosted
    if orphan_editions:
        errors.append(f"tournaments: {len(orphan_editions)} edição(ões) sem país-sede")

    return errors


def soft_checks(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Suspeitas, não violações.

    A diferença de status é deliberada, e vale a pena contar por que ela existe.

    A regra "não se vai aos pênaltis sem antes jogar a prorrogação" parece
    óbvia, e no recorte masculino ela não encontra nenhuma contradição. Mas
    encontrava uma quando o modelo ainda incluía a Copa feminina: a disputa de
    terceiro lugar de 1999, Brasil 0–0 Noruega, 5–4 nos pênaltis, com
    `extra_time = 0` na fonte. Não havia como saber, de dentro deste
    repositório, se a prorrogação não foi jogada ou se a coluna estava errada.

    Por isso a regra ficou aqui e não entre os erros: uma dúvida honesta sobre
    um dado de origem não deve travar a validação para sempre. A checagem
    continua rodando — se uma edição futura trouxer um caso desses, ele aparece.
    """
    notes: list[str] = []
    matches = tables["matches.csv"]

    odd = matches[(matches.penalty_shootout == 1) & (matches.extra_time == 0)]
    for row in odd.itertuples(index=False):
        notes.append(f"{row.match_id} ({row.year}, {row.stage}): pênaltis sem "
                     "prorrogação registrada na fonte")

    # Uma partida em que a mesma seleção aparece dos dois lados. É a
    # consequência visível da decisão de que o rótulo manda: duas entidades
    # históricas distintas recebem o mesmo nome moderno e se encontram em campo.
    # Aparece aqui toda execução, de propósito — uma decisão editorial que gera
    # um dado estranho deve continuar visível, não virar nota de rodapé.
    mirror = matches[matches.home_team == matches.away_team]
    for row in mirror.itertuples(index=False):
        notes.append(f"{row.match_id} ({row.year}): {row.home_team_raw} × "
                     f"{row.away_team_raw} colapsou em '{row.home_team}' × "
                     f"'{row.away_team}' — decisão de sucessão, não erro de dado")

    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=5,
                        help="quantas linhas com erro mostrar por tabela")
    args = parser.parse_args()

    tables: dict[str, pd.DataFrame] = {}
    failures = 0

    print("Validação de schema (pandera):")
    for name, schema in SCHEMAS.items():
        path = PROCESSED / name
        if not path.exists():
            print(f"  ERRO {name:<22} não encontrado — rode `python -m etl.model`")
            failures += 1
            continue

        frame = pd.read_csv(path)
        tables[name] = frame
        try:
            # `lazy=True` coleta todas as violações em vez de parar na primeira:
            # ver a lista inteira de uma vez economiza um ciclo de correção por erro.
            schema.validate(frame, lazy=True)
            print(f"  OK   {name:<22} {len(frame):>5} linhas, "
                  f"{len(schema.columns):>2} colunas")
        except SchemaErrors as error:
            failures += 1
            cases = error.failure_cases
            print(f"  ERRO {name:<22} {len(cases)} violação(ões):")
            for row in cases.head(args.sample).itertuples(index=False):
                print(f"         {row.column} — {row.check} — valor {row.failure_case!r}")
            if len(cases) > args.sample:
                print(f"         … e mais {len(cases) - args.sample}")

    if len(tables) == len(SCHEMAS):
        print("\nIntegridade referencial e regras cruzadas:")
        errors = cross_checks(tables)
        if errors:
            failures += len(errors)
            for message in errors:
                print(f"  ERRO {message}")
        else:
            print("  OK   todas as chaves estrangeiras e regras cruzadas")

        notes = soft_checks(tables)
        if notes:
            print(f"\nPara olho humano ({len(notes)}) — não invalidam o modelo:")
            for note in notes:
                print(f"  ?    {note}")

    print()
    if failures:
        print(f"{failures} problema(s) — o modelo em "
              f"{PROCESSED.relative_to(ROOT)}/ não está válido.")
        return 1
    print(f"Modelo válido: {len(SCHEMAS)} tabelas em {PROCESSED.relative_to(ROOT)}/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
