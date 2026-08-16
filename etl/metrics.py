"""Etapa 3 — métricas do mapa coroplético.

Transforma as tabelas modeladas (`etl.model`) no que o front-end consome:

    web/data/metrics.json    uma entrada por seleção, com as 6 métricas
    web/data/head2head.json  matriz de confrontos diretos
    web/data/timeline.json   a tabela longa em forma compacta (Etapa 4)
    web/data/colors.json     a rampa de cor de cada seleção (Etapa 4)
    web/data/names.json      o nome de cada seleção em português (Etapa 4)

**Escopo: Copa masculina**, herdado de `etl.model` — este módulo não filtra
nada, ele lê as tabelas do modelo. Por isso nenhum dos dois JSONs tem dimensão
de competição: `head2head` é `{seleção: {adversário: {...}}}`, e não
`{competição: {seleção: ...}}`. O feminino segue no dado bruto e em
`matches_clean.csv`.

O desenho do mapa (decidido em 08/08/2026) tem dois seletores — métrica e país
— e o modo de país repinta o mapa por confronto direto.

**A Etapa 4 abriu uma exceção à regra "o front-end não agrega nada".** O filtro
temporal escolhido foi um *slider de faixa de anos*, e não um seletor de década:
com 23 edições são 276 faixas possíveis, então pré-computar todas é inviável.
Por isso existe o `timeline.json` — a tabela longa em forma compacta — e o
JavaScript soma. A regra não foi simplesmente abandonada; ela virou uma
conferência: `metrics.json` continua sendo gerado aqui e o front-end **refaz a
faixa completa (1930–2026) e compara com ele, seleção por seleção**, avisando na
tela se divergir. Ou seja, a duplicação de lógica existe, mas não é silenciosa —
se o JS descolar do Python, a página denuncia.

Duas decisões do projeto estão implementadas aqui:

1. **Total e por partida, os dois.** Contagem bruta num coroplético reproduz
   sobretudo "quem se classificou mais vezes": a Alemanha tem 248 gols e o
   Brasil 247 porque os dois jogaram ~120 partidas. Por partida, a Hungria
   lidera com 2,72 e nem aparece no top 10 bruto. Por isso toda métrica sai nas
   duas formas, com piso de `PER_MATCH_FLOOR` partidas na versão por partida.

2. **O Reino Unido são quatro seleções.** Inglaterra, Escócia, País de Gales e
   Irlanda do Norte entram separadas, como estão no dado. A junção viraria uma
   "seleção do Reino Unido" que nunca existiu.

3. **A chave do join é a propriedade `team` do GeoJSON.** Cada polígono de
   `countries.geojson` já carrega o nome da seleção que o ocupa, resolvido aqui
   no ETL — o front-end nunca reinterpreta nomenclatura. O campo `gu_a3` das
   métricas é **informativo, não chave**: o mapa seleção→unidade é um-para-muitos
   (a Bélgica são três unidades no Natural Earth) e `gu_a3` guarda só uma delas.
   Casar por ele deixaria dois terços da Bélgica sem pintura.

Uso:
    python -m etl.model && python -m etl.metrics
"""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from etl.color import MIN_CHROMA, hex_to_oklch, ramp
from etl.model import COMPETITION
from etl.paths import (INTERIM, PROCESSED, RAW_FJELSTUL, REFERENCE, ROOT, WEB,
                       WEB_DATA, ensure_dirs)

# Abaixo deste número de partidas, a média por partida não é comparável: uma
# seleção com 3 jogos passaria o Brasil por acidente amostral.
PER_MATCH_FLOOR = 10

GROUP_STAGES = {"group stage", "second group stage"}


def load_model() -> tuple[pd.DataFrame, pd.DataFrame]:
    """As tabelas do modelo. Este módulo não deriva nada que `etl.model` já deriva.

    A tabela longa `(partida, seleção)` e a coluna `result` — que resolve
    disputas por pênaltis — são produzidas uma vez, na modelagem. Recalculá-las
    aqui seria manter duas definições da mesma coisa em dois arquivos.
    """
    missing = [name for name in ("matches.csv", "team_matches.csv")
               if not (PROCESSED / name).exists()]
    if missing:
        raise FileNotFoundError(
            f"{', '.join(missing)} não encontrado(s) — rode `python -m etl.model` antes.")
    return (pd.read_csv(PROCESSED / "matches.csv"),
            pd.read_csv(PROCESSED / "team_matches.csv"))


def map_units() -> dict[str, str]:
    """Seleção -> código da unidade de mapa, para o front-end casar o GeoJSON."""
    mapping = pd.read_csv(REFERENCE / "team_country.csv")
    return dict(zip(mapping.team_name, mapping.gu_a3))


