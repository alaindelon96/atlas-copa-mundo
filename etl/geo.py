"""Etapa 3 — a camada de polígonos do mapa coroplético.

O mapa pinta países, não marcadores. Isso troca o problema geográfico do
projeto: em vez de coordenadas de cidade, o que ele precisa é de uma resposta
para "qual pedaço do mapa-múndi é o Brasil?" — para as 83 seleções masculinas.

    data/raw/naturalearth/…    o GeoJSON original, imutável
    reference/team_country.csv o mapa curado seleção → unidade do mapa
    web/data/countries.geojson o que o Leaflet carrega

Por que **map units** e não países:

O Natural Earth publica duas divisões do mundo. `admin_0_countries` tem o Reino
Unido como uma peça só; `admin_0_map_units` o divide em Inglaterra, Escócia,
País de Gales e Irlanda do Norte — que é exatamente o recorte que o futebol usa
e que este projeto decidiu manter (somar as quatro criaria uma "seleção do Reino
Unido" que nunca existiu). Por isso a base é `map_units`.

O preço dessa escolha aparece na Bélgica: a mesma divisão que separa o Reino
Unido em quatro também separa a Bélgica em Flandres, Valônia e Bruxelas. Como o
mapa nunca dissolve polígonos, o `team_country.csv` é **um-para-muitos**: a
Bélgica ocupa três linhas, as três com `team_name = Belgium`. As três recebem a
mesma cor e o mapa não deixa ver a costura.

Uso:
    python -m etl.geo              # baixa se preciso, gera tudo
    python -m etl.geo --suggest    # só relata seleções sem polígono
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd
import requests

from etl.model import COMPETITION
from etl.paths import (PROCESSED, RAW_NATURALEARTH, REFERENCE, ROOT, WEB_DATA,
                       ensure_dirs)
from etl.provenance import load as load_provenance
from etl.provenance import record, save

NE_FILE = "ne_50m_admin_0_map_units.geojson"
NE_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
          f"master/geojson/{NE_FILE}")
NE_LICENSE = "Public domain (Natural Earth)"
NE_ATTRIBUTION = ("Made with Natural Earth. Free vector and raster map data @ "
                  "naturalearthdata.com")

USER_AGENT = "atlas-copa-mundo/0.1 (https://github.com/alaindelon96/atlas-copa-mundo)"

TEAM_COUNTRY_CSV = REFERENCE / "team_country.csv"

# As quatro seleções britânicas dividem o mesmo ISO ("GB") — o mesmo motivo pelo
# qual este projeto usa `map_units` e não `countries`. Cada uma recebe o código
# de subdivisão, que é como o conjunto de bandeiras vendorizado as identifica.
#
# Vale registrar o caminho até aqui: a primeira tentativa foi emoji, e o Unicode
# só tem bandeira para três das quatro — `GB-NIR` não existe como emoji em versão
# nenhuma. Foi um dos motivos de trocar emoji por SVG: em SVG as quatro existem.
ISO_OVERRIDES = {
    "England": "GB-ENG",
    "Scotland": "GB-SCT",
    "Wales": "GB-WLS",
    "Northern Ireland": "GB-NIR",
}

# Escala 1:50m em vez de 1:110m porque a 110m simplesmente não tem os países
# pequenos — e vários deles jogaram Copa (Curaçao, Trinidad e Tobago, Cabo
# Verde). Um país ausente do GeoJSON some do mapa sem gerar erro nenhum.
COORDINATE_PRECISION = 3  # ~110 m no equador; num mapa-múndi ninguém vê a diferença

# Os nomes que o dataset de futebol usa e o Natural Earth não. Cada um é uma
# decisão, não um erro de digitação — por isso estão aqui, à vista, e não
# escondidos atrás de um fuzzy match.
ALIASES: dict[str, list[str]] = {
    # Nome oficial do país vs. nome curto usado no futebol.
    "United States": ["United States of America"],
    "Czech Republic": ["Czechia"],
    "Cape Verde": ["Cabo Verde"],
    "DR Congo": ["Democratic Republic of the Congo"],
    # A Irlanda joga como "Republic of Ireland" porque existe uma seleção da
    # Irlanda do Norte; o mapa chama o mesmo território de "Ireland".
    "Republic of Ireland": ["Ireland"],
    # "Chinese Taipei" é o nome sob o qual Taiwan compete na FIFA.
    "Chinese Taipei": ["Taiwan"],
    # O único um-para-muitos: ver a nota no topo do módulo.
    "Belgium": ["Flemish Region", "Walloon Region", "Brussels Capital Region"],
}


def download(force: bool = False) -> None:
    """Baixa o GeoJSON do Natural Earth, com escrita atômica e proveniência."""
    destination = RAW_NATURALEARTH / NE_FILE
    if destination.exists() and not force:
        print(f"  {NE_FILE} já em disco ({destination.stat().st_size:,} bytes)")
        return

    print(f"  baixando {NE_FILE} …")
    response = requests.get(NE_URL, headers={"User-Agent": USER_AGENT}, timeout=180)
    response.raise_for_status()

    # Mesmo padrão do extract.py: grava `.part` e renomeia, para nunca deixar
    # um GeoJSON truncado em disco parecendo válido.
    partial = destination.with_suffix(destination.suffix + ".part")
    partial.write_bytes(response.content)
    partial.replace(destination)

    registry = load_provenance()
    record(registry, destination, source="Natural Earth (nvkelso/natural-earth-vector)",
           url=NE_URL, license_=NE_LICENSE, attribution=NE_ATTRIBUTION,
           extra={"scale": "1:50m", "division": "admin_0_map_units"})
    save(registry)
    print(f"  {len(response.content):,} bytes")


def load_map_units() -> list[dict]:
    """As unidades do mapa, como o Natural Earth as publica."""
    path = RAW_NATURALEARTH / NE_FILE
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)["features"]


def teams_in_data() -> list[str]:
    """As seleções que o modelo abrange.

    Mesmo recorte de `etl.model` (`COMPETITION`), e pelo mesmo motivo: um
    polígono para uma seleção que o mapa não mostra é peso morto no GeoJSON que
    o navegador baixa.
    """
    matches = pd.read_csv(PROCESSED / "matches_clean.csv")
    matches = matches[matches.competition == COMPETITION]
    return sorted(set(matches.home_team) | set(matches.away_team))


def match_teams(teams: list[str], features: list[dict]) -> tuple[pd.DataFrame, list[str]]:
    """Casa cada seleção com uma ou mais unidades do mapa.

    A regra é exata em duas etapas: nome idêntico ao `GEOUNIT`, ou um apelido
    declarado em `ALIASES`. Não há fuzzy matching aqui de propósito — um
    polígono errado pinta o país errado no mapa e ninguém percebe, ao contrário
    de um nome ausente, que este relatório mostra.
    """
    by_geounit = {f["properties"]["GEOUNIT"]: f["properties"] for f in features}

    rows: list[dict] = []
    unmatched: list[str] = []
    for team in teams:
        names = ALIASES.get(team, [team])
        found = [by_geounit[name] for name in names if name in by_geounit]
        if len(found) != len(names):
            unmatched.append(team)
            continue
        for properties in found:
            rows.append({
                "team_name": team,
                "gu_a3": properties["GU_A3"],
                "geounit_name": properties["GEOUNIT"],
                "sovereign": properties["SOVEREIGNT"],
                # `ISO_A2_EH` e não `ISO_A2`: o campo sem sufixo grava -99 para
                # dezenas de unidades (inclusive Noruega e Portugal), enquanto o
                # `_EH` resolve o código de fato. É daqui que sai a bandeira da
                # seleção — o emoji é o código de duas letras em indicadores
                # regionais, então a bandeira vem da mesma fonte que o polígono
                # em vez de virar uma terceira tabela curada à mão.
                "iso_a2": ISO_OVERRIDES.get(team, properties["ISO_A2_EH"]),
            })

    mapping = pd.DataFrame(rows).sort_values(["team_name", "gu_a3"])
    return mapping.reset_index(drop=True), unmatched


def round_coordinates(node, precision: int = COORDINATE_PRECISION):
    """Arredonda coordenadas recursivamente, sem saber a profundidade.

    Um Polygon aninha listas em 3 níveis e um MultiPolygon em 4; percorrer a
    árvore evita escrever um caso para cada tipo de geometria.
    """
    if isinstance(node, list):
        return [round_coordinates(item, precision) for item in node]
    if isinstance(node, float):
        return round(node, precision)
    return node


def build_geojson(features: list[dict], mapping: pd.DataFrame) -> dict:
    """O GeoJSON enxuto que o Leaflet carrega.

    O original tem ~170 propriedades por feature e 3,1 MB. O mapa usa cinco
    delas. Cortar o resto e arredondar as coordenadas é o que separa um download
    aceitável de um mapa que demora a abrir no celular.
    """
    team_of = dict(zip(mapping.gu_a3, mapping.team_name))

    slim = []
    for feature in features:
        properties = feature["properties"]
        gu_a3 = properties["GU_A3"]
        slim.append({
            "type": "Feature",
            "properties": {
                "gu_a3": gu_a3,
                "name": properties["GEOUNIT"],
                # O Natural Earth traz nome em português; a interface é em
                # português, então é de graça não traduzir 265 nomes à mão.
                "name_pt": properties.get("NAME_PT") or properties["GEOUNIT"],
                # `null` aqui significa "país que nunca disputou uma Copa": o
                # mapa desenha o contorno em cinza, sem valor de métrica.
                "team": team_of.get(gu_a3),
            },
            "geometry": {
                "type": feature["geometry"]["type"],
                "coordinates": round_coordinates(feature["geometry"]["coordinates"]),
            },
        })

    return {"type": "FeatureCollection",
            "attribution": NE_ATTRIBUTION,
            "features": slim}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suggest", action="store_true",
                        help="apenas relata seleções sem polígono; não grava nada")
    parser.add_argument("--force-download", action="store_true",
                        help="rebaixa o GeoJSON mesmo se já estiver em disco")
    args = parser.parse_args()

    ensure_dirs()
    download(force=args.force_download)

    features = load_map_units()
    print(f"  {len(features)} unidades de mapa\n")

    teams = teams_in_data()
    mapping, unmatched = match_teams(teams, features)
    print(f"{len(teams)} seleções -> {len(mapping)} polígonos "
          f"({len(unmatched)} sem correspondência)")

    if unmatched:
        print("\nSem polígono — acrescente um apelido em ALIASES:")
        for team in unmatched:
            print(f"  {team}")
        return 1

    multi = mapping.team_name.value_counts()
    multi = multi[multi > 1]
    if len(multi):
        print("\nSeleções em mais de uma unidade de mapa:")
        for team, count in multi.items():
            units = mapping.loc[mapping.team_name == team, "geounit_name"].tolist()
            print(f"  {team:<12} {count}  {', '.join(units)}")

    if args.suggest:
        print("\n--suggest: nada foi gravado.")
        return 0

    mapping.to_csv(TEAM_COUNTRY_CSV, index=False, encoding="utf-8")
    print(f"\n{len(mapping)} linhas -> {TEAM_COUNTRY_CSV.relative_to(ROOT)}")

    geojson = build_geojson(features, mapping)
    destination = WEB_DATA / "countries.geojson"
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(geojson, handle, ensure_ascii=False, separators=(",", ":"))

    original = (RAW_NATURALEARTH / NE_FILE).stat().st_size
    final = destination.stat().st_size
    print(f"{final:,} bytes -> {destination.relative_to(ROOT)} "
          f"({100 * final / original:.0f}% do original de {original:,})")

    # ---- conferências ----
    print("\nConferências:")
    painted = sum(1 for f in geojson["features"] if f["properties"]["team"])
    checks: list[tuple[str, object, object]] = [
        ("polígonos com seleção", painted, len(mapping)),
        ("features preservadas", len(geojson["features"]), len(features)),
        ("seleções mapeadas", mapping.team_name.nunique(), len(teams)),
        # Uma unidade de mapa não pode pertencer a duas seleções: seria o mesmo
        # pedaço do mapa com duas cores.
        ("unidades sem duplicata", mapping.gu_a3.nunique(), len(mapping)),
    ]

    # As quatro seleções britânicas precisam continuar sendo quatro polígonos.
    british = {"England", "Scotland", "Wales", "Northern Ireland"}
    found = sorted(british & set(mapping.team_name))
    checks.append(("seleções britânicas", found, sorted(british)))

    failures = 0
    for label, got, expected in checks:
        ok = got == expected
        failures += not ok
        print(f"  {'OK ' if ok else 'ERRO'} {label:<24} {got}  esperado {expected}")

    if failures:
        print(f"\n{failures} conferência(s) falharam.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
