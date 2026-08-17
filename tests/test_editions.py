"""Testes da edição como destino (Etapa 4h — Copa a Copa).

A tela de uma Copa não trouxe dado novo: ela DERIVA no navegador seis coisas a
partir do que já estava em `web/data/`. Derivar é barato e silencioso — se uma
suposição estiver errada, a tela não quebra, ela mente com aparência de fato.
Estes testes travam as suposições, uma a uma, do lado do Python:

    sede            `timeline.hosted`
    campeão         `timeline.titles`
    vice            o outro lado da final — menos em 1950, que não teve final
    artilheiro      `goals.json`, por `player_id` e nunca por nome
    totais          o placar de `matches.json`
    fases           os nomes de fase que a ordem do calendário conhece

O caso que mais pesa aqui é 1950: é a única edição sem final, e é a única em que
o vice sai de uma tabela de pontos. Um `min()` distraído ali daria a Suécia, e
ninguém notaria olhando a tela.

    pytest -q
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import pytest

from etl.paths import WEB_DATA

# A ordem do calendário que `map.js` usa para agrupar as partidas por fase. As
# duas listas têm que casar: uma fase que exista no dado e não esteja aqui cai
# no fim da tela, fora da ordem em que o torneio aconteceu.
STAGE_ORDER = [
    "group stage",
    "second group stage",
    "round of 32",
    "round of 16",
    "quarter-finals",
    "semi-finals",
    "third-place match",
    "final",
    "final round",
]


def _load(name: str) -> dict:
    path = WEB_DATA / f"{name}.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matches() -> dict:
    return _load("matches")


@pytest.fixture(scope="module")
def timeline() -> dict:
    return _load("timeline")


@pytest.fixture(scope="module")
def goals() -> dict:
    return _load("goals")


@pytest.fixture(scope="module")
def venues() -> dict:
    return _load("venues")


@pytest.fixture(scope="module")
def champions(timeline) -> dict[int, str]:
    """Ano → campeão, como `TIMELINE.titles` entrega para a tela."""
    return {
        timeline["years"][row[0]]: timeline["teams"][row[1]]
        for row in timeline["titles"]
    }


@pytest.fixture(scope="module")
def finals(matches) -> dict[int, tuple[str, str, int, int, list | None]]:
    """Ano → a final daquela edição (mandante, visitante, gols, pênaltis)."""
    out = {}
    for row in matches["rows"]:
        if matches["stages"][row[1]] != "final":
            continue
        out[row[0]] = (
            matches["teams"][row[2]],
            matches["teams"][row[3]],
            row[4],
            row[5],
            row[8],
        )
    return out


# --- campeão e vice -------------------------------------------------------


def test_toda_edicao_tem_exatamente_um_campeao(timeline, champions):
    """23 edições, 23 títulos, um por ano.

    A tela lê o campeão de `titles` e não da final, para nunca discordar da
    métrica "títulos" que pinta o mapa. Se um ano aparecesse duas vezes aqui, a
    varredura elegeria o último e o mapa mostraria outro.
    """
    anos = [row[0] for row in timeline["titles"]]
    assert len(anos) == len(set(anos)) == len(timeline["years"]) == 23
    assert champions[1970] == "Brazil"
    assert champions[2002] == "Brazil"


def test_so_1950_nao_teve_final(matches, finals):
    """A exceção que a tela precisa tratar, e a única.

    1950 foi decidida num quadrangular: não existe partida de fase `final`
    naquele ano. Toda a lógica de vice depende disso continuar verdade — se
    outra edição perdesse a final, a tela mostraria "Vice: —" em silêncio.
    """
    anos = {row[0] for row in matches["rows"]}
    assert set(finals) == anos - {1950}
    assert len(finals) == 22


def test_quem_ganha_a_final_e_o_campeao_da_edicao(finals, champions):
    """As duas fontes do pódio têm que apontar para a mesma seleção.

    O campeão vem de `titles` e o vice é "o outro lado da final". Se o vencedor
    da final não fosse o campeão, o vice seria o próprio campeão — a tela
    mostraria a mesma seleção nas duas linhas.
    """
    for ano, (casa, fora, gols_casa, gols_fora, penaltis) in finals.items():
        if gols_casa > gols_fora:
            vencedor = casa
        elif gols_fora > gols_casa:
            vencedor = fora
        else:
            assert penaltis, f"final de {ano} empatada e sem pênaltis"
            vencedor = casa if penaltis[0] > penaltis[1] else fora
        assert vencedor == champions[ano], f"final de {ano}"


def test_o_vice_de_1950_e_o_brasil_pela_tabela_do_quadrangular(matches, champions):
    """O Maracanaço, e por que ele não é uma final.

    Uruguai 2×1 Brasil foi o último jogo e decidiu o título, mas o dado o
    registra como `final round` — porque foi isso que ele foi. O vice sai da
    classificação, com os DOIS pontos por vitória de 1950.

    O desempate importa aqui e é contraintuitivo: o Brasil tem saldo +10 contra
    +2 do Uruguai e mesmo assim é o segundo. Quem ordenasse por saldo, ou por
    gols marcados, inverteria o campeão da Copa de 1950.
    """
    tabela: dict[str, dict[str, int]] = defaultdict(
        lambda: {"pontos": 0, "gols": 0, "sofridos": 0}
    )
    for row in matches["rows"]:
        if row[0] != 1950 or matches["stages"][row[1]] != "final round":
            continue
        casa, fora = matches["teams"][row[2]], matches["teams"][row[3]]
        tabela[casa]["gols"] += row[4]
        tabela[casa]["sofridos"] += row[5]
        tabela[fora]["gols"] += row[5]
        tabela[fora]["sofridos"] += row[4]
        if row[4] > row[5]:
            tabela[casa]["pontos"] += 2
        elif row[5] > row[4]:
            tabela[fora]["pontos"] += 2
        else:
            tabela[casa]["pontos"] += 1
            tabela[fora]["pontos"] += 1

    ordem = sorted(
        tabela,
        key=lambda t: (
            -tabela[t]["pontos"],
            -(tabela[t]["gols"] - tabela[t]["sofridos"]),
            -tabela[t]["gols"],
        ),
    )
    assert ordem[:2] == ["Uruguay", "Brazil"]
    assert champions[1950] == ordem[0]
    assert tabela["Uruguay"]["pontos"] == 5
    assert tabela["Brazil"]["pontos"] == 4
    # O saldo que perderia a conta se o critério fosse ele.
    assert tabela["Brazil"]["gols"] - tabela["Brazil"]["sofridos"] == 10
    assert tabela["Uruguay"]["gols"] - tabela["Uruguay"]["sofridos"] == 2


# --- sede -----------------------------------------------------------------


def test_toda_edicao_tem_sede_e_duas_foram_divididas(timeline):
    """26 linhas para 23 edições: 2002 e 2026 têm mais de um país.

    A tela mostra quantas partidas cada sede recebeu justamente porque elas não
    são iguais — em 2026 os Estados Unidos recebem 78 das 104.
    """
    por_ano: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for row in timeline["hosted"]:
        por_ano[timeline["years"][row[0]]].append((timeline["teams"][row[1]], row[2]))

    assert len(por_ano) == 23
    assert all(sedes for sedes in por_ano.values())

    divididas = {ano: sedes for ano, sedes in por_ano.items() if len(sedes) > 1}
    assert set(divididas) == {2002, 2026}
    assert dict(divididas[2002]) == {"South Korea": 32, "Japan": 32}
    assert dict(divididas[2026]) == {"United States": 78, "Mexico": 13, "Canada": 13}


def test_toda_partida_tem_sede_e_os_dois_arquivos_listam_na_mesma_ordem(
    matches, venues
):
    """Os alfinetes da edição dependem das duas coisas.

    A contagem por sede vem de `matches.json` (que respeita o ano) e a
    coordenada vem de `venues.json`, casadas pelo ÍNDICE. Se as listas
    saíssem em ordens diferentes, cada alfinete cairia na cidade errada — e o
    mapa não tem como avisar que está mentindo.
    """
    assert all(row[6] >= 0 for row in matches["rows"])
    assert len(matches["venues"]) == len(venues["rows"]) == 208
    for sede, linha in zip(matches["venues"], venues["rows"]):
        assert (sede["name"], sede["city"], sede["country"]) == (
            linha[5],
            linha[6],
            linha[7],
        )


# --- artilheiro, totais e fases -------------------------------------------


def test_o_artilheiro_de_cada_edicao_e_por_pessoa(matches, goals):
    """Os recordes de artilharia de uma Copa, travados um a um.

    A conta é por `player_id` e não por nome — a mesma regra que a Etapa 4g
    trouxe. Aqui ela é mais fácil de acertar por acaso (dentro de uma edição
    homônimo é raro), e por isso mesmo vale travar os números que qualquer
    torcedor conferiria: Fontaine 13 em 58 é o recorde de uma Copa só.

    Gol contra fica de fora: ele é creditado à seleção que o ganhou.
    """
    ano_da_partida = [row[0] for row in matches["rows"]]
    por_ano: dict[int, Counter] = defaultdict(Counter)
    for gol in goals["rows"]:
        if gol[5] == 2:
            continue
        por_ano[ano_da_partida[gol[0]]][gol[2]] += 1

    def artilheiros(ano: int) -> tuple[set[str], int]:
        contagem = por_ano[ano]
        topo = max(contagem.values())
        return {goals["players"][k] for k, n in contagem.items() if n == topo}, topo

    assert artilheiros(1958) == ({"Just Fontaine"}, 13)
    assert artilheiros(1954) == ({"Sándor Kocsis"}, 11)
    assert artilheiros(1970) == ({"Gerd Müller"}, 10)
    assert artilheiros(2002) == ({"Ronaldo"}, 8)
    assert artilheiros(2022) == ({"Kylian Mbappé"}, 8)
    # Empate é o caso comum, e a tela mostra todos: eleger um por ordem de
    # varredura calaria cinco pessoas em 1962.
    assert artilheiros(1994) == ({"Hristo Stoichkov", "Oleg Salenko"}, 6)
    assert len(artilheiros(1962)[0]) == 6
    assert len(artilheiros(2010)[0]) == 4


def test_o_placar_e_a_artilharia_fecham_edicao_a_edicao(matches, goals):
    """Os totais que a tela mostra e a lista de gols contam a mesma Copa.

    O total de gols vem do PLACAR e a lista de artilheiros vem de `goals.json`.
    Nas 23 edições os dois batem — é o que permite a tela somar de um lado e
    listar do outro sem precisar explicar a diferença.
    """
    ano_da_partida = [row[0] for row in matches["rows"]]
    placar, partidas = Counter(), Counter()
    for row in matches["rows"]:
        partidas[row[0]] += 1
        placar[row[0]] += row[4] + row[5]

    registrados = Counter(ano_da_partida[gol[0]] for gol in goals["rows"])
    assert placar == registrados

    assert partidas[1930] == 18 and placar[1930] == 70
    assert partidas[1970] == 32 and placar[1970] == 95
    assert partidas[2022] == 64 and placar[2022] == 172
    assert partidas[2026] == 104 and placar[2026] == 308
    assert sum(partidas.values()) == 1068
    assert sum(placar.values()) == 3028


# --- o índice de confrontos -----------------------------------------------


def test_o_indice_de_confrontos_conta_cada_partida_uma_vez(timeline):
    """Cada partida está DUAS vezes no timeline, uma por lado.

    A tela conta o par uma vez só, pelo lado de índice menor. O mesmo teste
    descarta a Alemanha × Alemanha de 1974 — a única partida em que os dois
    lados carregam o mesmo rótulo, por decisão editorial do projeto. Daí 1.067
    e não 1.068: a que falta não é um confronto entre duas seleções.

    Se a exclusão sumisse, ela viraria um "confronto" de uma seleção contra si
    mesma no topo de uma lista ordenada por partidas.
    """
    pares: dict[tuple[int, int], int] = defaultdict(int)
    mesmo_rotulo = 0
    for row in timeline["rows"]:
        if row[1] == row[2]:
            mesmo_rotulo += 1
            continue
        pares[(min(row[1], row[2]), max(row[1], row[2]))] += 1

    # As duas linhas da mesma partida de 1974.
    assert mesmo_rotulo == 2
    # Cada par foi contado dos dois lados, então cada partida aparece duas vezes.
    assert sum(pares.values()) == 2 * 1067
    assert len(pares) == 682

    uma_vez = sum(1 for n in pares.values() if n == 2)
    assert uma_vez == 457, "dois terços dos confrontos acontecem uma vez só"


def test_o_maior_confronto_da_copa_e_argentina_x_alemanha(timeline):
    """Oito partidas, três delas finais — 1986, 1990 e 2014.

    É o número que abre a tela de confrontos, e o que dá sentido a ela: numa
    competição em que a maioria dos encontros nunca se repete, oito é muito.
    """
    teams = timeline["teams"]
    pares: dict[tuple[str, str], int] = defaultdict(int)
    for row in timeline["rows"]:
        if row[1] == row[2]:
            continue
        a, b = sorted((teams[row[1]], teams[row[2]]))
        pares[(a, b)] += 1

    ordenado = sorted(pares.items(), key=lambda kv: (-kv[1], kv[0]))
    (maior, partidas) = ordenado[0]
    assert maior == ("Argentina", "Germany")
    assert partidas // 2 == 8
    assert pares[("Brazil", "Sweden")] // 2 == 7


def test_o_indice_de_selecoes_tem_as_83_e_oito_campeas(timeline, champions):
    """A lista de A a Z e os dois números que a resumem.

    São 83 seleções e oito campeãs distintas — Uruguai, Itália, Alemanha,
    Brasil, Inglaterra, Argentina, França e Espanha. Oito e não nove: é a
    contagem de quem levantou a taça, não de quantas taças houve.
    """
    assert len(timeline["teams"]) == 83

    campeas = set(champions.values())
    assert campeas == {
        "Uruguay",
        "Italy",
        "Germany",
        "Brazil",
        "England",
        "Argentina",
        "France",
        "Spain",
    }
    assert len(campeas) == 8

    # E a soma das partidas de cada lado é o dobro do total: é o que a tela
    # divide por dois para mostrar 1.068 em vez de 2.136.
    jogadas = Counter()
    for row in timeline["rows"]:
        jogadas[timeline["teams"][row[1]]] += 1
    assert sum(jogadas.values()) == 2136 == 2 * 1068


def test_a_ordem_das_fases_cobre_todas_as_que_existem(matches):
    """Nenhuma fase do dado fica fora do calendário da tela.

    `MATCHES.stages` chega em ordem alfabética — é a lista de valores
    distintos, não um calendário —, então a tela ordena por uma lista própria.
    Uma fase nova no dado e ausente lá cairia no fim da página, depois da
    final.
    """
    assert set(matches["stages"]) <= set(STAGE_ORDER)

    # E nenhuma edição repete uma fase fora de ordem: dentro de um ano, cada
    # fase acontece uma vez só, que é o que permite agrupar por ela.
    fases_por_ano: dict[int, set[str]] = defaultdict(set)
    for row in matches["rows"]:
        fases_por_ano[row[0]].add(matches["stages"][row[1]])

    assert fases_por_ano[1950] == {"group stage", "final round"}
    assert "final" not in fases_por_ano[1950]
    # 2026 é a primeira com 32-avos, e a única.
    com_trinta_e_dois = {ano for ano, f in fases_por_ano.items() if "round of 32" in f}
    assert com_trinta_e_dois == {2026}
