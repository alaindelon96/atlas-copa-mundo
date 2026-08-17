"""Etapa 3 — modelagem.

Transforma a tabela única de partidas em um esquema relacional explícito, com
chaves, em `data/processed/`:

    tournaments.csv       uma linha por edição
    tournament_hosts.csv  uma linha por (edição, país-sede)
    teams.csv             uma linha por seleção, com o polígono do mapa
    venues.csv            uma linha por sede, com coordenada e chave
    matches.csv           o fato: uma linha por partida
    team_matches.csv      a tabela longa: uma linha por (partida, seleção)

O diagrama do esquema está em `docs/schema.md`.

**Escopo: Copa masculina.** É aqui, e só aqui, que a decisão é tomada — a
constante `COMPETITION` filtra a entrada e todo o resto do modelo herda o
recorte. A Copa feminina **continua no dado**: `data/raw/` e
`data/processed/matches_clean.csv` seguem com as 284 partidas de 1991–2019 e
com a coluna `competition` que as identifica. O que foi retirado é o produto,
não a fonte. Reincluir o feminino é mexer nesta linha e devolver a coluna
`competition` às tabelas — de propósito, um diff pequeno.

Por isso as tabelas do modelo **não** têm coluna `competition`: ela teria um
único valor em 1.352 linhas, e uma coluna constante não informa nada — só
sugere uma variação que não existe mais.

Três coisas que o dado obrigou a modelar assim:

1. **Sede não é um campo, é uma tabela.** O Fjelstul guarda o país-sede em uma
   coluna só, e quando a edição teve mais de um país ele improvisa: 2002 vira a
   string `"Korea, Japan"` (com "Korea" — nome que não aparece em nenhum outro
   lugar do dataset) e 2026, no scraping, vira `"Canada Mexico United States"`,
   sem separador. Duas codificações ad hoc do mesmo um-para-muitos. Aqui os
   países-sede são **derivados das sedes onde as partidas de fato ocorreram** —
   nenhuma string é interpretada — e o valor declarado vira conferência.

2. **O fato vive no nível da partida.** É a única granularidade que as duas
   fontes têm completa: 2026 não tem escalação, nem gol com autor, nem
   confederação por edição. Modelar mais fino criaria um buraco em 104 partidas.

3. **A tabela longa é derivada, não digitada.** `team_matches` empilha mandante
   e visitante. Ela é redundante em relação a `matches` por construção — e é
   exatamente por isso que existe: quase toda métrica quer uma linha por
   seleção, e refazer essa dobra em cada agregação é como se conta só os
   mandantes sem perceber.

Uso:
    python -m etl.model
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata

import pandas as pd

from etl.paths import (INTERIM, PROCESSED, RAW_FJELSTUL, REFERENCE, ROOT,
                       ensure_dirs)

# O escopo do projeto. Ver a nota no topo do módulo: mudar esta constante (ou
# removê-la) é o que reincluiria a Copa feminina, que segue intacta no dado.
COMPETITION = "mens"

# As quatro estreantes de 2026 não existem no `teams.csv` do Fjelstul, que
# termina em 2022 — logo, não têm confederação lá. São quatro valores públicos e
# estáveis; digitá-los aqui é mais honesto do que deixar a coluna nula e
# descobrir depois que o filtro por confederação perde quatro seleções.
DEBUTANT_CONFEDERATIONS = {
    "Cape Verde": "CAF",
    "Curaçao": "CONCACAF",
    "Jordan": "AFC",
    "Uzbekistan": "AFC",
}


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """As três entradas da modelagem, cada uma produto de uma etapa anterior."""
    matches = pd.read_csv(PROCESSED / "matches_clean.csv")

    # O único ponto de recorte do escopo. A tabela limpa continua com as duas
    # competições; o modelo leva só uma.
    matches = matches[matches.competition == COMPETITION].reset_index(drop=True)

    geocoded = INTERIM / "venues_geocoded.csv"
    if not geocoded.exists():
        raise FileNotFoundError(
            f"{geocoded.name} não encontrado — rode `python -m etl.geocode` antes.")
    venues = pd.read_csv(geocoded)

    team_country = REFERENCE / "team_country.csv"
    if not team_country.exists():
        raise FileNotFoundError(
            f"{team_country.name} não encontrado — rode `python -m etl.geo` antes.")
    return matches, venues, pd.read_csv(team_country)


def build_venues(venues: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Dá chave à tabela de sedes, no recorte do modelo.

    A chave é `(estádio, cidade)`, e não o nome do estádio sozinho, por um
    motivo prático: nomes de estádio se repetem entre países (há mais de um
    "Estadio Nacional"). A cidade desempata.

    A geocodificação resolve **todas** as sedes do dado, inclusive as que só
    receberam Copa feminina — coordenada é cara de obter e barata de guardar, e
    o cache fica pronto se o feminino voltar. Já a tabela do modelo carrega só
    as sedes que o escopo usa, e os agregados (`matches_hosted`, `first_year`,
    `last_year`) são recontados aqui. Herdá-los da geocodificação faria uma sede
    dizer que recebeu partidas que este modelo não contém.
    """
    used = matches.groupby(["stadium_name", "city_name"]).agg(
        matches_hosted=("match_id", "size"),
        first_year=("year", "min"),
        last_year=("year", "max"),
    ).reset_index()

    venues = venues.drop(columns=["matches_hosted", "first_year", "last_year"])
    venues = used.merge(venues, on=["stadium_name", "city_name"], how="left",
                        validate="one_to_one")

    if venues.latitude.isna().any():
        orphans = venues.loc[venues.latitude.isna(), "stadium_name"].tolist()
        raise ValueError(f"sedes sem geocodificação: {orphans}")

    venues = venues.sort_values(["country_name", "city_name", "stadium_name"])
    venues = venues.reset_index(drop=True)
    venues.insert(0, "venue_id", [f"V-{i:03d}" for i in range(1, len(venues) + 1)])
    return venues[["venue_id", "stadium_name", "city_name", "country_name",
                   "country_code", "latitude", "longitude", "matches_hosted",
                   "first_year", "last_year", "match_level"]]