def champion_by_edition(editions: set[str]) -> dict[str, str]:
    """Campeão de cada edição, com o mapa de sucessão aplicado.

    Vem de `tournament_standings.csv`, não das finais: a Copa de 1950 não teve
    final, e derivar campeão do `stage == "final"` perderia aquela edição em
    silêncio (ver `transform.titles_table`).

    O recorte não é uma regex sobre `tournament_name`: são os `tournament_id`
    que o modelo de fato contém. Assim o escopo é decidido em um lugar só
    (`etl.model.COMPETITION`) em vez de ser reinterpretado aqui.

    Devolve *por edição*, e não já contado, porque o filtro de anos da Etapa 4
    precisa saber **quando** cada título foi ganho. A contagem é uma linha
    depois, em `titles_by_team`.
    """
    succession = pd.read_csv(ROOT / "reference" / "team_succession.csv")
    merges = dict(zip(succession.historic_name, succession.merge_records))
    labels = dict(zip(succession.historic_name, succession.display_name))

    standings = pd.read_csv(RAW_FJELSTUL / "tournament_standings.csv")
    winners = standings[(standings.position == 1)
                        & standings.tournament_id.isin(editions)]
    champions = dict(zip(winners.tournament_id, winners.team_name))

    modern = pd.read_csv(INTERIM / "tournament_2026.csv")
    modern = modern[modern.tournament_id.isin(editions)]
    champions.update(zip(modern.tournament_id, modern.winner))

    return {edition: (labels[raw] if merges.get(raw, 0) == 1 else raw)
            for edition, raw in champions.items()}


def titles_by_team(editions: set[str]) -> dict[str, int]:
    """Títulos por seleção — a contagem de `champion_by_edition`."""
    counts: dict[str, int] = {}
    for name in champion_by_edition(editions).values():
        counts[name] = counts.get(name, 0) + 1
    return counts


def build_metrics(long: pd.DataFrame, matches: pd.DataFrame) -> list[dict]:
    """As seis métricas, por seleção."""
    titles = titles_by_team(set(matches.tournament_id))
    units = map_units()

    # "Partidas recebidas" é a única métrica que não olha para a seleção, e sim
    # para o país onde se jogou. Desde a geocodificação das sedes de 2026 ela
    # está completa — era a última coluna nula do modelo.
    received = matches.dropna(subset=["country_name"]).groupby("country_name").size()

    rows = []
    for team, block in long.groupby("team"):
        played = len(block)
        wins = int((block.result == "W").sum())
        draws = int((block.result == "D").sum())
        losses = int((block.result == "L").sum())
        goals = int(block.goals_for.sum())
        conceded = int(block.goals_against.sum())

        rows.append({
            "team": team,
            "gu_a3": units.get(team),
            "goals": goals,
            "conceded": conceded,
            "goal_difference": goals - conceded,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_pct": round(100 * wins / played, 1),
            "matches_played": played,
            "matches_received": int(received.get(team, 0)),
            "titles": titles.get(team, 0),
            "participations": int(block.year.nunique()),
            "first_year": int(block.year.min()),
            "last_year": int(block.year.max()),
            # versões por partida — None abaixo do piso, para o front-end poder
            # apagar a seleção do mapa em vez de mostrar média não comparável
            "goals_per_match": round(goals / played, 3) if played >= PER_MATCH_FLOOR else None,
            "conceded_per_match": round(conceded / played, 3) if played >= PER_MATCH_FLOOR else None,
            "wins_per_match": round(wins / played, 3) if played >= PER_MATCH_FLOOR else None,
        })
    return sorted(rows, key=lambda r: (-r["goals"], r["team"]))


def build_head_to_head(long: pd.DataFrame) -> dict:
    """Matriz seleção × adversário — o que o modo de país selecionado pinta."""
    matrix: dict[str, dict[str, dict[str, int]]] = {}
    for (team, opponent), block in long.groupby(["team", "opponent"]):
        matrix.setdefault(team, {})[opponent] = {
            "goals": int(block.goals_for.sum()),
            "conceded": int(block.goals_against.sum()),
            "matches": len(block),
            "wins": int((block.result == "W").sum()),
            "draws": int((block.result == "D").sum()),
            "losses": int((block.result == "L").sum()),
        }
    return matrix


