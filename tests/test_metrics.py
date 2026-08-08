"""Testes da etapa 3 — métricas do mapa.

Travam as decisões de desenho do mapa e as invariantes que, se quebrarem,
produzem um mapa errado sem erro nenhum no console.

    pytest -q
"""

from __future__ import annotations

import json

import pytest

from etl.paths import WEB_DATA


@pytest.fixture(scope="module")
def metrics() -> dict:
    path = WEB_DATA / "metrics.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def head2head() -> dict:
    path = WEB_DATA / "head2head.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def men(metrics) -> dict:
    return {t["team"]: t for t in metrics["teams"] if t["competition"] == "mens"}


# --- decisões de desenho -------------------------------------------------


def test_reino_unido_sao_quatro_selecoes(men):
    """Decisão de 08/08/2026: as quatro seguem separadas.

    Juntá-las criaria uma "seleção do Reino Unido" que nunca disputou uma
    partida, creditada com 168 gols que ninguém marcou.
    """
    for team in ["England", "Scotland", "Wales", "Northern Ireland"]:
        assert team in men, f"{team} sumiu das métricas"
    assert "United Kingdom" not in men
    assert men["England"]["titles"] == 1
    assert men["Scotland"]["titles"] == 0


def test_por_partida_respeita_o_piso(metrics, men):
    """Abaixo do piso a média sai como None, não como número não comparável."""
    floor = metrics["per_match_floor"]
    assert floor == 10
    for team in men.values():
        if team["matches_played"] < floor:
            assert team["goals_per_match"] is None, f"{team['team']} devia estar sob o piso"
        else:
            assert team["goals_per_match"] is not None


def test_a_alternancia_muda_o_ranking(men):
    """O motivo de existirem as duas leituras.

    No total a Alemanha lidera; por partida a Hungria — que nem aparece no top
    10 bruto. Se este teste falhar, a alternância virou enfeite.
    """
    por_total = max(men.values(), key=lambda t: t["goals"])["team"]
    elegiveis = [t for t in men.values() if t["goals_per_match"] is not None]
    por_jogo = max(elegiveis, key=lambda t: t["goals_per_match"])["team"]
    assert por_total == "Germany"
    assert por_jogo == "Hungary"
    assert por_total != por_jogo


# --- invariantes da matriz de confrontos ---------------------------------


def test_confrontos_sao_simetricos(head2head):
    """A de A contra B tem que ser o inverso da de B contra A.

    É a invariante que pega erro na dobra mandante/visitante — o modo de país
    selecionado inteiro depende dela.
    """
    mens = head2head["mens"]
    for team, opponents in mens.items():
        for opponent, rec in opponents.items():
            mirror = mens[opponent][team]
            assert rec["goals"] == mirror["conceded"]
            assert rec["conceded"] == mirror["goals"]
            assert rec["matches"] == mirror["matches"]
            assert rec["wins"] == mirror["losses"]
            assert rec["draws"] == mirror["draws"]


def test_confrontos_somam_o_total_da_selecao(head2head, men):
    """Somar todos os adversários do Brasil tem que dar os gols do Brasil."""
    for team in ["Brazil", "Germany", "England"]:
        total = sum(r["goals"] for r in head2head["mens"][team].values())
        assert total == men[team]["goals"]
        jogos = sum(r["matches"] for r in head2head["mens"][team].values())
        assert jogos == men[team]["matches_played"]


def test_exemplo_brasil_suecia(head2head):
    """O caso que motivou o desenho: onde o Brasil mais fez gols."""
    brasil = head2head["mens"]["Brazil"]
    topo = max(brasil.items(), key=lambda kv: kv[1]["goals"])
    assert topo[0] == "Sweden"
    assert topo[1]["goals"] == 21
    # o Brasil nunca perdeu para a Suécia em Copa
    assert topo[1]["losses"] == 0


# --- integridade geral ---------------------------------------------------


def test_vitorias_empates_derrotas_fecham(men):
    for team in men.values():
        assert team["wins"] + team["draws"] + team["losses"] == team["matches_played"]


def test_titulos_fecham_com_as_edicoes(men):
    assert sum(t["titles"] for t in men.values()) == 23
    assert men["Germany"]["titles"] == 4, "decisão de sucessão deve valer aqui também"
    assert men["Brazil"]["titles"] == 5


def test_metrica_esparsa_continua_existindo(men):
    """Títulos pinta 8 países e sedes 18 — decidido que recebem o mesmo
    tratamento visual das métricas densas. O teste garante que a esparsidade é
    do dado, não de um filtro que apagou linhas."""
    assert sum(1 for t in men.values() if t["titles"] > 0) == 8
    assert sum(1 for t in men.values() if t["matches_received"] > 0) == 18
    assert len(men) == 83


def test_partidas_recebidas_esta_sinalizada_como_incompleta(metrics):
    """2026 ainda está sem country_name; o JSON precisa admitir isso, para o
    front-end não apresentar uma métrica furada como se fosse completa."""
    assert metrics["matches_received_complete"] is False
