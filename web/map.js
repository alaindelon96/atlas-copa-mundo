/* Atlas da Copa do Mundo — Etapa 4, o mapa.
 *
 * Este arquivo faz três coisas: agrega, classifica e pinta.
 *
 * AGREGA — e essa é a única exceção à regra do projeto de que o front-end não
 * agrega nada. O filtro temporal é um slider de faixa de anos: com 23 edições
 * são 276 faixas possíveis, e pré-computar todas seria absurdo. Então
 * `timeline.json` traz a tabela longa em forma compacta e as somas acontecem
 * aqui. A regra não sumiu, virou conferência: `selfCheck()` refaz a faixa
 * completa e compara com o `metrics.json` gerado pelo Python, seleção por
 * seleção. Se o JavaScript descolar do ETL, a página avisa em vez de mentir.
 * A implementação de referência é `etl.metrics.aggregate_timeline` — as duas
 * têm que casar, e um teste em Python trava o lado de lá.
 *
 * CLASSIFICA — escala CONTÍNUA, com raiz quadrada no valor, e a rampa é a cor da
 * seleção escolhida. Duas coisas se apoiam uma na outra aqui:
 *
 *   A raiz existe porque o dado é muito torto — o Brasil tem 247 gols e metade
 *   das seleções tem menos de 10. Numa escala linear contínua quase todo mundo
 *   se amontoa no primeiro décimo da rampa e o mapa devolve três países escuros
 *   num mundo pálido. A raiz abre o pé da distribuição sem inverter nenhuma
 *   ordem; o que ela distorce é a proporção, e a legenda assume isso marcando os
 *   valores na barra (as marcas se apertam à direita — a compressão é visível).
 *
 *   A cor vem do `colors.json`, gerado por `etl/color.py` a partir da cor curada
 *   de cada seleção em `reference/team_colors.csv`. Escolher o Brasil pinta o
 *   mapa de amarelo, a Itália de azzurro, a Holanda de laranja. A visão global
 *   NÃO faz isso: sem país escolhido a rampa é uma só, porque o olho lê
 *   escuridão como quantidade — dar a cada país a sua própria escala faria uma
 *   Itália azul-escura parecer "mais" que um Brasil amarelo com número maior.
 *
 * PINTA — casando pela propriedade `team` do GeoJSON, nunca pelo `gu_a3`. O
 * mapa seleção→unidade é um-para-muitos (a Bélgica são três unidades no Natural
 * Earth, o Reino Unido são quatro seleções), e o ETL já resolveu isso ao gravar
 * `team` em cada polígono. Casar por código deixaria dois terços da Bélgica sem
 * cor; casar por nome faria o front-end reinterpretar decisões do ETL.
 */

