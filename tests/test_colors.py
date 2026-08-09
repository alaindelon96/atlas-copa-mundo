"""Testes das rampas de cor do mapa (Etapa 4).

O mapa pinta o modo de confronto direto na cor da própria seleção — Brasil em
amarelo, Itália em azzurro. Isso transforma uma tabela curada à mão em cor na
tela, e as maneiras de errar são silenciosas: uma rampa que escurece e depois
clareia inverte a leitura num país só, e uma cor cinza demais vira o cinza de
"sem dado". Nenhuma das duas gera erro em lugar nenhum.

    pytest -q
"""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from etl.color import CHROMA_FLOOR, MIN_CHROMA, STOPS, hex_to_oklch, oklch_to_hex, ramp
from etl.paths import REFERENCE, WEB, WEB_DATA

HEX = re.compile(r"^#[0-9A-F]{6}$")


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(REFERENCE / "team_colors.csv")


@pytest.fixture(scope="module")
def colors() -> dict:
    path = WEB_DATA / "colors.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def metrics() -> dict:
    path = WEB_DATA / "metrics.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def teams() -> list[str]:
    path = WEB_DATA / "timeline.json"
    if not path.exists():
        pytest.skip("Rode `python -m etl.metrics` primeiro.")
    return json.loads(path.read_text(encoding="utf-8"))["teams"]


# --- a tabela curada ------------------------------------------------------


def test_toda_selecao_do_modelo_tem_cor(table, teams):
    """Sem cor, a seleção escolhida pintaria o mapa de nada.

    O modelo tem 83 seleções e a tabela precisa cobrir as 83. Uma linha faltando
    só apareceria quando alguém escolhesse justamente aquele país.
    """
    assert set(teams) <= set(table.team_name), \
        f"sem cor: {sorted(set(teams) - set(table.team_name))}"


def test_nenhuma_cor_lê_como_cinza(table):
    """Cinza é a cor de "sem dado" — uma rampa cinzenta seria ambígua.

    É por isso que as 16 seleções de camisa branca ou preta (Alemanha,
    Inglaterra, Polônia, Peru, Nova Zelândia…) recebem a cor cromática que as
    identifica, e não o branco/preto do uniforme.
    """
    faint = [(row.team_name, row.hex, round(hex_to_oklch(row.hex)[1], 3))
             for row in table.itertuples() if hex_to_oklch(row.hex)[1] < MIN_CHROMA]
    assert faint == []


def test_last_cup_bate_com_o_modelo(table, metrics):
    """A cor é a da camisa da **última Copa disputada** — então o ano tem que ser
    o mesmo que o modelo calcula.

    Sem esta conferência, uma seleção que voltasse a jogar deixaria a linha
    desatualizada em silêncio, e a cor passaria a descrever um uniforme que não é
    mais o último. Já pegou dois erros de curadoria: Itália (última em 2014, não
    2026) e Peru (2018).
    """
    declared = dict(zip(table.team_name, table.last_cup))
    for team in metrics["teams"]:
        assert int(declared[team["team"]]) == team["last_year"], team["team"]


def test_as_nove_selecoes_antigas_estao_certas(table):
    """As únicas em que "última Copa" difere do uniforme atual.

    48 das 83 disputaram 2026, então para a maioria a distinção não morde. Ela
    morde aqui — e é justamente onde a curadoria precisou de pesquisa.
    """
    antigas = dict(zip(table.team_name, table.last_cup))
    assert antigas["Cuba"] == 1938
    assert antigas["Indonesia"] == 1938   # como Índias Orientais Neerlandesas
    assert antigas["Israel"] == 1970
    assert antigas["Kuwait"] == 1982
    assert antigas["El Salvador"] == 1982
    assert antigas["Hungary"] == 1986
    assert antigas["Northern Ireland"] == 1986
    assert antigas["United Arab Emirates"] == 1990
    assert antigas["Bolivia"] == 1994
    assert sum(1 for year in table.last_cup if year < 1998) == 9


def test_as_excecoes_estao_declaradas(table):
    """Quem não usa a cor da camisa principal tem que dizer por quê.

    Mesma lógica do `team_succession.csv`: decisão editorial fica versionada com
    o motivo, não escondida no código.
    """
    identity = table[table.basis == "identity"]
    assert len(identity) >= 10
    assert identity.note.notna().all(), "exceção sem justificativa"
    assert set(table.basis) <= {"home", "identity"}
    assert table.hex.str.upper().str.match(HEX).all()


# --- as rampas geradas ----------------------------------------------------


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_claridade_e_monotona(colors, mode):
    """A claridade é o que carrega o dado.

    Ela sobe (ou desce) sem voltar em nenhum passo — é isso que mantém a rampa
    legível para quem não distingue matizes, já que a informação não está no
    matiz. Uma rampa que quebrasse a monotonia inverteria a leitura num trecho,
    e só naquele país.
    """
    for team, entry in colors["teams"].items():
        lightness = [hex_to_oklch(step)[0] for step in entry[mode]]
        ordered = sorted(lightness, reverse=(mode == "light"))
        assert lightness == pytest.approx(ordered, abs=1e-9), f"{team} ({mode})"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_a_rampa_continua_sendo_a_cor_da_selecao(colors, mode):
    """O matiz não pode escorregar ao longo da rampa.

    Se ele escorregasse, o amarelo do Brasil chegaria laranja na ponta escura e
    a rampa deixaria de identificar a seleção — que é o único motivo de ela
    existir. Por isso a conversão reduz o croma, e não os canais RGB, quando uma
    cor não cabe em sRGB: clampar canal move o matiz.

    A tolerância é maior no fim escuro porque lá o croma fica pequeno, e quanto
    menor o croma menos o ângulo de matiz significa.
    """
    for team, entry in colors["teams"].items():
        base = hex_to_oklch(entry["hex"])[2]
        for step in entry[mode]:
            lightness, chroma, hue = hex_to_oklch(step)
            if chroma < 0.03:
                continue
            drift = abs((hue - base + 180) % 360 - 180)
            assert drift < 12, f"{team} ({mode}): matiz andou {drift:.1f}° em {step}"


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_o_zero_nao_se_confunde_com_sem_dado(colors, mode):
    """O passo mais fraco carrega um traço do matiz, de propósito.

    Zero e "sem dado" são coisas diferentes: a seleção que jogou e não marcou
    não pode parecer a que nunca jogou. Se a ponta vazia fosse acromática, ela
    seria um cinza quase igual ao cinza de fora do dado.
    """
    for team, entry in colors["teams"].items():
        chroma = hex_to_oklch(entry[mode][0])[1]
        assert chroma > 0.004, f"{team} ({mode}): ponta vazia acromática"


