"""Testes da etapa 3 — métricas do mapa.

Travam as decisões de desenho do mapa e as invariantes que, se quebrarem,
produzem um mapa errado sem erro nenhum no console.

    pytest -q
"""

from __future__ import annotations

import json

import pytest

from etl.metrics import aggregate_timeline
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
def timeline() -> dict:
    path = WEB_DATA / "timeline.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def men(metrics) -> dict:
    """As seleções, indexadas por nome.

    O escopo do projeto é a Copa masculina e o recorte é feito uma vez só, em
    `etl.model`; aqui não se filtra nada. O teste abaixo garante que o JSON diz
    qual é o escopo, em vez de deixar o front-end deduzir.
    """
    return {t["team"]: t for t in metrics["teams"]}


def test_o_json_declara_o_escopo(metrics):
    """A Copa feminina saiu do produto, não do dado.

    `matches_clean.csv` continua com as 284 partidas de 1991–2019 e com a coluna
    `competition`. O que não existe mais é dimensão de competição nos arquivos
    que o mapa carrega — por isso o escopo precisa vir declarado, e não ser
    inferido de quantas seleções apareceram.
    """
    assert metrics["competition"] == "mens"
    assert all("competition" not in team for team in metrics["teams"])


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
    for team, opponents in head2head.items():
        for opponent, rec in opponents.items():
            mirror = head2head[opponent][team]
            assert rec["goals"] == mirror["conceded"]
            assert rec["conceded"] == mirror["goals"]
            assert rec["matches"] == mirror["matches"]
            assert rec["wins"] == mirror["losses"]
            assert rec["draws"] == mirror["draws"]


def test_confrontos_somam_o_total_da_selecao(head2head, men):
    """Somar todos os adversários do Brasil tem que dar os gols do Brasil."""
    for team in ["Brazil", "Germany", "England"]:
        total = sum(r["goals"] for r in head2head[team].values())
        assert total == men[team]["goals"]
        jogos = sum(r["matches"] for r in head2head[team].values())
        assert jogos == men[team]["matches_played"]


def test_exemplo_brasil_suecia(head2head):
    """O caso que motivou o desenho: onde o Brasil mais fez gols."""
    brasil = head2head["Brazil"]
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
    """Títulos pinta 8 países e sedes 19 — decidido que recebem o mesmo
    tratamento visual das métricas densas. O teste garante que a esparsidade é
    do dado, não de um filtro que apagou linhas.

    Foram 18 sedes até a geocodificação da Etapa 3. O 19º é o **Canadá**, que
    nunca havia recebido uma partida de Copa masculina antes de 2026 — e que só
    apareceu depois que o `country_name` das 16 sedes de 2026 foi preenchido.
    """
    assert sum(1 for t in men.values() if t["titles"] > 0) == 8
    assert sum(1 for t in men.values() if t["matches_received"] > 0) == 19
    assert men["Canada"]["matches_received"] > 0
    assert len(men) == 83


# --- o payload do slider (Etapa 4) ---------------------------------------


def test_timeline_reproduz_o_metrics_na_faixa_completa(timeline, men):
    """A conferência que sustenta a decisão de agregar no navegador.

    O filtro temporal virou um slider de faixa de anos, então o JavaScript
    precisa somar — não dá para pré-computar 276 faixas. O risco é a soma do JS
    descolar da do Python e o mapa mostrar número errado sem erro nenhum.

    A defesa é esta: na faixa completa, agregar o `timeline.json` tem que
    devolver exatamente o `metrics.json`. `etl.metrics.aggregate_timeline` é a
    implementação de referência, o `map.js` a espelha, e a página refaz esta
    mesma comparação ao carregar. Se este teste falhar, o payload que o slider
    consome está mentindo em *toda* faixa, não só na completa.
    """
    todos = aggregate_timeline(timeline, min(timeline["years"]), max(timeline["years"]))
    assert set(todos) >= set(men)
    for nome, esperado in men.items():
        obtido = todos[nome]
        for campo in ("goals", "conceded", "goal_difference", "wins", "draws", "losses",
                      "matches_played", "matches_received", "titles", "participations"):
            assert obtido[campo] == esperado[campo], f"{nome}.{campo}"


def test_timeline_e_uma_reescrita_sem_perda(timeline):
    """Uma linha por seleção por partida — o mesmo que a tabela longa."""
    assert len(timeline["rows"]) == 2136
    assert len(timeline["years"]) == 23
    assert timeline["results"] == "WDL"
    assert timeline["competition"] == "mens"


def test_o_recorte_por_ano_muda_o_que_o_mapa_mostra(timeline):
    """O filtro precisa recortar de verdade, e não devolver sempre o total.

    2022–2026 são as duas últimas edições: 32 seleções em 2022 e 48 em 2026,
    54 distintas somando as duas. Se este número virar 83, o recorte não está
    sendo aplicado; se virar 48, ele está pegando uma edição só.
    """
    recente = aggregate_timeline(timeline, 2022, 2026)
    assert len(recente) == 54
    assert recente["Spain"]["titles"] == 1
    assert recente["Argentina"]["titles"] == 1
    assert recente["Brazil"]["titles"] == 0, "o Brasil não ganhou nenhuma das duas"
    assert "Hungary" not in recente, "a Hungria não disputa uma Copa desde 1986"


def test_a_copa_de_1950_tem_campeao_no_recorte(timeline):
    """A edição sem final não pode sumir quando o slider passa por ela.

    Era o buraco clássico do projeto: contar campeão por `stage == "final"`
    devolve 22 títulos para 23 edições, em silêncio. Aqui o risco volta em outra
    forma — uma faixa que contém 1950 e não mostra o Uruguai campeão.
    """
    faixa = aggregate_timeline(timeline, 1950, 1950)
    campeoes = {nome: rec["titles"] for nome, rec in faixa.items() if rec["titles"]}
    assert campeoes == {"Uruguay": 1}


def test_titulos_somados_ano_a_ano_batem_com_o_total(timeline, men):
    """Somar os títulos de cada edição isolada tem que dar os 23."""
    total = sum(
        rec["titles"]
        for ano in timeline["years"]
        for rec in aggregate_timeline(timeline, ano, ano).values()
    )
    assert total == 23 == sum(t["titles"] for t in men.values())


def test_partidas_recebidas_seguem_o_pais_e_nao_a_selecao(timeline):
    """A única métrica que descreve um lugar.

    O Catar recebeu as 64 partidas de 2022 sem que isso tenha relação com o
    desempenho da seleção — e o Brasil, que não sediou nada nessa faixa, tem que
    aparecer com zero recebidas mesmo tendo jogado.
    """
    faixa = aggregate_timeline(timeline, 2022, 2022)
    assert faixa["Qatar"]["matches_received"] == 64
    assert faixa["Brazil"]["matches_received"] == 0
    assert faixa["Brazil"]["matches_played"] > 0


def test_partidas_recebidas_esta_completa(metrics):
    """A métrica ficou completa na Etapa 3.

    Era a última coluna nula do modelo: o scraping da Wikipédia não trazia o
    país da sede, e sem ele 104 partidas não eram contadas em lugar nenhum do
    mapa. A geocodificação fechou o buraco — e a flag existe para o front-end
    nunca precisar adivinhar se pode confiar na métrica.
    """
    assert metrics["matches_received_complete"] is True