def build_timeline(long: pd.DataFrame, matches: pd.DataFrame) -> dict:
    """A tabela longa em forma compacta — o que o slider de anos agrega.

    Formato colunar com dicionários de índices, e não uma lista de objetos: os
    mesmos 2.136 registros saem de ~400 KB para ~60 KB, porque `"team"`,
    `"opponent"` e os nomes das seleções deixam de ser repetidos linha a linha.
    O arquivo é lido inteiro no `load` e nunca mais; o custo é de rede, uma vez.

    Cada linha é `[ano, seleção, adversário, gols pró, gols contra, resultado]`,
    tudo como índice inteiro nas listas `years`, `teams` e na string `results`.

    Três agregados que não saem da tabela longa vão junto, porque o front-end
    precisa deles recortados pelo mesmo intervalo:

    - `titles`  — campeão de cada edição (a Copa de 1950 não teve final, então
      isto vem de `titles_by_team`, não de `stage == "final"`).
    - `hosted`  — partidas por país-sede, por edição. É a única métrica que
      descreve um **lugar** e não uma seleção; sai indexada em `teams` porque as
      19 sedes históricas são todas países que também jogaram, o que mantém um
      único espaço de nomes para o mapa casar.
    - `units`   — o `gu_a3` de cada seleção, paralelo a `teams`, só para rótulo.
    """
    teams = sorted(set(long.team) | set(matches.country_name.dropna()))
    # `int()` explícito: os anos vêm do pandas como `int64`, que o `json` não
    # serializa — e o erro só apareceria na escrita, depois de tudo pronto.
    years = sorted(int(year) for year in long.year.unique())
    team_ix = {name: i for i, name in enumerate(teams)}
    year_ix = {year: i for i, year in enumerate(years)}
    result_ix = {"W": 0, "D": 1, "L": 2}

    rows = [
        [year_ix[r.year], team_ix[r.team], team_ix[r.opponent],
         int(r.goals_for), int(r.goals_against), result_ix[r.result]]
        for r in long.itertuples()
    ]

    year_of = {edition: int(year) for edition, year in zip(matches.tournament_id, matches.year)}
    titles = [[year_ix[year_of[edition]], team_ix[champion]]
              for edition, champion in champion_by_edition(set(matches.tournament_id)).items()]

    hosted = [
        [year_ix[year], team_ix[country], int(count)]
        for (year, country), count in
        matches.dropna(subset=["country_name"]).groupby(["year", "country_name"]).size().items()
    ]

    units = map_units()
    return {
        "generated_from": "data/processed/team_matches.csv",
        "competition": COMPETITION,
        "per_match_floor": PER_MATCH_FLOOR,
        "years": years,
        "teams": teams,
        "units": [units.get(name) for name in teams],
        "results": "WDL",
        "rows": rows,
        "titles": titles,
        "hosted": hosted,
    }


# A rampa da visão global. Não é a cor de nenhuma seleção — é o azul da paleta
# validada do skill `dataviz`, usado quando nenhum país está escolhido. Pintar a
# visão global com a cor de cada seleção deixaria o mapa bonito e ilegível: o
# olho lê escuridão como quantidade, e cada país passaria a ter a sua própria
# escala, então uma Itália azul-escura pareceria "mais" que um Brasil amarelo
# vivo mesmo com o número menor.
DEFAULT_HUE = "#2A78D6"

# Os dois polos do saldo de gols. Eles NÃO seguem a cor da seleção escolhida, e
# isso é decisão, não esquecimento: polaridade precisa de dois polos fixos. Se o
# lado positivo virasse amarelo com o Brasil e vermelho com a Espanha, "negativo"
# mudaria de cor a cada troca de país e o mapa deixaria de ter um lado.
DIVERGING = {"negative": "#C8102E", "positive": DEFAULT_HUE}


def flag_file(code: str) -> str:
    """Código ISO -> nome do arquivo SVG da bandeira, em `web/vendor/flags/`.

    **Por que SVG e não emoji.** A primeira versão gerava emoji de bandeira, que
    não custa byte nenhum. O problema é que emoji de bandeira depende da fonte do
    sistema, e o **Windows não tem nenhuma**: um `🇧🇷` vira as letras "BR" em duas
    caixinhas, e as bandeiras britânicas (sequências de tag) viram uma bandeira
    preta lisa, igual para as três. Numa página que é justamente sobre países,
    isso deixaria de fora todo visitante de Windows.

    O conjunto vendorizado resolve os dois problemas de uma vez — desenha igual
    em qualquer sistema e **tem a Irlanda do Norte**, que o Unicode nunca criou
    como emoji e que por isso ficava sem bandeira na versão anterior.
    """
    return f"{code.lower()}.svg" if code and code != "-99" else ""


