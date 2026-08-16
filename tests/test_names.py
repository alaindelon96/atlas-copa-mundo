"""Testes dos nomes de seleção em português (Etapa 4).

A página é em pt-BR e o dado é em inglês. A ponte é `reference/team_names.csv`,
e as maneiras de errar são silenciosas: uma seleção sem linha aparece como
"Germany" no meio da tabela, e dois países com o mesmo rótulo viram duas linhas
idênticas no ranking com números diferentes — o que parece dado errado e é
rótulo errado.

    pytest -q
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from etl.metrics import build_names
from etl.paths import REFERENCE, WEB_DATA

ARTICLES = {"", "o", "a", "os", "as"}


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    return pd.read_csv(REFERENCE / "team_names.csv", keep_default_na=False)


@pytest.fixture(scope="module")
def names() -> dict:
    path = WEB_DATA / "names.json"
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


def test_toda_selecao_do_modelo_tem_nome(table, teams):
    """Uma linha faltando só apareceria quando alguém olhasse aquele país."""
    assert set(teams) <= set(table.team_name), \
        f"sem nome: {sorted(set(teams) - set(table.team_name))}"


def test_nenhum_nome_em_portugues_se_repete(table):
    """Dois rótulos iguais seriam duas linhas idênticas no ranking.

    O caso real que isso vigia é a Irlanda: "Republic of Ireland" e "Northern
    Ireland" são seleções diferentes, com polígonos diferentes, e encurtar as
    duas para "Irlanda" as fundiria na tela sem fundir nada no dado.
    """
    repeated = table.name_pt[table.name_pt.duplicated()].tolist()
    assert repeated == []


def test_os_artigos_sao_os_cinco_possiveis(table):
    """O artigo é o que faz a legenda dizer "da Alemanha" e não "de Alemanha".

    Vazio é uma resposta legítima — Portugal, Cuba, Israel e Cabo Verde não
    levam artigo —, mas qualquer outra coisa é erro de digitação que viraria
    "a cor dundefined Brasil".
    """
    assert set(table.artigo) <= ARTICLES


def test_paises_sem_artigo_sao_os_conhecidos(table):
    """A lista é curta e vale a pena estar à vista: quem acrescentar um país
    novo sem artigo por engano derruba este teste."""
    sem = set(table.team_name[table.artigo == ""])
    assert {"Portugal", "Cuba", "Israel", "Cape Verde", "El Salvador"} <= sem


def test_as_decisoes_editoriais_estao_justificadas(table):
    """Nome que não é a tradução óbvia tem que dizer por quê — mesma regra do
    `team_colors.csv`: decisão editorial fica versionada com o motivo."""
    for team in ("Netherlands", "Republic of Ireland", "Czech Republic",
                 "Russia", "Serbia"):
        note = table.loc[table.team_name == team, "note"].iloc[0]
        assert note.strip(), f"{team} sem justificativa"


# --- a sigla do placar ----------------------------------------------------


def test_toda_sigla_tem_tres_maiusculas(table):
    """O placar reserva uma caixa de largura fixa para ela; quatro letras
    estouram a caixa e duas deixam o placar torto."""
    bad = table.team_name[~table.sigla.str.fullmatch(r"[A-Z]{3}")].tolist()
    assert bad == []


def test_nenhuma_sigla_se_repete(table):
    """Duas seleções com a mesma sigla seriam dois placares idênticos com
    resultados diferentes — e a sigla é curta demais para alguém estranhar."""
    repeated = table.sigla[table.sigla.duplicated()].tolist()
    assert repeated == []


def test_as_siglas_sao_as_da_fifa_e_nao_as_do_portugues(table):
    """A sigla é o trigrama FIFA, o que aparece no placar da transmissão.

    Derivar das três primeiras letras do nome em português daria "ALE", "HOL",
    "ING" e "SUI" — os três primeiros nunca apareceram numa tela de Copa, e o
    quarto colidiria com a Suíça. O padrão vale mais que a regra porque é ele
    que o torcedor reconhece.
    """
    expected = {"Germany": "GER", "Netherlands": "NED", "England": "ENG",
                "Switzerland": "SUI", "Sweden": "SWE", "South Korea": "KOR",
                "Saudi Arabia": "KSA", "South Africa": "RSA",
                "Ivory Coast": "CIV", "United States": "USA"}
    for team, sigla in expected.items():
        assert table.loc[table.team_name == team, "sigla"].iloc[0] == sigla


# --- o arquivo gerado -----------------------------------------------------


def test_o_json_cobre_o_modelo_inteiro(names, teams):
    assert sorted(names["teams"]) == sorted(teams)


def test_a_chave_continua_em_ingles(names):
    """A tradução é rótulo, não chave.

    A chave em inglês é a mesma do `team` do GeoJSON, dos índices do
    `timeline.json` e do `t=` da URL. Se ela virasse português, todo link já
    compartilhado deixaria de abrir na visão que descreve.
    """
    assert names["teams"]["Brazil"] == "Brasil"
    assert names["teams"]["Germany"] == "Alemanha"
    assert names["teams"]["Netherlands"] == "Holanda"
    assert "Brasil" not in names["teams"]


def test_so_quem_tem_artigo_entra_no_json(names):
    """Chave com string vazia seria peso morto num arquivo que o navegador baixa."""
    assert names["articles"]["Brazil"] == "o"
    assert names["articles"]["Germany"] == "a"
    assert names["articles"]["United States"] == "os"
    assert "Portugal" not in names["articles"]
    assert all(value in ARTICLES - {""} for value in names["articles"].values())


def test_o_json_traz_a_sigla_de_toda_selecao(names, teams):
    """Sem sigla o placar cai para o nome inteiro e a linha quebra em duas."""
    assert sorted(names["siglas"]) == sorted(teams)
    assert names["siglas"]["Brazil"] == "BRA"
    assert names["siglas"]["Germany"] == "GER"


def test_selecao_sem_nome_para_o_etl():
    """O ETL falha alto em vez de gravar um JSON com buraco.

    Um `names.json` incompleto não quebra a página — ela cai para o nome em
    inglês —, e é justamente por isso que o erro precisa aparecer aqui.
    """
    with pytest.raises(ValueError, match="Atlantis"):
        build_names(["Brazil", "Atlantis"])