def build_matches(matches: pd.DataFrame, venues: pd.DataFrame) -> pd.DataFrame:
    """O fato, com a sede resolvida em chave e o país-sede finalmente completo.

    Aqui é onde as 104 partidas de 2026 deixam de ter `country_name` nulo: o
    país vem da sede geocodificada, o que destrava a métrica "partidas
    recebidas". Ela estava incompleta desde a Etapa 2.
    """
    keys = venues[["venue_id", "stadium_name", "city_name", "country_name"]]
    merged = matches.drop(columns=["country_name"]).merge(
        keys, on=["stadium_name", "city_name"], how="left", validate="many_to_one")

    if merged.venue_id.isna().any():
        orphans = merged.loc[merged.venue_id.isna(), "stadium_name"].unique()
        raise ValueError(f"partidas sem sede correspondente: {list(orphans)}")

    # As duas fontes discordam sobre como dizer "não houve disputa de pênaltis":
    # o Fjelstul grava 0–0 e a Wikipédia deixa em branco. Um 0 é um placar
    # válido, então "Brasil 0 × 0 Itália nos pênaltis" em 1.205 partidas passa
    # por qualquer soma sem levantar suspeita. Ausência vira ausência aqui.
    no_shootout = merged.penalty_shootout != 1
    for column in ("home_team_score_penalties", "away_team_score_penalties"):
        merged.loc[no_shootout, column] = pd.NA

    # Mesmo problema, outra coluna: partida de mata-mata não tem grupo, e as duas
    # fontes dizem isso de jeitos diferentes — o Fjelstul escreve a string
    # `"not applicable"` (332 partidas), a Wikipédia deixa em branco (32). Um
    # `groupby("group_name")` devolveria um "grupo" chamado "not applicable" com
    # 332 partidas de mata-mata dentro, e o gráfico sairia sem erro nenhum.
    merged["group_name"] = merged.group_name.replace("not applicable", pd.NA)

    columns = ["match_id", "tournament_id", "year", "stage",
               "group_name", "match_date", "venue_id", "country_name",
               "home_team", "away_team", "home_team_score", "away_team_score",
               "extra_time", "penalty_shootout", "home_team_score_penalties",
               "away_team_score_penalties", "attendance",
               "home_team_raw", "away_team_raw", "source"]
    return merged[columns].sort_values(["match_date", "match_id"]).reset_index(drop=True)


