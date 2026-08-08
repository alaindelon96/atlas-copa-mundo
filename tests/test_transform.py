"""Testes da etapa 2 — reconciliação.

Rodam offline, contra `data/processed/matches_clean.csv`. Cada teste trava uma
decisão ou uma armadilha que já custou caro durante a construção do pipeline —
a ideia é que, se alguém mudar o mapa de sucessão ou a normalização de fases sem
perceber a consequência, um teste falhe com a explicação junto.

    pytest -q
"""

from __future__ import annotations

import pandas as pd
import pytest

from etl.paths import PROCESSED, ROOT
from etl.transform import STAGE_CANONICAL, apply_succession, load_succession


@pytest.fixture(scope="module")
def matches() -> pd.DataFrame:
    path = PROCESSED / "matches_clean.csv"
    if not path.exists():
        pytest.skip("Rode `python -m etl.transform` primeiro.")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def succession() -> pd.DataFrame:
    return load_succession()


# --- o mapa de sucessão --------------------------------------------------


def test_alemanha_ocidental_vira_alemanha(succession):
    """Decisão do projeto, 08/08/2026 — muda a contagem de títulos de 1 para 4."""
    row = succession[succession.historic_name == "West Germany"].iloc[0]
    assert row.display_name == "Germany"
    assert row.merge_records == 1


def test_zaire_vira_dr_congo_e_soma(succession):
    """Renomeação, não dissolução: é o mesmo país, então os registros somam."""
    row = succession[succession.historic_name == "Zaire"].iloc[0]
    assert row.display_name == "DR Congo"
    assert row.merge_records == 1


def test_dissolucoes_nao_somam_registros(succession):
    """URSS, Iugoslávia e Tchecoslováquia viraram vários países.

    Elas recebem rótulo moderno para o mapa, mas o histórico NÃO é creditado ao
    sucessor — seria atribuir a um país o que várias seleções conquistaram.
    """
    for name in ["Soviet Union", "Yugoslavia", "Czechoslovakia", "Serbia and Montenegro"]:
        row = succession[succession.historic_name == name].iloc[0]
        assert row.merge_records == 0, f"{name} não deveria somar registros"
        assert row.display_name != name, f"{name} deveria ter rótulo moderno"


def test_fuzzy_matching_nao_resolveria_zaire():
    """O motivo de o mapa curado existir.

    Se `rapidfuzz` resolvesse sucessão sozinho, este par teria similaridade alta.
    Ele não tem — e é justamente a única sucessão real entre as duas fontes.
    """
    from rapidfuzz import fuzz

    assert fuzz.WRatio("Zaire", "DR Congo") < 50


def test_apply_succession_preserva_nomes_desconhecidos(succession):
    nomes = pd.Series(["Brazil", "West Germany", "Cape Verde"])
    resultado = apply_succession(nomes, succession)
    assert list(resultado) == ["Brazil", "Germany", "Cape Verde"]


# --- a armadilha masculino/feminino --------------------------------------


def test_competition_separa_as_duas_copas(matches):
    """`tournament_id` NÃO distingue: WC-1991 é feminina, WC-1994 é masculina."""
    assert set(matches.competition.unique()) == {"mens", "womens"}

    womens = matches[matches.competition == "womens"]
    assert womens.year.min() == 1991
    assert womens.year.max() == 2019

    # Nenhum torneio pode conter as duas competições.
    por_torneio = matches.groupby("tournament_id").competition.nunique()
    assert (por_torneio == 1).all()


# --- normalização de fases -----------------------------------------------


def test_variantes_de_fase_colapsam(matches):
    """O Fjelstul traz "quarter-final" E "quarter-finals"; 2026 traz "Quarterfinals"."""
    assert STAGE_CANONICAL["quarter-final"] == "quarter-finals"
    assert STAGE_CANONICAL["quarterfinals"] == "quarter-finals"
    assert STAGE_CANONICAL["semifinals"] == "semi-finals"

    # Depois de normalizar, nenhuma variante sobra na coluna canônica.
    assert "quarter-final" not in set(matches.stage)
    assert "Quarterfinals" not in set(matches.stage)


def test_toda_partida_tem_fase_canonica(matches):
    assert matches.stage.notna().all()
    assert set(matches.stage) <= set(STAGE_CANONICAL.values())


# --- a Copa de 1950 ------------------------------------------------------


def test_1950_nao_teve_final(matches):
    """Armadilha histórica: contar campeões filtrando `stage == "final"`
    perderia 1950 em silêncio, porque aquela edição foi decidida por um
    quadrangular final. O resultado daria 22 títulos em vez de 23."""
    c50 = matches[(matches.year == 1950) & (matches.competition == "mens")]
    assert len(c50) > 0
    assert "final" not in set(c50.stage)
    assert "final round" in set(c50.stage)


def test_titulos_fecham_com_o_numero_de_edicoes(succession):
    """Cada edição masculina tem exatamente um campeão."""
    from etl.transform import titles_table

    titles = titles_table(succession)
    assert int(titles.titles.sum()) == 23

    germany = titles[titles.team == "Germany"].titles.iloc[0]
    assert germany == 4, "Alemanha Ocidental deve somar com a Alemanha"

    spain = titles[titles.team == "Spain"].titles.iloc[0]
    assert spain == 2, "2026 deve estar incluído"


# --- integridade geral ---------------------------------------------------


def test_as_duas_fontes_estao_presentes(matches):
    assert set(matches.source.unique()) == {"fjelstul", "wikipedia"}
    assert len(matches[matches.source == "wikipedia"]) == 104
    assert len(matches) == 1352


def test_publico_so_existe_em_2026(matches):
    """O Fjelstul não tem público; a Wikipédia tem. A lacuna é conhecida."""
    com_publico = matches[matches.attendance.notna()]
    assert set(com_publico.year.unique()) == {2026}
    assert int(com_publico.attendance.sum()) == 6_810_966


def test_placares_nunca_sao_nulos(matches):
    assert matches.home_team_score.notna().all()
    assert matches.away_team_score.notna().all()


def test_mapa_de_sucessao_esta_versionado():
    """A decisão editorial precisa ser auditável, não implícita no código."""
    assert (ROOT / "reference" / "team_succession.csv").exists()