(function () {
  "use strict";

  var NUM = new Intl.NumberFormat("pt-BR");
  /* Ordenação de nomes em português. `localeCompare` sem locale usa o do
   * navegador, e num navegador em inglês "Áustria" cai depois de "Uzbequistão"
   * — acento vira um caractere qualquer no fim do alfabeto. */
  var ORDER = new Intl.Collator("pt-BR", { sensitivity: "base" });
  var RATE = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var PCT = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  /* As métricas do mapa. Cada uma declara três coisas que mudam o comportamento:
   *
   *   kind  'sequential' (magnitude, um matiz) ou 'diverging' (polaridade, dois
   *         matizes com cinza no meio). Duas são divergentes, e as duas têm um
   *         meio que significa alguma coisa: o saldo em 0 (marcou tanto quanto
   *         sofreu) e o aproveitamento em 50% (ganhou tanto quanto não ganhou).
   *         Numa rampa sequencial esse meio some — 49% e 51% viram dois tons
   *         quase iguais do mesmo matiz, e o lado de cada um deixa de existir.
   *   pivot onde fica o meio da barra divergente. Ausente é 0, que é o do saldo;
   *         o aproveitamento declara 50 porque a métrica não tem lado negativo,
   *         o que ela tem é um ponto de virada.
   *   rate  se a leitura "por partida" faz sentido. Aproveitamento já é uma
   *         taxa; partidas jogadas por partida seria 1; título por partida não
   *         significa nada. Nesses casos o botão desliga em vez de mentir.
   *   h2h   se a métrica existe em confronto direto. "Títulos", "participações"
   *         e "partidas recebidas" não existem: um título não é ganho *contra*
   *         alguém, e uma sede não joga.
   *   unit  o que a métrica conta *por*. Só as de unidade `match` ganham o
   *         contexto "N partidas" — no tooltip e na coluna J do ranking. Um
   *         título não é ganho por partida e uma participação conta torneios,
   *         não jogos; pôr o número de partidas ao lado deles sugere uma
   *         proporção que não existe (o Catar recebeu 64 partidas e disputou 6).
   */
  var METRICS = [
    { key: "goals",            label: "Gols marcados",     kind: "sequential", rate: true,  h2h: true,  unit: "match" },
    { key: "conceded",         label: "Gols sofridos",     kind: "sequential", rate: true,  h2h: true,  unit: "match" },
    { key: "goal_difference",  label: "Saldo de gols",     kind: "diverging",  rate: true,  h2h: true,  unit: "match" },
    { key: "wins",             label: "Vitórias",          kind: "sequential", rate: true,  h2h: true,  unit: "match" },
    { key: "win_pct",          label: "Aproveitamento",    kind: "diverging",  rate: false, h2h: true,  unit: "match", pct: true, pivot: 50 },
    { key: "matches_played",   label: "Partidas jogadas",  kind: "sequential", rate: false, h2h: true,  unit: "match" },
    // Contadas por torneio, não por partida: um título não é ganho por jogo e
    // uma participação conta edições. O número de partidas ao lado delas é ruído.
    { key: "titles",           label: "Títulos",           kind: "sequential", rate: false, h2h: false, unit: "tournament" },
    { key: "participations",   label: "Participações",     kind: "sequential", rate: false, h2h: false, unit: "tournament" },
    // Descreve o LUGAR, não a seleção. Uma sede não joga — o Catar recebeu 64
    // partidas e disputou 6.
    { key: "matches_received", label: "Partidas recebidas",kind: "sequential", rate: false, h2h: false, unit: "place" }
  ];

  var FIELDS = ["goals", "conceded", "goal_difference", "wins", "draws", "losses",
                "matches_played", "matches_received", "titles", "participations"];

  var state = {
    metric: "goals", mode: "total", team: null, from: 0, to: 0,
    versus: null,     // segunda seleção, para a comparação lado a lado
    // null = padrão (o mapa); "matches"; "scorers"; e os três índices que a
    // barra da marca abre: "editions", "teams", "duels"
    view: null,
    opponent: null,   // adversário do detalhamento, quando veio de um confronto
    player: null,     // índice do jogador aberto — a PESSOA, não o nome
    edition: null,    // índice da edição aberta em TIMELINE.years — a Copa como destino
    venues: false     // camada de sedes
  };

  var TIMELINE = null, GOLDEN = null, GEO = null, COLORS = null;
  var MATCHES = null, VENUES = null, GOALS = null, NAMES = null;
  var map = null, layer = null, venueLayer = null, byTeam = {};
  var current = { records: null, scale: null, metric: null };
  /* Quem recebe a edição aberta. Fica fora do `state` porque não é escolha de
   * ninguém: é consequência de `state.edition`, recalculada a cada repintura e
   * lida pelo `styleFor`, que roda uma vez por país e não pode varrer as 26
   * linhas de `TIMELINE.hosted` a cada chamada. */
  var hostTeams = {};

  // ---------------------------------------------------------------- utilidades

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  /* O nome de uma seleção como a página o mostra: em português.
   *
   * A CHAVE continua em inglês, em todo lugar — é a chave do dado (a propriedade
   * `team` do GeoJSON, os índices do `timeline.json`, o `t=` da URL). Traduzir a
   * chave quebraria os links já compartilhados e obrigaria a destraduzir em cada
   * join; traduzir só o rótulo não custa nada. Por isso `pt()` aparece na saída
   * — tooltip, tabela, seletor — e nunca numa comparação ou numa busca.
   *
   * O fallback devolve o nome cru: se `names.json` não carregar, a página mostra
   * "Germany" em vez de quebrar. */
  function pt(team) {
    return (NAMES && NAMES.teams[team]) || team;
  }

  /* A sigla de três letras — BRA, ARG, GER —, que é como o placar de uma
   * transmissão nomeia as duas seleções. Curada em `reference/team_names.csv`
   * pelo trigrama da FIFA, e não derivada do nome: "Alemanha" daria "ALE" e
   * "Holanda" daria "HOL", que não apareceram na tela de ninguém em Copa
   * nenhuma. O que o torcedor reconhece é o padrão, não a regra.
   *
   * A reserva devolve as três primeiras letras em caixa-alta: se `names.json`
   * não carregar, o placar fica com "GER" errado em vez de vazio. */
  function sigla(team) {
    return (NAMES && NAMES.siglas && NAMES.siglas[team]) ||
           team.slice(0, 3).toUpperCase();
  }

  /* Ordem alfabética pelo rótulo mostrado — que é o único que a pessoa vê. Em
   * inglês, Alemanha vem antes de Argentina; em português, é o contrário. */
  function byName(a, b) {
    return ORDER.compare(pt(a), pt(b));
  }

  /* Nome de país dentro de uma frase precisa de artigo — e em português o
   * artigo é propriedade do nome, não regra: "a Alemanha", "o Brasil", "os
   * Estados Unidos", mas "Portugal" e "Cuba" sem nenhum. A tabela curada é
   * quem sabe; o ETL só manda quem tem.
   *
   * `theTeam` é o nome com artigo ("a Alemanha"), e é o que a legenda e o
   * tooltip usam quando o país aparece no meio de uma frase. */
  function article(team) {
    return (NAMES && NAMES.articles && NAMES.articles[team]) || "";
  }

  function theTeam(team) {
    var word = article(team);
    return word ? word + " " + pt(team) : pt(team);
  }

  /* "Os Estados Unidos aparecem", "o Brasil aparece". O número vem do artigo —
   * é a única marca de plural que a tabela carrega, e é do que a única frase da
   * legenda com verbo precisa. */
  function plural(team) {
    var word = article(team);
    return word === "os" || word === "as";
  }

  /* O marcador de uma seleção: a bandeira dela.
   *
   * São SVGs versionados em `web/vendor/flags/`, não emoji. Emoji de bandeira
   * depende da fonte do sistema e o **Windows não tem nenhuma** — um `🇧🇷` vira
   * as letras "BR" ali, e as três bandeiras britânicas de emoji viram uma
   * bandeira preta lisa, igual para as três. Numa página sobre países, isso
   * deixaria de fora todo visitante de Windows. O conjunto vendorizado desenha
   * igual em qualquer sistema e ainda tem a Irlanda do Norte, que o Unicode
   * nunca criou como emoji.
   *
   * O ponto colorido continua existindo para quando a bandeira não carregar —
   * e o `onerror` troca um pelo outro sem deixar ícone quebrado na tabela.
   */
  function badge(team, value) {
    var entry = COLORS.teams[team];
    var dot = '<span class="chip" style="background:' +
              (colorFor(value, current.scale) || css("--absent")) + '"></span>';
    if (!entry || !entry.flag) return dot;
    // Sem `loading="lazy"`: as bandeiras vivem dentro de um painel com rolagem
    // própria, e o carregamento preguiçoso depende de a linha estar visível — o
    // que nem sempre é avaliado como se espera dentro de um contêiner rolável.
    // O conjunto inteiro são 146 KB e uma tela usa no máximo umas 47; carregar
    // direto custa pouco e não tem esse modo de falha.
    // As duas aspas precisam ser escapadas, não só a simples: o `dot` traz
    // `class="chip"` dentro dele, e uma aspa dupla crua encerra o atributo
    // `onerror` no meio — o resto do `<img>` vaza como texto na tela.
    var fallback = dot.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "\\'");
    return '<img class="flag" src="vendor/flags/' + entry.flag + '" alt="" aria-hidden="true"' +
           ' decoding="async"' +
           " onerror=\"this.outerHTML='" + fallback + "'\">";
  }

  /* Se a métrica ganha o contexto "N partidas" — no tooltip e na coluna J.
   *
   * Duas exclusões, por motivos diferentes. As métricas contadas por torneio ou
   * por lugar (títulos, participações, partidas recebidas) não têm relação com o
   * número de jogos, e pôr os dois lado a lado sugere uma proporção inexistente.
   * "Partidas jogadas" é excluída pelo motivo oposto: o contexto seria ela
   * mesma, repetida na coluna ao lado. */
  function showsMatchContext(def) {
    return def.unit === "match" && def.key !== "matches_played";
  }

  function metricDef(key) {
    for (var i = 0; i < METRICS.length; i++) if (METRICS[i].key === key) return METRICS[i];
    return METRICS[0];
  }

  function blank() {
    return { goals: 0, conceded: 0, wins: 0, draws: 0, losses: 0,
             matches_played: 0, matches_received: 0, titles: 0, years: {} };
  }

  function finish(rec) {
    rec.goal_difference = rec.goals - rec.conceded;
    rec.participations = Object.keys(rec.years).length;
    return rec;
  }

  // ------------------------------------------------------------- agregação

  /* Espelho de `etl.metrics.aggregate_timeline`. Se você mudar uma soma aqui,
   * mude lá — e é justamente isso que a autoconferência vigia. */
  function aggregate(from, to) {
    var teams = TIMELINE.teams, out = {}, i, row;

    function slot(index) {
      var name = teams[index];
      if (!out[name]) out[name] = blank();
      return out[name];
    }

    for (i = 0; i < TIMELINE.rows.length; i++) {
      row = TIMELINE.rows[i];
      if (row[0] < from || row[0] > to) continue;
      var rec = slot(row[1]);
      rec.goals += row[3];
      rec.conceded += row[4];
      rec.matches_played += 1;
      rec[row[5] === 0 ? "wins" : row[5] === 1 ? "draws" : "losses"] += 1;
      rec.years[row[0]] = 1;
    }
    for (i = 0; i < TIMELINE.titles.length; i++) {
      row = TIMELINE.titles[i];
      if (row[0] >= from && row[0] <= to) slot(row[1]).titles += 1;
    }
    for (i = 0; i < TIMELINE.hosted.length; i++) {
      row = TIMELINE.hosted[i];
      if (row[0] >= from && row[0] <= to) slot(row[1]).matches_received += row[2];
    }
    for (var name in out) finish(out[name]);
    return out;
  }

  /* Confronto direto: as mesmas somas, restritas às linhas da seleção escolhida
   * e agrupadas pelo adversário. `titles` e `matches_received` ficam em zero de
   * propósito — não existem em confronto, e a lista de métricas já impede
   * escolhê-las neste modo. */
  function headToHead(team, from, to) {
    var teams = TIMELINE.teams, index = teams.indexOf(team), out = {};
    if (index < 0) return out;
    for (var i = 0; i < TIMELINE.rows.length; i++) {
      var row = TIMELINE.rows[i];
      if (row[0] < from || row[0] > to || row[1] !== index) continue;
      var name = teams[row[2]];
      if (!out[name]) out[name] = blank();
      var rec = out[name];
      rec.goals += row[3];
      rec.conceded += row[4];
      rec.matches_played += 1;
      rec[row[5] === 0 ? "wins" : row[5] === 1 ? "draws" : "losses"] += 1;
      rec.years[row[0]] = 1;
    }
    for (var key in out) finish(out[key]);
    return out;
  }

  /* O valor que o mapa pinta. Devolve `null` para "não pinta" — que é diferente
   * de zero: zero é um fato (jogou e não marcou), null é ausência de base. */
  function valueOf(rec, def, mode) {
    if (!rec) return null;
    if (def.key === "win_pct") {
      return rec.matches_played ? (100 * rec.wins) / rec.matches_played : null;
    }
    var raw = rec[def.key];
    if (mode !== "rate" || !def.rate) return raw;
    // O piso existe para uma seleção de 3 jogos não passar o Brasil por acidente
    // amostral. Abaixo dele a média não é comparável, então ela não é mostrada.
    if (rec.matches_played < TIMELINE.per_match_floor) return null;
    return raw / rec.matches_played;
  }

  function format(value, def, mode) {
    if (value === null || value === undefined) return "—";
    if (def.pct) return PCT.format(value) + "%";
    if (mode === "rate" && def.rate) return RATE.format(value);
    return NUM.format(value);
  }

  // ------------------------------------------------------------ classificação

  /* Qual modo de cor está valendo. As rampas vêm prontas do `colors.json` nos
   * dois modos, e a página escolhe uma — não há conversão de cor no navegador. */
  function darkMode() {
    var stamped = document.documentElement.getAttribute("data-theme");
    if (stamped) return stamped === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  /* A rampa da métrica atual: a cor da seleção escolhida, ou o azul da visão
   * global. É aqui que "o mapa fica da cor do time" acontece. */
  function rampFor() {
    var mode = darkMode() ? "dark" : "light";
    if (state.team && COLORS.teams[state.team]) return COLORS.teams[state.team][mode];
    return COLORS.default[mode];
  }

  function mix(from, to, ratio) {
    var out = "#";
    for (var i = 1; i < 7; i += 2) {
      var a = parseInt(from.substr(i, 2), 16), b = parseInt(to.substr(i, 2), 16);
      var value = Math.round(a + (b - a) * ratio);
      out += (value < 16 ? "0" : "") + value.toString(16);
    }
    return out.toUpperCase();
  }

  /* Amostra contínua da rampa. Os passos vizinhos estão perto o bastante para
   * interpolar em sRGB sem sujar o matiz — o trabalho perceptual (OKLab) já foi
   * feito em `etl/color.py`, que é quem posicionou os passos. */
  function sample(stops, position) {
    position = Math.max(0, Math.min(1, position));
    var exact = position * (stops.length - 1), index = Math.floor(exact);
    if (index >= stops.length - 1) return stops[stops.length - 1];
    return mix(stops[index], stops[index + 1], exact - index);
  }

  /* Escala CONTÍNUA, com raiz quadrada no valor.
   *
   * A raiz não é enfeite: sem ela o mapa some. A distribuição é muito torta — o
   * Brasil tem 247 gols e metade das seleções tem menos de 10 —, então uma
   * escala linear empurra quase todo mundo para o primeiro décimo da rampa e
   * devolve três países escuros num mundo pálido. A raiz abre o pé da
   * distribuição sem inverter nenhuma ordem: se A > B, a cor de A continua mais
   * forte que a de B. O que ela distorce é a *proporção* — o dobro da cor não é
   * o dobro do valor —, e é por isso que a legenda traz os números marcados na
   * barra em vez de deixar a escala implícita.
   */
  function scaleFor(records, def, mode) {
    var values = [], name, v;
    for (name in records) {
      v = valueOf(records[name], def, mode);
      if (v !== null && v !== undefined) values.push(v);
    }
    var theme = darkMode() ? "dark" : "light";

    if (def.kind === "diverging") {
      // A extensão é medida A PARTIR DO PIVÔ, não do zero: no aproveitamento o
      // zero é o pior resultado possível, não o meio, e medir dali jogaria toda
      // a distribuição para um lado só da barra.
      var pivot = def.pivot || 0;
      var extent = 0;
      values.forEach(function (x) { extent = Math.max(extent, Math.abs(x - pivot)); });
      return { kind: "diverging", pivot: pivot, extent: extent,
               negative: COLORS.diverging[theme].negative,
               positive: COLORS.diverging[theme].positive };
    }

    var max = 0;
    values.forEach(function (x) { max = Math.max(max, x); });
    return { kind: "sequential", max: max, stops: rampFor() };
  }

  function colorFor(value, scale) {
    if (value === null || value === undefined) return null;
    if (scale.kind === "diverging") {
      if (!scale.extent) return sample(scale.positive, 0);
      var delta = value - scale.pivot;
      var arm = delta < 0 ? scale.negative : scale.positive;
      return sample(arm, Math.sqrt(Math.abs(delta) / scale.extent));
    }
    if (!scale.max) return sample(scale.stops, 0);
    return sample(scale.stops, Math.sqrt(Math.max(0, value) / scale.max));
  }

  // ------------------------------------------------------------------- mapa

  function styleFor(feature) {
    var team = feature.properties.team;
    var absent = { fillColor: css("--absent"), fillOpacity: 1, color: css("--coast"),
                   weight: 0.6, opacity: 1 };
    if (!team) return absent;

    if (state.team && team === state.team) {
      // A seleção escolhida não joga contra si mesma. Em vez de sumir do mapa,
      // ela vira contorno: o olho precisa achar de onde os confrontos partem.
      return { fillColor: css("--accent-soft"), fillOpacity: 1,
               color: css("--accent"), weight: 2.5, opacity: 1 };
    }

    if (state.versus && team === state.versus) {
      // Na comparação, a segunda seleção precisa ser achável no mapa sem virar
      // um valor da escala — daí contorno tracejado em vez de preenchimento.
      return { fillColor: css("--accent-soft"), fillOpacity: .55,
               color: css("--accent"), weight: 2.5, opacity: 1, dashArray: "5 3" };
    }

    var value = valueOf(current.records[team], metricDef(state.metric), state.mode);
    var fill = colorFor(value, current.scale);

    /* O país-sede da edição aberta, contornado na cor do alfinete.
     *
     * A cor é a do alfinete e não a do acento por um motivo só: os alfinetes
     * dele estão dentro do contorno, e as duas marcas dizem a mesma coisa — é
     * aqui que se jogou. Verde ali seria a cor dos controles, que já significa
     * "escolhido". O preenchimento continua sendo o da métrica: a sede não
     * deixa de ser um país do mapa por estar recebendo a Copa.
     *
     * O contorno não decide nada sozinho — o painel nomeia a sede em texto e os
     * alfinetes marcam os estádios. É reforço, não código. */
    if (state.edition !== null && hostTeams[team]) {
      return { fillColor: fill === null ? css("--absent") : fill, fillOpacity: 1,
               color: css("--pin"), weight: 2.5, opacity: 1 };
    }

    if (fill === null) return absent;
    return { fillColor: fill, fillOpacity: 1, color: css("--coast"), weight: 0.6, opacity: 1 };
  }

  /* Uma linha do tooltip.
   *
   * `<div>` e não `<em>`, e o motivo é defensivo: `<div>` já é bloco na folha de
   * estilo do próprio navegador, enquanto `<em>` só quebra linha se a NOSSA
   * folha disser que quebra. Quando ela não dizia, "247" e "119 partidas"
   * apareciam colados como "247119 partidas" — um número maior que todos os gols
   * de todas as Copas, que parecia erro de dado e era erro de estilo. Legibilidade
   * de número não pode depender de o CSS ter carregado.
   */
  function tipLine(text) {
    return '<div class="tip-line">' + text + "</div>";
  }

  function tooltipFor(team) {
    var def = metricDef(state.metric);
    var rec = state.team && team === state.team ? null : current.records[team];
    var value = valueOf(rec, def, state.mode);
    var lines = "<b>" + pt(team) + "</b>";

    if (state.team && team === state.team) {
      return lines + tipLine("seleção escolhida");
    }
    if (!rec) {
      return lines + tipLine(state.team ? "nunca enfrentou " + theTeam(state.team)
                                        : "sem partidas na faixa");
    }

    var headline = def.label + ": " + format(value, def, state.mode);
    if (state.mode === "rate" && def.rate && value === null) {
      headline += " (menos de " + TIMELINE.per_match_floor + " partidas)";
    }
    lines += tipLine(headline);

    // "Partidas jogadas" é o contexto de todas as métricas de desempenho — menos
    // das que descrevem o lugar. Numa sede, o número de jogos da seleção não
    // explica nada e ainda sugere uma relação que não existe.
    if (showsMatchContext(def)) {
      lines += tipLine(NUM.format(rec.matches_played) + " partidas");
    }
    return lines;
  }

  function repaint() {
    var def = metricDef(state.metric);
    current.records = state.team ? headToHead(state.team, state.from, state.to)
                                 : aggregate(state.from, state.to);
    current.scale = scaleFor(current.records, def, state.mode);
    current.metric = def;

    hostTeams = {};
    if (state.edition !== null) {
      hostsOf(state.edition).forEach(function (host) { hostTeams[host.team] = 1; });
    }

    if (layer) {
      layer.eachLayer(function (child) {
        child.setStyle(styleFor(child.feature));
        var team = child.feature.properties.team;
        if (team) child.setTooltipContent(tooltipFor(team));
      });
    }
    drawScale();
    drawPanel();
    drawVenues();
    syncVenueButton();
    syncNav();
    focusEdition();
    syncURL();
  }

  /* O enquadramento de uma edição: os estádios daquele ano, todos na tela.
   *
   * Só quando a edição MUDA. `repaint()` roda a cada pixel do slider e a cada
   * troca de métrica; reenquadrar em toda repintura arrancaria o mapa da mão de
   * quem acabou de arrastá-lo.
   *
   * As margens saem dos retângulos dos próprios cartões, e não de números
   * fixos: eles flutuam por cima do mapa, e um `fitBounds` sem isso deixaria
   * Montevidéu embaixo do painel lateral. Recolhido, o cartão continua tendo
   * retângulo (a barra de título), e é ele que vale.
   *
   * O teto de zoom existe porque 1930 são três estádios em Montevidéu: sem
   * limite, o enquadramento perfeito é uma cidade, e o mapa deixa de mostrar em
   * que país aquilo aconteceu.
   *
   * **Sem animação**, e isso é correção de bug e não gosto. A animação de zoom
   * do Leaflet termina no `transitionend` da transformação CSS; numa aba que
   * não está compondo quadros (segundo plano, janela minimizada) esse evento
   * não chega, o `_resetView` do fim nunca roda e o mapa fica parado onde
   * estava — a tela da edição abre com os alfinetes fora do quadro e nada no
   * console. Foi exatamente isso que aconteceu ao conferir esta etapa. Um corte
   * seco sempre acontece; uma animação bonita que às vezes não termina deixa a
   * metade do recurso que o mapa deveria entregar em silêncio. */
  var flownTo = null;

  function focusEdition() {
    if (state.edition === null) { flownTo = null; return; }
    if (flownTo === state.edition || !map) return;
    flownTo = state.edition;

    var counts = venueCounts(state.from, state.to), points = [];
    Object.keys(counts).forEach(function (index) {
      points.push([VENUES.rows[index][0], VENUES.rows[index][1]]);
    });
    if (!points.length) return;

    var gap = 12;
    var side = document.getElementById("card-side").getBoundingClientRect();
    var controls = document.getElementById("card-controls").getBoundingClientRect();
    var topLeft, bottomRight;

    if (narrow()) {
      // No celular o painel é uma folha encostada na borda de baixo e os
      // controles ficam no topo: as margens são horizontais só na sobra.
      topLeft = [gap, controls.bottom + gap];
      bottomRight = [gap, Math.max(gap, window.innerHeight - side.top + gap)];
    } else {
      topLeft = [controls.right + gap, controls.top];
      bottomRight = [Math.max(gap, window.innerWidth - side.left + gap), gap];
    }

    map.fitBounds(L.latLngBounds(points), {
      paddingTopLeft: topLeft, paddingBottomRight: bottomRight, maxZoom: 5, animate: false
    });
  }

  function buildMap() {
    map = L.map("map", {
      // Equirretangular, e não a Mercator padrão: num coroplético a Mercator
      // infla Rússia, Canadá e Groenlândia — justamente as áreas grandes cuja
      // cor a gente quer comparar com a dos países pequenos.
      crs: L.CRS.EPSG4326,
      center: [25, 0], zoom: 2, minZoom: 1, maxZoom: 6,
      zoomControl: false,
      // A atribuição não vem do controle minúsculo do Leaflet: ela está no bloco
      // "Fontes e licenças" do cartão da legenda, que nomeia as três fontes e as
      // licenças por extenso. CC BY-SA é obrigação, e obrigação não cabe em 10px
      // no canto da tela.
      attributionControl: false,
      maxBounds: [[-90, -200], [90, 200]], maxBoundsViscosity: 0.8
    });
    L.control.zoom({ position: "bottomleft" }).addTo(map);

    layer = L.geoJSON(GEO, {
      // A Antártida ocupa um quinto da tela e nunca disputou nada — tirá-la é
      // devolver esse espaço ao dado.
      filter: function (feature) { return feature.properties.gu_a3 !== "ATA"; },
      style: styleFor,
      onEachFeature: function (feature, child) {
        var team = feature.properties.team;
        if (!team) return;
        child.bindTooltip("", { sticky: true, className: "atlas-tip", direction: "top" });
        child.on({
          mouseover: function () {
            child.setStyle({ weight: 2, color: css("--ink") });
            child.bringToFront();
          },
          mouseout: function () { child.setStyle(styleFor(feature)); },
          click: function () {
            // Clicar no país já selecionado desfaz a seleção — é o caminho de
            // volta óbvio, sem procurar "Nenhum" no seletor.
            select(state.team === team ? "" : team);
          }
        });
      }
    }).addTo(map);
  }

  // ------------------------------------------------------------ camada de sedes

  /* As 208 sedes onde as partidas de fato aconteceram.
   *
   * A Etapa 3 geocodificou 252 sedes no Nominatim e o mapa nunca usou nenhuma:
   * o desenho é coroplético, que pinta países, e as coordenadas ficaram paradas.
   * Esta camada responde o que o coroplético não responde, porque ele agrega ao
   * país: **onde**. O México inteiro fica de uma cor só; o Azteca sozinho
   * recebeu 24 partidas em três edições separadas por 56 anos.
   *
   * A contagem respeita o filtro de anos, e por isso é recontada a partir do
   * detalhamento em vez de usar o total pré-computado do `venues.json` — que
   * vale para a faixa inteira. Os dois arquivos listam as sedes na mesma ordem;
   * é contrato conferido no ETL, não coincidência.
   *
   * **Todos os alfinetes têm o mesmo tamanho**, o menor. A versão anterior
   * dimensionava a marca pela contagem de partidas, e num alfinete isso custa
   * mais do que rende: 208 deles se amontoam onde as Copas se repetiram (a
   * Europa e o México são um bloco só), e os grandes cobrem os pequenos —
   * escondendo justamente as sedes que a camada existe para mostrar. A
   * quantidade continua onde ela é exata: no tooltip, em número. Aqui o
   * alfinete responde só "aqui teve jogo", que é a pergunta do mapa.
   *
   * A marca é um alfinete, e ele mora no `markerPane` — que é a correção de um
   * bug real: como `circleMarker`, as sedes eram vetores do MESMO `overlayPane`
   * dos países, e o `bringToFront()` do país sob o mouse reordenava o SVG
   * inteiro e enterrava os pinos. Como a ordem ficava gravada na árvore, tirar o
   * mouse não desfazia: a sede sumia até recarregar. Panes separados tornam a
   * sobreposição impossível em vez de remediável — o `markerPane` (z 600) está
   * sempre acima do `overlayPane` (z 400). */
  function venueCounts(from, to) {
    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var counts = {};
    MATCHES.rows.forEach(function (row) {
      if (row[0] < firstYear || row[0] > lastYear || row[6] < 0) return;
      counts[row[6]] = (counts[row[6]] || 0) + 1;
    });
    return counts;
  }

  /* O desenho do alfinete: cabeça esférica vermelha, agulha metálica, ponta no
   * pé do viewBox — o alfinete de mapa de verdade, não a gota de aplicativo.
   *
   * A ordem importa: a agulha é desenhada ANTES da cabeça, para o topo dela
   * desaparecer atrás da esfera em vez de cruzá-la. O brilho é uma elipse
   * branca no canto superior esquerdo — é o que faz a cabeça ler como esfera e
   * não como um círculo chapado.
   *
   * As cores saem dos tokens do tema COM RESERVA literal (`var(--pin,#E01B24)`).
   * A reserva não é excesso de zelo: o SVG sem `fill` resolvido cai no preto
   * padrão, e uma folha de estilo em cache já entregou 208 alfinetes pretos sem
   * um erro sequer no console. O contorno na cor da costa separa a agulha fina
   * do país embaixo dela — sem ele, ela some sobre um país escuro. */
  var PIN_BOX_W = 28, PIN_BOX = 43;   // o viewBox, com a folga do traço
  var PIN_TIP = 41.4 / 43;            // onde a ponta cai dentro dele
  var PIN_WIDTH = 14;                 // igual para todas as sedes: ver drawVenues

  var PIN = '<svg viewBox="-2 -1 28 43" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<path d="M10.7 15.5 13.3 15.5 12.3 40.4a.32.32 0 0 1-.6 0z"' +
    ' style="fill:var(--pin-needle,#8A97A5);stroke:var(--coast,#FFF);stroke-width:.7"/>' +
    '<circle cx="12" cy="11" r="10"' +
    ' style="fill:var(--pin,#E01B24);stroke:var(--coast,#FFF);stroke-width:1.4"/>' +
    '<ellipse cx="8.3" cy="7.2" rx="3.4" ry="2.3" transform="rotate(-38 8.3 7.2)"' +
    ' fill="#FFF" opacity=".45"/></svg>';

  /* A camada está no ar quando alguém pediu — ou quando há uma edição aberta.
   *
   * Ela não é enfeite ali: a Copa de 1970 *é* cinco estádios no México, e a
   * tela existe justamente para o mapa responder "onde", que é a pergunta que
   * nenhum painel de números responde. Por isso a camada é IMPLICADA pela
   * edição em vez de ligada por ela: um `#copa=1970` colado por outra pessoa
   * abre exatamente a mesma tela, sem precisar carregar `sedes=1` junto. */
  function venuesOn() {
    return state.venues || state.edition !== null;
  }

  function drawVenues() {
    if (venueLayer) { map.removeLayer(venueLayer); venueLayer = null; }
    if (!venuesOn()) return;

    var counts = venueCounts(state.from, state.to);
    venueLayer = L.layerGroup();

    VENUES.rows.forEach(function (row, index) {
      var hosted = counts[index];
      if (!hosted) return;   // sede fora da faixa de anos escolhida
      var width = PIN_WIDTH;
      var height = Math.round(width * PIN_BOX / PIN_BOX_W);
      var marker = L.marker([row[0], row[1]], {
        keyboard: false,
        icon: L.divIcon({
          className: "venue-pin",
          html: PIN,
          iconSize: [width, height],
          // A PONTA da agulha é o lugar, e ela não fica no pé da caixa — o
          // viewBox tem uma folga embaixo para o traço não sair cortado. Ancorar
          // no pé deslocaria toda sede alguns pixels para o norte.
          iconAnchor: [width / 2, height * PIN_TIP],
          tooltipAnchor: [0, -height * PIN_TIP]
        })
      });
      marker.bindTooltip(
        "<b>" + row[5] + "</b>" +
        // O país da sede é o mesmo rótulo do mapa; a cidade e o estádio são
        // nomes próprios e ficam como estão.
        tipLine(row[6] + " · " + pt(row[7])) +
        tipLine(NUM.format(hosted) + (hosted === 1 ? " partida" : " partidas") +
                (row[3] === row[4] ? " em " + row[3] : " · " + row[3] + "–" + row[4])),
        { className: "atlas-tip", direction: "top" });
      venueLayer.addLayer(marker);
    });
    venueLayer.addTo(map);
  }

  // ------------------------------------------------------------ estado na URL

  /* Toda a visão cabe na URL — e é isso que torna o mapa compartilhável.
   *
   * Sem isso, "olha o Brasil contra a Suécia entre 1958 e 1970" é um conjunto de
   * instruções para a pessoa executar à mão. Com isso, é um link. Também é o que
   * faz o botão voltar do navegador significar alguma coisa numa página que não
   * troca de página nunca.
   *
   * Só o que difere do padrão entra na URL: uma visão inicial devolve `#` limpo,
   * em vez de um parágrafo de parâmetros redundantes. */
  function serialize() {
    var parts = [];
    if (state.metric !== "goals") parts.push("m=" + state.metric);
    if (state.team) parts.push("t=" + encodeURIComponent(state.team));
    if (state.versus) parts.push("v=" + encodeURIComponent(state.versus));
    if (state.mode === "rate") parts.push("r=1");
    // Uma edição aberta JÁ é a faixa de anos — `copa=1970` e `y=1970-1970` são a
    // mesma coisa dita duas vezes, e o link fica dizendo o dobro do que precisa.
    var implied = state.edition !== null &&
                  state.from === state.edition && state.to === state.edition;
    if (!implied && (state.from !== 0 || state.to !== TIMELINE.years.length - 1)) {
      parts.push("y=" + TIMELINE.years[state.from] + "-" + TIMELINE.years[state.to]);
    }
    if (state.venues) parts.push("sedes=1");
    // A edição como destino: `copa=1` é a lista, `copa=1970` é a Copa de 1970.
    // O ano cru e não o índice — um índice mudaria de dono se uma edição fosse
    // acrescentada ao dado, e "1970" é o que a pessoa escreveria na mão.
    if (state.edition !== null) parts.push("copa=" + TIMELINE.years[state.edition]);
    else if (state.view === "editions") parts.push("copa=1");
    if (state.view === "teams") parts.push("selecoes=1");
    if (state.view === "duels") parts.push("confrontos=1");
    if (state.view === "matches") {
      parts.push("jogos=" + (state.opponent ? encodeURIComponent(state.opponent) : "1"));
    }
    // O link de um jogador aponta para o `player_id`, não para o nome nem para
    // a posição na lista: por nome, `art=Ronaldo` seria ambíguo justamente no
    // caso que a identidade existe para separar; por posição, o link passaria a
    // abrir outra pessoa se o dado fosse regerado com um artilheiro a mais.
    if (state.player !== null) parts.push("art=" + encodeURIComponent(GOALS.player_ids[state.player]));
    else if (state.view === "scorers") parts.push("art=1");
    return parts.join("&");
  }

  /* `player_id` → índice, montado no primeiro uso. Só a URL precisa dele; o
   * resto do arquivo já trabalha com o índice. */
  var playerByID = null;

  function playerIndex(id) {
    if (!playerByID) {
      playerByID = {};
      GOALS.player_ids.forEach(function (value, index) { playerByID[value] = index; });
    }
    return playerByID.hasOwnProperty(id) ? playerByID[id] : -1;
  }

  var writingHash = false;

  function syncURL() {
    var hash = serialize();
    var target = hash ? "#" + hash : window.location.pathname + window.location.search;
    writingHash = true;
    // `replaceState` e não `pushState`: cada passo do slider viraria uma entrada
    // no histórico, e voltar exigiria dezenas de cliques para desfazer um gesto.
    window.history.replaceState(null, "", target);
    writingHash = false;
  }

  function applyURL() {
    var raw = window.location.hash.replace(/^#/, "");
    var params = {};
    raw.split("&").forEach(function (pair) {
      var bits = pair.split("=");
      if (bits[0]) params[bits[0]] = decodeURIComponent(bits.slice(1).join("=") || "");
    });

    var known = {};
    TIMELINE.teams.forEach(function (name) { known[name] = true; });

    /* A URL descreve o estado inteiro, então aplicá-la é **restaurar**, não
     * mesclar. Zerar antes é o que faz um parâmetro *ausente* significar
     * alguma coisa: sem isso, voltar de `#t=Brazil&jogos=Sweden` para
     * `#t=Brazil` deixava o detalhamento aberto, porque "sem `jogos`" não
     * desligava nada — o botão voltar do navegador ficava preso na tela. */
    state.team = null;
    state.versus = null;
    state.view = null;
    state.opponent = null;
    state.player = null;
    state.edition = null;

    state.metric = params.m && metricDef(params.m).key === params.m ? params.m : "goals";
    if (params.t && known[params.t]) state.team = params.t;
    if (params.v && known[params.v] && params.v !== state.team) state.versus = params.v;
    state.mode = params.r === "1" ? "rate" : "total";
    state.venues = params.sedes === "1";

    if (params.y) {
      var edges = params.y.split("-").map(Number);
      var from = TIMELINE.years.indexOf(edges[0]);
      var to = TIMELINE.years.indexOf(edges[1]);
      // Anos que não são edições (2020, digamos) são ignorados em vez de
      // aproximados: aproximar mostraria um recorte que ninguém pediu.
      if (from >= 0 && to >= 0 && from <= to) { state.from = from; state.to = to; }
    }
    if (params.jogos && state.team) {
      state.view = "matches";
      state.opponent = params.jogos !== "1" && known[params.jogos] ? params.jogos : null;
    }
    if (params.art === "1") {
      state.view = "scorers";
    } else if (params.art) {
      var who = playerIndex(params.art);
      // Um id que não existe mais é ignorado, como um ano que não é edição: a
      // página abre no que sobrou do link em vez de numa tela vazia.
      if (who >= 0) {
        state.player = who;
        // Sem seleção escolhida, a lista de artilheiros é a casa do jogador —
        // é para lá que o "voltar" da página dele leva.
        if (!state.team) state.view = "scorers";
      }
    }
    // A faixa de anos volta ao total quando a URL não a menciona, pelo mesmo
    // motivo de tudo o mais aqui: ausência é informação.
    if (!params.y) { state.from = 0; state.to = TIMELINE.years.length - 1; }

    /* A Copa vem DEPOIS da faixa de anos porque ela manda nela: abrir a Copa de
     * 1970 é olhar só 1970, e o mapa, a legenda e o ranking atrás do painel
     * passam a falar dessa edição. Um `y=` escrito junto na mão perde para o
     * `copa=`, o que deixa o resultado previsível em vez de depender da ordem
     * em que os parâmetros foram digitados. */
    // Os dois índices que não dependem de mais nada: a lista de seleções e a de
    // confrontos. Ficam antes da Copa porque `copa=` também mexe na faixa de
    // anos, e o último a falar sobre a mesma coisa é quem manda.
    if (params.selecoes === "1") state.view = "teams";
    if (params.confrontos === "1") state.view = "duels";

    if (params.copa === "1") {
      state.view = "editions";
    } else if (params.copa) {
      var edicao = TIMELINE.years.indexOf(Number(params.copa));
      // Um ano que não é edição (2020) é ignorado, como um `player_id` que não
      // existe mais: a página abre no que sobrou do link, não numa tela vazia.
      if (edicao >= 0) {
        state.edition = edicao;
        state.from = edicao;
        state.to = edicao;
      }
    }
    return true;
  }

  // ---------------------------------------------------------------- legenda

  /* Valores "redondos" dentro de um intervalo, para marcar a barra da legenda.
   * Sem isso as marcas cairiam em 61,75 ou 0,3625 — números que ninguém procura. */
  function niceTicks(max, count) {
    if (!(max > 0)) return [0];
    var rough = max / count;
    var magnitude = Math.pow(10, Math.floor(Math.log(rough) / Math.LN10));
    var step = magnitude;
    [2, 5, 10].forEach(function (factor) {
      if (step < rough) step = magnitude * factor;
    });
    var ticks = [];
    for (var value = 0; value <= max + 1e-9; value += step) ticks.push(value);
    return ticks;
  }

  /* A legenda de uma escala contínua é uma barra, não uma fileira de quadrados.
   *
   * A barra é o degradê da rampa, e as marcas são posicionadas onde o valor de
   * fato cai — ou seja, em `sqrt(v/máx)`, a mesma transformação que pinta o
   * mapa. É isso que impede a raiz de virar mentira: as marcas ficam apertadas
   * do lado direito, e essa compressão visível *é* o aviso de que a escala não
   * é linear. */
  function drawScale() {
    var def = current.metric, scale = current.scale;
    var box = document.getElementById("scale");
    var title = document.getElementById("scale-title");
    var note = document.getElementById("scale-note");

    title.textContent = def.label + (state.mode === "rate" && def.rate ? " por partida" : "");

    var edge = function (v) { return format(v, def, state.mode); };
    var marks = [], gradient;

    // A raiz aperta as marcas contra a ponta direita da barra, então marcas
    // vizinhas demais viram um borrão de números sobrepostos. Guardo posição e
    // rótulo, e descarto no fim o que não couber — melhor uma marca a menos que
    // dois números empilhados.
    var placed = [];
    function mark(position, label) { placed.push([position, label]); }

    function flush() {
      placed.sort(function (a, b) { return a[0] - b[0]; });
      var last = -1;
      placed.forEach(function (entry) {
        if (entry[0] - last < 0.11) return;
        last = entry[0];
        marks.push('<span class="tick" style="left:' + (100 * entry[0]).toFixed(2) + '%">' +
                   '<i></i><em>' + entry[1] + '</em></span>');
      });
    }

    function gradientOf(stops, from, to) {
      return stops.map(function (color, index) {
        var at = from + (to - from) * (index / (stops.length - 1));
        return color + " " + (100 * at).toFixed(2) + "%";
      }).join(", ");
    }

    if (scale.kind === "diverging") {
      // Barra espelhada: o pivô fica no meio e cada braço cresce para fora, de
      // modo que −15 e +15 (ou 30% e 70%) ficam à mesma distância do centro.
      gradient = gradientOf(scale.negative.slice().reverse(), 0, 0.5) + ", " +
                 gradientOf(scale.positive, 0.5, 1);
      mark(0.5, edge(scale.pivot));
      niceTicks(scale.extent, 3).slice(1).forEach(function (value) {
        var offset = 0.5 * Math.sqrt(value / scale.extent);
        // Com pivô em zero a marca é a distância COM SINAL ("−50", "+50"): o
        // sinal é a própria leitura do saldo. Com pivô em 50% ela é o valor de
        // fato ("30,0%", "70,0%") — "−20%" ali seria um aproveitamento que não
        // existe.
        if (scale.pivot) {
          mark(0.5 - offset, edge(scale.pivot - value));
          mark(0.5 + offset, edge(scale.pivot + value));
        } else {
          mark(0.5 - offset, "−" + edge(value));
          mark(0.5 + offset, "+" + edge(value));
        }
      });
    } else {
      gradient = gradientOf(scale.stops, 0, 1);
      niceTicks(scale.max, 6).forEach(function (value) {
        mark(scale.max ? Math.sqrt(value / scale.max) : 0, edge(value));
      });
    }
    flush();

    box.innerHTML =
      '<div class="bar" style="background:linear-gradient(to right, ' + gradient + ')"></div>' +
      '<div class="ticks">' + marks.join("") + '</div>' +
      '<div class="absent-key"><i style="background:' + css("--absent") + '"></i>' +
      '<span>sem dado</span></div>';

    var messages = ["Escala contínua, com raiz quadrada — o pé da distribuição " +
                    "abre sem que nenhuma ordem se inverta. As marcas se apertam " +
                    "à direita justamente por isso."];
    if (scale.kind === "diverging") {
      messages.push("O meio da barra é " + edge(scale.pivot) +
                    ": vermelho abaixo, azul acima. Os dois polos ficam fixos mesmo com " +
                    "uma seleção escolhida — se um dos lados mudasse de cor a cada país, " +
                    "o mapa deixaria de ter lado.");
    }
    if (state.mode === "rate" && def.rate) {
      messages.push("Seleções com menos de " + TIMELINE.per_match_floor +
                    " partidas na faixa saem do mapa: a média não seria comparável.");
    }
    if (state.team) {
      // "Contornada, não pintada" concordava em gênero com a seleção — e virava
      // erro em Brasil, Japão, Catar. Sem particípio, sobra o verbo, que só
      // precisa concordar em número.
      messages.push("No mapa, " + theTeam(state.team) +
                    (plural(state.team) ? " aparecem" : " aparece") +
                    " só com contorno, sem preenchimento — ninguém joga contra si mesmo.");
    }
    if (state.swapped) {
      messages.push("“" + state.swapped + "” não existe em confronto direto; a métrica " +
                    "voltou para gols.");
    }
    note.textContent = messages.join(" ");
  }

  // ----------------------------------------------------------------- painel

  function tile(value, label) {
    return '<div class="tile"><b>' + value + '</b><span>' + label + '</span></div>';
  }

  // ---------------------------------------------------- detalhamento (partidas)

  /* Índice partida→seleção, construído uma vez no primeiro uso.
   *
   * São 1.068 partidas e 83 seleções; varrer a lista inteira a cada clique
   * funcionaria, mas o painel repinta a cada movimento do slider e isso vira
   * varredura em cima de varredura. O índice troca isso por uma leitura direta. */
  var matchIndex = null;

  function indexMatches() {
    matchIndex = {};
    MATCHES.rows.forEach(function (row, position) {
      [MATCHES.teams[row[2]], MATCHES.teams[row[3]]].forEach(function (name) {
        (matchIndex[name] = matchIndex[name] || []).push(position);
      });
    });
  }

  /* O resultado de uma partida do ponto de vista de uma seleção.
   *
   * Espelha `etl.model`: numa partida decidida nos pênaltis **não existe
   * empate** — quem passou tem vitória, quem caiu tem derrota. Tratar o tempo
   * normal como final criaria empates que não aconteceram e tiraria vitórias de
   * quem avançou. São 39 partidas em 1.068, e são justamente as mais lembradas.
   *
   * Se esta regra divergir da do Python, o detalhamento contradiz o agregado que
   * está logo acima dele na tela — por isso um teste refaz esta conta a partir
   * do `matches.json` e a compara com o `metrics.json`. */
  function resultOf(goalsFor, goalsAgainst, pensFor, pensAgainst) {
    if (goalsFor > goalsAgainst) return "W";
    if (goalsFor < goalsAgainst) return "L";
    if (pensFor === null || pensFor === undefined) return "D";
    return pensFor > pensAgainst ? "W" : "L";
  }

  /* Uma partida como ELA é, sem ponto de vista: mandante, visitante, placar,
   * fase, sede. É esta a forma que o `.placar` desenha.
   *
   * A separação existe porque uma partida agora é lida de dois lugares que
   * querem coisas diferentes. A lista de uma seleção quer o *resultado dela* —
   * V/E/D, que só existe se houver uma seleção escolhida. A tela de uma edição
   * não tem seleção nenhuma: ali a partida é um fato do torneio, e um V/E/D
   * exigiria eleger um dos dois lados como "o certo". Então a perspectiva é uma
   * camada opcional por cima (`matchesFor`), e não parte da partida. */
  function matchAt(position) {
    var row = MATCHES.rows[position], pens = row[8];
    return {
      position: position,
      year: row[0],
      stage: MATCHES.stages[row[1]],
      date: row[7],
      homeTeam: MATCHES.teams[row[2]], awayTeam: MATCHES.teams[row[3]],
      homeGoals: row[4], awayGoals: row[5],
      homePens: pens ? pens[0] : null, awayPens: pens ? pens[1] : null,
      venue: row[6] >= 0 ? MATCHES.venues[row[6]] : null,
      // Sem seleção escolhida não há resultado a declarar. `null` aqui é o que
      // faz o placar sair sem régua e sem letra, em vez de inventar um lado.
      team: null, result: null
    };
  }

  /* As partidas de uma seleção na faixa escolhida, opcionalmente contra um
   * adversário só. Devolve o mais recente primeiro. */
  function matchesFor(team, opponent, from, to) {
    if (!matchIndex) indexMatches();
    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var out = [];

    (matchIndex[team] || []).forEach(function (position) {
      var row = MATCHES.rows[position];
      if (row[0] < firstYear || row[0] > lastYear) return;

      var match = matchAt(position);
      var atHome = match.homeTeam === team;
      var other = atHome ? match.awayTeam : match.homeTeam;
      if (opponent && other !== opponent) return;

      // A camada de perspectiva: quem é "nós", quem é "eles", e o que o placar
      // significa para nós.
      match.team = team;
      match.opponent = other;
      match.home = atHome;
      match.goalsFor = atHome ? match.homeGoals : match.awayGoals;
      match.goalsAgainst = atHome ? match.awayGoals : match.homeGoals;
      match.pensFor = atHome ? match.homePens : match.awayPens;
      match.pensAgainst = atHome ? match.awayPens : match.homePens;
      match.result = resultOf(match.goalsFor, match.goalsAgainst,
                              match.pensFor, match.pensAgainst);
      out.push(match);
    });

    return out.sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; });
  }

  /* Os gols, indexados pela posição da partida — a mesma chave que o
   * `matches.json` usa. O ETL confere que as duas listas estão alinhadas. */
  var goalIndex = null;

  function goalsOfMatch(position) {
    if (!goalIndex) {
      goalIndex = {};
      GOALS.rows.forEach(function (row) {
        (goalIndex[row[0]] = goalIndex[row[0]] || []).push(row);
      });
    }
    return goalIndex[position] || [];
  }

  /* Os artilheiros de um lado da partida, agrupados por jogador.
   *
   * Agrupar importa: "Pelé 55', 90'" é uma linha e duas linhas separadas com o
   * mesmo nome parecem dois jogadores homônimos. As marcas ficam coladas no
   * minuto que as gerou, porque é o minuto que foi de pênalti — não o jogador. */
  function scorers(position, teamName) {
    var byPlayer = [], seen = {};
    goalsOfMatch(position).forEach(function (row) {
      if (MATCHES.teams[row[1]] !== teamName) return;
      var name = GOALS.players[row[2]];
      var minute = row[3] + (row[4] ? "+" + row[4] : "") + "'";
      if (row[5] === 1) minute += " (p)";
      if (row[5] === 2) minute += " (gc)";
      if (!seen[name]) { seen[name] = { name: name, minutes: [] }; byPlayer.push(seen[name]); }
      seen[name].minutes.push(minute);
    });
    return byPlayer.map(function (player) {
      return '<span class="scorer">' + player.name + " " +
             '<em>' + player.minutes.join(", ") + "</em></span>";
    }).join("");
  }

  /* Artilheiros de uma seleção na faixa escolhida.
   *
   * Gol contra fica de fora: ele é creditado à seleção que *ganhou* o gol, mas
   * quem chutou joga do outro lado. Contá-lo aqui daria a um adversário uma
   * linha na lista de artilheiros do time — o oposto do que a lista quer dizer. */
  function topScorers(team, from, to, limit) {
    // O índice é preguiçoso e `matchesFor` costuma criá-lo primeiro — mas não
    // quando a página abre já com um país na URL: aí o painel pede artilheiro
    // antes de qualquer lista de partidas existir.
    if (!matchIndex) indexMatches();

    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var tally = {}, out = [];

    (matchIndex[team] || []).forEach(function (position) {
      var row = MATCHES.rows[position];
      if (row[0] < firstYear || row[0] > lastYear) return;
      goalsOfMatch(position).forEach(function (goal) {
        if (goal[5] === 2) return;                       // gol contra
        if (MATCHES.teams[goal[1]] !== team) return;
        // Agrupado pela PESSOA, não pelo nome: dois homônimos da mesma seleção
        // (o Oscar de 1982 e o de 2014, o Júnior de 82 e o de 2002) somavam
        // numa linha só e inventavam um artilheiro que nenhum dos dois foi.
        var who = goal[2];
        if (!tally[who]) {
          tally[who] = { player: who, name: GOALS.players[who], goals: 0 };
          out.push(tally[who]);
        }
        tally[who].goals += 1;
      });
    });

    return out.sort(function (a, b) {
      return b.goals - a.goals || ORDER.compare(a.name, b.name);
    }).slice(0, limit || 8);
  }

  /* Os destaques da faixa escolhida — o que a visão global mostra no lugar dos
   * três números que ela mostrava antes ("83 seleções · 23 edições · 83 no
   * mapa"). Dois daqueles descreviam o *conjunto de dados*, não o futebol.
   *
   * Tudo aqui acompanha o slider: mudar o recorte muda quem é o artilheiro e
   * qual é a maior goleada, que é justamente o que torna o slider interessante
   * em vez de um filtro abstrato.
   *
   * Uma varredura só sobre as 1.068 partidas e outra sobre os 3.028 gols, a
   * cada repintura. São 4 mil iterações — o slider dispara isso a cada pixel
   * arrastado e nem aparece no perfil; o `matchYear` existe só para a segunda
   * varredura não ter que procurar a partida de cada gol. */
  var matchYear = null;

  function factsFor(from, to) {
    if (!matchYear) matchYear = MATCHES.rows.map(function (row) { return row[0]; });
    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var played = 0, scored = 0, rout = null;

    MATCHES.rows.forEach(function (row) {
      if (row[0] < firstYear || row[0] > lastYear) return;
      played += 1;
      scored += row[4] + row[5];
      var margin = Math.abs(row[4] - row[5]);
      var total = row[4] + row[5];
      // Desempate pela quantidade de gols: 10–1 e 9–0 têm a mesma diferença, e
      // a goleada que se lembra é a de dois dígitos.
      if (!rout || margin > rout.margin || (margin === rout.margin && total > rout.total)) {
        rout = { margin: margin, total: total, row: row };
      }
    });

    // A conta é POR PESSOA, e a chave é o índice do jogador — que o ETL montou
    // a partir do `player_id`, não do nome. Enquanto ela foi o nome, o Ronaldo
    // brasileiro (15 gols) somava com um Ronaldo português de 2026 (3) e esta
    // linha anunciava um artilheiro de 18 que nunca existiu, na frente do
    // Klose, que tem o recorde de verdade com 16.
    var tally = {}, best = null;
    GOALS.rows.forEach(function (goal) {
      if (goal[5] === 2) return;                       // gol contra não é do artilheiro
      var year = matchYear[goal[0]];
      if (year < firstYear || year > lastYear) return;
      var who = goal[2];
      tally[who] = (tally[who] || 0) + 1;
      // Empate resolvido pelo rótulo, para o destaque não trocar de dono a cada
      // repintura só porque a ordem de varredura mudou.
      if (!best || tally[who] > tally[best] ||
          (tally[who] === tally[best] && GOALS.players[who] < GOALS.players[best])) {
        best = who;
      }
    });

    return {
      matches: played,
      goals: scored,
      rout: rout,
      scorer: best,
      scorerGoals: best === null ? 0 : tally[best]
    };
  }

  /* A seleção de um artilheiro — a dele, não a creditada pelo gol.
   *
   * Num gol contra a linha credita a seleção ADVERSÁRIA de quem chutou, porque
   * é assim que o placar fecha. Tirar o time do artilheiro dali poria o autor
   * de um gol contra jogando pelo time que levou o gol; por isso o ETL manda
   * `player_teams`, index a index com `players`. */
  function teamOfPlayer(who) {
    var index = GOALS.player_teams[who];
    return index >= 0 ? MATCHES.teams[index] : null;
  }

  /* A tabela de artilheiros da faixa. Uma linha por pessoa, com a seleção, os
   * gols, quantos foram de pênalti e em quantas Copas ela marcou. */
  function scorerTable(from, to) {
    if (!matchYear) matchYear = MATCHES.rows.map(function (row) { return row[0]; });
    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var byPlayer = {}, out = [];

    GOALS.rows.forEach(function (goal) {
      if (goal[5] === 2) return;
      var year = matchYear[goal[0]];
      if (year < firstYear || year > lastYear) return;
      var who = goal[2];
      if (!byPlayer[who]) {
        byPlayer[who] = { player: who, name: GOALS.players[who], team: teamOfPlayer(who),
                          goals: 0, pens: 0, years: {} };
        out.push(byPlayer[who]);
      }
      byPlayer[who].goals += 1;
      if (goal[5] === 1) byPlayer[who].pens += 1;
      byPlayer[who].years[year] = 1;
    });

    out.forEach(function (entry) { entry.cups = Object.keys(entry.years).length; });
    return out.sort(function (a, b) {
      return b.goals - a.goals || ORDER.compare(a.name, b.name);
    });
  }

  /* Os gols de um jogador, do mais recente para o mais antigo, com a partida
   * em que cada um saiu. */
  function goalsOfPlayer(who, from, to) {
    if (!matchYear) matchYear = MATCHES.rows.map(function (row) { return row[0]; });
    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var out = [];

    GOALS.rows.forEach(function (goal) {
      if (goal[2] !== who || goal[5] === 2) return;
      var year = matchYear[goal[0]];
      if (year < firstYear || year > lastYear) return;
      var match = MATCHES.rows[goal[0]];
      out.push({
        year: year,
        stage: MATCHES.stages[match[1]],
        date: match[7],
        home: MATCHES.teams[match[2]], away: MATCHES.teams[match[3]],
        homeGoals: match[4], awayGoals: match[5],
        minute: goal[3] + (goal[4] ? "+" + goal[4] : "") + "'",
        penalty: goal[5] === 1
      });
    });

    return out.sort(function (a, b) {
      return a.date < b.date ? 1 : a.date > b.date ? -1 : 0;
    });
  }

  var STAGE_SHORT = {
    "group stage": "Grupos", "second group stage": "2ª fase de grupos",
    "round of 32": "32-avos", "round of 16": "Oitavas", "quarter-finals": "Quartas",
    "semi-finals": "Semi", "third-place match": "3º lugar",
    "final": "Final", "final round": "Quadrangular"
  };

  /* As fases que ganham a tarja dourada. Uma final não pesa o mesmo que um jogo
   * de grupo, e num bloco de rótulos cinza as duas pesam igual. */
  var STAGE_GOLD = { "final": 1, "final round": 1 };

  /* A ordem em que um torneio acontece.
   *
   * `MATCHES.stages` chega em ordem ALFABÉTICA — é a lista de valores distintos
   * que o ETL gravou, não um calendário. Ordenar por ela poria a final antes da
   * fase de grupos e as quartas depois das semis. Esta lista é o calendário, e
   * ela vale para as 23 edições porque nenhuma delas repete uma fase.
   *
   * O "quadrangular" de 1950 fica no fim de propósito: naquela edição ele veio
   * DEPOIS da fase de grupos, e foi ele que decidiu o título. */
  var STAGE_ORDER = ["group stage", "second group stage", "round of 32", "round of 16",
                     "quarter-finals", "semi-finals", "third-place match", "final",
                     "final round"];

  // ------------------------------------------------------- a Copa como destino

  /* O slider recorta; ele nunca abre. Estas funções são o que faltava para uma
   * edição ser um LUGAR — com sede, campeão, vice, artilheiro e as partidas na
   * ordem em que aconteceram — e não só um filtro de anos.
   *
   * Tudo aqui sai do que já está no navegador: `matches.json` tem ano, fase,
   * placar e sede; `timeline.json` tem os títulos e quem recebeu cada edição;
   * `goals.json` tem o gol com identidade de pessoa. Nada de novo no ETL. */

  /* As partidas de uma edição, em ordem cronológica.
   *
   * Guardadas depois da primeira montagem: a lista das 23 Copas pede as 23 de
   * uma vez, e ela é redesenhada a cada movimento do slider. Sem a memória
   * seriam 1.068 objetos e 23 ordenações por quadro arrastado, para um dado que
   * não muda nunca — as partidas de 1970 são as mesmas em toda repintura.
   *
   * O desempate da ordenação é a posição no arquivo, e não a ordem em que o
   * `sort` calhar de deixar: numa mesma data há até oito jogos, e sem critério
   * estável dois desenhos da mesma tela sairiam em ordens diferentes. */
  var yearIndex = null, yearCache = {};

  function matchesOfYear(year) {
    if (yearCache[year]) return yearCache[year];
    if (!yearIndex) {
      yearIndex = {};
      MATCHES.rows.forEach(function (row, position) {
        (yearIndex[row[0]] = yearIndex[row[0]] || []).push(position);
      });
    }
    yearCache[year] = (yearIndex[year] || []).map(matchAt).sort(function (a, b) {
      return a.date < b.date ? -1 : a.date > b.date ? 1 : a.position - b.position;
    });
    return yearCache[year];
  }

  /* Quem recebeu a edição. São 26 linhas para 23 edições porque duas foram
   * divididas: 2002 entre Coreia do Sul e Japão, 2026 entre Estados Unidos,
   * México e Canadá. Quem recebeu mais partidas vem primeiro — em 2026 os
   * Estados Unidos receberam 78 das 104, e listar em ordem alfabética poria o
   * Canadá (13) na frente como se fosse a sede principal. */
  function hostsOf(index) {
    var out = [];
    TIMELINE.hosted.forEach(function (row) {
      if (row[0] === index) out.push({ team: TIMELINE.teams[row[1]], matches: row[2] });
    });
    return out.sort(function (a, b) {
      return b.matches - a.matches || byName(a.team, b.team);
    });
  }

  /* A classificação de um grupo, a partir das partidas dele.
   *
   * Existe por uma edição só: **1950 não teve final**. O título saiu de um
   * quadrangular de seis jogos, e o vice de lá não é "quem perdeu a decisão" —
   * é o segundo colocado de uma tabela. A regra de pontos é a de 1950, DUAS por
   * vitória; com três o campeão e o vice seriam os mesmos, mas o dado é de 1950
   * e a conta também deve ser.
   *
   * O desempate é saldo e depois gols marcados. Ele não decide nada aqui — o
   * Uruguai lidera por ponto — e existe para a tabela nunca sair numa ordem que
   * dependa de como as partidas foram varridas. */
  function standingsOf(list) {
    var table = {}, out = [];
    function slot(team) {
      if (!table[team]) {
        table[team] = { team: team, points: 0, wins: 0, draws: 0, losses: 0,
                        goals: 0, conceded: 0 };
        out.push(table[team]);
      }
      return table[team];
    }
    list.forEach(function (match) {
      var home = slot(match.homeTeam), away = slot(match.awayTeam);
      home.goals += match.homeGoals; home.conceded += match.awayGoals;
      away.goals += match.awayGoals; away.conceded += match.homeGoals;
      if (match.homeGoals > match.awayGoals) { home.points += 2; home.wins++; away.losses++; }
      else if (match.homeGoals < match.awayGoals) { away.points += 2; away.wins++; home.losses++; }
      else { home.points++; away.points++; home.draws++; away.draws++; }
    });
    return out.sort(function (a, b) {
      return b.points - a.points ||
             (b.goals - b.conceded) - (a.goals - a.conceded) ||
             b.goals - a.goals || byName(a.team, b.team);
    });
  }

  /* Campeão e vice de uma edição.
   *
   * O CAMPEÃO vem de `TIMELINE.titles`, que é a autoridade do ETL e a mesma
   * fonte que pinta a métrica "títulos" no mapa — assim as duas telas nunca
   * podem discordar. O VICE é derivado, e o caminho depende da edição:
   *
   *   com final     o outro lado da decisão. Não "quem perdeu": o lado que não
   *                 é o campeão. Se um dia o dado se contradissesse, a tela
   *                 mostraria a contradição em vez de escondê-la atrás de um
   *                 vencedor recalculado aqui.
   *   sem final     1950, e só ela: o segundo da tabela do quadrangular.
   *
   * As 39 decisões por pênalti não precisam de tratamento — o campeão não sai
   * daqui, e o vice é o outro lado seja qual for o caminho do desempate. */
  function podiumOf(index, list) {
    var year = TIMELINE.years[index], champion = null, i;
    for (i = 0; i < TIMELINE.titles.length; i++) {
      if (TIMELINE.titles[i][0] === index) champion = TIMELINE.teams[TIMELINE.titles[i][1]];
    }

    var decider = null;
    for (i = 0; i < list.length; i++) if (list[i].stage === "final") decider = list[i];

    if (decider) {
      var runner = decider.homeTeam === champion ? decider.awayTeam : decider.homeTeam;
      return { year: year, champion: champion, runner: runner, decider: decider, group: null };
    }

    var round = list.filter(function (match) { return match.stage === "final round"; });
    if (!round.length) return { year: year, champion: champion, runner: null, decider: null, group: null };
    var table = standingsOf(round);
    var second = null;
    for (i = 0; i < table.length; i++) if (table[i].team !== champion) { second = table[i].team; break; }
    return { year: year, champion: champion, runner: second, decider: null, group: table };
  }

  /* Os artilheiros de uma edição, por PESSOA e não por nome — a mesma regra do
   * resto da página. Gol contra fica de fora: ele é creditado à seleção que o
   * ganhou, e quem chutou joga do outro lado.
   *
   * Empate no topo é o caso comum, não a exceção: 1962 teve SEIS jogadores com
   * 4 gols, 2010 teve quatro com 5 e 1994 teve dois com 6. Por isso a função
   * devolve a lista ordenada e quem chama decide quantos mostrar — eleger "o
   * artilheiro" por ordem de varredura calaria cinco pessoas em 1962. */
  function editionScorers(list) {
    var tally = {}, out = [];
    list.forEach(function (match) {
      goalsOfMatch(match.position).forEach(function (goal) {
        if (goal[5] === 2) return;
        var who = goal[2];
        if (!tally[who]) {
          tally[who] = { player: who, name: GOALS.players[who], team: teamOfPlayer(who),
                         goals: 0, pens: 0 };
          out.push(tally[who]);
        }
        tally[who].goals += 1;
        if (goal[5] === 1) tally[who].pens += 1;
      });
    });
    return out.sort(function (a, b) {
      return b.goals - a.goals || ORDER.compare(a.name, b.name);
    });
  }

  /* Gols, partidas e quantos estádios a edição usou. O total de gols sai do
   * PLACAR e não da contagem de artilheiros: são iguais nas 23 edições (o ETL
   * confere), e o placar é quem manda — um gol sem autor registrado ainda é um
   * gol no placar. */
  function editionTotals(list) {
    var goals = 0, venues = {};
    list.forEach(function (match) {
      goals += match.homeGoals + match.awayGoals;
      if (match.venue) venues[match.venue.name + "|" + match.venue.city] = 1;
    });
    return { matches: list.length, goals: goals, venues: Object.keys(venues).length };
  }

  // ------------------------------------------------------- os confrontos

  /* Todos os confrontos da faixa, do mais repetido para o menos.
   *
   * O confronto direto já existia — mas só depois de escolher uma seleção, e
   * sempre a partir dela. Não havia como perguntar "quais são os clássicos da
   * Copa?", que é uma pergunta sobre o conjunto e não sobre um time.
   *
   * Cada partida está DUAS VEZES em `TIMELINE.rows`, uma por lado. Contar as
   * duas dobraria tudo, então o par é contado uma vez só, pelo lado de índice
   * menor — e é o mesmo teste que descarta a Alemanha × Alemanha de 1974, a
   * única partida em que os dois lados carregam o mesmo rótulo por decisão
   * editorial do projeto. São 1.067 das 1.068 partidas; a que falta é essa, e
   * ela não é um confronto entre duas seleções. */
  function duelIndex(from, to) {
    var teams = TIMELINE.teams, pairs = {}, out = [];
    for (var i = 0; i < TIMELINE.rows.length; i++) {
      var row = TIMELINE.rows[i];
      if (row[0] < from || row[0] > to) continue;
      if (row[1] >= row[2]) continue;          // o outro lado, ou a de 1974
      var key = row[1] + ":" + row[2];
      if (!pairs[key]) {
        pairs[key] = { a: teams[row[1]], b: teams[row[2]], matches: 0,
                       wins: 0, draws: 0, losses: 0, goals: 0, conceded: 0,
                       first: TIMELINE.years[row[0]], last: TIMELINE.years[row[0]] };
        out.push(pairs[key]);
      }
      var duel = pairs[key];
      duel.matches += 1;
      duel.goals += row[3];
      duel.conceded += row[4];
      duel[row[5] === 0 ? "wins" : row[5] === 1 ? "draws" : "losses"] += 1;
      var year = TIMELINE.years[row[0]];
      if (year < duel.first) duel.first = year;
      if (year > duel.last) duel.last = year;
    }
    return out.sort(function (x, y) {
      // Desempate pelo total de gols e depois pelo nome: sem ele, dois
      // confrontos de 5 partidas trocariam de lugar entre repinturas.
      return y.matches - x.matches ||
             (y.goals + y.conceded) - (x.goals + x.conceded) ||
             byName(x.a, y.a) || byName(x.b, y.b);
    });
  }

  /* As partidas agrupadas por fase, na ordem do calendário. Uma fase que a
   * edição não teve simplesmente não aparece — 1930 não teve quartas, 1950 não
   * teve final, 2026 é a primeira com 32-avos. */
  function stageGroups(list) {
    var byStage = {}, out = [];
    list.forEach(function (match) {
      (byStage[match.stage] = byStage[match.stage] || []).push(match);
    });
    STAGE_ORDER.forEach(function (stage) {
      if (byStage[stage]) out.push({ stage: stage, list: byStage[stage] });
    });
    // Uma fase que o dado tenha e esta lista não conheça entra no fim, em vez
    // de sumir da tela sem aviso.
    Object.keys(byStage).sort().forEach(function (stage) {
      if (STAGE_ORDER.indexOf(stage) < 0) out.push({ stage: stage, list: byStage[stage] });
    });
    return out;
  }

  /* A letra do resultado, em português: V, E, D. A CHAVE continua sendo W/D/L —
   * ela vem de `resultOf`, espelha `etl.model` e nomeia as classes de CSS —, mas
   * a letra dentro do quadradinho é o que a pessoa lê, e numa página em pt-BR
   * "W" não quer dizer nada. O "D" das duas línguas significa coisas opostas
   * (draw / derrota), o que é exatamente o motivo de a tradução existir. */
  var RESULT_LETTER = { W: "V", D: "E", L: "D" };
  var RESULT_TITLE = { W: "Vitória", D: "Empate", L: "Derrota" };

  /* O placar de uma partida, no formato da cartela de transmissão.
   *
   * A ORDEM É A DA PARTIDA — mandante à esquerda, visitante à direita, sempre.
   * A versão anterior escrevia o placar do ponto de vista da seleção escolhida
   * ("4–1 vs Itália"), e isso dá dois placares diferentes para a mesma partida
   * dependendo de por onde você chegou nela: a final de 70 seria "4–1" pelo
   * Brasil e "1–4" pela Itália. O resultado (V/E/D) continua sendo o da seleção
   * escolhida, porque é a pergunta que a lista responde — ele fica na régua
   * colorida da borda E na letra, nunca só na cor.
   *
   * SEM seleção escolhida não há V/E/D: a régua e a letra somem em vez de
   * escolherem um lado. É o caso da tela de uma edição, onde a partida não é de
   * ninguém — e uma régua cinza ali seria lida como empate. */
  function placar(match) {
    var homeTeam = match.homeTeam, awayTeam = match.awayTeam;
    var homeGoals = match.homeGoals, awayGoals = match.awayGoals;
    var homePens = match.homePens, awayPens = match.awayPens;
    var sided = Boolean(match.result);

    function side(team, away) {
      // A sigla já nomeia a seleção, então uma bandeira que não carrega some em
      // vez de virar ícone quebrado — diferente da tabela, onde a bandeira é a
      // única marca da linha e o `badge()` a troca por um quadrado colorido.
      var flag = '<img class="flag" src="vendor/flags/' +
                 ((COLORS.teams[team] && COLORS.teams[team].flag) || "") +
                 '" alt="" aria-hidden="true" decoding="async"' +
                 ' onerror="this.remove()">';
      var tag = '<b class="sigla" title="' + pt(team) + '">' + sigla(team) + "</b>";
      return '<span class="placar-side' + (away ? " away" : "") +
             (team === match.team ? " is-team" : "") + '">' +
             (away ? tag + flag : flag + tag) + "</span>";
    }

    var stage = STAGE_SHORT[match.stage] || match.stage;
    // O ano é a porta para a edição — de qualquer placar, em qualquer tela, se
    // chega na Copa em que aquela partida aconteceu. Dentro da própria edição
    // ele volta a ser texto: um link para a tela em que já se está não leva a
    // lugar nenhum.
    var year = state.edition !== null && TIMELINE.years[state.edition] === match.year
      ? '<span class="year">' + match.year + "</span>"
      : '<a class="year" href="#copa=' + match.year + '" title="Abrir a Copa de ' +
        match.year + '">' + match.year + "</a>";

    var meta = '<div class="placar-meta">' +
      '<span class="stage' + (STAGE_GOLD[match.stage] ? " final" : "") + '">' + stage + "</span>" +
      year +
      (match.venue ? "<span>" + match.venue.city + "</span>" : "") +
      (sided ? '<span class="res-letter" title="' + RESULT_TITLE[match.result] + '">' +
               RESULT_LETTER[match.result] + "</span>" : "") + "</div>";

    var line = '<div class="placar-line">' + side(homeTeam, false) +
      '<span class="placar-score">' + homeGoals + "<i>×</i>" + awayGoals + "</span>" +
      side(awayTeam, true) + "</div>";

    // Nos pênaltis o placar do tempo normal é empate, e sem esta linha a lista
    // mostraria um "E" ao lado de uma vitória — as 39 decisões por pênalti são
    // justamente as partidas mais lembradas do dado.
    var pens = homePens === null || homePens === undefined ? "" :
      '<i class="pens">' + homePens + " × " + awayPens + " nos pênaltis</i>";

    var homeScorers = scorers(match.position, homeTeam);
    var awayScorers = scorers(match.position, awayTeam);
    var goals = homeScorers || awayScorers ?
      '<div class="placar-goals"><span>' + homeScorers + "</span>" +
      '<span class="against">' + awayScorers + "</span></div>" : "";

    return '<div class="placar ' + (sided ? "res-" + match.result : "neutro") + '">' +
           meta + line + pens + goals + "</div>";
  }

  function matchRows(list) {
    if (!list.length) return '<p class="empty">Nenhuma partida nesta faixa.</p>';
    return '<div class="matches">' + list.map(placar).join("") + "</div>";
  }

  /* Resumo V–E–D de uma lista de partidas, para o cabeçalho do detalhamento. */
  function tally(list) {
    var wins = 0, draws = 0, losses = 0, forGoals = 0, against = 0;
    list.forEach(function (match) {
      if (match.result === "W") wins++;
      else if (match.result === "D") draws++;
      else losses++;
      forGoals += match.goalsFor;
      against += match.goalsAgainst;
    });
    return { wins: wins, draws: draws, losses: losses, goals: forGoals, conceded: against };
  }

  /* Duas seleções lado a lado.
   *
   * O confronto direto já existia no mapa; o que faltava era comparar quem nunca
   * se enfrentou — Brasil e Holanda têm história, Brasil e Japão quase não têm, e
   * as duas perguntas são legítimas. Por isso a tabela tem duas partes: as
   * carreiras separadas (que sempre existem) e o histórico entre elas (que pode
   * estar vazio, e o painel diz isso em vez de mostrar zeros).
   *
   * O vencedor de cada linha recebe destaque. "Vencedor" não é sempre o maior:
   * em gols sofridos, menos é melhor — daí a tabela declarar a direção de cada
   * linha em vez de assumir. */
  function comparePanel(span) {
    var totals = aggregate(state.from, state.to);
    var left = totals[state.team], right = totals[state.versus];

    if (!left || !right) {
      var quem = pt(!left ? state.team : state.versus);
      return '<div class="sub">' + span + "</div><h2>" + pt(state.team) + " × " + pt(state.versus) +
             '</h2><p class="empty">' + quem +
             " não disputou nenhuma partida nesta faixa de edições.</p>";
    }

    var lines = [
      ["Partidas", "matches_played", 1], ["Vitórias", "wins", 1],
      ["Empates", "draws", 0], ["Derrotas", "losses", -1],
      ["Gols", "goals", 1], ["Gols sofridos", "conceded", -1],
      ["Saldo", "goal_difference", 1], ["Títulos", "titles", 1],
      ["Participações", "participations", 1], ["Partidas recebidas", "matches_received", 1]
    ];

    // O cabeçalho repete as duas seleções em sigla, uma por coluna: sem ele a
    // tabela é uma pilha de pares de números e a pessoa tem que voltar ao
    // título toda vez para lembrar qual coluna é de quem.
    var html = '<div class="sub">' + span + "</div>" +
      "<h2>" + badge(state.team, null) + pt(state.team) + " <span class='vs'>×</span> " +
      badge(state.versus, null) + pt(state.versus) + "</h2>" +
      '<table class="compare"><thead><tr>' +
        "<th>" + badge(state.team, null) + sigla(state.team) + "</th>" +
        '<th><span class="sr-only">Métrica</span></th>' +
        "<th>" + badge(state.versus, null) + sigla(state.versus) + "</th>" +
      "</tr></thead><tbody>";

    lines.forEach(function (line) {
      var a = left[line[1]], b = right[line[1]], direction = line[2];
      var better = direction === 0 || a === b ? 0 : (a > b ? 1 : -1) * direction;
      html += "<tr>" +
        '<td class="' + (better > 0 ? "win" : "") + '">' + NUM.format(a) + "</td>" +
        '<th scope="row">' + line[0] + "</th>" +
        '<td class="' + (better < 0 ? "win" : "") + '">' + NUM.format(b) + "</td></tr>";
    });

    var aprovA = left.matches_played ? 100 * left.wins / left.matches_played : 0;
    var aprovB = right.matches_played ? 100 * right.wins / right.matches_played : 0;
    html += "<tr>" +
      '<td class="' + (aprovA > aprovB ? "win" : "") + '">' + PCT.format(aprovA) + "%</td>" +
      '<th scope="row">Aproveitamento</th>' +
      '<td class="' + (aprovB > aprovA ? "win" : "") + '">' + PCT.format(aprovB) + "%</td></tr>" +
      "</tbody></table>";

    var duels = matchesFor(state.team, state.versus, state.from, state.to);
    html += '<div><div class="sub">Entre as duas · ' + duels.length +
            (duels.length === 1 ? " partida" : " partidas") + "</div>";
    if (duels.length) {
      var sums = tally(duels);
      html += '<p class="muted">' + pt(state.team) + " " + sums.wins + "–" + sums.draws + "–" +
              sums.losses + " " + pt(state.versus) + " · " + sums.goals + "–" + sums.conceded +
              " em gols.</p>" + matchRows(duels);
    } else {
      html += '<p class="empty">Nunca se enfrentaram em Copas do Mundo.</p>';
    }
    return html + "</div>";
  }

  /* A tabela de artilheiros da faixa.
   *
   * O jogador só existia escondido dentro do painel de uma seleção, cortado em
   * oito nomes. São 1.624 pessoas e 3.028 gols no navegador; esta é a tela que
   * trata jogador como entidade em vez de nota de rodapé.
   *
   * O corte em 60 linhas não é preguiça: passa disso e a lista vira listagem
   * telefônica — o 60º da faixa completa tem 5 gols, e abaixo disso a ordem é
   * quase alfabética. Quem procura alguém específico chega pela seleção. */
  function scorersPanel(span) {
    var table = scorerTable(state.from, state.to);
    if (!table.length) {
      return '<div class="sub">' + span + '</div><h2>Artilheiros</h2>' +
             '<p class="empty">Nenhum gol nesta faixa de edições.</p>';
    }

    var goals = 0, pens = 0;
    table.forEach(function (entry) { goals += entry.goals; pens += entry.pens; });

    var html = '<div class="sub">' + span + '</div><h2>Artilheiros</h2>' +
      '<div class="tiles">' +
        tile(NUM.format(goals), "Gols") +
        tile(NUM.format(table.length), "Artilheiros") +
        tile(NUM.format(pens), "De pênalti") +
      "</div>" +
      '<div><div class="sub">Ranking · gols em Copas</div>' +
      '<div class="h2h-scroll"><table class="rank"><thead><tr><th>#</th><th>Jogador</th>' +
      "<th>Seleção</th><th>Gols</th></tr></thead><tbody>";

    table.slice(0, 60).forEach(function (entry, index) {
      html += '<tr class="drill" data-player="' + entry.player + '" tabindex="0">' +
        '<td class="pos">' + (index + 1) + "</td>" +
        "<td>" + entry.name + "</td>" +
        "<td>" + (entry.team ? badge(entry.team, null) + sigla(entry.team) : "—") + "</td>" +
        "<td>" + NUM.format(entry.goals) + "</td></tr>";
    });

    html += "</tbody></table></div>" +
      '<p class="hint"><b>' + (narrow() ? "Toque" : "Clique") +
      " num jogador</b> para ver os gols dele, um a um.</p></div>";

    // Gol contra não entra em artilharia — ele é creditado a quem ganhou o gol,
    // e quem chutou joga do outro lado. Dizer isso evita a conta não fechar aos
    // olhos de quem somar a coluna e comparar com o total de gols da faixa.
    html += '<p class="muted">Gols contra ficam de fora: o gol conta para a ' +
      "seleção que o ganhou, e quem chutou joga do outro lado.</p>";
    return html;
  }

  /* A página de um jogador: os gols dele, agrupados por edição.
   *
   * Agrupar por Copa e não numa lista corrida é o que transforma dezoito linhas
   * numa carreira — "2002: 8 gols" é a frase que alguém repete, e ela não
   * aparece numa lista plana.
   *
   * É A CARREIRA INTEIRA, e não o recorte do slider. Esta é a única tela da
   * página que ignora a faixa de anos, e o motivo é o que ela é: as outras
   * respondem "o que aconteceu neste recorte" — o mapa, o ranking, a edição —,
   * e uma pessoa não é um recorte. Chegar no Klose pela tabela de 2002 e ver
   * "5 gols" descreve 2002 corretamente e descreve o Klose errado; o recorde
   * dele são 16, em quatro Copas, e é isso que a página de uma pessoa deve
   * dizer. A faixa continua valendo para todo o resto da tela, e a linha
   * abaixo do título diz isso quando as duas discordam. */
  function playerPanel() {
    var who = state.player;
    var name = GOALS.players[who];
    var team = teamOfPlayer(who);
    var last = TIMELINE.years.length - 1;
    var list = goalsOfPlayer(who, 0, last);

    var pens = 0, byYear = {}, years = [];
    list.forEach(function (goal) {
      if (goal.penalty) pens += 1;
      if (!byYear[goal.year]) { byYear[goal.year] = []; years.push(goal.year); }
      byYear[goal.year].push(goal);
    });

    // `goalsOfPlayer` devolve do mais recente para o mais antigo, então a
    // carreira vai do último ano da lista até o primeiro.
    var carreira = years.length
      ? (years[years.length - 1] === years[0] ? String(years[0])
                                              : years[years.length - 1] + "–" + years[0])
      : "";

    var head = '<div class="sub">' + carreira + "</div>" +
      '<button class="back" type="button" data-back="player">← voltar</button>' +
      "<h2>" + (team ? badge(team, null) : "") + name +
      (team ? '<span class="sigla-tag">' + sigla(team) + "</span>" : "") + "</h2>";

    if (!list.length) {
      // Não deve acontecer: quem está em `GOALS.players` marcou pelo menos um
      // gol. Fica como rede, porque uma tela em branco não explica nada.
      return head + '<p class="empty">Nenhum gol registrado.</p>';
    }

    var html = head + '<div class="tiles">' +
      tile(NUM.format(list.length), "Gols") +
      tile(NUM.format(years.length), years.length === 1 ? "Copa" : "Copas") +
      tile(NUM.format(pens), "De pênalti") +
      "</div>";

    /* O aviso só aparece quando as duas leituras discordam de fato — ou seja,
     * quando o recorte no ar deixaria alguma Copa dele de fora. Sem ele, quem
     * chega da tabela de artilheiros de 1958 vê 13 numa tela e 16 na outra e
     * não tem como saber qual das duas está certa: as duas estão. */
    var fora = years.filter(function (year) {
      var index = TIMELINE.years.indexOf(year);
      return index < state.from || index > state.to;
    });
    if (fora.length) {
      html += '<p class="muted">Carreira inteira, fora do recorte de <b>' +
        TIMELINE.years[state.from] + "–" + TIMELINE.years[state.to] +
        "</b> que vale para o resto da tela: uma pessoa não é uma faixa de anos. " +
        (fora.length === 1 ? "A Copa de " + fora[0] + " está aqui e não no mapa."
                           : NUM.format(fora.length) +
                             " das Copas dele estão aqui e não no mapa.") + "</p>";
    }

    years.forEach(function (year) {
      var goals = byYear[year];
      html += '<div><div class="sub">' + year + " · " + goals.length +
        (goals.length === 1 ? " gol" : " gols") + '</div><div class="goal-list">';
      goals.forEach(function (goal) {
        var stage = STAGE_SHORT[goal.stage] || goal.stage;
        html += '<div class="goal-row">' +
          '<span class="stage' + (STAGE_GOLD[goal.stage] ? " final" : "") + '">' + stage + "</span>" +
          '<span class="goal-match">' + sigla(goal.home) + " " + goal.homeGoals + " × " +
          goal.awayGoals + " " + sigla(goal.away) + "</span>" +
          "<b>" + goal.minute + (goal.penalty ? " <i>p</i>" : "") + "</b></div>";
      });
      html += "</div></div>";
    });
    return html;
  }

  /* Copa a Copa: as edições da faixa, cada uma um link.
   *
   * É a porta que faltava. O slider recorta o mapa por ano, mas recortar não é
   * abrir — não havia jeito de dizer "quero a Copa de 1970" e receber a Copa de
   * 1970. Esta lista existe para isso, e ela respeita o slider como todo o
   * resto: com "só o século XXI" no ar, são as sete edições desse recorte.
   *
   * Cada linha é um `<a href="#copa=…">` de verdade, e não uma linha com
   * ouvinte: a URL já descreve o estado inteiro, então o link entra no
   * histórico, funciona com o botão voltar e pode ser copiado — o mesmo motivo
   * das tarjas de pergunta pronta da abertura. */
  function editionsPanel(span) {
    var html = '<div class="sub">' + span + '</div><h2>Copa a Copa</h2>';
    var count = state.to - state.from + 1;

    html += '<p class="muted">' + NUM.format(count) +
      (count === 1 ? " edição neste recorte." : " edições neste recorte.") +
      " Abrir uma leva o mapa até a sede, com os alfinetes dos estádios daquele ano.</p>";

    html += '<div class="copas"><div class="copa-head"><span>Ano</span><span>Sede</span>' +
            "<span>Campeão</span></div>";

    for (var index = state.from; index <= state.to; index++) {
      var year = TIMELINE.years[index];
      var hosts = hostsOf(index);
      var pod = podiumOf(index, matchesOfYear(year));

      // Sede única: bandeira e sigla, que é como um placar nomeia um país em
      // pouco espaço. Sede dividida (2002 e 2026): só as bandeiras, porque três
      // siglas numa coluna de 8rem viram uma linha cortada no meio.
      //
      // E aí a linha precisa dizer a sede de outro jeito para quem não vê as
      // bandeiras: a `<img>` é decorativa (`alt=""`), então sem a sigla o link
      // de 2002 seria anunciado como "2002, Brasil" — a Coreia do Sul e o Japão
      // sumiriam da linha inteira. O nome por extenso entra escondido.
      var titulo = hosts.map(function (host) { return pt(host.team); }).join(" · ");
      var sede = hosts.length === 1
        ? badge(hosts[0].team, null) + '<span class="sigla-tag">' + sigla(hosts[0].team) + "</span>"
        : hosts.map(function (host) { return badge(host.team, null); }).join("") +
          '<span class="sr-only">' + titulo + "</span>";

      html += '<a class="copa" href="#copa=' + year + '">' +
        "<b>" + year + "</b>" +
        '<span class="copa-sede" title="' + titulo + '">' + sede + "</span>" +
        '<span class="copa-champ">' +
        (pod.champion ? badge(pod.champion, null) + pt(pod.champion) : "—") +
        "</span></a>";
    }
    return html + "</div>";
  }

  /* O índice das seleções: as 83, em ordem alfabética.
   *
   * Ele é DIRETÓRIO e não classificação, e a diferença é o que o justifica: a
   * página já sabe ordenar seleção por qualquer métrica — é o ranking do mapa,
   * que muda com o seletor. O que não existia era a lista completa, onde uma
   * seleção se acha pelo nome sem saber antes em que posição ela está. Quem
   * quer a ordem por títulos tem `#m=titles` a um clique.
   *
   * A ordem é a do rótulo em português, como em todo o resto: em inglês a
   * Alemanha viria antes da Argentina, e a lista é para ser lida em português. */
  function teamsPanel(span) {
    var totals = aggregate(state.from, state.to);
    var names = [];
    for (var name in totals) names.push(name);
    names.sort(byName);

    if (!names.length) {
      return '<div class="sub">' + span + '</div><h2>Seleções</h2>' +
             '<p class="empty">Nenhuma seleção jogou nesta faixa de edições.</p>';
    }

    var champions = 0, played = 0;
    names.forEach(function (team) {
      if (totals[team].titles > 0) champions += 1;
      played += totals[team].matches_played;
    });

    var html = '<div class="sub">' + span + '</div><h2>Seleções</h2>' +
      '<div class="tiles">' +
        tile(NUM.format(names.length), "Seleções") +
        tile(NUM.format(champions), champions === 1 ? "Campeã" : "Campeãs") +
        // A soma das partidas de cada seleção conta cada jogo duas vezes, uma
        // por lado. O número que interessa é o de PARTIDAS, então divide.
        tile(NUM.format(Math.round(played / 2)), "Partidas") +
      "</div>" +
      '<div><div class="sub">Todas, de A a Z</div>' +
      '<div class="h2h-scroll"><table><thead><tr><th>Seleção</th><th>Copas</th>' +
      "<th>J</th><th>Títulos</th></tr></thead><tbody>";

    names.forEach(function (team) {
      var rec = totals[team];
      html += '<tr class="drill" data-team="' + team + '" tabindex="0">' +
        "<td>" + badge(team, null) + pt(team) + "</td>" +
        "<td>" + NUM.format(rec.participations) + "</td>" +
        "<td>" + NUM.format(rec.matches_played) + "</td>" +
        // Zero título vira travessão: uma coluna com 74 zeros é uma coluna de
        // ruído, e o que ela precisa mostrar são as nove que ganharam.
        "<td>" + (rec.titles ? "<b>" + NUM.format(rec.titles) + "</b>" : "—") +
        "</td></tr>";
    });

    return html + "</tbody></table></div>" +
      '<p class="hint"><b>' + (narrow() ? "Toque" : "Clique") +
      " numa seleção</b> para pintar o mapa com os confrontos diretos dela.</p></div>";
  }

  /* O índice dos confrontos: os clássicos da Copa.
   *
   * Cada linha abre a comparação lado a lado que já existia — esta tela é o
   * índice dela. Antes, chegar em "Argentina × Alemanha" exigia saber de
   * antemão que esse confronto vale a pena e digitar os dois nomes; agora ele
   * está no topo de uma lista, com as oito partidas que o tornam o maior. */
  function duelsPanel(span) {
    var duels = duelIndex(state.from, state.to);
    if (!duels.length) {
      return '<div class="sub">' + span + '</div><h2>Confrontos</h2>' +
             '<p class="empty">Nenhuma partida nesta faixa de edições.</p>';
    }

    var once = 0;
    duels.forEach(function (duel) { if (duel.matches === 1) once += 1; });

    var html = '<div class="sub">' + span + '</div><h2>Confrontos</h2>' +
      '<div class="tiles">' +
        tile(NUM.format(duels.length), "Confrontos") +
        tile(NUM.format(duels[0].matches), "Do maior") +
        tile(NUM.format(once), "Uma vez só") +
      "</div>" +
      // O número que dá sentido à lista: a Copa é um torneio de encontros
      // únicos. Dois terços dos confrontos aconteceram uma vez e não se
      // repetiram nunca — é isso que faz os oito Argentina × Alemanha pesarem.
      '<p class="muted">' + PCT.format(100 * once / duels.length) +
      "% dos confrontos aconteceram uma vez só: em Copa, a maioria dos " +
      "encontros nunca se repete.</p>" +
      '<div><div class="sub">Os mais repetidos</div>' +
      '<div class="h2h-scroll"><table class="rank"><thead><tr><th>#</th>' +
      "<th>Confronto</th><th>J</th><th>V–E–D</th></tr></thead><tbody>";

    duels.slice(0, 40).forEach(function (duel, index) {
      html += '<tr class="drill" data-duel="' + duel.a + "|" + duel.b + '" tabindex="0">' +
        '<td class="pos">' + (index + 1) + "</td>" +
        '<td class="duel">' + badge(duel.a, null) + sigla(duel.a) +
        '<i>×</i>' + badge(duel.b, null) + sigla(duel.b) + "</td>" +
        "<td>" + NUM.format(duel.matches) + "</td>" +
        // O V–E–D é o da PRIMEIRA sigla da linha, que é a da esquerda — a
        // mesma ordem em que as duas aparecem, para não haver o que decorar.
        "<td>" + duel.wins + "–" + duel.draws + "–" + duel.losses + "</td></tr>";
    });

    return html + "</tbody></table></div>" +
      '<p class="hint"><b>' + (narrow() ? "Toque" : "Clique") +
      " num confronto</b> para ver as duas seleções lado a lado.</p></div>";
  }

  /* Uma edição inteira: sede, campeão, vice, artilheiro, totais e as partidas
   * na ordem em que o torneio aconteceu.
   *
   * O que o mapa faz enquanto esta tela está aberta é o que só ele faz — a sede
   * contornada e os alfinetes dos estádios daquele ano, e mais nada. Um gráfico
   * responde "quantos"; o mapa responde "onde", e "onde" é metade do que uma
   * Copa é. */
  function editionPanel() {
    var index = state.edition, year = TIMELINE.years[index];
    var list = matchesOfYear(year);
    var hosts = hostsOf(index);
    var pod = podiumOf(index, list);
    var totals = editionTotals(list);
    var scorers = editionScorers(list);

    var html = '<div class="sub">Copa a Copa</div>' +
      '<a class="back" href="#copa=1">← todas as Copas</a>' +
      "<h2>Copa de " + year + "</h2>";

    // Ir para a edição vizinha sem passar pela lista — é o gesto que o nome
    // "Copa a Copa" promete. Nas pontas o link vira texto apagado em vez de
    // sumir: some e a barra muda de forma entre uma edição e outra.
    var before = index > 0 ? TIMELINE.years[index - 1] : null;
    var after = index < TIMELINE.years.length - 1 ? TIMELINE.years[index + 1] : null;
    html += '<div class="copa-nav">' +
      (before ? '<a href="#copa=' + before + '">‹ ' + before + "</a>"
              : '<span class="off">‹ ' + year + " foi a primeira</span>") +
      (after ? '<a href="#copa=' + after + '">' + after + " ›</a>"
             : '<span class="off">a mais recente ›</span>') + "</div>";

    // A sede é a primeira coisa, porque é a que o mapa está mostrando. Com sede
    // dividida cada país leva quantas partidas recebeu: em 2026 os Estados
    // Unidos receberam 78 das 104, e sem o número os três parecem iguais.
    html += '<div class="copa-sedes">' + hosts.map(function (host) {
      return '<span class="copa-host">' + badge(host.team, null) + pt(host.team) +
        (hosts.length > 1 ? "<i>" + NUM.format(host.matches) + "</i>" : "") + "</span>";
    }).join("") + "</div>";

    html += '<div class="tiles">' +
      tile(NUM.format(totals.matches), "Partidas") +
      tile(NUM.format(totals.goals), "Gols") +
      tile(NUM.format(totals.venues), totals.venues === 1 ? "Estádio" : "Estádios") +
      "</div>";

    /* Campeão e vice. O número do campeão é o placar da decisão — "4 × 1" diz
     * mais sobre a final de 70 do que qualquer rótulo ao lado do nome.
     *
     * E O PLACAR SOZINHO MENTE EM TRÊS EDIÇÕES. As finais de 1994, 2006 e 2022
     * terminaram empatadas e foram para os pênaltis; só com o tempo normal, a
     * linha lia "Campeão · Brasil · 0 × 0", que parece erro de dado. A disputa
     * entra embaixo, na linha de baixo do mesmo número — é a mesma regra do
     * `.placar`, onde as 39 decisões por pênalti já ganham linha própria porque
     * são justamente as partidas mais lembradas. */
    var decisao = "";
    if (pod.decider) {
      var venceuEmCasa = pod.decider.homeTeam === pod.champion;
      decisao = venceuEmCasa
        ? pod.decider.homeGoals + " × " + pod.decider.awayGoals
        : pod.decider.awayGoals + " × " + pod.decider.homeGoals;
      if (pod.decider.homePens !== null && pod.decider.homePens !== undefined) {
        // "pên." e não "nos pênaltis": por extenso a linha fica mais larga do
        // que a coluna e o nome do campeão sai com reticências — "Argentina"
        // virava "Argenti…" justamente em 2022. A frase inteira está no placar
        // da final, logo abaixo na mesma tela.
        decisao += "<i>pên. " + (venceuEmCasa
          ? pod.decider.homePens + " × " + pod.decider.awayPens
          : pod.decider.awayPens + " × " + pod.decider.homePens) + "</i>";
      }
    }
    html += '<div class="facts">' +
      (pod.champion ? '<div class="fact campeao"><span>Campeão</span><strong>' +
        badge(pod.champion, null) + pt(pod.champion) + "</strong><b>" + decisao + "</b></div>" : "") +
      (pod.runner ? '<div class="fact"><span>Vice</span><strong>' +
        badge(pod.runner, null) + pt(pod.runner) + "</strong><b></b></div>" : "") +
      "</div>";

    // 1950 é a única edição sem final, e o vice dali não é "quem perdeu a
    // decisão" — é o segundo de uma tabela. Dizer isso é o que impede a linha
    // "Vice: Brasil" de parecer um dado que veio do nada.
    if (pod.group) {
      html += '<p class="muted">Não houve final em ' + year +
        ": o título saiu de um quadrangular de seis jogos, e o vice é o segundo " +
        "colocado dele.</p>" +
        '<div class="h2h-scroll"><table><thead><tr><th>Quadrangular</th><th>P</th>' +
        "<th>V–E–D</th><th>Gols</th></tr></thead><tbody>";
      pod.group.forEach(function (line) {
        html += "<tr><td>" + badge(line.team, null) + pt(line.team) + "</td>" +
          "<td>" + line.points + "</td>" +
          "<td>" + line.wins + "–" + line.draws + "–" + line.losses + "</td>" +
          "<td>" + line.goals + "–" + line.conceded + "</td></tr>";
      });
      html += "</tbody></table></div>";
    }

    /* Artilheiro da edição. A lista mostra pelo menos cinco, e nunca corta um
     * empate no meio: em 1962 seis jogadores fizeram 4 gols cada, e mostrar
     * quatro deles inventaria um pódio que não existiu. A posição repete no
     * empate (1º, 1º, 1º…), que é como qualquer tabela esportiva escreve. */
    if (scorers.length) {
      var top = scorers[0].goals, tied = 0;
      scorers.forEach(function (entry) { if (entry.goals === top) tied += 1; });
      var shown = scorers.slice(0, Math.max(5, tied));

      html += '<div><div class="sub">Artilheiros da edição</div><div class="scorer-list">';
      var place = 0, previous = null;
      shown.forEach(function (entry, position) {
        if (entry.goals !== previous) { place = position + 1; previous = entry.goals; }
        html += '<div class="scorer-row drill" data-player="' + entry.player +
          '" tabindex="0"><i>' + place + "º</i><span>" + entry.name +
          (entry.team ? '<span class="sigla-tag">' + sigla(entry.team) + "</span>" : "") +
          "</span><b>" + NUM.format(entry.goals) + "</b></div>";
      });
      html += "</div></div>";
    }

    // As partidas, fase a fase, na ordem do calendário — que é a ordem em que a
    // Copa aconteceu, e não a alfabética em que as fases chegam do ETL.
    stageGroups(list).forEach(function (group) {
      var label = STAGE_SHORT[group.stage] || group.stage;
      html += '<div><div class="sub">' + label + " · " + NUM.format(group.list.length) +
        (group.list.length === 1 ? " partida" : " partidas") + "</div>" +
        matchRows(group.list) + "</div>";
    });

    return html;
  }

  function drawPanel() {
    var def = current.metric, panel = document.getElementById("panel");
    var span = TIMELINE.years[state.from] + "–" + TIMELINE.years[state.to];
    var rows = [], name, html;

    // A barra do cartão diz o que ele contém mesmo recolhido — é a única pista
    // que sobra quando o painel está fechado.
    document.getElementById("side-title").textContent =
      state.player !== null ? GOALS.players[state.player]
      : state.edition !== null ? "Copa de " + TIMELINE.years[state.edition]
      : state.view === "editions" ? "Copa a Copa"
      : state.view === "teams" ? "Seleções"
      : state.view === "duels" ? "Confrontos"
      : state.view === "scorers" ? "Artilheiros"
      : state.versus ? pt(state.team) + " × " + pt(state.versus)
      : state.team ? pt(state.team) : "Ranking";

    // --- a página de um jogador ----------------------------------------
    // Ela vem antes da edição de propósito: abrir um artilheiro de 1970 não
    // fecha a Copa de 1970, e é para lá que o "voltar" dele leva.
    if (state.player !== null) {
      panel.innerHTML = playerPanel();
      return;
    }

    // --- uma edição, e a lista de todas -------------------------------
    if (state.edition !== null) {
      panel.innerHTML = editionPanel();
      return;
    }
    if (state.view === "editions") {
      panel.innerHTML = editionsPanel(span);
      return;
    }

    // --- os outros dois índices da barra --------------------------------
    if (state.view === "teams") {
      panel.innerHTML = teamsPanel(span);
      return;
    }
    if (state.view === "duels") {
      panel.innerHTML = duelsPanel(span);
      return;
    }

    // --- a tabela de artilheiros ---------------------------------------
    if (state.view === "scorers") {
      panel.innerHTML = scorersPanel(span);
      return;
    }

    // --- detalhamento: as partidas que formam o número -----------------
    if (state.view === "matches" && state.team) {
      var list = matchesFor(state.team, state.opponent, state.from, state.to);
      var sums = tally(list);
      panel.innerHTML =
        '<div class="sub">' + span + '</div>' +
        '<button class="back" type="button" data-back="1">← voltar</button>' +
        '<h2>' + badge(state.team, null) + pt(state.team) +
        (state.opponent ? " × " + pt(state.opponent) : "") + "</h2>" +
        '<div class="tiles">' +
          tile(NUM.format(list.length), "Partidas") +
          tile(sums.wins + "–" + sums.draws + "–" + sums.losses, "V–E–D") +
          tile(NUM.format(sums.goals) + "–" + NUM.format(sums.conceded), "Gols") +
        "</div>" + matchRows(list);
      return;
    }

    // --- comparação de duas seleções -----------------------------------
    if (state.team && state.versus) {
      panel.innerHTML = comparePanel(span);
      return;
    }

    if (state.team) {
      var totals = aggregate(state.from, state.to)[state.team];
      if (!totals) {
        panel.innerHTML = '<div class="sub">' + span + '</div><h2>' + pt(state.team) + '</h2>' +
          '<p class="empty">Não disputou nenhuma partida nesta faixa de edições.</p>';
        return;
      }
      // A cor da camisa continua sendo a rampa do mapa (`reference/team_colors.csv`,
      // com o `last_cup` conferido no ETL) — ela só não se anuncia na tela: o
      // painel é sobre os números da seleção, não sobre a origem do amarelo.
      html = '<div class="sub">' + span + '</div>' +
        '<h2>' + badge(state.team, null) + pt(state.team) +
        '<span class="sigla-tag">' + sigla(state.team) + '</span></h2>' +
        '<div class="tiles">' +
          tile(NUM.format(totals.goals), "Gols") +
          tile(NUM.format(totals.conceded), "Sofridos") +
          tile((totals.goal_difference > 0 ? "+" : "") + NUM.format(totals.goal_difference), "Saldo") +
          tile(NUM.format(totals.wins) + "–" + NUM.format(totals.draws) + "–" + NUM.format(totals.losses), "V–E–D") +
          tile(NUM.format(totals.matches_played), "Partidas") +
          tile(NUM.format(totals.participations), "Participações") +
          tile(NUM.format(totals.titles), "Títulos") +
          tile(PCT.format(totals.matches_played ? 100 * totals.wins / totals.matches_played : 0) + "%", "Aproveit.") +
          tile(NUM.format(totals.matches_received), "Recebidas") +
        '</div>';

      for (name in current.records) rows.push([name, current.records[name]]);
      rows.sort(function (a, b) {
        var x = valueOf(a[1], def, state.mode), y = valueOf(b[1], def, state.mode);
        if (x === null) x = -Infinity;
        if (y === null) y = -Infinity;
        return y - x || byName(a[0], b[0]);
      });

      var scorersList = topScorers(state.team, state.from, state.to, 8);
      if (scorersList.length) {
        html += '<div><div class="sub">Artilheiros · ' + span + "</div>" +
          '<div class="scorer-list">';
        // A linha abre a página do jogador. É o mesmo gesto da linha de
        // confronto logo abaixo, e o mesmo motivo: ligar o número às partidas
        // que o produziram.
        scorersList.forEach(function (player, index) {
          html += '<div class="scorer-row drill" data-player="' + player.player +
                  '" tabindex="0"><i>' + (index + 1) + "º</i>" +
                  "<span>" + player.name + "</span>" +
                  "<b>" + NUM.format(player.goals) + "</b></div>";
        });
        html += "</div></div>";
      }

      html += '<button class="back solid" type="button" data-matches="1">' +
        "Ver as " + NUM.format(totals.matches_played) + " partidas →</button>";

      html += '<div><div class="sub">Confrontos diretos · ' + rows.length + ' adversários</div>' +
        '<div class="h2h-scroll"><table><thead><tr><th>Adversário</th><th>' +
        def.label + '</th><th>J</th><th>V–E–D</th></tr></thead><tbody>';
      rows.forEach(function (entry) {
        var rec = entry[1], value = valueOf(rec, def, state.mode);
        // A linha inteira abre o detalhamento daquele confronto: é o gesto que
        // liga "21 gols em 7 jogos" às sete partidas que produziram o número.
        // `data-opponent` guarda a chave em inglês — é ela que volta para o
        // estado e para a URL. Só o texto da célula é traduzido.
        html += '<tr class="drill" data-opponent="' + entry[0] + '" tabindex="0">' +
          '<td>' + badge(entry[0], value) + pt(entry[0]) + '</td>' +
          '<td>' + format(value, def, state.mode) + '</td>' +
          '<td>' + NUM.format(rec.matches_played) + '</td>' +
          '<td>' + rec.wins + '–' + rec.draws + '–' + rec.losses + '</td></tr>';
      });
      html += '</tbody></table></div></div>';
      panel.innerHTML = html;
      return;
    }

    // Visão global: o ranking da métrica escolhida. Ele não é enfeite — é a
    // "table view" que a regra de acessibilidade exige quando a informação está
    // codificada em cor, e é onde os empates que o mapa achata ficam visíveis.
    for (name in current.records) rows.push([name, current.records[name]]);
    rows.sort(function (a, b) {
      var x = valueOf(a[1], def, state.mode), y = valueOf(b[1], def, state.mode);
      if (x === null) x = -Infinity;
      if (y === null) y = -Infinity;
      return y - x || byName(a[0], b[0]);
    });

    var facts = factsFor(state.from, state.to);

    // O maior campeão da faixa sai do mesmo agregado que pinta o mapa, então
    // ele nunca pode discordar dele.
    //
    // Empate é o caso comum, não a exceção: em qualquer recorte curto várias
    // seleções têm um título cada, e mostrar só a primeira da lista elegeria um
    // "maior campeão" por ordem de varredura — em 2018–2026 saía "França",
    // calando Argentina e Espanha, que ganharam as outras duas. Empatados
    // aparecem juntos, e acima de três vira contagem para a linha não virar
    // parágrafo.
    var mostTitles = 0, champions = [];
    rows.forEach(function (entry) {
      if (entry[1].titles > mostTitles) { mostTitles = entry[1].titles; champions = [entry[0]]; }
      else if (entry[1].titles === mostTitles && mostTitles > 0) champions.push(entry[0]);
    });
    champions.sort(byName);

    var championLine = champions.length > 3
      ? NUM.format(champions.length) + " seleções empatadas"
      : champions.map(function (team) { return badge(team, null) + pt(team); }).join(" · ");

    html = '<div class="sub">' + span + '</div><h2>Visão global</h2>' +
      '<div class="tiles">' +
        tile(NUM.format(state.to - state.from + 1), "Edições") +
        tile(NUM.format(facts.matches), "Partidas") +
        tile(NUM.format(facts.goals), "Gols") +
      '</div>' +
      '<div class="facts">' +
        (mostTitles ?
          '<div class="fact"><span>' +
          (champions.length > 1 ? "Mais títulos" : "Maior campeão") + "</span><strong>" +
          championLine + "</strong><b>" + NUM.format(mostTitles) + "</b></div>" : "") +
        (facts.scorer !== null ?
          '<div class="fact drill" data-player="' + facts.scorer + '" tabindex="0">' +
          "<span>Artilheiro</span><strong>" + GOALS.players[facts.scorer] +
          "</strong><b>" + NUM.format(facts.scorerGoals) + "</b></div>" : "") +
        (facts.rout ?
          '<div class="fact"><span>Maior goleada</span><strong>' +
          sigla(MATCHES.teams[facts.rout.row[2]]) + " " + facts.rout.row[4] + " × " +
          facts.rout.row[5] + " " + sigla(MATCHES.teams[facts.rout.row[3]]) +
          "</strong><b>" + facts.rout.row[0] + "</b></div>" : "") +
      "</div>" +
      // Cada tarja é um link cujo `href` descreve o estado inteiro — o mesmo
      // formato que a barra de endereço aceita. Sendo link de verdade, elas
      // entram no histórico, funcionam com o botão voltar e podem ser copiadas;
      // e o `hashchange` que já existia faz o resto sem nenhum código novo.
      '<div><div class="sub">Por onde começar</div><div class="asks">' +
        // "A Copa de 1970" apontava para `y=1970-1970`, que RECORTA o mapa em
        // 1970 e não abre nada. Agora ela leva à edição de verdade — que é a
        // diferença entre filtrar e chegar.
        '<a class="ask" href="#copa=1">Copa a Copa</a>' +
        '<a class="ask" href="#copa=1970">A Copa de 1970</a>' +
        '<a class="ask" href="#art=1">Artilheiros de todos os tempos</a>' +
        '<a class="ask" href="#m=titles">Maiores campeões</a>' +
        '<a class="ask" href="#m=win_pct">Melhor aproveitamento</a>' +
        '<a class="ask" href="#t=Brazil&v=Argentina">Brasil × Argentina</a>' +
        '<a class="ask" href="#y=2002-2026">Só o século XXI</a>' +
        '<a class="ask" href="#sedes=1">Onde se jogou</a>' +
      "</div></div>" +
      '<div><div class="sub">Ranking · ' + def.label +
      (state.mode === "rate" && def.rate ? " por partida" : "") + '</div>' +
      // `table.rank` é o que liga a coluna de posição e a tarja dourada dos três
      // primeiros — a leitura de tabela de campeonato, que o confronto direto
      // não tem porque ali não existe classificação.
      '<div class="h2h-scroll"><table class="rank"><thead><tr><th>#</th><th>Seleção</th><th>' +
      def.label + "</th>" + (showsMatchContext(def) ? "<th>J</th>" : "") + "</tr></thead><tbody>";
    rows.slice(0, 30).forEach(function (entry, index) {
      var rec = entry[1], value = valueOf(rec, def, state.mode);
      html += '<tr><td class="pos">' + (index + 1) + '</td>' +
        '<td>' + badge(entry[0], value) + pt(entry[0]) + '</td>' +
        '<td>' + format(value, def, state.mode) + "</td>" +
        // A coluna de jogos sai junto com a linha do tooltip, e pelo mesmo
        // motivo: em "partidas recebidas" ela fala de outra coisa.
        (showsMatchContext(def) ? "<td>" + NUM.format(rec.matches_played) + "</td>" : "") + "</tr>";
    });
    // "Toque" no celular, "Clique" no desktop: a dica descreve um gesto, e
    // descrever o gesto errado é pior do que não descrever nenhum.
    html += '</tbody></table></div>' +
      '<p class="hint"><b>' + (narrow() ? "Toque" : "Clique") + ' num país</b> ' +
      "do mapa para abrir os confrontos diretos dele.</p></div>";
    panel.innerHTML = html;
  }

  // ------------------------------------------------------------- conferência

  /* A contrapartida de ter movido a agregação para o navegador.
   *
   * Refaz a faixa inteira aqui e compara com o `metrics.json` que o Python
   * gerou. São as mesmas 83 seleções e os mesmos 10 campos; qualquer diferença
   * significa que uma das duas implementações mudou sem a outra — e aparece na
   * tela, em vez de virar um número errado bonito. */
  function selfCheck() {
    var mine = aggregate(0, TIMELINE.years.length - 1), bad = [];
    GOLDEN.teams.forEach(function (golden) {
      var rec = mine[golden.team];
      if (!rec) { bad.push(golden.team + " (ausente)"); return; }
      for (var i = 0; i < FIELDS.length; i++) {
        var field = FIELDS[i];
        if (rec[field] !== golden[field]) {
          bad.push(golden.team + "/" + field + ": " + rec[field] + " ≠ " + golden[field]);
          return;
        }
      }
    });

    var box = document.getElementById("alarm");
    if (!bad.length) return true;
    document.getElementById("alarm-text").innerHTML =
      "A soma feita no navegador não bate com <code>metrics.json</code> em " + bad.length +
      " seleção(ões): " + bad.slice(0, 4).join("; ") +
      ". Os números do mapa não são confiáveis até isso ser resolvido — " +
      "compare <code>map.js</code> com <code>etl/metrics.py</code>.";
    box.setAttribute("data-on", "");
    return false;
  }

  // ------------------------------------------------------------- controles

  function select(team) {
    var previous = metricDef(state.metric).label;
    state.team = team || null;
    // Trocar de seleção zera o que dependia da anterior: o detalhamento de um
    // confronto que não é mais o atual, e uma comparação com ela mesma. A Copa
    // aberta também sai: pedir uma seleção é pedir outra pergunta, e deixar a
    // tela da edição por cima dela seria ignorar o clique. A FAIXA DE ANOS
    // fica — quem clicou no México dentro da Copa de 1970 continua em 1970, e
    // o slider e a faixa da marca continuam dizendo isso.
    state.view = null;
    state.opponent = null;
    state.edition = null;
    if (state.versus === state.team) state.versus = null;
    teamCombo.set(state.team);
    if (syncMetricOptions()) {
      state.swapped = previous;
      syncMode();
    } else {
      state.swapped = null;
    }
    syncVersusOptions();
    repaint();
  }

  /* A segunda seleção da comparação. Ela não pode ser a mesma da primeira — a
   * opção some da lista em vez de existir e não fazer nada. */
  function syncVersusOptions() {
    // A primeira seleção sai da lista da segunda em vez de ficar lá escolhível
    // e não fazer nada — ninguém joga contra si mesmo.
    versusCombo.exclude(state.team);
    versusCombo.disable(!state.team, state.team ? "" : "Escolha uma seleção primeiro");
    if (!state.team) state.versus = null;
    versusCombo.set(state.versus);
  }

  function selectVersus(team) {
    state.versus = team || null;
    state.view = null;
    state.opponent = null;
    syncVersusOptions();
    repaint();
  }

  /* Abre um confronto do índice: as duas seleções lado a lado.
   *
   * Não é `select()` seguido de `selectVersus()` — a primeira apagaria a
   * comparação que a segunda ia montar, e as duas repintariam a tela. Aqui o
   * estado inteiro é montado antes de uma repintura só. */
  function openDuel(a, b) {
    // A métrica em vigor pode não existir em confronto direto — "títulos" é a
    // que leva a lista dos maiores campeões até aqui. A troca é anunciada na
    // legenda em vez de acontecer calada, exatamente como em `select()`.
    var previous = metricDef(state.metric).label;
    state.team = a;
    state.versus = b;
    state.view = null;
    state.opponent = null;
    state.player = null;
    state.edition = null;
    teamCombo.set(a);
    if (syncMetricOptions()) {
      state.swapped = previous;
      syncMode();
    } else {
      state.swapped = null;
    }
    syncVersusOptions();
    repaint();
  }

  /* Qual das cinco portas da barra está aberta.
   *
   * "Mapa" é o padrão porque ele é o estado sem índice nenhum — inclusive com
   * uma seleção escolhida ou uma comparação no ar, que são o mapa fazendo o que
   * ele faz. A página de um jogador conta como Artilheiros e uma edição conta
   * como Copas: são as telas de dentro de cada índice. */
  function syncNav() {
    var open =
      state.edition !== null || state.view === "editions" ? "editions"
      : state.view === "teams" ? "teams"
      : state.view === "duels" ? "duels"
      : state.player !== null || state.view === "scorers" ? "scorers"
      : "map";

    var links = document.querySelectorAll(".masthead-nav a");
    for (var i = 0; i < links.length; i++) {
      var mine = links[i].getAttribute("data-nav") === open;
      // `aria-current` e não uma classe: é o atributo que diz "esta é a página
      // atual" para o leitor de tela, e o sublinhado verde pendura nele.
      if (mine) links[i].setAttribute("aria-current", "page");
      else links[i].removeAttribute("aria-current");
    }
  }

  /* Abre o detalhamento. Sem adversário, são todas as partidas da seleção. */
  function openMatches(opponent) {
    state.view = "matches";
    state.opponent = opponent || null;
    repaint();
  }

  function closeMatches() {
    state.view = null;
    state.opponent = null;
    repaint();
  }

  /* Abre a página de um jogador. O detalhamento de partidas fecha junto: as
   * duas são telas de aprofundamento e empilhá-las deixaria um "voltar" sem
   * destino claro. */
  function openPlayer(who) {
    state.player = who;
    if (state.view === "matches") { state.view = null; state.opponent = null; }
    repaint();
  }

  /* O "voltar" da página do jogador não escolhe destino: ele só apaga o
   * jogador. Quem chegou pela lista de artilheiros tem `view === "scorers"` e
   * volta para a lista; quem chegou pelo painel de uma seleção não tem, e
   * volta para a seleção. O caminho de volta é o caminho de ida ao contrário
   * sem nenhum histórico próprio para manter. */
  function closePlayer() {
    state.player = null;
    repaint();
  }

  /* No modo de país, três métricas deixam de existir. Em vez de deixá-las
   * escolhíveis e mostrar um mapa vazio, elas ficam desabilitadas — e se uma
   * delas estava escolhida, a troca é anunciada no lugar de acontecer calada. */
  function syncMetricOptions() {
    var chosen = state.team;
    var options = document.getElementById("metric").options;
    var swapped = false;

    for (var i = 0; i < options.length; i++) {
      var def = metricDef(options[i].value);
      var blocked = Boolean(chosen) && !def.h2h;
      options[i].disabled = blocked;
      options[i].textContent = def.label + (blocked ? " — não existe em confronto" : "");
      if (blocked && state.metric === def.key) swapped = true;
    }
    if (swapped) {
      state.metric = "goals";
      document.getElementById("metric").value = "goals";
    }
    // Esta função mexe SÓ nas opções de métrica. Ela também reescrevia o valor
    // do seletor de seleção, o que era inofensivo enquanto ele era um `<select>`
    // (a chave em inglês era o `value` de uma opção) e virou bug quando ele
    // virou caixa de texto: a chave crua aparecia escrita na tela, "South
    // Korea" num painel que dizia "Coreia do Sul". Quem sincroniza a caixa é
    // `select()` e o ouvinte de `hashchange`, e os dois já o fazem.
    return swapped;
  }

  // ------------------------------------------------- a caixa de busca de seleção

  /* Texto comparável: sem acento e em minúsculas. Quem procura a Argélia digita
   * "argelia", e quem procura a Bósnia não digita nada com acento nenhum. */
  function fold(text) {
    return text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  }

  /* Uma caixa de busca de seleção, sobre um `<input>`.
   *
   * Substitui um `<select>` de 83 países em ordem alfabética, que só se navega
   * rolando: a busca nativa do `<select>` casa prefixo, é invisível e expira em
   * um segundo. Aqui o texto casa em qualquer posição do nome em português, da
   * sigla FIFA e da chave em inglês — "kor", "coreia" e "korea" chegam todos na
   * Coreia do Sul.
   *
   * A lista é anexada ao `<body>` e posicionada em coordenadas de janela. Ela
   * não pode morar dentro do cartão: o cartão de controles tem `overflow` para
   * poder rolar em tela baixa, e um elemento absoluto lá dentro é cortado na
   * borda — a lista apareceria com uma linha e meia. O preço de sair de lá é
   * que ela não acompanha rolagem nenhuma, então ela fecha quando algo rola.
   *
   * `chosen` guarda a CHAVE em inglês, nunca o rótulo: é ela que vai para o
   * estado e para a URL, e é a mesma regra do resto do arquivo. O texto visível
   * é só rótulo, e é reescrito a partir da chave sempre que a caixa fecha. */
  function makeCombo(id, teams, onPick) {
    var input = document.getElementById(id);
    var box = input.parentNode;
    var clear = box.querySelector(".combo-clear");

    var pop = document.createElement("ul");
    pop.className = "combo-pop";
    pop.id = id + "-list";
    pop.setAttribute("role", "listbox");
    pop.hidden = true;
    document.body.appendChild(pop);

    var haystack = {};
    teams.forEach(function (team) {
      haystack[team] = fold(pt(team) + " " + sigla(team) + " " + team);
    });

    var chosen = null, excluded = null, shown = [], active = -1;

    function labelOf(team) { return team ? pt(team) : ""; }

    function candidates() {
      var typed = fold(input.value.trim());
      // Texto igual ao rótulo do que já está escolhido significa que ninguém
      // digitou nada — abrir mostra a lista inteira, como um `<select>` faria.
      var filtering = typed && typed !== fold(labelOf(chosen));
      return teams.filter(function (team) {
        if (team === excluded) return false;
        return !filtering || haystack[team].indexOf(typed) >= 0;
      });
    }

    function render() {
      if (!shown.length) {
        pop.innerHTML = '<li class="combo-empty">Nenhuma seleção com esse nome.</li>';
        return;
      }
      pop.innerHTML = shown.map(function (team, i) {
        return '<li role="option" id="' + pop.id + "-" + i + '" data-team="' + team +
          '" aria-selected="' + (team === chosen) + '"' + (i === active ? ' class="on"' : "") +
          ">" + badge(team, null) + pt(team) +
          '<span class="sigla-tag">' + sigla(team) + "</span></li>";
      }).join("");
    }

    /* Abaixo da caixa quando cabe, acima quando não cabe e há mais espaço lá.
     * A altura é medida depois de renderizar porque ela depende de quantos
     * países sobraram do filtro. */
    function place() {
      var rect = box.getBoundingClientRect();
      // Sem caixa não há onde ancorar: um retângulo zerado significa que o
      // cartão foi recolhido (`display:none`), e posicionar a partir dele
      // largaria a lista no canto superior esquerdo da tela.
      if (!rect.width && !rect.height) { pop.hidden = true; return; }
      var gap = 4, margin = 12, ceiling = 256;

      /* A LARGURA DO CAMPO É O PISO, NÃO A MEDIDA.
       *
       * A lista copiava a largura da caixa, e em janela média a caixa é
       * estreita: abaixo de 72rem os campos dos controles fluem lado a lado
       * (`flex:1 1 8rem`), e numa janela de 750px sobram ~145px para cada um.
       * Com `white-space:nowrap` nas linhas, "Bósnia e Herzegovina" passava 60px
       * da borda e a lista ganhava BARRA DE ROLAGEM HORIZONTAL — para ler o nome
       * do país era preciso arrastar a lista de lado.
       *
       * Agora ela cresce até o conteúdo e para na janela. Alinhada à esquerda do
       * campo quando cabe; encostada na margem direita quando não cabe, em vez
       * de vazar para fora da tela. */
      pop.style.width = "auto";
      pop.style.minWidth = Math.round(rect.width) + "px";
      pop.style.maxWidth = Math.round(window.innerWidth - 2 * margin) + "px";
      var width = pop.getBoundingClientRect().width;
      var left = Math.min(rect.left, window.innerWidth - margin - width);
      pop.style.left = Math.round(Math.max(margin, left)) + "px";

      pop.style.maxHeight = ceiling + "px";
      var wanted = Math.min(pop.scrollHeight + 2, ceiling);
      var below = window.innerHeight - rect.bottom - gap - margin;
      var above = rect.top - gap - margin;
      if (wanted > below && above > below) {
        pop.style.top = "";
        pop.style.bottom = Math.round(window.innerHeight - rect.top + gap) + "px";
        pop.style.maxHeight = Math.round(Math.min(wanted, above)) + "px";
      } else {
        pop.style.bottom = "";
        pop.style.top = Math.round(rect.bottom + gap) + "px";
        pop.style.maxHeight = Math.round(Math.min(wanted, below)) + "px";
      }
    }

    function open() {
      if (input.disabled) return;
      shown = candidates();
      active = shown.indexOf(chosen);
      render();
      pop.hidden = false;
      place();
      input.setAttribute("aria-expanded", "true");
      scrollActiveIntoView();
    }

    function close() {
      pop.hidden = true;
      active = -1;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      // O texto sempre volta a descrever a escolha atual: sair da caixa com
      // "arge" escrito e a Argentina pintada no mapa seria a caixa mentindo.
      input.value = labelOf(chosen);
    }

    function scrollActiveIntoView() {
      var row = active >= 0 && pop.children[active];
      if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
    }

    function highlight(next) {
      if (!shown.length) return;
      active = (next + shown.length) % shown.length;
      Array.prototype.forEach.call(pop.children, function (row, i) {
        row.classList.toggle("on", i === active);
      });
      input.setAttribute("aria-activedescendant", pop.id + "-" + active);
      scrollActiveIntoView();
    }

    function commit(team) {
      chosen = team || null;
      close();
      syncClear();
      onPick(chosen);
    }

    function syncClear() { clear.hidden = !chosen || input.disabled; }

    input.addEventListener("input", function () {
      shown = candidates();
      active = shown.length ? 0 : -1;
      render();
      pop.hidden = false;
      place();
      input.setAttribute("aria-expanded", "true");
      if (active >= 0) input.setAttribute("aria-activedescendant", pop.id + "-" + active);
    });

    input.addEventListener("focus", function () { input.select(); open(); });
    input.addEventListener("mousedown", function () {
      if (document.activeElement === input && pop.hidden) open();
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown") { event.preventDefault(); pop.hidden ? open() : highlight(active + 1); }
      else if (event.key === "ArrowUp") { event.preventDefault(); pop.hidden ? open() : highlight(active - 1); }
      else if (event.key === "Enter") {
        if (pop.hidden) return;
        event.preventDefault();
        if (active >= 0 && shown[active]) commit(shown[active]);
      } else if (event.key === "Escape") {
        if (pop.hidden) return;
        event.preventDefault();     // não deixa o Esc escapar e fechar outra coisa
        close();
      } else if (event.key === "Tab") {
        close();
      }
    });

    /* `mousedown` e não `click`: o clique numa lista fora do campo tira o foco
     * do `<input>` antes, e o `blur` fecharia a lista debaixo do ponteiro.
     *
     * O `preventDefault` vale para QUALQUER ponto da lista, e não só para as
     * linhas. A barra de rolagem faz parte dela: arrastá-la disparava o `blur`
     * do campo, o `blur` fechava a lista, e a barra sumia debaixo do ponteiro
     * no meio do arrasto. Segurar o foco no campo é o que mantém a lista de pé
     * enquanto se rola. */
    pop.addEventListener("mousedown", function (event) {
      event.preventDefault();
      var row = event.target.closest("[data-team]");
      if (!row) return;
      commit(row.getAttribute("data-team"));
      input.focus();
    });

    input.addEventListener("blur", function () {
      // Um quadro de atraso: sem ele o `blur` do clique na lista fecha antes de
      // o `mousedown` de lá ser processado em navegadores que ordenam assim.
      window.setTimeout(function () {
        if (!pop.hidden && !pop.contains(document.activeElement)) close();
      }, 0);
    });

    clear.addEventListener("click", function () { input.value = ""; commit(null); });

    /* Uma lista `position:fixed` não acompanha o que rolou embaixo dela, então
     * ela fecha em vez de ficar flutuando ao lado do campo que a abriu.
     *
     * MENOS QUANDO QUEM ROLOU FOI ELA. O ouvinte está na fase de captura da
     * janela para pegar rolagem de qualquer contêiner da página — e pegava
     * também a da própria lista, que é o único caso em que fechar é errado.
     * São 83 países em 254px de altura: 2.650px de conteúdo, ou seja, chegar em
     * qualquer país depois da Croácia EXIGE rolar. A lista fechava no primeiro
     * giro da roda do mouse, e a caixa de busca virava utilizável só para quem
     * soubesse digitar o nome. */
    var dismiss = function (event) {
      if (event && event.target === pop) return;
      if (!pop.hidden) close();
    };
    window.addEventListener("resize", dismiss);
    window.addEventListener("scroll", dismiss, true);
    document.addEventListener("mousedown", function (event) {
      if (!pop.hidden && !box.contains(event.target) && !pop.contains(event.target)) close();
    });

    return {
      set: function (team) {
        chosen = team || null;
        input.value = labelOf(chosen);
        syncClear();
      },
      exclude: function (team) { excluded = team || null; },
      disable: function (off, why) {
        input.disabled = off;
        input.title = why || "";
        if (off) { close(); }
        syncClear();
      }
    };
  }

  var teamCombo = null, versusCombo = null;

  /* Recolher e mostrar os painéis.
   *
   * Recolhido, o cartão fica reduzido à sua barra de título — nunca some. Um
   * painel que desaparece por inteiro exige um segundo controle, em outro canto,
   * só para trazê-lo de volta; a barra é o caminho de volta, e fica exatamente
   * onde o painel estava.
   *
   * A escolha fica no `localStorage`: quem recolhe o painel lateral para ver o
   * mapa inteiro não quer fazer isso de novo a cada recarga. Se o armazenamento
   * estiver bloqueado (navegação privada, terceiros), a interface segue igual —
   * só não lembra. Por isso o acesso é sempre dentro de try/catch: falhar em
   * lembrar uma preferência não pode derrubar o mapa. */
  var CARDS = { controls: "card-controls", legend: "card-legend", side: "card-side" };
  var STORAGE_KEY = "atlas.cards.collapsed";

  function remember(collapsed) {
    try {
      window.localStorage.setItem(STORAGE_KEY, collapsed.join(","));
    } catch (error) { /* sem persistência; a interface não muda */ }
  }

  /* Devolve `null` quando nunca houve escolha — que é diferente de "abriu tudo".
   * A diferença importa porque o padrão do celular depende dela: `[]` é uma
   * decisão da pessoa e tem que ser respeitada, `null` é a primeira visita. */
  function recall() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw === null) return null;
      return raw.split(",").filter(Boolean);
    } catch (error) { return null; }
  }

  /* O mesmo limite do `@media (max-width:30rem)` da folha de estilo. Ele está
   * repetido aqui porque o JavaScript precisa saber a mesma coisa, e não há
   * como perguntar ao CSS — o jeito de manter os dois em dia é este comentário
   * e o fato de o número aparecer duas vezes na busca. */
  function narrow() {
    return window.matchMedia("(max-width:30rem)").matches;
  }

  function collapsedNow() {
    return Object.keys(CARDS).filter(function (name) {
      return document.getElementById(CARDS[name]).classList.contains("collapsed");
    });
  }

  function setCard(name, collapsed) {
    var card = document.getElementById(CARDS[name]);
    if (!card) return;
    card.classList.toggle("collapsed", collapsed);
    var toggle = card.querySelector(".card-toggle");
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.title = collapsed ? "Mostrar" : "Recolher";
  }

  function syncMaster() {
    var all = Object.keys(CARDS);
    var every = collapsedNow().length === all.length;
    var button = document.getElementById("panels");
    var label = every ? "Mostrar todos os painéis" : "Recolher todos os painéis";
    button.setAttribute("aria-pressed", String(every));
    button.title = label;
    // O botão é um ícone, então o nome acessível vem do texto escondido dentro
    // dele — e conteúdo ganha de `title`. Atualizar só o `title` deixaria o
    // leitor de tela anunciando "recolher" num botão que agora mostra.
    button.querySelector(".sr-only").textContent = label;
  }

  function wirePanels() {
    var saved = recall();
    // Primeira visita num celular: os controles começam recolhidos. Abertos,
    // eles ocupam ~230px de uma tela de 812px, e com a folha do rodapé sobram
    // 150px de mapa — numa página cujo desenho inteiro parte de "o mapa é a
    // página". Recolhidos, sobram 340px e a barra de título continua ali,
    // dizendo onde eles estão. Quem já escolheu alguma coisa mantém a escolha,
    // inclusive a de deixar tudo aberto.
    if (saved === null) saved = narrow() ? ["controls"] : [];
    Object.keys(CARDS).forEach(function (name) {
      setCard(name, saved.indexOf(name) >= 0);
      var card = document.getElementById(CARDS[name]);
      card.querySelector(".card-toggle").addEventListener("click", function () {
        setCard(name, !card.classList.contains("collapsed"));
        syncMaster();
        remember(collapsedNow());
      });
    });

    // O botão da barra recolhe todos — ou devolve todos, se já estiverem todos
    // recolhidos. O mapa não muda de tamanho (ele já ocupa a janela toda; os
    // cartões só flutuam por cima), então não há `invalidateSize` a fazer.
    document.getElementById("panels").addEventListener("click", function () {
      var every = collapsedNow().length === Object.keys(CARDS).length;
      Object.keys(CARDS).forEach(function (name) { setCard(name, !every); });
      syncMaster();
      remember(collapsedNow());
    });

    syncMaster();
  }

  /* O botão "Sedes" diz o que está no mapa, e com uma edição aberta ele não
   * manda mais nisso: os alfinetes daquela Copa fazem parte da tela. Então ele
   * aparece ligado e desabilitado, com o motivo no `title` — a mesma escolha
   * das métricas que não existem em confronto direto e do segundo seletor sem
   * seleção. Um botão que continua clicável e não faz nada é pior do que um
   * botão desligado que explica por quê. */
  function syncVenueButton() {
    var button = document.getElementById("layer-venues");
    var forced = state.edition !== null;
    button.setAttribute("aria-pressed", String(venuesOn()));
    button.disabled = forced;
    button.title = forced
      ? "A Copa aberta já mostra as sedes dela no mapa."
      : "";
  }

  function syncMode() {
    var def = metricDef(state.metric);
    var rate = document.getElementById("mode-rate");
    rate.disabled = !def.rate;
    if (!def.rate && state.mode === "rate") state.mode = "total";
    document.getElementById("mode-total").setAttribute("aria-pressed", String(state.mode !== "rate"));
    rate.setAttribute("aria-pressed", String(state.mode === "rate"));
  }

  /* Percorrer as edições.
   *
   * O slider já dizia *qual* recorte olhar; o play mostra a **mudança** entre
   * eles, que é o que uma imagem parada não consegue. Ele desliza a janela que
   * você escolheu, mantendo a largura: com duas edições selecionadas, caminha de
   * duas em duas. A faixa completa é o único caso especial — não há para onde
   * deslizar uma janela que já cobre tudo —, então ela encolhe para uma edição
   * antes de começar. Sem isso o botão não faria nada justamente no estado
   * inicial, que é onde a maioria vai clicar nele.
   */
  var playTimer = null;

  function playing() { return playTimer !== null; }

  function stopPlay() {
    if (playTimer) window.clearInterval(playTimer);
    playTimer = null;
    var button = document.getElementById("play");
    button.textContent = "▶";
    button.setAttribute("aria-pressed", "false");
    button.title = "Percorrer as edições";
  }

  function stepPlay() {
    var last = TIMELINE.years.length - 1;
    var width = state.to - state.from;

    if (state.to >= last) return stopPlay();   // chegou em 2026

    setYears(state.from + 1, Math.min(last, state.from + 1 + width));
  }

  function startPlay() {
    var last = TIMELINE.years.length - 1;
    // Já no fim, recomeça do início em vez de não fazer nada — é o que um botão
    // de play faz quando a faixa acabou, e "não faz nada" seria lido como quebra.
    if (state.from === 0 && state.to === last) setYears(0, 0);
    else if (state.to >= last) setYears(0, state.to - state.from);

    var button = document.getElementById("play");
    button.textContent = "⏸";
    button.setAttribute("aria-pressed", "true");
    button.title = "Pausar";
    // 1,1 s por edição: rápido o bastante para as 23 passarem em meio minuto e
    // lento o bastante para dar tempo de ler o mapa antes da próxima.
    playTimer = window.setInterval(stepPlay, 1100);
  }

  /* Move a faixa e mantém os dois sliders em dia. Existe porque o play precisa
   * mexer no estado sem passar pelos eventos de input dos sliders. */
  function setYears(from, to) {
    document.getElementById("year-from").value = from;
    document.getElementById("year-to").value = to;
    // Pelo mesmo motivo do arrasto: percorrer as edições sai da edição aberta.
    state.edition = null;
    syncYears();
    repaint();
  }

  function syncYears() {
    var from = document.getElementById("year-from");
    var to = document.getElementById("year-to");
    var last = TIMELINE.years.length - 1;

    state.from = Math.min(Number(from.value), Number(to.value));
    state.to = Math.max(Number(from.value), Number(to.value));

    document.getElementById("read-from").textContent = TIMELINE.years[state.from];
    document.getElementById("read-to").textContent = TIMELINE.years[state.to];
    var count = state.to - state.from + 1;
    var label = count + (count === 1 ? " edição" : " edições");
    document.getElementById("read-count").textContent = label;

    // O mesmo recorte, na faixa da marca. Ele é o estado global da página: com
    // todos os cartões recolhidos, é a única coisa que sobra dizendo o que a
    // tela está mostrando.
    document.getElementById("head-span").textContent =
      TIMELINE.years[state.from] + "–" + TIMELINE.years[state.to];
    document.getElementById("head-count").textContent = label;

    var fill = document.getElementById("range-fill");
    fill.style.left = (100 * state.from / last) + "%";
    fill.style.right = (100 * (last - state.to) / last) + "%";
  }

  function wire() {
    var metric = document.getElementById("metric");
    METRICS.forEach(function (def) {
      var option = document.createElement("option");
      option.value = def.key;
      option.textContent = def.label;
      metric.appendChild(option);
    });
    metric.value = state.metric;
    metric.addEventListener("change", function () {
      state.metric = metric.value;
      state.swapped = null;  // escolha explícita apaga o aviso da troca automática
      syncMode();
      repaint();
    });

    // Só as seleções que de fato jogaram: `TIMELINE.teams` inclui países-sede,
    // e no dado masculino todos jogaram, mas a conferência é barata.
    var played = {};
    TIMELINE.rows.forEach(function (row) { played[TIMELINE.teams[row[1]]] = 1; });
    // A ordem é a do rótulo em português; a chave guardada é a inglesa. As duas
    // caixas recebem a MESMA lista, da mesma variável, para nunca divergirem.
    var roster = Object.keys(played).sort(byName);

    teamCombo = makeCombo("team", roster, function (name) { select(name || ""); });
    versusCombo = makeCombo("versus", roster, function (name) { selectVersus(name || ""); });

    document.getElementById("play").addEventListener("click", function () {
      if (playing()) stopPlay(); else startPlay();
    });

    document.getElementById("layer-venues").addEventListener("click", function () {
      state.venues = !state.venues;
      repaint();   // quem sincroniza o botão é `syncVenueButton`, de dentro dela
    });

    /* Um só ouvinte no painel, em vez de um por linha: o painel é reescrito
     * inteiro a cada repintura, e ouvintes presos às linhas morreriam junto. */
    document.getElementById("panel").addEventListener("click", function (event) {
      var back = event.target.closest("[data-back]");
      if (back) {
        if (back.getAttribute("data-back") === "player") closePlayer();
        else closeMatches();
        return;
      }
      var all = event.target.closest("[data-matches]");
      if (all) { openMatches(null); return; }
      var who = event.target.closest("[data-player]");
      if (who) { openPlayer(Number(who.getAttribute("data-player"))); return; }
      var team = event.target.closest("[data-team]");
      if (team) { select(team.getAttribute("data-team")); return; }
      var duel = event.target.closest("[data-duel]");
      if (duel) {
        var pair = duel.getAttribute("data-duel").split("|");
        openDuel(pair[0], pair[1]);
        return;
      }
      var row = event.target.closest("[data-opponent]");
      if (row) openMatches(row.getAttribute("data-opponent"));
    });
    document.getElementById("panel").addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
      var who = event.target.closest("[data-player]");
      if (who) { event.preventDefault(); openPlayer(Number(who.getAttribute("data-player"))); return; }
      var team = event.target.closest("[data-team]");
      if (team) { event.preventDefault(); select(team.getAttribute("data-team")); return; }
      var duel = event.target.closest("[data-duel]");
      if (duel) {
        event.preventDefault();
        var pares = duel.getAttribute("data-duel").split("|");
        openDuel(pares[0], pares[1]);
        return;
      }
      var row = event.target.closest("[data-opponent]");
      if (row) { event.preventDefault(); openMatches(row.getAttribute("data-opponent")); }
    });

    // Voltar/avançar do navegador, e links colados na barra de endereço.
    window.addEventListener("hashchange", function () {
      if (writingHash) return;
      if (applyURL()) {
        document.getElementById("metric").value = state.metric;
        document.getElementById("year-from").value = state.from;
        document.getElementById("year-to").value = state.to;
        syncVenueButton();
        // A caixa da seleção também segue a URL. Ela ficava de fora, e o botão
        // voltar do navegador deixava "Brasil" escrito num mapa que já tinha
        // voltado para a visão global — as perguntas prontas, que são links,
        // tornaram isso um caminho comum em vez de um canto raro.
        teamCombo.set(state.team);
        syncYears();
        syncMode();
        syncMetricOptions();
        syncVersusOptions();
        repaint();
      }
    });

    document.getElementById("mode-total").addEventListener("click", function () {
      state.mode = "total"; syncMode(); repaint();
    });
    document.getElementById("mode-rate").addEventListener("click", function () {
      state.mode = "rate"; syncMode(); repaint();
    });

    var last = TIMELINE.years.length - 1;
    ["year-from", "year-to"].forEach(function (id, index) {
      var input = document.getElementById(id);
      input.min = 0; input.max = last; input.step = 1;
      input.value = index === 0 ? 0 : last;
      input.addEventListener("input", function () {
        // Mexer no slider durante a animação para a animação: quem arrastou quer
        // olhar aquele recorte, não ser levado para o próximo em um segundo.
        stopPlay();
        // E fecha a Copa aberta: a tela de uma edição É uma faixa de um ano só,
        // então arrastar para outro recorte já não descreve aquela edição. A
        // lista de Copas continua aberta, porque ela acompanha o recorte em vez
        // de ser um.
        state.edition = null;
        syncYears();
        repaint();
      });
    });

    wirePanels();

    var system = window.matchMedia("(prefers-color-scheme: dark)");

    document.getElementById("theme").addEventListener("click", function () {
      var root = document.documentElement;
      var currentTheme = root.getAttribute("data-theme") || (system.matches ? "dark" : "light");
      applyTheme(currentTheme === "dark" ? "light" : "dark");
    });

    // O sistema mudando de tema por conta própria (o modo noturno do Windows
    // virando na hora marcada) tem o mesmo problema das transições presas, e
    // não passa pelo botão. Se a pessoa já escolheu um tema, a escolha dela
    // manda e não há o que fazer aqui.
    var onSystem = function () {
      if (!document.documentElement.getAttribute("data-theme")) suspendTransitions();
    };
    if (system.addEventListener) system.addEventListener("change", onSystem);
    else if (system.addListener) system.addListener(onSystem);   // Safari < 14
  }

  /* Troca o tema sem deixar cor presa no caminho — ver a nota de
   * `:root.theming` na folha de estilo. */
  function suspendTransitions() {
    var root = document.documentElement;
    root.classList.add("theming");
    // Dois quadros: o primeiro aplica os valores novos com as transições
    // desligadas, o segundo devolve as transições com o valor certo já no
    // lugar. Um quadro só devolveria cedo demais e a transição pegaria a
    // mudança pela metade.
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { root.classList.remove("theming"); });
    });
  }

  function applyTheme(name) {
    suspendTransitions();
    document.documentElement.setAttribute("data-theme", name);
    // As cores vêm de variáveis CSS lidas na hora de pintar, então trocar o
    // tema exige repintar — o Leaflet não reavalia estilo sozinho.
    repaint();
  }

  // -------------------------------------------------------------------- boot

  function fail(message) {
    document.getElementById("alarm-text").textContent = message;
    document.getElementById("alarm").setAttribute("data-on", "");
  }

  function load(path) {
    return fetch(path).then(function (response) {
      if (!response.ok) throw new Error(path + " → HTTP " + response.status);
      return response.json();
    });
  }

  Promise.all([
    load("data/timeline.json"),
    load("data/metrics.json"),
    load("data/countries.geojson"),
    load("data/colors.json"),
    load("data/matches.json"),
    load("data/venues.json"),
    load("data/goals.json"),
    load("data/names.json")
  ]).then(function (loaded) {
    TIMELINE = loaded[0];
    GOLDEN = loaded[1];
    GEO = loaded[2];
    COLORS = loaded[3];
    MATCHES = loaded[4];
    VENUES = loaded[5];
    GOALS = loaded[6];
    NAMES = loaded[7];

    state.to = TIMELINE.years.length - 1;
    // A URL manda: um link compartilhado precisa abrir na visão que ele
    // descreve, não na visão padrão para só então pular para ela.
    applyURL();

    wire();
    document.getElementById("metric").value = state.metric;
    teamCombo.set(state.team);
    document.getElementById("year-from").value = state.from;
    document.getElementById("year-to").value = state.to;
    syncVenueButton();
    syncYears();
    syncMode();
    syncMetricOptions();
    syncVersusOptions();

    current.records = aggregate(state.from, state.to);
    current.scale = scaleFor(current.records, metricDef(state.metric), state.mode);
    current.metric = metricDef(state.metric);

    buildMap();
    selfCheck();
    repaint();
  }).catch(function (error) {
    // O comando é `python serve.py`, e não o `python -m http.server` que esta
    // linha indicava: em HTTP/1.0 o servidor padrão derruba o countries.geojson
    // no meio da transferência, e a página abre sem nenhum país no mapa. O
    // porquê inteiro está em `serve.py`.
    fail("Não consegui carregar os dados (" + error.message + "). Esta página precisa " +
         "de um servidor HTTP — abrir o arquivo direto do disco esbarra na política " +
         "de origem do navegador. Rode `python serve.py` na raiz do repositório.");
  });
})();