def build_colors(teams: list[str], last_cup: dict[str, int]) -> dict:
    """A rampa de cada seleção, nos dois modos, pronta para o navegador.

    A cor de cada seleção é curada à mão em `reference/team_colors.csv`, na mesma
    lógica do `team_succession.csv`: é decisão editorial, não dado da fonte, e
    por isso fica versionada com o porquê de cada linha não óbvia.

    A regra da curadoria: **a camisa principal da última Copa que a seleção
    disputou**. Não é "a cor do país" nem a do uniforme atual — é a que estava em
    campo da última vez que aquela seleção apareceu neste dado. Para 48 das 83 a
    última Copa é 2026, então a distinção quase não morde; ela aparece nas nove
    que não jogam desde antes de 1998 (Cuba 1938, Israel 1970, Kuwait 1982…).

    A exceção: quando essa camisa é branca ou preta — que não têm matiz para
    sustentar uma rampa, e cujo cinza colidiria com o cinza de "sem dado" —, usa-se
    a cor cromática que identifica a seleção, marcada `identity` e justificada
    linha a linha.

    A coluna `last_cup` é **conferida contra o modelo**, não decorativa: se uma
    seleção voltar a disputar uma Copa, a linha fica desatualizada em silêncio, e
    a cor passaria a descrever um uniforme que não é mais o último.
    """
    table = pd.read_csv(REFERENCE / "team_colors.csv")
    base = dict(zip(table.team_name, table.hex))
    declared = dict(zip(table.team_name, table.last_cup))

    # A bandeira vem do `iso_a2` que `etl.geo` extraiu do Natural Earth — mesma
    # fonte do polígono, em vez de uma terceira tabela curada à mão.
    units = pd.read_csv(REFERENCE / "team_country.csv").drop_duplicates("team_name")
    flags = {name: flag_file(str(code) if pd.notna(code) else "")
             for name, code in zip(units.team_name, units.get("iso_a2", pd.Series(dtype=str)))}

    # Um SVG ausente vira um ícone quebrado na tabela — some sem erro no console
    # e sem falha em teste nenhum. Conferir aqui é barato e fecha esse buraco.
    absent = sorted(name for name in teams
                    if not flags.get(name) or not (WEB / "vendor" / "flags" / flags[name]).exists())
    if absent:
        raise ValueError(
            "sem arquivo de bandeira em web/vendor/flags/ para: " + ", ".join(absent))

    missing = sorted(set(teams) - set(base))
    if missing:
        raise ValueError(f"sem cor em reference/team_colors.csv: {', '.join(missing)}")

    stale = sorted(
        f"{name} (tabela diz {declared[name]}, modelo diz {last_cup[name]})"
        for name in teams if int(declared[name]) != int(last_cup[name])
    )
    if stale:
        raise ValueError(
            "`last_cup` desatualizado — a cor precisa ser a da camisa da última Copa "
            f"disputada: {'; '.join(stale)}")

    faint = sorted(name for name in teams if hex_to_oklch(base[name])[1] < MIN_CHROMA)
    if faint:
        raise ValueError(
            f"cor acromática demais para virar rampa (lê como cinza, que é 'sem dado'): "
            f"{', '.join(faint)}")

    return {
        "default": {mode: ramp(DEFAULT_HUE, mode) for mode in ("light", "dark")},
        "diverging": {
            mode: {arm: ramp(hue, mode) for arm, hue in DIVERGING.items()}
            for mode in ("light", "dark")
        },
        "teams": {
            name: {
                "hex": base[name],
                "flag": flags.get(name, ""),
                "last_cup": int(declared[name]),
                "light": ramp(base[name], "light"),
                "dark": ramp(base[name], "dark"),
            }
            for name in teams
        },
    }


def build_names(teams: list[str]) -> dict:
    """O nome de cada seleção em português, para a interface.

    A chave continua sendo o nome em inglês — ele é a chave do dado em todo o
    resto do projeto (`matches_clean.csv`, a propriedade `team` do GeoJSON, o
    parâmetro `t=` da URL), e traduzir a chave obrigaria a retraduzir de volta em
    cada join. O que muda é só o rótulo: a página é em português e mostrava
    "Germany" ao lado de "Gols marcados".

    A tradução é curada em `reference/team_names.csv`, e não tirada do
    `NAME_PT` do Natural Earth, por dois motivos. O primeiro é que ele descreve
    países e o dado descreve seleções: "Republic of Ireland" e "Chinese Taipei"
    não são nomes de país, e a Bélgica ocupa três unidades de mapa cujos nomes
    em português são "Flandres", "Valônia" e "Bruxelas" — nenhum deles é a
    seleção. O segundo é que o `NAME_PT` é português europeu em vários casos
    (Chéquia, Irão), e a página é pt-BR.
    """
    table = pd.read_csv(REFERENCE / "team_names.csv", keep_default_na=False)
    names = dict(zip(table.team_name, table.name_pt))
    # O artigo é o que separa "a cor de Alemanha" de "a cor da Alemanha". Ele é
    # propriedade do nome, não regra derivável: Portugal e Cuba não levam artigo,
    # o Brasil leva "o", os Estados Unidos levam "os". Fica na mesma linha do
    # nome porque é a mesma decisão editorial.
    articles = dict(zip(table.team_name, table.artigo))
    # O trigrama FIFA — BRA, ARG, GER —, que é como o placar de uma transmissão
    # nomeia as duas seleções. Curado, e não derivado das três primeiras letras
    # do nome: "Croácia" e "Costa Rica" dariam "CRO" e "COS" por acaso, mas
    # "Alemanha" daria "ALE" e "Holanda" daria "HOL", que não são os códigos que
    # apareceram na tela de ninguém em nenhuma Copa. O padrão vale mais que a
    # regra porque é ele que o torcedor reconhece.
    siglas = dict(zip(table.team_name, table.sigla))

    unknown = sorted({a for a in articles.values()} - {"", "o", "a", "os", "as"})
    if unknown:
        raise ValueError(f"artigo desconhecido em reference/team_names.csv: {unknown}")

    missing = sorted(set(teams) - set(names))
    if missing:
        raise ValueError(f"sem nome em reference/team_names.csv: {', '.join(missing)}")

    malformed = sorted(
        team for team in teams
        if not (len(siglas[team]) == 3 and siglas[team].isupper() and siglas[team].isalpha())
    )
    if malformed:
        raise ValueError(
            "sigla fora do formato de três maiúsculas em reference/team_names.csv: "
            + ", ".join(malformed)
        )

    # Duas seleções com a mesma sigla seriam dois placares idênticos com
    # resultados diferentes — o mesmo modo de falha do nome repetido, e mais
    # difícil de perceber, porque a sigla é curta demais para estranhar.
    repeated: dict[str, str] = {}
    collisions = []
    for team in teams:
        other = repeated.setdefault(siglas[team], team)
        if other != team:
            collisions.append(f"{other} e {team} → {siglas[team]}")
    if collisions:
        raise ValueError("sigla repetida: " + "; ".join(collisions))

    # Dois rótulos iguais seriam duas linhas idênticas no ranking, com números
    # diferentes — o tipo de erro que parece dado errado e é rótulo errado.
    seen: dict[str, str] = {}
    clashes = []
    for team in teams:
        other = seen.setdefault(names[team], team)
        if other != team:
            clashes.append(f"{other} e {team} → {names[team]}")
    if clashes:
        raise ValueError("nome em português repetido: " + "; ".join(clashes))

    return {
        "generated_from": "reference/team_names.csv",
        "teams": {team: names[team] for team in teams},
        # Só quem tem artigo entra: no front-end a ausência já significa "sem
        # artigo", e 15 chaves com string vazia seriam peso morto no download.
        "articles": {team: articles[team] for team in teams if articles[team]},
        "siglas": {team: siglas[team] for team in teams},
    }


