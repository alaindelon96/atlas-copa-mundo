"""Etapa 3 — geocodificação das sedes.

Transforma as 256 sedes distintas de `matches_clean.csv` em uma tabela com
coordenadas e país:

    data/interim/geocode_cache.json    respostas cruas do Nominatim (versionado)
    data/interim/venues_geocoded.csv   as sedes com coordenada e país

Três decisões estruturam este módulo:

1. **Cache primeiro, rede depois.** O Nominatim é um serviço público e gratuito
   que pede no máximo 1 requisição por segundo. Rodar isto do zero leva ~5
   minutos. O cache é gravado a cada resposta (não no fim), então uma execução
   interrompida no meio não joga fora o que já custou; e ele é **versionado no
   git**, para que reproduzir o pipeline não exija tocar na rede.

2. **A consulta desce em degraus.** Primeiro `estádio, cidade, país`; se não
   voltar nada, `cidade, país`; e, quando o país é desconhecido — que é
   exatamente o caso das 16 sedes de 2026 —, `estádio, cidade`. O degrau que
   respondeu fica registrado em `match_level`, para dar para auditar depois
   quais linhas vieram do palpite mais fraco.

3. **O geocodificador confirma, não decide.** Onde o Fjelstul já traz o país, o
   país devolvido pelo Nominatim é usado só como *conferência* — divergências
   são reportadas, não aplicadas. O valor do Nominatim é preencher o que está
   faltando (2026) e acrescentar o que ninguém tinha (latitude/longitude).

Uso:
    python -m etl.geocode              # usa o cache, busca só o que falta
    python -m etl.geocode --offline    # falha se algo não estiver em cache
    python -m etl.geocode --refresh    # ignora o cache e busca tudo de novo
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import pandas as pd
from geopy.exc import GeocoderServiceError
from geopy.geocoders import Nominatim

from etl.paths import GEOCODE_CACHE, INTERIM, PROCESSED, ROOT, ensure_dirs

# A política de uso do Nominatim exige um user-agent que identifique a
# aplicação e um contato: https://operations.osmfoundation.org/policies/nominatim/
USER_AGENT = "atlas-copa-mundo/0.1 (https://github.com/alaindelon96/atlas-copa-mundo)"

# 1 req/s é o teto da política; 1,1 s dá margem para variação de relógio.
DELAY_SECONDS = 1.1

# O Nominatim devolve o país no idioma pedido; fixamos inglês para casar com os
# nomes que já estão no dataset (`country_name` do Fjelstul é em inglês).
LANGUAGE = "en"


def cache_key(query: str) -> str:
    """Chave do cache: a consulta exata, normalizada."""
    return " ".join(query.split()).lower()


def load_cache() -> dict[str, dict | None]:
    if not GEOCODE_CACHE.exists():
        return {}
    with GEOCODE_CACHE.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_cache(cache: dict[str, dict | None]) -> None:
    """Grava ordenado por chave, para o diff no git ser legível."""
    GEOCODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with GEOCODE_CACHE.open("w", encoding="utf-8") as handle:
        json.dump(dict(sorted(cache.items())), handle, indent=1, ensure_ascii=False)
        handle.write("\n")


def venue_queries(stadium: str, city: str, country: str | None) -> list[tuple[str, str]]:
    """Os degraus de consulta, do mais específico para o mais genérico.

    Cada item é `(nível, consulta)`. O nível vai para a tabela final: uma sede
    resolvida por `city` tem a coordenada da cidade, não do estádio, e quem for
    desenhar um marcador precisa saber disso.
    """
    steps: list[tuple[str, str]] = []
    if country:
        steps.append(("stadium+country", f"{stadium}, {city}, {country}"))
        steps.append(("city+country", f"{city}, {country}"))
    else:
        # 2026: o país é justamente o que queremos descobrir. Os 16 estádios são
        # nomes globalmente únicos (MetLife Stadium, Estadio Azteca), então a
        # consulta sem país é segura aqui — e é conferida contra os 3 países-sede.
        steps.append(("stadium", f"{stadium}, {city}"))
        steps.append(("city", city))
    return steps


def lookup(
    geolocator: Nominatim | None,
    cache: dict[str, dict | None],
    query: str,
    *,
    offline: bool,
) -> dict | None:
    """Resolve uma consulta, preferindo o cache. `None` = não encontrado."""
    key = cache_key(query)
    if key in cache:
        return cache[key]

    if offline:
        raise LookupError(f"consulta ausente do cache em modo --offline: {query!r}")

    location = geolocator.geocode(query, addressdetails=True, language=LANGUAGE)
    time.sleep(DELAY_SECONDS)

    if location is None:
        cache[key] = None
    else:
        address = location.raw.get("address", {})
        cache[key] = {
            "lat": float(location.latitude),
            "lon": float(location.longitude),
            "display_name": location.address,
            "country": address.get("country"),
            "country_code": (address.get("country_code") or "").upper() or None,
            "osm_type": location.raw.get("osm_type"),
            "osm_id": location.raw.get("osm_id"),
        }
    save_cache(cache)
    return cache[key]


def distinct_venues(matches: pd.DataFrame) -> pd.DataFrame:
    """As sedes distintas, com a janela de anos em que cada uma foi usada."""
    grouped = matches.groupby(["stadium_name", "city_name"], dropna=False)
    venues = grouped.agg(
        country_name=("country_name", "first"),
        matches_hosted=("match_id", "size"),
        first_year=("year", "min"),
        last_year=("year", "max"),
    ).reset_index()
    return venues.sort_values(["country_name", "city_name", "stadium_name"],
                              na_position="last").reset_index(drop=True)


def geocode_venues(
    venues: pd.DataFrame,
    *,
    offline: bool,
    refresh: bool,
) -> pd.DataFrame:
    """Preenche latitude, longitude e país geocodificado de cada sede."""
    cache = {} if refresh else load_cache()
    geolocator = None if offline else Nominatim(user_agent=USER_AGENT, timeout=30)

    cached_before = len(cache)
    results = []
    for row in venues.itertuples(index=False):
        country = row.country_name if pd.notna(row.country_name) else None
        hit = None
        level = None
        for step, query in venue_queries(row.stadium_name, row.city_name, country):
            hit = lookup(geolocator, cache, query, offline=offline)
            if hit is not None:
                level = step
                break

        results.append({
            "latitude": round(hit["lat"], 6) if hit else None,
            "longitude": round(hit["lon"], 6) if hit else None,
            "geocoded_country": hit["country"] if hit else None,
            "country_code": hit["country_code"] if hit else None,
            "match_level": level,
        })

    fetched = len(cache) - cached_before
    print(f"  cache: {cached_before} consultas conhecidas, {fetched} novas")
    return pd.concat([venues, pd.DataFrame(results)], axis=1)


def reconcile(venues: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Fecha a coluna `country_name` e reporta divergências.

    Onde o Fjelstul já tem país, ele manda: o Nominatim entra como conferência.
    Onde não tem (2026), o país geocodificado preenche o buraco — que é o que
    destrava a métrica "partidas recebidas".
    """
    warnings: list[str] = []
    filled = venues.country_name.copy()

    missing = venues.country_name.isna()
    filled[missing] = venues.loc[missing, "geocoded_country"]

    known = venues.country_name.notna() & venues.geocoded_country.notna()
    diverge = venues[known & (venues.country_name != venues.geocoded_country)]
    for row in diverge.itertuples(index=False):
        warnings.append(
            f"{row.stadium_name} ({row.city_name}): dataset diz "
            f"{row.country_name!r}, Nominatim diz {row.geocoded_country!r}")

    venues = venues.copy()
    venues["country_name"] = filled
    return venues, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true",
                        help="não acessa a rede; falha se faltar algo no cache")
    parser.add_argument("--refresh", action="store_true",
                        help="ignora o cache e refaz todas as consultas")
    args = parser.parse_args()

    ensure_dirs()
    matches = pd.read_csv(PROCESSED / "matches_clean.csv")
    venues = distinct_venues(matches)
    print(f"{len(venues)} sedes distintas em {len(matches)} partidas")

    unknown_country = int(venues.country_name.isna().sum())
    print(f"  {unknown_country} sem país no dataset (2026)\n")

    try:
        venues = geocode_venues(venues, offline=args.offline, refresh=args.refresh)
    except (GeocoderServiceError, LookupError) as error:
        print(f"ERRO na geocodificação: {error}")
        return 1

    # Quem estava sem país antes da reconciliação — são as sedes de 2026 que o
    # scraping não trouxe, e é sobre elas que a conferência dos países-sede vale.
    was_missing = venues.country_name.isna().to_numpy()

    venues, warnings = reconcile(venues)

    # Saída intermediária: quem fecha a tabela de sedes (e lhe dá uma chave) é
    # `etl.model`. Aqui o trabalho é só resolver coordenada e país.
    destination = INTERIM / "venues_geocoded.csv"
    columns = ["stadium_name", "city_name", "country_name", "country_code",
               "latitude", "longitude", "matches_hosted", "first_year",
               "last_year", "match_level", "geocoded_country"]
    venues[columns].to_csv(destination, index=False, encoding="utf-8")
    print(f"\n{len(venues)} sedes -> {destination.relative_to(ROOT)}")

    print("\nPor degrau de consulta:")
    for level, count in venues.match_level.value_counts(dropna=False).items():
        print(f"  {str(level):<16} {count:>4}")

    failed = venues[venues.latitude.isna()]
    if len(failed):
        print(f"\n{len(failed)} sede(s) sem coordenada:")
        for row in failed.itertuples(index=False):
            print(f"  {row.stadium_name} — {row.city_name}")

    if warnings:
        print(f"\nDivergências de país ({len(warnings)}) — dataset prevalece:")
        for warning in warnings:
            print(f"  {warning}")

    # ---- conferências ----
    print("\nConferências:")
    checks: list[tuple[str, object, object]] = []
    checks.append(("sedes com coordenada", int(venues.latitude.notna().sum()), len(venues)))
    checks.append(("sedes com país", int(venues.country_name.notna().sum()), len(venues)))

    # As sedes de 2026 sem país têm que cair nos três países-sede, e só neles.
    hosts_2026 = set(venues.loc[was_missing, "country_name"].dropna())
    checks.append(("países-sede de 2026", sorted(hosts_2026),
                   ["Canada", "Mexico", "United States"]))

    # Coordenadas dentro do planeta — pega inversão lat/lon e resposta corrompida.
    in_range = ((venues.latitude.between(-90, 90)) &
                (venues.longitude.between(-180, 180))).sum()
    checks.append(("coordenadas no intervalo", int(in_range), len(venues)))

    failures = 0
    for label, got, expected in checks:
        ok = got == expected
        failures += not ok
        print(f"  {'OK ' if ok else 'ERRO'} {label:<26} {got}  esperado {expected}")

    if failures:
        print(f"\n{failures} conferência(s) falharam.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
