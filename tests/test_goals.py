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
    # Uma entrada por PESSOA, não por nome. Eram `player.nunique()` (1.562)
    # enquanto o índice era o nome; são `player_id.nunique()` (1.618) desde que
    # a identidade passou a ser o id — a diferença são os homônimos, que antes
    # somavam gols de gente diferente na mesma linha.
    assert len(payload["players"]) == goals.player_id.nunique()
    assert goals.player_id.nunique() > goals.player.nunique()

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


# --- identidade de jogador ------------------------------------------------


def test_todo_gol_tem_player_id(goals):
    """Sem id não há artilheiro: a soma cairia de volta no nome."""
    assert goals.player_id.notna().all()
    assert (goals.player_id.str.strip() != "").all()


def test_um_id_tem_um_nome_so(goals):
    """O id é a pessoa e o nome é o rótulo dela. Um id com dois nomes seria
    duas pessoas coladas — o erro que a ponte existe para não cometer."""
    split = goals.groupby("player_id").player.nunique()
    assert split.max() == 1, f"id com mais de um nome: {sorted(split[split > 1].index)}"


def test_os_dois_ronaldos_sao_pessoas_diferentes(goals):
    """O caso que motivou tudo isto.

    Por nome, o Ronaldo brasileiro (15 gols entre 1998 e 2006) somava com um
    Ronaldo português de 2026 e virava um artilheiro de 18 — recorde que nunca
    existiu, e que passava na frente do Klose, que tem o de verdade com 16.
    """
    ronaldos = goals[goals.player == "Ronaldo"].groupby("player_id")
    assert len(ronaldos) == 2, "os dois Ronaldos voltaram a ser um só"
    times = {sorted(set(sub.player_team))[0] for _, sub in ronaldos}
    assert times == {"Brazil", "Portugal"}


def test_quem_marcou_nas_duas_fontes_continua_uma_pessoa(goals):
    """O outro lado da mesma moeda: Casemiro e Neymar marcaram antes e em 2026,
    pelo Brasil nas duas vezes. Separá-los subestimaria os dois."""
    for nome, esperado in (("Neymar", {"Brazil"}), ("Casemiro", {"Brazil"})):
        sub = goals[goals.player == nome]
        assert sub.player_id.nunique() == 1, f"{nome} foi partido em dois"
        assert set(sub.player_team) == esperado
        assert {"fjelstul", "wikipedia"} <= set(sub.source), f"{nome} não cruza as fontes"


def test_homonimo_do_fjelstul_nao_vira_ponte(goals):
    """Cinco nomes do Fjelstul têm dois `player_id` cada, mesma seleção,
    décadas diferentes. Um nome de 2026 que casasse com um deles não teria como
    saber com qual — e a regra é recusar a ponte, não escolher."""
    for nome in ("Oscar", "Júnior", "Juanito", "József Tóth", "Andoni Goikoetxea"):
        sub = goals[goals.player == nome]
        if sub.empty:
            continue
        assert sub.player_id.nunique() >= 2, f"{nome} foi fundido num id só"


def test_o_artilheiro_de_todos_os_tempos_e_klose(goals):
    """A conta que a página mostra. Klose 16 é o recorde real da Copa; se este
    teste apontar para outra pessoa, ou a identidade quebrou ou o dado mudou."""
    marcados = goals[~goals.own_goal.astype(bool)]
    top = marcados.groupby("player_id").size().sort_values(ascending=False)
    campeao = top.index[0]
    linha = marcados[marcados.player_id == campeao].iloc[0]
    assert (linha.player, int(top.iloc[0])) == ("Miroslav Klose", 16)


def test_o_json_carrega_a_selecao_de_cada_artilheiro(payload):
    """`player_teams` existe porque a coluna `team` do gol é a **creditada** —
    num gol contra, a adversária de quem chutou. Sem ela o front-end colocaria
    o autor de um gol contra na seleção errada."""
    assert len(payload["player_teams"]) == len(payload["players"])
    assert all(index >= 0 for index in payload["player_teams"])


def test_homonimos_no_json_sao_entradas_separadas(payload):
    """Dois jogadores com o mesmo nome viram duas entradas com o mesmo rótulo —
    é `player_teams` que os separa na tela."""
    nomes = payload["players"]
    repetidos = {nome for nome in nomes if nomes.count(nome) > 1}
    assert "Ronaldo" in repetidos
    posicoes = [i for i, nome in enumerate(nomes) if nome == "Ronaldo"]
    times = {payload["player_teams"][i] for i in posicoes}
    assert len(times) == len(posicoes), "os Ronaldos ficaram na mesma seleção"