def build_match_list(matches: pd.DataFrame, venues: pd.DataFrame) -> tuple[dict, list[str]]:
    """As 1.068 partidas, uma a uma — o que o detalhamento abre.

    Até aqui o front-end só via agregados: "Brasil 21 gols contra a Suécia em 7
    jogos". Isso responde *quanto* e nunca *quais*. Este arquivo é a resposta de
    baixo: data, edição, fase, placar, sede e disputa de pênaltis de cada
    partida, para a página poder abrir o número e mostrar as linhas que o formam.

    Colunar pelo mesmo motivo do `timeline.json`: nomes de seleção, fase e sede
    se repetem centenas de vezes e viram índices. **Os índices são próprios**,
    não os do `timeline.json` — os dois arquivos não se conhecem, e assim mexer
    em um nunca corrompe silenciosamente a leitura do outro.

    O placar de pênaltis só aparece nas partidas que tiveram disputa; nas outras
    é nulo, e não `0–0`. Foi um dos sentinels que o `pandera` pegou na Etapa 3: a
    fonte grava `0–0` em 1.205 partidas sem disputa, e um zero é um placar
    perfeitamente válido.
    """
    stages = sorted(matches.stage.unique())
    teams = sorted(set(matches.home_team) | set(matches.away_team))
    venue_names = venues.set_index("venue_id")

    stage_ix = {name: i for i, name in enumerate(stages)}
    team_ix = {name: i for i, name in enumerate(teams)}
    used = [vid for vid in venues.venue_id if vid in set(matches.venue_id)]
    venue_ix = {vid: i for i, vid in enumerate(used)}

    rows = []
    order: list[str] = []
    for match in matches.sort_values("match_date").itertuples():
        order.append(match.match_id)
        penalties = None
        if match.penalty_shootout and pd.notna(match.home_team_score_penalties):
            penalties = [int(match.home_team_score_penalties),
                         int(match.away_team_score_penalties)]
        rows.append([
            int(match.year), stage_ix[match.stage],
            team_ix[match.home_team], team_ix[match.away_team],
            int(match.home_team_score), int(match.away_team_score),
            venue_ix.get(match.venue_id, -1),
            str(match.match_date),
            penalties,
        ])

    return {
        "generated_from": "data/processed/matches.csv",
        "competition": COMPETITION,
        "stages": stages,
        "teams": teams,
        "venues": [
            {
                "name": venue_names.loc[vid, "stadium_name"],
                "city": venue_names.loc[vid, "city_name"],
                "country": venue_names.loc[vid, "country_name"],
            }
            for vid in used
        ],
        "rows": rows,
    }, order