def build_team_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (partida, seleção), com o resultado já resolvido.

    O resultado não sai do placar sozinho: no mata-mata um 1–1 não é empate,
    alguém avançou nos pênaltis. Tratar o tempo normal como final criaria
    empates que não existiram e tiraria vitórias de quem passou.
    """
    shared = ["match_id", "tournament_id", "year", "stage",
              "match_date", "venue_id", "country_name", "penalty_shootout"]
    renames = [
        {"home_team": "team", "away_team": "opponent",
         "home_team_score": "goals_for", "away_team_score": "goals_against",
         "home_team_score_penalties": "pens_for",
         "away_team_score_penalties": "pens_against"},
        {"away_team": "team", "home_team": "opponent",
         "away_team_score": "goals_for", "home_team_score": "goals_against",
         "away_team_score_penalties": "pens_for",
         "home_team_score_penalties": "pens_against"},
    ]
    columns = shared + ["team", "opponent", "goals_for", "goals_against",
                        "pens_for", "pens_against", "home_away"]

    sides = []
    for rename, side in zip(renames, ["home", "away"]):
        frame = matches.rename(columns=rename)
        frame["home_away"] = side
        sides.append(frame[columns])

    long = pd.concat(sides, ignore_index=True)

    won = long.goals_for > long.goals_against
    lost = long.goals_for < long.goals_against
    shootout_won = (long.penalty_shootout == 1) & (long.pens_for > long.pens_against)
    long["result"] = "D"
    long.loc[lost | ((long.penalty_shootout == 1) & ~won & ~lost), "result"] = "L"
    long.loc[won | shootout_won, "result"] = "W"

    return long.sort_values(["match_date", "match_id", "home_away"]).reset_index(drop=True)


# "Luis Díaz (footballer, born 1997)" -> o parêntese final que a Wikipédia usa
# para separar homônimos. Sai do rótulo, mas **não** sai da identidade.
RE_DISAMBIGUATION = re.compile(r"\s*\([^)]*\)$")


def display_name(page: str, shown: str) -> str:
    """O rótulo de um artilheiro de 2026: o nome do artigo, sem o desambiguador.

    A caixa de partida da Wikipédia abrevia — "Mbappé", "Quiñones", "I. Sarr" —
    e era esse nome curto que a página exibia, ao lado dos nomes inteiros que o
    Fjelstul traz para 1930–2022. O artigo apontado pelo link tem o nome
    completo, e é dele que o rótulo passa a sair.

    O que se tira é só o desambiguador: "Luis Díaz (footballer, born 1997)" é
    rotulado "Luis Díaz". Ele é ruído na tela — mas é sinal na identidade, e por
    isso quem decide a ponte é `bridge_player_ids`, olhando o título inteiro.
    """
    if not page:
        return shown
    return RE_DISAMBIGUATION.sub("", page).strip() or shown


def fold_name(name: str) -> str:
    """Nome sem acento e sem caixa, só para comparar as duas fontes.

    As duas grafam o mesmo jogador com diacríticos diferentes: a Wikipédia
    titula o artigo do argentino como "Julián Alvarez" e o Fjelstul o grava
    "Julián Álvarez". São a mesma pessoa e os mesmos 5 gols (4 em 2022, 1 em
    2026), que a comparação literal separava em dois artilheiros de 4 e de 1.

    Isto normaliza a **comparação**, nunca o que é exibido: o rótulo continua
    saindo da fonte, com acento e tudo.
    """
    decomposed = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def bridge_player_ids(historic: pd.DataFrame, modern: pd.DataFrame) -> pd.Series:
    """O id de jogador de 2026: emprestado do Fjelstul quando dá, novo quando não.

    **Sem isto, "artilheiro de todos os tempos" é uma conta falsa** — e ela erra
    para os dois lados. O Fjelstul tem `player_id` e a Wikipédia não, então unir
    as fontes é decidir, jogador a jogador, quem de 2026 já jogou antes:

    - **Somar demais.** Com o nome como chave, o Ronaldo brasileiro (15 gols,
      1998–2006) somava com um Ronaldo português de 2026 e virava um artilheiro
      de 18 que nunca existiu, à frente do Klose, que tem o recorde de verdade
      com 16.
    - **Somar de menos.** Enquanto o nome de 2026 era o nome curto da caixa de
      partida, "Mbappé" não casava com "Kylian Mbappé" e a mesma pessoa aparecia
      duas vezes na lista — 12 gols numa linha, 10 na outra, e o recorde de 22
      não aparecia em lugar nenhum.

    **Quem casa os dois lados é o artigo, não o nome.** O link da caixa de
    partida (ver `etl.parse_2026.player_pages`) é a identidade que a própria
    fonte declara, e é sobre ela que a ponte decide, com três regras:

    1. **Mesmo nome de artigo E mesma seleção** une. São 27 casos — Mbappé,
       Messi, Cristiano Ronaldo, Kane, Neymar, Casemiro, Vinícius Júnior — e a
       comparação ignora acento (ver `fold_name`), que é o que salva o Julián
       Álvarez. A seleção continua na chave: ela é o que mantém o Ronaldo
       brasileiro separado do português.
    2. **Título desambiguado não faz ponte.** Quando a Wikipédia precisa escrever
       "Teboho Mokoena (soccer, born 1997)", ela está dizendo que o nome sozinho
       pertence a mais de uma pessoa — e o outro Teboho Mokoena, o que fez o gol
       da África do Sul em 2002, é justamente quem está no Fjelstul. O
       desambiguador é a fonte avisando que a ponte seria falsa; 15 artilheiros
       de 2026 têm título assim, e este é o único que encostaria no histórico.
    3. **Homônimo dentro do próprio Fjelstul é abstenção.** Cinco nomes de lá têm
       dois `player_id` cada (Oscar e Júnior no Brasil, Juanito e Andoni
       Goikoetxea na Espanha, József Tóth na Hungria) — jogadores diferentes,
       décadas diferentes, mesmo nome e mesma seleção. Se um nome de 2026 casar
       com um desses, não há como saber com qual, e a função **recusa a ponte**
       em vez de escolher: um id novo separa um jogador que talvez fosse o mesmo,
       o que subestima um total; um id errado credita gols a quem não os fez.

    Quem não casa ganha um id sintético `W-000`, um por artigo — que é o caso dos
    163 estreantes de 2026.
    """
    seen: dict[tuple[str, str], set[str]] = {}
    for player, team, player_id in zip(
            historic.player, historic.player_team, historic.player_id):
        seen.setdefault((fold_name(player), team), set()).add(player_id)
    known = {key: next(iter(ids)) for key, ids in seen.items() if len(ids) == 1}

    minted: dict[tuple[str, str], str] = {}

    def identify(row: pd.Series) -> str:
        page = str(row.player_page or "")
        # Regra 2: o desambiguador é a fonte dizendo que o nome é de mais de um.
        # Sem ele, o título já é o nome inteiro e vai direto para a comparação.
        if page and not RE_DISAMBIGUATION.search(page):
            match = known.get((fold_name(page), row.player_team))
            if match is not None:
                return match
        key = (page or row.player, row.player_team)
        if key not in minted:
            minted[key] = f"W-{len(minted):03d}"
        return minted[key]

    return modern.apply(identify, axis=1)


def build_goals(matches: pd.DataFrame) -> pd.DataFrame:
    """Os 3.028 gols, com autor e minuto — duas fontes num formato só.

    **Esta tabela desmente uma decisão de escopo do projeto.** A Etapa 3 concluiu
    que dado de jogador teria buraco em 2026 e cortou as features para "só
    estatística de jogo". A conclusão estava certa sobre o Fjelstul, que termina
    em 2022, e errada sobre o que já havia no disco: as páginas raspadas da
    Wikipédia trazem os 308 artilheiros de 2026 com minuto. O buraco não existia
    — faltava um parser (ver `etl.parse_2026.parse_goals`).

    Somando as duas fontes: 2.720 gols masculinos de 1930 a 2022 e 308 de 2026.
    O total, 3.028, é exatamente o que os placares do modelo já diziam — o que
    torna esta tabela conferível linha a linha contra `matches.csv` em vez de
    apenas plausível.

    Duas ressalvas que o dado impõe:

    - **Gol contra é creditado a quem ganhou o gol.** As duas fontes concordam
      nisso, e é o que faz a soma bater com o placar; `player_team` guarda o time
      de quem de fato chutou, que nos gols contra é o adversário.
    - **Nome de jogador não é comparável entre as fontes.** O Fjelstul separa
      `given_name` e `family_name` e grava a string `"not applicable"` para quem
      só tem um nome — o Ronaldo brasileiro entre eles. A Wikipédia exibe na
      caixa de partida o nome curto ("Mbappé"), e o nome inteiro fica no artigo
      para onde o link aponta ("Kylian Mbappé"). O rótulo sai desses dois lados
      num campo só, `player` — para 2026, via `display_name` —, e continua não
      sendo identidade.

      **Quem identifica é `player_id`**, e é por isso que ele existe: o Fjelstul
      tem o dele, a Wikipédia não tem nenhum, e `bridge_player_ids` decide caso a
      caso qual jogador de 2026 é alguém que já jogou. As duas contas erradas que
      ele evita estão documentadas lá: o Ronaldo brasileiro somando com um
      Ronaldo português (um recorde de 18 que nunca existiu) e o Mbappé partido
      em dois (12 gols numa linha, 10 na outra, e o recorde de 22 em nenhuma).
      Somar carreira entre fontes agora é seguro; o que continua não sendo é
      somar por nome.
    """
    succession = pd.read_csv(REFERENCE / "team_succession.csv")
    labels = dict(zip(succession.historic_name, succession.display_name))

    historic = pd.read_csv(RAW_FJELSTUL / "goals.csv")
    historic = historic[historic.match_id.isin(set(matches.match_id))].copy()

    def full_name(row: pd.Series) -> str:
        given = "" if str(row.given_name) == "not applicable" else str(row.given_name)
        return f"{given} {row.family_name}".strip()

    historic["player"] = historic.apply(full_name, axis=1)
    historic["team"] = historic.team_name.map(lambda name: labels.get(name, name))
    historic["player_team"] = historic.player_team_name.map(lambda name: labels.get(name, name))
    historic["player_id"] = historic.player_id
    historic["source"] = "fjelstul"

    modern = pd.read_csv(INTERIM / "goals_2026.csv")
    modern = modern[modern.match_id.isin(set(matches.match_id))].copy()
    modern["player_page"] = modern.player_page.fillna("")
    modern["player"] = modern.apply(
        lambda row: display_name(row.player_page, row.player_name), axis=1)
    modern["team"] = modern.team_name.map(lambda name: labels.get(name, name))
    # Num gol contra, quem chutou é do outro time — a fonte de 2026 não diz o
    # time do jogador, mas a partida diz quem é o adversário.
    modern["player_team"] = modern.apply(
        lambda row: row.opponent_name if row.own_goal else row.team_name, axis=1)
    modern["player_team"] = modern.player_team.map(lambda name: labels.get(name, name))
    modern["source"] = "wikipedia"
    modern["player_id"] = bridge_player_ids(historic, modern)

    # **Uma identidade, um rótulo.** Onde a ponte reconheceu alguém que já jogou,
    # o nome que fica é o que ele já tinha — as duas fontes discordam da grafia
    # em um caso, "Julián Álvarez" no Fjelstul e "Julián Alvarez" no título do
    # artigo, e sem isto a mesma pessoa entraria na lista com dois nomes. Não é
    # cosmético: `etl.metrics.build_goal_layer` recusa um `player_id` com mais de
    # um rótulo, porque é assim que ele detecta uma identidade mal resolvida.
    historic_labels = dict(zip(historic.player_id, historic.player))
    modern["player"] = modern.player_id.map(historic_labels).fillna(modern.player)

    columns = ["match_id", "team", "player_team", "player", "player_id",
               "minute_regulation", "minute_stoppage", "penalty", "own_goal", "source"]
    goals = pd.concat([historic[columns], modern[columns]], ignore_index=True)

    context = matches[["match_id", "tournament_id", "year", "stage", "match_date"]]
    goals = goals.merge(context, on="match_id", how="left")

    goals["minute_stoppage"] = goals.minute_stoppage.astype("Int64")
    goals["minute"] = goals.minute_regulation + goals.minute_stoppage.fillna(0).astype(int)

    ordered = ["match_id", "tournament_id", "year", "stage", "match_date",
               "team", "player_team", "player", "player_id",
               "minute", "minute_regulation", "minute_stoppage",
               "penalty", "own_goal", "source"]
    return goals[ordered].sort_values(["match_date", "match_id", "minute"]).reset_index(drop=True)


def build_tournaments(matches: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por edição, com campeão e vice.

    O campeão vem de `tournament_standings.csv`, **não** das finais: a Copa de
    1950 não teve final — foi decidida por um quadrangular. Derivar campeão de
    `stage == "final"` devolveria 22 títulos para 23 edições, e em silêncio.
    """
    standings = pd.read_csv(RAW_FJELSTUL / "tournament_standings.csv")
    podium = standings[standings.position.isin([1, 2])].pivot(
        index="tournament_id", columns="position", values="team_name")
    podium.columns = ["champion", "runner_up"]

    modern = pd.read_csv(INTERIM / "tournament_2026.csv").set_index("tournament_id")
    podium = pd.concat([podium, modern[["winner", "runner_up"]].rename(
        columns={"winner": "champion"})])

    sizes = pd.read_csv(RAW_FJELSTUL / "tournaments.csv").set_index("tournament_id")
    counts = pd.concat([sizes.count_teams, modern.count_teams])

    scored = matches.assign(goals=matches.home_team_score + matches.away_team_score)
    editions = scored.groupby(["tournament_id", "year"]).agg(
        matches=("match_id", "size"),
        goals=("goals", "sum"),
        venues=("venue_id", "nunique"),
        start_date=("match_date", "min"),
        end_date=("match_date", "max"),
    ).reset_index()

    editions["count_teams"] = editions.tournament_id.map(counts)
    editions["champion"] = editions.tournament_id.map(podium.champion)
    editions["runner_up"] = editions.tournament_id.map(podium.runner_up)
    return editions.sort_values("year").reset_index(drop=True)


