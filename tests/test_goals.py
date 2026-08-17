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

from etl.paths import INTERIM, PROCESSED, WEB_DATA


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
def goals_2026() -> pd.DataFrame:
    """A camada intermediária: o que a página de 2026 disse, antes do modelo."""
    path = INTERIM / "goals_2026.csv"
    if not path.exists():
        pytest.skip("Rode `python -m etl.parse_2026` primeiro.")
    return pd.read_csv(path)


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


def test_o_parser_guarda_o_artigo_de_cada_artilheiro_de_2026(goals_2026):
    """A identidade de 2026 vem do link, e este é o teste que a protege na origem.

    O `player_page` é o artigo para onde a caixa de partida aponta — a única
    identidade que a Wikipédia oferece, já que ela não tem id de jogador. Se o
    parser voltar a ler só o texto exibido, a coluna esvazia aqui, muito antes de
    o estrago aparecer como um artilheiro partido em dois lá na frente.

    Os 308 gols têm link. Um nome sem âncora não seria erro — a Wikipédia deixa
    sem link quem não tem artigo —, mas hoje não há nenhum, e é o que se afirma.
    """
    assert len(goals_2026) == 308
    assert goals_2026.player_page.notna().all()
    assert (goals_2026.player_page.str.strip() != "").all()

    artigo = dict(zip(goals_2026.player_name, goals_2026.player_page))
    assert artigo["Mbappé"] == "Kylian Mbappé"
    assert artigo["Quiñones"] == "Julián Quiñones"
    assert artigo["Mokoena"] == "Teboho Mokoena (soccer, born 1997)"

    # Um nome exibido nunca aponta para dois artigos: se apontasse, o rótulo
    # curto seria ambíguo dentro do próprio torneio e a ponte não teria chave.
    assert goals_2026.groupby("player_name").player_page.nunique().max() == 1


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
    """Kylian Mbappé, 10 gols.

    O número foi extraído dos artilheiros partida a partida; o artigo declara o
    mesmo total em outro lugar da página, sem que o parser o leia. As duas vias
    chegando ao mesmo lugar é a conferência.
    """
    de_2026 = goals[(goals.year == 2026) & (goals.own_goal == 0)]
    artilheiro = de_2026.player.value_counts()
    assert artilheiro.index[0] == "Kylian Mbappé"
    assert artilheiro.iloc[0] == 10