def build_goal_list(goals: pd.DataFrame, match_list: dict, order: list[str]) -> dict:
    """Os 3.028 gols em forma compacta, presos ao índice do `matches.json`.

    Cada linha é `[partida, seleção, jogador, minuto, acréscimo, marca]`, tudo
    como índice — o nome "Cristiano Ronaldo" aparece uma vez no dicionário e não
    nas dezenas de linhas dele. A marca é 0 (normal), 1 (pênalti) ou 2 (contra).

    O índice de partida é a **posição no `matches.json`**, não um id: o
    detalhamento já carrega aquela lista e casar por posição evita mandar 3.028
    strings de id junto. É o mesmo contrato das sedes, e com a mesma armadilha —
    se as duas listas saírem de ordem, os gols aparecem na partida errada sem
    nada acusar. Por isso a ordem é passada de fora, vinda de quem montou o
    `matches.json`, e conferida em `main`.

    O gol contra é creditado à seleção que **ganhou** o gol, como no placar; o
    nome que aparece é o de quem chutou. Sem isso a soma não fecharia.

    **O índice de jogador é a pessoa, não o nome.** Ele vem do `player_id` que
    `etl.model.bridge_player_ids` resolve, e não de `player.unique()` como antes:
    por nome, o Ronaldo brasileiro (15 gols) e um Ronaldo português de 2026 (3)
    viravam uma entrada só de 18 gols — um recorde que não existe, à frente do
    Klose, que tem o de verdade com 16. Dois jogadores homônimos aparecem aqui
    como duas entradas com o mesmo rótulo, e é o `player_teams` que os separa na
    tela.

    `player_teams` existe para o front-end não ter que adivinhar de que seleção
    é um artilheiro: a coluna `team` da linha do gol é a **creditada**, que num
    gol contra é a adversária de quem chutou.
    """
    team_ix = {name: i for i, name in enumerate(match_list["teams"])}
    match_ix = {match_id: i for i, match_id in enumerate(order)}

    identities = (goals[["player_id", "player", "player_team"]]
                  .drop_duplicates("player_id")
                  .sort_values(["player", "player_id"])
                  .reset_index(drop=True))

    split = goals.groupby("player_id").player.nunique()
    if (split > 1).any():
        raise ValueError(
            "player_id com mais de um nome em data/processed/goals.csv: "
            + ", ".join(sorted(split[split > 1].index))
        )

    players = identities.player.tolist()
    player_teams = [team_ix.get(name, -1) for name in identities.player_team]
    player_ix = dict(zip(identities.player_id, range(len(identities))))

    rows = []
    for goal in goals.itertuples():
        if goal.match_id not in match_ix or goal.team not in team_ix:
            continue
        rows.append([
            match_ix[goal.match_id],
            team_ix[goal.team],
            player_ix[goal.player_id],
            int(goal.minute_regulation),
            int(goal.minute_stoppage) if pd.notna(goal.minute_stoppage) else 0,
            2 if goal.own_goal else 1 if goal.penalty else 0,
        ])

    return {
        "generated_from": "data/processed/goals.csv",
        "competition": COMPETITION,
        "players": players,
        "player_teams": player_teams,
        # O id vai junto porque a URL da página de um jogador precisa apontar
        # para a PESSOA. Por nome, `art=Ronaldo` seria ambíguo exatamente no
        # caso que a identidade existe para separar; por posição na lista, o
        # link quebraria calado se o dado fosse regerado com um artilheiro a
        # mais. São ~13 KB num arquivo de 86 KB.
        "player_ids": identities.player_id.tolist(),
        "marks": ["normal", "pênalti", "contra"],
        "rows": rows,
    }


def build_venue_layer(venues: pd.DataFrame, matches: pd.DataFrame) -> dict:
    """As sedes geocodificadas, prontas para virar uma camada no mapa.

    A Etapa 3 resolveu 252 sedes no Nominatim e o mapa nunca usou nenhuma: o
    desenho escolhido foi coroplético, que pinta países, e as coordenadas
    ficaram paradas. Esta camada devolve esse trabalho — e responde uma pergunta
    que o coroplético não responde, porque ele agrega ao país: *onde exatamente*
    se jogou.

    Só entram as sedes que de fato receberam partida no recorte do modelo. Uma
    sede sem partida seria um ponto no mapa que não corresponde a nada.

    **A ordem das linhas é a mesma do índice de sedes do `matches.json`**, e isso
    é contrato, não coincidência: o front-end filtra as sedes pelo intervalo de
    anos contando partidas do detalhamento, e sem alinhamento ele plotaria a
    contagem de um estádio na coordenada de outro. Ordenar aqui por número de
    partidas — que foi a primeira versão — quebrava exatamente isso, e em
    silêncio, porque as duas listas continuam do mesmo tamanho. Uma conferência
    em `main` compara os dois nomes posição a posição.
    """
    hosted = matches.groupby("venue_id").size()
    rows = []
    for venue in venues.itertuples():
        if venue.venue_id not in hosted.index:
            continue
        rows.append([
            round(float(venue.latitude), 4),
            round(float(venue.longitude), 4),
            int(hosted[venue.venue_id]),
            int(venue.first_year), int(venue.last_year),
            venue.stadium_name, venue.city_name, venue.country_name,
        ])
    return {
        "generated_from": "data/processed/venues.csv",
        "competition": COMPETITION,
        "fields": ["lat", "lon", "matches", "first_year", "last_year",
                   "stadium", "city", "country"],
        "rows": rows,
    }