def test_a_visao_global_nao_usa_a_cor_de_ninguem(colors):
    """Sem país escolhido, a rampa é uma só.

    Dar a cada país a sua própria cor deixaria o mapa bonito e ilegível: o olho
    lê escuridão como quantidade, então uma Itália azul-escura pareceria "mais"
    que um Brasil amarelo vivo com número maior.
    """
    assert set(colors["default"]) == {"light", "dark"}
    assert set(colors["diverging"]["light"]) == {"negative", "positive"}
    for mode in ("light", "dark"):
        assert len(colors["default"][mode]) == STOPS


def test_os_polos_do_saldo_sao_fixos(colors):
    """Polaridade precisa de dois polos fixos.

    Se o lado positivo virasse a cor da seleção escolhida, "negativo" mudaria de
    cor a cada troca de país e o mapa deixaria de ter um lado.
    """
    negative = colors["diverging"]["light"]["negative"]
    positive = colors["diverging"]["light"]["positive"]
    # extremos em matizes opostos o suficiente para lerem como polos
    quente = hex_to_oklch(negative[-1])[2]
    frio = hex_to_oklch(positive[-1])[2]
    assert abs((quente - frio + 180) % 360 - 180) > 90


# --- a matemática de cor --------------------------------------------------


def test_a_conversao_ida_e_volta_fecha():
    for value in ["#FFDF00", "#0066B2", "#FF6C00", "#75AADB", "#006847"]:
        lightness, chroma, hue = hex_to_oklch(value)
        assert oklch_to_hex(lightness, chroma, hue).upper() == value.upper()


def test_cor_fora_do_gamut_perde_croma_e_nao_matiz():
    """Amarelo escuro e saturado não existe em sRGB.

    Clampar os canais devolveria um laranja; reduzir o croma devolve um amarelo
    apagado — que é o certo, porque claridade e matiz são o que a rampa precisa
    preservar.
    """
    _, chroma, hue = hex_to_oklch("#FFDF00")
    escuro = oklch_to_hex(0.35, chroma, hue)
    assert HEX.match(escuro)
    resultado = hex_to_oklch(escuro)
    assert resultado[0] == pytest.approx(0.35, abs=0.02)
    assert resultado[1] < chroma
    assert abs((resultado[2] - hue + 180) % 360 - 180) < 12


# --- bandeiras -----------------------------------------------------------


def test_toda_selecao_tem_bandeira_no_disco(colors):
    """Um SVG ausente vira ícone quebrado na tabela — sem erro, sem teste falhando.

    O caminho é montado no ETL e servido como arquivo estático, então nada no
    navegador confere se ele existe; o `onerror` do `<img>` volta para o ponto
    colorido, e o buraco passaria despercebido.
    """
    for team, entry in colors["teams"].items():
        assert entry["flag"], f"{team} sem bandeira"
        assert (WEB / "vendor" / "flags" / entry["flag"]).exists(), f"{team}: {entry['flag']}"


def test_as_quatro_selecoes_britanicas_tem_bandeiras_distintas(colors):
    """O mesmo motivo pelo qual o projeto usa `map_units` e não `countries`.

    As quatro dividem o ISO "GB". Se a bandeira saísse do código de país, as
    quatro mostrariam a Union Jack e o mapa diria que são o mesmo país — que é
    exatamente a fusão que este projeto recusa desde a Etapa 3.
    """
    files = {name: colors["teams"][name]["flag"]
             for name in ("England", "Scotland", "Wales", "Northern Ireland")}
    assert len(set(files.values())) == 4, files
    assert files["Northern Ireland"] == "gb-nir.svg"


def test_a_irlanda_do_norte_tem_bandeira(colors):
    """Foi ela que decidiu SVG em vez de emoji.

    O Unicode nunca criou `GB-NIR`: com emoji, a Irlanda do Norte era a única
    seleção sem bandeira possível. Este teste trava o ganho — se alguém voltar
    para emoji, ele falha e diz o porquê.
    """
    assert colors["teams"]["Northern Ireland"]["flag"]
    assert (WEB / "vendor" / "flags" / "gb-nir.svg").exists()


def test_flag_file_ignora_codigo_ausente():
    from etl.metrics import flag_file
    assert flag_file("BR") == "br.svg"
    assert flag_file("GB-ENG") == "gb-eng.svg"
    assert flag_file("-99") == ""
    assert flag_file("") == ""


def test_a_licenca_das_bandeiras_esta_versionada():
    """São arquivos de terceiros redistribuídos — a licença vai junto."""
    assert (WEB / "vendor" / "flags" / "LICENSE.md").exists()


def test_a_rampa_tem_o_numero_de_passos_declarado():
    assert len(ramp("#FFDF00", "light")) == STOPS
    assert 0 < CHROMA_FLOOR < 1