def test_o_artilheiro_de_2026_tem_nome_inteiro(goals):
    """A caixa de partida abrevia; o link não — e o rótulo passou a sair do link.

    Enquanto o parser lia só o texto exibido, 2026 entrava na lista com o nome
    curto ("Mbappé", "Quiñones") ao lado dos nomes inteiros de 1930–2022. Não era
    só desalinho de estilo: era o que impedia a mesma pessoa de se reconhecer
    entre as duas fontes.

    Sobram cinco nomes de uma palavra só, e os cinco são assim de fato — nome
    artístico brasileiro ou egípcio, não sobrenome solto.
    """
    de_2026 = set(goals[goals.year == 2026].player)
    assert {"Kylian Mbappé", "Lionel Messi", "Julián Quiñones"} <= de_2026

    monônimos = {nome for nome in de_2026 if " " not in nome}
    assert monônimos == {"Casemiro", "Diney", "Maurício", "Neymar", "Trézéguet"}


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
    # Uma entrada por PESSOA, não por nome. Eram `player.nunique()` enquanto o
    # índice era o nome; são `player_id.nunique()` (1.599) desde que a identidade
    # passou a ser o id — a diferença são os homônimos, que antes somavam gols de
    # gente diferente na mesma linha. O número caiu de 1.618 quando 2026 passou a
    # trazer o nome inteiro: 27 entradas que eram a mesma pessoa duas vezes.
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

    Desde que o rótulo de 2026 vem do artigo, os dois nem homônimos são mais: o
    português aparece como "Cristiano Ronaldo". O que sustenta a separação, no
    entanto, continua sendo o `player_id` — o rótulo é consequência, não causa.
    """
    brasileiro = goals[(goals.player == "Ronaldo") & (goals.player_team == "Brazil")]
    portugues = goals[goals.player == "Cristiano Ronaldo"]

    assert brasileiro.player_id.nunique() == 1
    assert portugues.player_id.nunique() == 1
    assert set(brasileiro.player_id) != set(portugues.player_id), "voltaram a ser um só"
    assert len(brasileiro) == 15
    assert set(portugues.player_team) == {"Portugal"}


def test_quem_marcou_nas_duas_fontes_continua_uma_pessoa(goals):
    """O outro lado da mesma moeda: Casemiro e Neymar marcaram antes e em 2026,
    pelo Brasil nas duas vezes. Separá-los subestimaria os dois."""
    for nome, esperado in (("Neymar", {"Brazil"}), ("Casemiro", {"Brazil"})):
        sub = goals[goals.player == nome]
        assert sub.player_id.nunique() == 1, f"{nome} foi partido em dois"
        assert set(sub.player_team) == esperado
        assert {"fjelstul", "wikipedia"} <= set(sub.source), f"{nome} não cruza as fontes"


def test_quem_ja_jogava_nao_recomeca_do_zero_em_2026(goals):
    """As 27 uniões — o que a página estava contando duas vezes.

    Enquanto o nome de 2026 era o nome curto da caixa de partida, "Mbappé" não
    casava com "Kylian Mbappé" e a lista trazia a mesma pessoa em duas linhas.
    Aqui os totais são a soma das duas fontes, e cada um deles é conferível de
    cabeça: 12 + 10, 13 + 8, 8 + 6, 8 + 3.
    """
    marcados = goals[~goals.own_goal.astype(bool)]

    def carreira(nome: str) -> tuple[int, set[str]]:
        dele = marcados[marcados.player == nome]
        assert dele.player_id.nunique() == 1, f"{nome} está partido em dois"
        return len(dele), set(dele.source)

    for nome, total in (("Kylian Mbappé", 22), ("Lionel Messi", 21),
                        ("Harry Kane", 14), ("Cristiano Ronaldo", 11),
                        ("Jude Bellingham", 8), ("Vinícius Júnior", 5)):
        gols, fontes = carreira(nome)
        assert gols == total, f"{nome}: {gols} gols, esperado {total}"
        assert fontes == {"fjelstul", "wikipedia"}, f"{nome} não cruza as fontes"

    unidos = set(marcados[marcados.year == 2026].player_id) & \
        set(marcados[marcados.year < 2026].player_id)
    assert len(unidos) == 27


def test_acento_a_menos_nao_faz_dois_jogadores(goals):
    """As fontes discordam da grafia em um caso, e ele custava um gol.

    A Wikipédia titula o artigo do argentino "Julián Alvarez" e o Fjelstul grava
    "Julián Álvarez". Pela comparação literal viravam duas pessoas, uma de 4 gols
    e outra de 1; é o mesmo jogador e são 5. O rótulo que fica é o da fonte que
    já o tinha — uma identidade, um nome só.
    """
    dele = goals[goals.player.str.contains("lvarez") & (goals.player_team == "Argentina")]
    assert dele.player_id.nunique() == 1, "o acento partiu o Julián Álvarez em dois"
    assert set(dele.player) == {"Julián Álvarez"}
    assert len(dele) == 5
    assert {"fjelstul", "wikipedia"} <= set(dele.source)


def test_titulo_desambiguado_nao_vira_ponte(goals):
    """Os dois Teboho Mokoena — a união que **não** pode acontecer.

    Um fez o gol da África do Sul em 2002; o outro, o de 2026. Mesmo nome, mesma
    seleção, pessoas diferentes — e quem avisa é a própria Wikipédia, que precisa
    titular o artigo do segundo como "Teboho Mokoena (soccer, born 1997)". É o
    desambiguador que impede a ponte: sem essa regra, a regra de nome + seleção
    somaria os dois, que é o erro do Ronaldo ao contrário.
    """
    mokoena = goals[goals.player == "Teboho Mokoena"]
    assert len(mokoena) == 2
    assert mokoena.player_id.nunique() == 2, "os dois Mokoena viraram um só"
    assert set(mokoena.year) == {2002, 2026}
    assert set(mokoena.player_team) == {"South Africa"}


def test_sobrenome_igual_nao_e_a_mesma_pessoa(goals):
    """A ponte é pelo artigo, não pelo sobrenome.

    Keito Nakamura (2026) não é Shunsuke Nakamura, e Mateo Chávez não é Luis
    Chávez. São os dois únicos casos em que um artilheiro de 2026 divide o
    sobrenome com alguém da mesma seleção no histórico — e nos dois o nome
    inteiro, que agora existe, já diz que são pessoas diferentes.
    """
    for antigo, novo in (("Shunsuke Nakamura", "Keito Nakamura"),
                         ("Luis Chávez", "Mateo Chávez")):
        ids = set(goals[goals.player == antigo].player_id)
        assert ids and not ids & set(goals[goals.player == novo].player_id)


def test_homonimo_do_fjelstul_nao_vira_ponte(goals):
    """Cinco nomes do Fjelstul têm dois `player_id` cada, mesma seleção,
    décadas diferentes. Um nome de 2026 que casasse com um deles não teria como
    saber com qual — e a regra é recusar a ponte, não escolher."""
    for nome in ("Oscar", "Júnior", "Juanito", "József Tóth", "Andoni Goikoetxea"):
        sub = goals[goals.player == nome]
        if sub.empty:
            continue
        assert sub.player_id.nunique() >= 2, f"{nome} foi fundido num id só"


def test_o_artilheiro_de_todos_os_tempos(goals):
    """A conta que a página mostra — e que só fecha com a identidade resolvida.

    São duas afirmações, e é preciso as duas: **Mbappé tem 22** somando 1930–2026
    e **Klose tem 16**, que era o recorde e continua sendo o maior de quem parou
    antes de 2026. Se este teste apontasse para o Klose, seria sinal de que os 10
    gols de 2026 do Mbappé estão de novo numa linha separada dos 12 anteriores —
    exatamente o que a página exibia antes: 12 numa entrada, 10 na outra, e o
    número que importa em nenhuma.
    """
    marcados = goals[~goals.own_goal.astype(bool)]
    top = marcados.groupby("player_id").size().sort_values(ascending=False)
    campeao = top.index[0]
    linha = marcados[marcados.player_id == campeao].iloc[0]
    assert (linha.player, int(top.iloc[0])) == ("Kylian Mbappé", 22)

    ate_2022 = marcados[marcados.year <= 2022]
    recorde_antigo = ate_2022.groupby("player_id").size().sort_values(ascending=False)
    assert ate_2022[ate_2022.player_id == recorde_antigo.index[0]].player.iloc[0] == "Miroslav Klose"
    assert int(recorde_antigo.iloc[0]) == 16


def test_a_carreira_de_um_jogador_soma_entre_as_copas(goals):
    """A página de um jogador mostra a CARREIRA, e não o recorte do slider.

    Ela é a única tela que ignora a faixa de anos, porque uma pessoa não é uma
    faixa de anos: abrir o Pelé pela Copa de 1970 e ler "4 gols" descreve 1970
    certo e descreve o Pelé errado. Como a tela passou a afirmar o total de uma
    carreira, o total vira número conferível — e por identidade, nunca por nome.

    Os três aqui são os que qualquer torcedor confere de cabeça.
    """
    marcados = goals[~goals.own_goal.astype(bool)]

    def carreira(nome: str) -> tuple[int, int]:
        dele = marcados[marcados.player == nome]
        assert dele.player_id.nunique() == 1, f"{nome} não é uma pessoa só"
        return len(dele), dele.year.nunique()

    assert carreira("Pelé") == (12, 4)
    assert carreira("Miroslav Klose") == (16, 4)
    assert carreira("Just Fontaine") == (13, 1)


def test_o_json_carrega_a_selecao_de_cada_artilheiro(payload):
    """`player_teams` existe porque a coluna `team` do gol é a **creditada** —
    num gol contra, a adversária de quem chutou. Sem ela o front-end colocaria
    o autor de um gol contra na seleção errada."""
    assert len(payload["player_teams"]) == len(payload["players"])
    assert all(index >= 0 for index in payload["player_teams"])


def test_homonimos_no_json_sao_entradas_separadas(payload):
    """Dois jogadores com o mesmo nome viram duas entradas com o mesmo rótulo.

    A lista de homônimos encolheu quando 2026 passou a trazer o nome inteiro — o
    "Ronaldo" português virou "Cristiano Ronaldo" e saiu daqui. Os que restam são
    homônimos de verdade, gente diferente com o mesmo nome, e o `player_id` os
    mantém como entradas separadas.
    """
    nomes = payload["players"]
    repetidos = {nome for nome in nomes if nomes.count(nome) > 1}
    assert "Ronaldo" not in repetidos, "o rótulo de 2026 voltou a ser o nome curto"
    assert repetidos == {"Andoni Goikoetxea", "Juanito", "József Tóth",
                         "Júnior", "Oscar", "Teboho Mokoena"}