def aggregate_timeline(timeline: dict, first: int, last: int) -> dict[str, dict]:
    """Agrega o `timeline.json` numa faixa de anos — a referência do JavaScript.

    Existe para que a conferência da Etapa 4 seja executável dos dois lados: o
    `map.js` implementa exatamente estas somas, e o teste em Python confere que,
    na faixa completa, elas reproduzem o `metrics.json` linha a linha. Se as duas
    implementações divergirem, alguém quebrou uma das duas — e não fica escondido.
    """
    teams, years = timeline["teams"], timeline["years"]
    inside = {i for i, year in enumerate(years) if first <= year <= last}

    totals: dict[str, dict] = {}

    def slot(name: str) -> dict:
        return totals.setdefault(name, {
            "goals": 0, "conceded": 0, "wins": 0, "draws": 0, "losses": 0,
            "matches_played": 0, "matches_received": 0, "titles": 0,
            "_years": set(),
        })

    for year_i, team_i, _opponent, goals_for, goals_against, result in timeline["rows"]:
        if year_i not in inside:
            continue
        row = slot(teams[team_i])
        row["goals"] += goals_for
        row["conceded"] += goals_against
        row["matches_played"] += 1
        row["wins" if result == 0 else "draws" if result == 1 else "losses"] += 1
        row["_years"].add(year_i)

    for year_i, team_i in timeline["titles"]:
        if year_i in inside:
            slot(teams[team_i])["titles"] += 1

    for year_i, team_i, count in timeline["hosted"]:
        if year_i in inside:
            slot(teams[team_i])["matches_received"] += count

    for row in totals.values():
        row["participations"] = len(row.pop("_years"))
        row["goal_difference"] = row["goals"] - row["conceded"]
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args()

    ensure_dirs()
    try:
        matches, long = load_model()
    except FileNotFoundError as error:
        print(f"ERRO: {error}")
        return 1

    # Cada partida gera exatamente duas linhas na tabela longa.
    if len(long) != 2 * len(matches):
        print(f"ERRO: {len(long)} linhas longas para {len(matches)} partidas")
        return 1

    venues = pd.read_csv(PROCESSED / "venues.csv")
    metrics = build_metrics(long, matches)
    head2head = build_head_to_head(long)
    timeline = build_timeline(long, matches)
    match_list, match_order = build_match_list(matches, venues)
    goal_list = build_goal_list(pd.read_csv(PROCESSED / "goals.csv"), match_list, match_order)
    venue_layer = build_venue_layer(venues, matches)
    try:
        colors = build_colors(
            timeline["teams"],
            {name: int(year) for name, year in long.groupby("team").year.max().items()},
        )
    except ValueError as error:
        print(f"ERRO: {error}")
        return 1

    try:
        names = build_names(timeline["teams"])
    except ValueError as error:
        print(f"ERRO: {error}")
        return 1

    for name, payload in (("metrics.json", {
        "generated_from": "data/processed/team_matches.csv",
        # O front-end não deve inferir o escopo contando linhas.
        "competition": COMPETITION,
        "per_match_floor": PER_MATCH_FLOOR,
        "matches_received_complete": bool(matches.country_name.notna().all()),
        "teams": metrics,
    }), ("head2head.json", head2head), ("timeline.json", timeline),
            ("colors.json", colors), ("matches.json", match_list),
            ("venues.json", venue_layer), ("goals.json", goal_list),
            ("names.json", names)):
        path = WEB_DATA / name
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        size = path.stat().st_size
        print(f"  {name:<16} {size:>9,} bytes -> {path.relative_to(ROOT)}")

    # ---- conferências contra o dado de origem ----
    print("\nConferências:")
    checks: list[tuple[str, object, object]] = []

    total_goals = sum(r["goals"] for r in metrics)
    expected_goals = int((matches.home_team_score + matches.away_team_score).sum())
    checks.append(("gols somados", total_goals, expected_goals))

    total_played = sum(r["matches_played"] for r in metrics)
    checks.append(("participações em partidas", total_played, 2 * len(matches)))

    total_titles = sum(r["titles"] for r in metrics)
    checks.append(("títulos", total_titles, matches.tournament_id.nunique()))

    # V + E + D tem que fechar com as partidas jogadas
    wdl = sum(r["wins"] + r["draws"] + r["losses"] for r in metrics)
    checks.append(("V+E+D", wdl, 2 * len(matches)))

    # O `timeline.json` tem que ser uma reescrita sem perda da tabela longa: se
    # agregá-lo na faixa completa não devolver o `metrics.json`, o payload que o
    # slider consome está mentindo, e o mapa mentiria junto em toda faixa.
    full = aggregate_timeline(timeline, min(timeline["years"]), max(timeline["years"]))
    divergent = [
        team["team"] for team in metrics
        if any(full.get(team["team"], {}).get(field) != team[field]
               for field in ("goals", "conceded", "goal_difference", "wins", "draws",
                             "losses", "matches_played", "matches_received", "titles",
                             "participations"))
    ]
    if divergent:
        print(f"  seleções divergentes: {', '.join(divergent[:8])}")
    checks.append(("timeline reproduz metrics", len(divergent), 0))
    checks.append(("linhas do timeline", len(timeline["rows"]), 2 * len(matches)))

    # O detalhamento tem que conter TODAS as partidas: uma lista que perde linhas
    # mostraria um confronto incompleto embaixo de um total correto — a pior
    # combinação possível, porque o número de cima continua batendo.
    checks.append(("partidas no detalhamento", len(match_list["rows"]), len(matches)))
    detailed_goals = sum(row[4] + row[5] for row in match_list["rows"])
    checks.append(("gols no detalhamento", detailed_goals, expected_goals))
    checks.append(("sedes na camada", len(venue_layer["rows"]), matches.venue_id.nunique()))
    hosted_in_layer = sum(row[2] for row in venue_layer["rows"])
    checks.append(("partidas por sede", hosted_in_layer, len(matches)))

    # Os dois arquivos precisam listar as sedes na MESMA ordem — o front-end usa
    # o índice de um para achar a coordenada no outro.
    aligned = sum(1 for layer, listed in zip(venue_layer["rows"], match_list["venues"])
                  if layer[5] == listed["name"])
    checks.append(("sedes alinhadas", aligned, len(venue_layer["rows"])))

    # Os gols casam com a partida por POSIÇÃO na lista. Se as duas listas
    # saírem de ordem, cada gol aparece na partida errada e nada acusa — os
    # totais continuam certos. Refazer a soma por partida a partir dos índices
    # e comparar com o placar é o que fecha essa porta.
    scored = {}
    for row in goal_list["rows"]:
        scored[(row[0], row[1])] = scored.get((row[0], row[1]), 0) + 1
    misplaced = 0
    same_label = 0
    for position, row in enumerate(match_list["rows"]):
        home, away = row[2], row[3]
        # Alemanha Oriental 1–0 Alemanha Ocidental, 1974: pela decisão editorial
        # do projeto os dois lados são "Germany", e um gol creditado a "Germany"
        # nesta partida não tem como dizer a qual das duas pertence. A conferência
        # pula o caso em vez de fingir que ele não existe — `etl.validate` já o
        # imprime a cada execução e um teste o trava.
        if home == away:
            same_label += 1
            continue
        if scored.get((position, home), 0) != row[4]: misplaced += 1
        if scored.get((position, away), 0) != row[5]: misplaced += 1
    checks.append(("gols na partida certa", misplaced, 0))
    checks.append(("partidas seleção × ela mesma", same_label, 1))
    checks.append(("gols no detalhamento", len(goal_list["rows"]), expected_goals))
    checks.append(("seleções com rampa", len(colors["teams"]), len(timeline["teams"])))
    checks.append(("seleções com nome em pt", len(names["teams"]), len(timeline["teams"])))

    # A claridade tem que ser monótona em toda rampa: é ela que carrega o dado, e
    # é ela que mantém a rampa legível para quem não distingue matizes. Uma cor
    # cujo passo escuro saísse mais claro que o anterior inverteria a leitura em
    # silêncio, num país só.
    broken = [
        name for name, entry in colors["teams"].items()
        for mode in ("light", "dark")
        if not all(
            (hex_to_oklch(entry[mode][i])[0] < hex_to_oklch(entry[mode][i + 1])[0])
            == (mode == "dark")
            for i in range(len(entry[mode]) - 1)
        )
    ]
    if broken:
        print(f"  rampas não monótonas: {', '.join(sorted(set(broken))[:8])}")
    checks.append(("rampas monótonas", len(broken), 0))

    # Uma seleção sem `gu_a3` existe nas métricas mas não pinta nada no mapa —
    # some da visualização sem gerar erro. Por isso é conferência, não aviso.
    with_unit = sum(1 for r in metrics if r["gu_a3"])
    checks.append(("entradas com gu_a3", with_unit, len(metrics)))

    failed = 0
    for label, got, expected in checks:
        ok = got == expected
        failed += not ok
        print(f"  {'OK ' if ok else 'ERRO'} {label:<26} {got:<8} esperado {expected}")

    if failed:
        print(f"\n{failed} conferência(s) falharam.")
        return 1

    incomplete = matches.country_name.isna().sum()
    if incomplete:
        print(f"\nAVISO: 'partidas recebidas' está incompleta — {incomplete} partidas "
              f"sem country_name (2026). Preencher na geocodificação.")

    print(f"\n{len(metrics)} seleções prontas para o mapa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
