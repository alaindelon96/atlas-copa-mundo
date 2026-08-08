"""Testes da etapa 3 — modelagem, geocodificação e camada de polígonos.

O `etl.validate` já verifica tipos, faixas e chaves estrangeiras a cada
execução. Estes testes travam outra coisa: as **decisões** da etapa e os fatos
concretos que provam que a geocodificação e o mapeamento de polígonos fizeram o
que deviam. Um schema válido não distingue "Wembley em Londres" de "Wembley no
meio do Atlântico" — as duas linhas passam.

    pytest -q
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from etl.paths import PROCESSED, REFERENCE, WEB_DATA


def _read(name: str) -> pd.DataFrame:
    path = PROCESSED / name
    if not path.exists():
        pytest.skip("Rode `python -m etl.geocode && python -m etl.model` primeiro.")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def matches() -> pd.DataFrame:
    return _read("matches.csv")


@pytest.fixture(scope="module")
def venues() -> pd.DataFrame:
    return _read("venues.csv")


@pytest.fixture(scope="module")
def teams() -> pd.DataFrame:
    return _read("teams.csv")


@pytest.fixture(scope="module")
def long() -> pd.DataFrame:
    return _read("team_matches.csv")


@pytest.fixture(scope="module")
def hosts() -> pd.DataFrame:
    return _read("tournament_hosts.csv")


@pytest.fixture(scope="module")
def team_country() -> pd.DataFrame:
    path = REFERENCE / "team_country.csv"
    if not path.exists():
        pytest.skip("Rode `python -m etl.geo` primeiro.")
    return pd.read_csv(path)


# --- geocodificação ------------------------------------------------------


def test_escopo_e_masculino_mas_o_dado_feminino_sobreviveu(matches):
    """A fronteira entre "produto" e "dado", travada em um teste.

    A Copa feminina saiu do modelo, do mapa e dos JSONs. Ela **não** saiu do
    dado: `matches_clean.csv` continua com as 284 partidas de 1991–2019 e com a
    coluna `competition` que as identifica. É isso que torna barato reincluí-la
    — mudar `etl.model.COMPETITION` e devolver a coluna às tabelas.

    Se alguém um dia filtrar o feminino lá atrás, no `transform`, este teste
    falha e explica o que se perdeu.
    """
    from etl.model import COMPETITION

    assert COMPETITION == "mens"
    assert "competition" not in matches.columns, "coluna constante não informa nada"
    assert len(matches) == 1068
    assert matches.year.between(1930, 2026).all()

    limpo = pd.read_csv(PROCESSED / "matches_clean.csv")
    feminino = limpo[limpo.competition == "womens"]
    assert len(feminino) == 284, "o dado feminino não pode ser descartado"
    assert feminino.year.min() == 1991 and feminino.year.max() == 2019


def test_2026_ganhou_pais_sede(matches):
    """O buraco que a Etapa 2 deixou aberto.

    As 104 partidas de 2026 vinham sem `country_name` — o scraping da Wikipédia
    não traz o país na tabela de partidas. Sem ele, "partidas recebidas" ignorava
    um torneio inteiro sem reclamar de nada.
    """
    modern = matches[matches.year == 2026]
    assert len(modern) == 104
    assert modern.country_name.notna().all()
    assert set(modern.country_name) == {"Canada", "Mexico", "United States"}
    assert matches.country_name.notna().all()


def test_coordenadas_caem_no_lugar_certo(venues):
    """Amostra conferida à mão, uma por continente.

    Faixa de meio grau (~55 km) em vez de igualdade: o Nominatim pode devolver
    o centroide do estádio ou o da cidade, e a diferença não importa num
    mapa-múndi. O que este teste pega é o erro que importa — coordenada no país
    errado, ou latitude e longitude trocadas.
    """
    known = {
        ("Estádio do Maracanã", "Rio de Janeiro"): (-22.91, -43.23),
        ("Wembley Stadium", "London"): (51.56, -0.28),
        ("Estadio Azteca", "Mexico City"): (19.30, -99.15),
        ("Soccer City", "Johannesburg"): (-26.23, 27.98),
        ("Lusail Stadium", "Lusail"): (25.41, 51.49),
        # A final de 2026 — a sede que só ganhou país depois da geocodificação.
        ("MetLife Stadium", "East Rutherford"): (40.81, -74.07),
    }
    indexed = venues.set_index(["stadium_name", "city_name"])
    for key, (latitude, longitude) in known.items():
        assert key in indexed.index, f"{key[0]} sumiu da tabela de sedes"
        row = indexed.loc[key]
        assert abs(row.latitude - latitude) < 0.5, f"{key[0]}: latitude fora do lugar"
        assert abs(row.longitude - longitude) < 0.5, f"{key[0]}: longitude fora do lugar"


def test_nenhuma_sede_no_ponto_zero(venues):
    """(0, 0) fica no Golfo da Guiné e é o valor que um geocoder devolve quando
    falha em silêncio. Nenhuma Copa foi jogada lá."""
    at_null_island = (venues.latitude.abs() < 0.5) & (venues.longitude.abs() < 0.5)
    assert not at_null_island.any()


# --- países-sede como tabela ---------------------------------------------


def test_sedes_multiplas_viraram_linhas(hosts):
    """As duas edições com mais de um país-sede.

    A fonte codifica as duas de formas diferentes e ambíguas — `"Korea, Japan"`
    com vírgula e `"Canada Mexico United States"` sem separador nenhum. Aqui elas
    são derivadas das sedes onde se jogou, e "Korea" vira "South Korea", que é o
    nome usado no resto do dataset.
    """
    by_edition = hosts.groupby("tournament_id").host_country.apply(set)
    assert by_edition["WC-2002"] == {"Japan", "South Korea"}
    assert by_edition["WC-2026"] == {"Canada", "Mexico", "United States"}
    assert (by_edition.apply(len) >= 1).all()


# --- polígonos do mapa ---------------------------------------------------


def test_reino_unido_sao_quatro_poligonos(team_country):
    """A razão de a base ser `map_units` e não `countries`."""
    british = team_country[team_country.sovereign == "United Kingdom"]
    assert set(british.team_name) == {"England", "Scotland", "Wales", "Northern Ireland"}
    assert set(british.gu_a3) == {"ENG", "SCT", "WLS", "NIR"}


def test_belgica_e_o_preco_da_escolha(team_country):
    """A mesma divisão que separa o Reino Unido em quatro separa a Bélgica em
    três. O mapeamento é um-para-muitos por isso, e as três regiões recebem a
    mesma cor — a costura não aparece."""
    belgium = team_country[team_country.team_name == "Belgium"]
    assert len(belgium) == 3
    assert set(belgium.gu_a3) == {"BFR", "BWR", "BCR"}


def test_toda_selecao_tem_poligono(teams, team_country):
    assert teams.gu_a3.notna().all()
    assert set(teams.team_name) == set(team_country.team_name)
    # Uma unidade de mapa não pode pertencer a duas seleções: seria o mesmo
    # pedaço do mapa reivindicado por duas cores.
    assert team_country.gu_a3.is_unique


def test_geojson_casa_com_as_metricas():
    """A ponte entre os dois arquivos que o front-end carrega.

    O mapa casa GeoJSON e métricas por `gu_a3`. Se os dois conjuntos de códigos
    divergirem, o país simplesmente não pinta — sem erro no console.
    """
    geojson_path = WEB_DATA / "countries.geojson"
    metrics_path = WEB_DATA / "metrics.json"
    if not geojson_path.exists() or not metrics_path.exists():
        pytest.skip("Rode `python -m etl.geo && python -m etl.metrics` primeiro.")

    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    painted = {f["properties"]["gu_a3"] for f in geojson["features"]
               if f["properties"]["team"]}
    wanted = {t["gu_a3"] for t in metrics["teams"]}
    assert wanted <= painted, f"sem polígono: {sorted(wanted - painted)}"

    # Países que nunca jogaram uma Copa continuam no GeoJSON, com `team` nulo:
    # o mapa desenha o contorno em cinza em vez de deixar um buraco branco.
    assert any(f["properties"]["team"] is None for f in geojson["features"])


# --- a tabela longa ------------------------------------------------------


def test_tabela_longa_e_o_dobro(long, matches):
    assert len(long) == 2 * len(matches)
    assert (long.groupby("match_id").size() == 2).all()


def test_penaltis_so_existem_onde_houve_disputa(matches):
    """O Fjelstul grava 0–0 onde não houve disputa e a Wikipédia deixa em branco.

    Um 0 é um placar válido: sem essa normalização, 1.205 partidas carregavam um
    "0–0 nos pênaltis" que passa por qualquer soma sem levantar suspeita.
    """
    shootout = matches.penalty_shootout == 1
    assert matches.loc[shootout, "home_team_score_penalties"].notna().all()
    assert matches.loc[~shootout, "home_team_score_penalties"].isna().all()


def test_grupo_so_existe_na_fase_de_grupos(matches):
    """O outro sentinel, encontrado pelo pandera e não a olho.

    O Fjelstul escreve a string `"not applicable"` em `group_name` nas 332
    partidas de mata-mata; a Wikipédia deixa em branco nas 32 dela. Sem
    normalizar, um agrupamento por grupo devolveria um "grupo" chamado
    `not applicable` com 332 partidas de mata-mata dentro — e nenhum erro.
    """
    group_stage = matches.stage.isin(["group stage", "second group stage"])
    assert matches.loc[group_stage, "group_name"].notna().all()
    assert matches.loc[~group_stage, "group_name"].isna().all()
    assert "not applicable" not in set(matches.group_name.dropna())


def test_1974_alemanha_contra_alemanha(matches):
    """A consequência da decisão de que o rótulo manda.

    Alemanha Oriental 1–0 Alemanha Ocidental, 1974, vira "Germany × Germany". O
    projeto escolheu manter assim — e o teste existe para que a escolha continue
    sendo uma escolha visível, e não algo que alguém "conserta" sem perceber que
    está mexendo numa decisão editorial. Os nomes crus seguem na tabela.
    """
    mirror = matches[matches.home_team == matches.away_team]
    assert len(mirror) == 1
    row = mirror.iloc[0]
    assert row.year == 1974
    assert {row.home_team_raw, row.away_team_raw} == {"East Germany", "West Germany"}
    # Ela não desequilibra nada: a Alemanha some com uma vitória e uma derrota.
    assert row.home_team_score != row.away_team_score