def build_hosts(matches: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por (edição, país-sede) — derivada, não interpretada.

    Ver a nota 1 no topo do módulo: as duas fontes codificam vários países-sede
    de formas diferentes e ambíguas. Onde as partidas foram jogadas é um fato
    do dado; a string declarada não é confiável o bastante para virar chave.
    """
    hosts = (matches[["tournament_id", "country_name"]].drop_duplicates()
             .sort_values(["tournament_id", "country_name"]).reset_index(drop=True))
    return hosts.rename(columns={"country_name": "host_country"})


def build_teams(long: pd.DataFrame, team_country: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por seleção: identidade, polígono e janela histórica.

    `gu_a3` é a ponte para o mapa. A Bélgica ocupa três unidades de mapa (ver
    `etl.geo`), então aqui ela guarda a primeira e o GeoJSON é quem resolve as
    outras duas — a tabela de seleções é uma linha por seleção, e não por
    pedaço de polígono.
    """
    fjelstul = pd.read_csv(RAW_FJELSTUL / "teams.csv")
    succession = pd.read_csv(REFERENCE / "team_succession.csv")
    labels = dict(zip(succession.historic_name, succession.display_name))
    fjelstul["team"] = fjelstul.team_name.map(lambda name: labels.get(name, name))

    # Nomes históricos e modernos colapsam na mesma seleção (Alemanha Ocidental
    # e Alemanha, por exemplo). Todos concordam na confederação, então a
    # primeira ocorrência serve.
    confederation = fjelstul.drop_duplicates("team").set_index("team")

    units = team_country.groupby("team_name").agg(
        gu_a3=("gu_a3", "first"),
        geounit_name=("geounit_name", "first"),
        map_units=("gu_a3", "size"))

    teams = long.groupby("team").agg(
        first_year=("year", "min"),
        last_year=("year", "max"),
        participations=("year", "nunique"),
        matches_played=("match_id", "size"),
    ).reset_index().rename(columns={"team": "team_name"})

    teams["confederation"] = teams.team_name.map(confederation.confederation_code)
    teams["confederation"] = teams.confederation.fillna(
        teams.team_name.map(DEBUTANT_CONFEDERATIONS))
    teams["gu_a3"] = teams.team_name.map(units.gu_a3)
    teams["geounit_name"] = teams.team_name.map(units.geounit_name)
    teams["map_units"] = teams.team_name.map(units.map_units)

    columns = ["team_name", "gu_a3", "geounit_name", "map_units", "confederation",
               "first_year", "last_year", "participations", "matches_played"]
    return teams[columns].sort_values("team_name").reset_index(drop=True)


def declared_hosts() -> dict[str, str]:
    """A string de país-sede como cada fonte a declara — só para conferência."""
    fjelstul = pd.read_csv(RAW_FJELSTUL / "tournaments.csv")
    modern = pd.read_csv(INTERIM / "tournament_2026.csv")
    declared = dict(zip(fjelstul.tournament_id, fjelstul.host_country))
    declared.update(dict(zip(modern.tournament_id, modern.host_countries)))
    return declared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    ensure_dirs()
    try:
        raw_matches, raw_venues, team_country = load_inputs()
    except FileNotFoundError as error:
        print(f"ERRO: {error}")
        return 1

    venues = build_venues(raw_venues, raw_matches)
    matches = build_matches(raw_matches, venues)
    long = build_team_matches(matches)
    goals = build_goals(matches)
    tournaments = build_tournaments(matches)
    hosts = build_hosts(matches)
    teams = build_teams(long, team_country)

    tables = {
        "tournaments.csv": tournaments,
        "tournament_hosts.csv": hosts,
        "teams.csv": teams,
        "venues.csv": venues,
        "matches.csv": matches,
        "team_matches.csv": long,
        "goals.csv": goals,
    }
    print("Tabelas do modelo:")
    for name, table in tables.items():
        path = PROCESSED / name
        table.to_csv(path, index=False, encoding="utf-8")
        print(f"  {name:<22} {len(table):>5} linhas  {len(table.columns):>2} colunas"
              f"  {path.stat().st_size:>9,} bytes")

    print(f"\nEscrito em {PROCESSED.relative_to(ROOT)}/")

    print("\nPaíses-sede por edição (derivado das sedes usadas):")
    declared = declared_hosts()
    multi = hosts.tournament_id.value_counts()
    for tournament_id in sorted(multi[multi > 1].index):
        derived = hosts.loc[hosts.tournament_id == tournament_id, "host_country"]
        print(f"  {tournament_id}  {', '.join(derived)}"
              f"   (declarado: {declared.get(tournament_id)!r})")

    # ---- conferências ----
    print("\nConferências:")
    checks: list[tuple[str, object, object]] = [
        ("partidas preservadas", len(matches), len(raw_matches)),
        ("tabela longa = 2× partidas", len(long), 2 * len(matches)),
        ("sem país-sede nulo", int(matches.country_name.isna().sum()), 0),
        ("V+E+D fecha", int(long.result.isin(["W", "D", "L"]).sum()), len(long)),
        # Empates são simétricos: se A empatou com B, B empatou com A. Um número
        # ímpar de empates significaria que o desempate por pênaltis vazou.
        ("empates em pares", int((long.result == "D").sum()) % 2, 0),
        ("seleções com polígono", int(teams.gu_a3.notna().sum()), len(teams)),
        ("seleções com confederação", int(teams.confederation.notna().sum()), len(teams)),
        ("sedes com coordenada", int(venues.latitude.notna().sum()), len(venues)),
        ("edições", len(tournaments), raw_matches.tournament_id.nunique()),
        # A conferência que torna a tabela de gols verificável em vez de
        # plausível: a soma dos gols com autor tem que dar o mesmo que a soma
        # dos placares, que é um número que o modelo já produzia sozinho.
        ("gols com autor = placares", len(goals),
         int((matches.home_team_score + matches.away_team_score).sum())),
        ("gols sem minuto", int(goals.minute.isna().sum()), 0),
        ("gols sem autor", int(goals.player.isna().sum() + (goals.player == "").sum()), 0),
    ]

    # Cada partida gera uma vitória e uma derrota, ou dois empates.
    wins = int((long.result == "W").sum())
    losses = int((long.result == "L").sum())
    checks.append(("vitórias = derrotas", wins, losses))

    # Gols marcados = gols sofridos, olhando todo mundo.
    checks.append(("gols marcados = sofridos",
                   int(long.goals_for.sum()), int(long.goals_against.sum())))

    failures = 0
    for label, got, expected in checks:
        ok = got == expected
        failures += not ok
        print(f"  {'OK ' if ok else 'ERRO'} {label:<28} {got}  esperado {expected}")

    if failures:
        print(f"\n{failures} conferência(s) falharam.")
        return 1

    print(f"\n{len(teams)} seleções · {len(venues)} sedes · {len(tournaments)} edições "
          f"· {len(matches)} partidas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
