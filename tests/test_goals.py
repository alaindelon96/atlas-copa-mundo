"""Testes da tabela de gols (Etapa 5).

Esta tabela existe porque uma suposição do projeto estava errada. A Etapa 3
concluiu que dado de jogador teria buraco em 2026 e cortou as features para "só
estatística de jogo" — conclusão certa sobre o Fjelstul, que termina em 2022, e
errada sobre o que já estava no disco: as páginas raspadas trazem os 308
artilheiros de 2026 com minuto.

Os testes aqui protegem as duas coisas que essa junção pode quebrar em silêncio:
o total (um gol perdido no parsing não gera erro nenhum) e a atribuição (um gol
contra creditado ao time errado inverte dois números de uma vez).

    pytest -q
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from etl.paths import PROCESSED, WEB_DATA


@pytest.fixture(scope="module")
def goals() -> pd.DataFrame:
    path = PROCESSED / "goals.csv"
    if not path.exists():
        pytest.skip("Rode `python -m etl.model` primeiro.")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def matches() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "matches.csv")


@pytest.fixture(scope="module")
def payload() -> dict:
    path = WEB_DATA / "goals.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))


# --- o total e a origem ---------------------------------------------------


def test_todo_gol_tem_autor_e_minuto(goals):
    """3.028 gols — o mesmo número que os placares já diziam.

    É o que torna esta tabela conferível em vez de apenas plausível: ela não
    inventa uma contagem própria, ela tem que reproduzir uma que o modelo já
    produzia por outro caminho.
    """
    assert len(goals) == 3028
    assert goals.player.notna().all() and (goals.player != "").all()
    assert goals.minute.notna().all()
    assert goals.minute_regulation.between(1, 120).all()


def test_as_duas_fontes_cobrem_periodos_diferentes(goals):
    """O Fjelstul vai até 2022; 2026 veio do HTML raspado da Wikipédia."""
    por_fonte = goals.groupby("source").year.agg(["min", "max", "size"])
    assert por_fonte.loc["fjelstul", "max"] == 2022
    assert por_fonte.loc["wikipedia", "min"] == 2026
    assert por_fonte.loc["wikipedia", "size"] == 308
    assert por_fonte.loc["fjelstul", "size"] == 2720


def test_cada_partida_fecha_com_o_proprio_placar(goals, matches):
    """A conferência linha a linha, e não só de total.

    Um gol atribuído à seleção errada mantém o total intacto e troca dois
    números de lugar — o tipo de erro que só aparece assim.

    A exceção é a Alemanha × Alemanha de 1974: pela decisão editorial do projeto
    os dois lados têm o mesmo rótulo, e não há como dizer a qual deles um gol
    pertence. `etl.validate` imprime o caso a cada execução.
    """
    contagem = goals.groupby(["match_id", "team"]).size()
    divergentes = []

    for match in matches.itertuples():
        if match.home_team == match.away_team:
            continue
        casa = contagem.get((match.match_id, match.home_team), 0)
        fora = contagem.get((match.match_id, match.away_team), 0)
        if casa != match.home_team_score or fora != match.away_team_score:
            divergentes.append(match.match_id)

    assert divergentes == []


# --- gol contra -----------------------------------------------------------


def test_gol_contra_e_creditado_a_quem_ganhou_o_gol(goals):
    """A regra que faz a soma fechar com o placar.

    Quem chuta é de um time, o gol conta para o outro. Se `team` fosse o time do
    jogador, todo gol contra ficaria do lado errado e duas seleções teriam o
    número trocado na mesma partida.
    """
    contras = goals[goals.own_goal == 1]
    assert len(contras) > 50
    assert (contras.team != contras.player_team).all()

    normais = goals[goals.own_goal == 0]
    assert (normais.team == normais.player_team).all()


# --- artilheiros ----------------------------------------------------------


def test_artilheiro_de_2026_bate_com_a_fonte(goals):
    """Mbappé, 10 gols.

    O número foi extraído dos artilheiros partida a partida; o artigo declara o
    mesmo total em outro lugar da página, sem que o parser o leia. As duas vias
    chegando ao mesmo lugar é a conferência.
    """
    de_2026 = goals[(goals.year == 2026) & (goals.own_goal == 0)]
    artilheiro = de_2026.player.value_counts()
    assert artilheiro.index[0] == "Mbappé"
    assert artilheiro.iloc[0] == 10


def test_artilheiros_historicos_do_brasil(goals):
    """Ronaldo 15 e Pelé 12 — os dois números mais conhecidos do país."""
    brasil = goals[(goals.team == "Brazil") & (goals.own_goal == 0)]
    contagem = brasil.player.value_counts()
    assert contagem["Ronaldo"] == 15
    assert contagem["Pelé"] == 12


def test_nome_de_jogador_sem_o_sentinel_da_fonte(goals):
    """O Fjelstul grava `"not applicable"` no primeiro nome de quem só tem um.

    O Ronaldo brasileiro é o caso famoso. Sem tratamento, ele apareceria na tela
    como "not applicable Ronaldo" — o mesmo tipo de sentinel que o `pandera`
    pegou na Etapa 3, agora numa coluna de texto.
    """
    assert not goals.player.str.contains("not applicable").any()


# --- o payload do front-end -----------------------------------------------


def test_o_payload_preserva_tudo(payload, goals):
    assert len(payload["rows"]) == len(goals) == 3028
    assert payload["competition"] == "mens"
    assert len(payload["players"]) == goals.player.nunique()

    marcas = [row[5] for row in payload["rows"]]
    assert marcas.count(1) == int(goals.penalty.sum())
    assert marcas.count(2) == int(goals.own_goal.sum())


def test_o_minuto_de_acrescimo_sobrevive_ao_payload(payload):
    """`90+7'` não é `97'` — e a diferença aparece na tela.

    O acréscimo é guardado à parte justamente para o front-end poder escrever
    "90+7'". Somar os dois no ETL perderia a distinção sem perder nenhum gol.
    """
    com_acrescimo = [row for row in payload["rows"] if row[4] > 0]
    assert len(com_acrescimo) > 100
    assert all(row[3] in (45, 90, 105, 120) for row in com_acrescimo)
