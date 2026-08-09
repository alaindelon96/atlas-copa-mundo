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
from etl.paths import REFERENCE, WEB_DATA

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

    É por isso que as 12 seleções de camisa branca ou preta (Alemanha,
    Inglaterra, Polônia, Nova Zelândia…) recebem a cor cromática que as
    identifica, e não o branco/preto do uniforme.
    """
    faint = [(row.team_name, row.hex, round(hex_to_oklch(row.hex)[1], 3))
             for row in table.itertuples() if hex_to_oklch(row.hex)[1] < MIN_CHROMA]
    assert faint == []


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


def test_a_rampa_tem_o_numero_de_passos_declarado():
    assert len(ramp("#FFDF00", "light")) == STOPS
    assert 0 < CHROMA_FLOOR < 1
