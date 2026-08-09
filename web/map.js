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
  var RATE = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var PCT = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  /* As métricas do mapa. Cada uma declara três coisas que mudam o comportamento:
   *
   *   kind  'sequential' (magnitude, um matiz) ou 'diverging' (polaridade, dois
   *         matizes com cinza no meio). Só o saldo é divergente — é a única com
   *         lado negativo, e uma rampa sequencial esconderia o sinal.
   *   rate  se a leitura "por partida" faz sentido. Aproveitamento já é uma
   *         taxa; partidas jogadas por partida seria 1; título por partida não
   *         significa nada. Nesses casos o botão desliga em vez de mentir.
   *   h2h   se a métrica existe em confronto direto. "Títulos", "participações"
   *         e "partidas recebidas" não existem: um título não é ganho *contra*
   *         alguém, e uma sede não joga.
   */
  var METRICS = [
    { key: "goals",            label: "Gols marcados",     kind: "sequential", rate: true,  h2h: true },
    { key: "conceded",         label: "Gols sofridos",     kind: "sequential", rate: true,  h2h: true },
    { key: "goal_difference",  label: "Saldo de gols",     kind: "diverging",  rate: true,  h2h: true },
    { key: "wins",             label: "Vitórias",          kind: "sequential", rate: true,  h2h: true },
    { key: "win_pct",          label: "Aproveitamento",    kind: "sequential", rate: false, h2h: true, pct: true },
    { key: "matches_played",   label: "Partidas jogadas",  kind: "sequential", rate: false, h2h: true },
    // `place`: descreve o LUGAR, não a seleção. Uma sede não joga — o Catar
    // recebeu 64 partidas e disputou 6 —, então tudo que fala do desempenho da
    // seleção sai de cena quando esta métrica está escolhida.
    { key: "matches_received", label: "Partidas recebidas",kind: "sequential", rate: false, h2h: false, place: true },
    { key: "titles",           label: "Títulos",           kind: "sequential", rate: false, h2h: false },
    { key: "participations",   label: "Participações",     kind: "sequential", rate: false, h2h: false }
  ];

  var FIELDS = ["goals", "conceded", "goal_difference", "wins", "draws", "losses",
                "matches_played", "matches_received", "titles", "participations"];

  var state = {
    metric: "goals", mode: "total", team: null, from: 0, to: 0,
    versus: null,     // segunda seleção, para a comparação lado a lado
    view: null,       // null = padrão; "matches" = detalhamento de partidas
    opponent: null,   // adversário do detalhamento, quando veio de um confronto
    venues: false     // camada de sedes
  };

  var TIMELINE = null, GOLDEN = null, GEO = null, COLORS = null;
  var MATCHES = null, VENUES = null;
  var map = null, layer = null, venueLayer = null, byTeam = {};
  var current = { records: null, scale: null, metric: null };

  // ---------------------------------------------------------------- utilidades

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
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
      var extent = 0;
      values.forEach(function (x) { extent = Math.max(extent, Math.abs(x)); });
      return { kind: "diverging", extent: extent,
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
      var arm = value < 0 ? scale.negative : scale.positive;
      return sample(arm, Math.sqrt(Math.abs(value) / scale.extent));
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
    var lines = "<b>" + team + "</b>";

    if (state.team && team === state.team) {
      return lines + tipLine("seleção escolhida");
    }
    if (!rec) {
      return lines + tipLine(state.team ? "nunca enfrentou " + state.team
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
    if (def.key !== "matches_played" && !def.place) {
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
    syncURL();
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
   * O raio cresce com a raiz da contagem, não com ela: área é o que o olho
   * compara num círculo, e área cresce com o quadrado do raio. Sem a raiz, uma
   * sede com 24 partidas pareceria vinte e quatro vezes maior que uma com uma. */
  function venueCounts(from, to) {
    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var counts = {};
    MATCHES.rows.forEach(function (row) {
      if (row[0] < firstYear || row[0] > lastYear || row[6] < 0) return;
      counts[row[6]] = (counts[row[6]] || 0) + 1;
    });
    return counts;
  }

  function drawVenues() {
    if (venueLayer) { map.removeLayer(venueLayer); venueLayer = null; }
    if (!state.venues) return;

    var counts = venueCounts(state.from, state.to);
    var accent = css("--accent");
    venueLayer = L.layerGroup();

    VENUES.rows.forEach(function (row, index) {
      var hosted = counts[index];
      if (!hosted) return;   // sede fora da faixa de anos escolhida
      var marker = L.circleMarker([row[0], row[1]], {
        radius: 3 + Math.sqrt(hosted) * 1.9,
        color: accent, weight: 1.5, opacity: .9,
        fillColor: accent, fillOpacity: .35
      });
      marker.bindTooltip(
        "<b>" + row[5] + "</b>" +
        tipLine(row[6] + " · " + row[7]) +
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
    if (state.from !== 0 || state.to !== TIMELINE.years.length - 1) {
      parts.push("y=" + TIMELINE.years[state.from] + "-" + TIMELINE.years[state.to]);
    }
    if (state.venues) parts.push("sedes=1");
    if (state.view === "matches") {
      parts.push("jogos=" + (state.opponent ? encodeURIComponent(state.opponent) : "1"));
    }
    return parts.join("&");
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
    if (!raw) return false;
    var params = {};
    raw.split("&").forEach(function (pair) {
      var bits = pair.split("=");
      if (bits[0]) params[bits[0]] = decodeURIComponent(bits.slice(1).join("=") || "");
    });

    var known = {};
    TIMELINE.teams.forEach(function (name) { known[name] = true; });

    if (params.m && metricDef(params.m).key === params.m) state.metric = params.m;
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
      // Barra espelhada: o zero fica no meio e cada braço cresce para fora, de
      // modo que −15 e +15 ficam à mesma distância do centro.
      gradient = gradientOf(scale.negative.slice().reverse(), 0, 0.5) + ", " +
                 gradientOf(scale.positive, 0.5, 1);
      mark(0.5, "0");
      niceTicks(scale.extent, 3).slice(1).forEach(function (value) {
        var offset = 0.5 * Math.sqrt(value / scale.extent);
        mark(0.5 - offset, "−" + edge(value));
        mark(0.5 + offset, "+" + edge(value));
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
      messages.push("O saldo mantém os dois polos fixos mesmo com uma seleção escolhida: " +
                    "se o lado positivo mudasse de cor a cada país, “negativo” deixaria " +
                    "de ter cor.");
    } else if (state.team) {
      messages.push("A rampa é a cor de " + state.team + ".");
    }
    if (state.mode === "rate" && def.rate) {
      messages.push("Seleções com menos de " + TIMELINE.per_match_floor +
                    " partidas na faixa saem do mapa: a média não seria comparável.");
    }
    if (state.team) {
      messages.push(state.team + " aparece contornada, não pintada — ninguém joga contra si mesmo.");
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

  /* As partidas de uma seleção na faixa escolhida, opcionalmente contra um
   * adversário só. Devolve o mais recente primeiro. */
  function matchesFor(team, opponent, from, to) {
    if (!matchIndex) indexMatches();
    var firstYear = TIMELINE.years[from], lastYear = TIMELINE.years[to];
    var out = [];

    (matchIndex[team] || []).forEach(function (position) {
      var row = MATCHES.rows[position];
      if (row[0] < firstYear || row[0] > lastYear) return;

      var home = MATCHES.teams[row[2]], away = MATCHES.teams[row[3]];
      var atHome = home === team;
      var other = atHome ? away : home;
      if (opponent && other !== opponent) return;

      var pens = row[8];
      out.push({
        year: row[0],
        stage: MATCHES.stages[row[1]],
        date: row[7],
        opponent: other,
        home: atHome,
        goalsFor: atHome ? row[4] : row[5],
        goalsAgainst: atHome ? row[5] : row[4],
        pensFor: pens ? (atHome ? pens[0] : pens[1]) : null,
        pensAgainst: pens ? (atHome ? pens[1] : pens[0]) : null,
        venue: row[6] >= 0 ? MATCHES.venues[row[6]] : null
      });
    });

    out.forEach(function (match) {
      match.result = resultOf(match.goalsFor, match.goalsAgainst,
                              match.pensFor, match.pensAgainst);
    });
    return out.sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; });
  }

  var STAGE_SHORT = {
    "group stage": "Grupos", "second group stage": "2ª fase de grupos",
    "round of 32": "32-avos", "round of 16": "Oitavas", "quarter-finals": "Quartas",
    "semi-finals": "Semi", "third-place match": "3º lugar",
    "final": "Final", "final round": "Quadrangular"
  };

  function matchRows(list) {
    if (!list.length) return '<p class="empty">Nenhuma partida nesta faixa.</p>';
    var html = '<div class="matches">';
    list.forEach(function (match) {
      var score = match.goalsFor + "–" + match.goalsAgainst;
      var pens = match.pensFor === null ? "" :
                 ' <em class="pens">(' + match.pensFor + "–" + match.pensAgainst + " p)</em>";
      html += '<div class="match">' +
        '<span class="res res-' + match.result + '">' + match.result + "</span>" +
        '<span class="match-main">' +
          '<b>' + score + pens + "</b> " + (match.home ? "vs " : "em ") + match.opponent +
          '<span class="match-sub">' + match.year + " · " + (STAGE_SHORT[match.stage] || match.stage) +
          (match.venue ? " · " + match.venue.city : "") + "</span>" +
        "</span></div>";
    });
    return html + "</div>";
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
      var quem = !left ? state.team : state.versus;
      return '<div class="sub">' + span + "</div><h2>" + state.team + " × " + state.versus +
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

    var html = '<div class="sub">' + span + "</div>" +
      "<h2>" + badge(state.team, null) + state.team + " <span class='vs'>×</span> " +
      badge(state.versus, null) + state.versus + "</h2>" +
      '<table class="compare"><tbody>';

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
      html += '<p class="muted">' + state.team + " " + sums.wins + "–" + sums.draws + "–" +
              sums.losses + " " + state.versus + " · " + sums.goals + "–" + sums.conceded +
              " em gols.</p>" + matchRows(duels);
    } else {
      html += '<p class="empty">Nunca se enfrentaram em Copas do Mundo.</p>';
    }
    return html + "</div>";
  }

  function drawPanel() {
    var def = current.metric, panel = document.getElementById("panel");
    var span = TIMELINE.years[state.from] + "–" + TIMELINE.years[state.to];
    var rows = [], name, html;

    // A barra do cartão diz o que ele contém mesmo recolhido — é a única pista
    // que sobra quando o painel está fechado.
    document.getElementById("side-title").textContent =
      state.versus ? "⚔️ " + state.team + " × " + state.versus
      : state.team ? "📋 " + state.team : "📋 Ranking";

    // --- detalhamento: as partidas que formam o número -----------------
    if (state.view === "matches" && state.team) {
      var list = matchesFor(state.team, state.opponent, state.from, state.to);
      var sums = tally(list);
      panel.innerHTML =
        '<div class="sub">' + span + '</div>' +
        '<button class="back" type="button" data-back="1">← voltar</button>' +
        '<h2>' + badge(state.team, null) + state.team +
        (state.opponent ? " × " + state.opponent : "") + "</h2>" +
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
        panel.innerHTML = '<div class="sub">' + span + '</div><h2>' + state.team + '</h2>' +
          '<p class="empty">Não disputou nenhuma partida nesta faixa de edições.</p>';
        return;
      }
      // O ponto colorido não é enfeite: ele diz de onde veio a cor do mapa. A
      // regra da tabela é "a camisa da última Copa que a seleção disputou", e o
      // ano ao lado é o que torna isso verificável em vez de decorativo.
      var identity = COLORS.teams[state.team];
      html = '<div class="sub">' + span + '</div>' +
        '<h2>' + badge(state.team, null) + state.team + '</h2>' +
        (identity ? '<div class="sub" style="margin-top:-.5rem">Cor da camisa em ' +
                    identity.last_cup + '</div>' : '') +
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
        return y - x || a[0].localeCompare(b[0]);
      });

      html += '<button class="back" type="button" data-matches="1">' +
        "Ver as " + NUM.format(totals.matches_played) + " partidas →</button>";

      html += '<div><div class="sub">Confrontos diretos · ' + rows.length + ' adversários</div>' +
        '<div class="h2h-scroll"><table><thead><tr><th>Adversário</th><th>' +
        def.label + '</th><th>J</th><th>V–E–D</th></tr></thead><tbody>';
      rows.forEach(function (entry) {
        var rec = entry[1], value = valueOf(rec, def, state.mode);
        // A linha inteira abre o detalhamento daquele confronto: é o gesto que
        // liga "21 gols em 7 jogos" às sete partidas que produziram o número.
        html += '<tr class="drill" data-opponent="' + entry[0] + '" tabindex="0">' +
          '<td>' + badge(entry[0], value) + entry[0] + '</td>' +
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
      return y - x || a[0].localeCompare(b[0]);
    });

    var painted = rows.filter(function (entry) {
      return valueOf(entry[1], def, state.mode) !== null;
    });

    html = '<div class="sub">' + span + '</div><h2>Visão global</h2>' +
      '<div class="tiles">' +
        tile(NUM.format(rows.length), "Seleções") +
        tile(NUM.format(state.to - state.from + 1), "Edições") +
        tile(NUM.format(painted.length), "No mapa") +
      '</div>' +
      '<div><div class="sub">Ranking · ' + def.label +
      (state.mode === "rate" && def.rate ? " por partida" : "") + '</div>' +
      '<div class="h2h-scroll"><table><thead><tr><th>#</th><th>Seleção</th><th>' +
      def.label + "</th>" + (def.place ? "" : "<th>J</th>") + "</tr></thead><tbody>";
    rows.slice(0, 30).forEach(function (entry, index) {
      var rec = entry[1], value = valueOf(rec, def, state.mode);
      html += '<tr><td>' + (index + 1) + '</td>' +
        '<td>' + badge(entry[0], value) + entry[0] + '</td>' +
        '<td>' + format(value, def, state.mode) + "</td>" +
        // A coluna de jogos sai junto com a linha do tooltip, e pelo mesmo
        // motivo: em "partidas recebidas" ela fala de outra coisa.
        (def.place ? "" : "<td>" + NUM.format(rec.matches_played) + "</td>") + "</tr>";
    });
    html += '</tbody></table></div><p class="muted" style="margin-top:.5rem">' +
      'Clique num país do mapa para ver os confrontos diretos dele.</p></div>';
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
    // confronto que não é mais o atual, e uma comparação com ela mesma.
    state.view = null;
    state.opponent = null;
    if (state.versus === state.team) state.versus = null;
    document.getElementById("team").value = state.team || "";
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
    var picker = document.getElementById("versus");
    var options = picker.options;
    for (var i = 0; i < options.length; i++) {
      options[i].disabled = Boolean(options[i].value) && options[i].value === state.team;
    }
    picker.disabled = !state.team;
    picker.title = state.team ? "" : "Escolha um país primeiro";
    if (!state.team) state.versus = null;
    picker.value = state.versus || "";
  }

  function selectVersus(team) {
    state.versus = team || null;
    state.view = null;
    state.opponent = null;
    syncVersusOptions();
    repaint();
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

  /* No modo de país, três métricas deixam de existir. Em vez de deixá-las
   * escolhíveis e mostrar um mapa vazio, elas ficam desabilitadas — e se uma
   * delas estava escolhida, a troca é anunciada no lugar de acontecer calada. */
  function syncMetricOptions() {
    var picker = document.getElementById("team");
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
    picker.value = chosen || "";
    return swapped;
  }

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

  function recall() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      return raw ? raw.split(",").filter(Boolean) : [];
    } catch (error) { return []; }
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
    button.setAttribute("aria-pressed", String(every));
    button.title = every ? "Mostrar todos os painéis" : "Recolher todos os painéis";
    // Sem painéis abertos não há o que a barra de ferramentas precise evitar.
    document.querySelector(".ui").classList.toggle("bare", every);
  }

  function wirePanels() {
    var saved = recall();
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

  function syncMode() {
    var def = metricDef(state.metric);
    var rate = document.getElementById("mode-rate");
    rate.disabled = !def.rate;
    if (!def.rate && state.mode === "rate") state.mode = "total";
    document.getElementById("mode-total").setAttribute("aria-pressed", String(state.mode !== "rate"));
    rate.setAttribute("aria-pressed", String(state.mode === "rate"));
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
    document.getElementById("read-count").textContent =
      count + (count === 1 ? " edição" : " edições");

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

    var team = document.getElementById("team");
    var none = document.createElement("option");
    none.value = "";
    none.textContent = "Nenhum — visão global";
    team.appendChild(none);
    // Só as seleções que de fato jogaram: `TIMELINE.teams` inclui países-sede,
    // e no dado masculino todos jogaram, mas a conferência é barata.
    var played = {};
    TIMELINE.rows.forEach(function (row) { played[TIMELINE.teams[row[1]]] = 1; });
    Object.keys(played).sort(function (a, b) { return a.localeCompare(b); })
      .forEach(function (name) {
        var option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        team.appendChild(option);
      });
    team.addEventListener("change", function () { select(team.value); });

    // O seletor de comparação recebe a mesma lista. Ele é preenchido a partir do
    // primeiro para as duas listas nunca divergirem.
    var versus = document.getElementById("versus");
    var blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Ninguém — sem comparação";
    versus.appendChild(blank);
    Array.prototype.slice.call(team.options, 1).forEach(function (option) {
      var copy = document.createElement("option");
      copy.value = option.value;
      copy.textContent = option.value;
      versus.appendChild(copy);
    });
    versus.addEventListener("change", function () { selectVersus(versus.value); });

    document.getElementById("layer-venues").addEventListener("click", function () {
      state.venues = !state.venues;
      this.setAttribute("aria-pressed", String(state.venues));
      repaint();
    });

    /* Um só ouvinte no painel, em vez de um por linha: o painel é reescrito
     * inteiro a cada repintura, e ouvintes presos às linhas morreriam junto. */
    document.getElementById("panel").addEventListener("click", function (event) {
      var back = event.target.closest("[data-back]");
      if (back) { closeMatches(); return; }
      var all = event.target.closest("[data-matches]");
      if (all) { openMatches(null); return; }
      var row = event.target.closest("[data-opponent]");
      if (row) openMatches(row.getAttribute("data-opponent"));
    });
    document.getElementById("panel").addEventListener("keydown", function (event) {
      if (event.key !== "Enter" && event.key !== " ") return;
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
        document.getElementById("layer-venues").setAttribute("aria-pressed", String(state.venues));
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
      input.addEventListener("input", function () { syncYears(); repaint(); });
    });

    wirePanels();

    document.getElementById("theme").addEventListener("click", function () {
      var root = document.documentElement;
      var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      var currentTheme = root.getAttribute("data-theme") || (dark ? "dark" : "light");
      root.setAttribute("data-theme", currentTheme === "dark" ? "light" : "dark");
      // As cores vêm de variáveis CSS lidas na hora de pintar, então trocar o
      // tema exige repintar — o Leaflet não reavalia estilo sozinho.
      repaint();
    });
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
    load("data/venues.json")
  ]).then(function (loaded) {
    TIMELINE = loaded[0];
    GOLDEN = loaded[1];
    GEO = loaded[2];
    COLORS = loaded[3];
    MATCHES = loaded[4];
    VENUES = loaded[5];

    state.to = TIMELINE.years.length - 1;
    // A URL manda: um link compartilhado precisa abrir na visão que ele
    // descreve, não na visão padrão para só então pular para ela.
    applyURL();

    wire();
    document.getElementById("metric").value = state.metric;
    document.getElementById("team").value = state.team || "";
    document.getElementById("year-from").value = state.from;
    document.getElementById("year-to").value = state.to;
    document.getElementById("layer-venues").setAttribute("aria-pressed", String(state.venues));
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
    fail("Não consegui carregar os dados (" + error.message + "). Esta página precisa " +
         "de um servidor HTTP — abrir o arquivo direto do disco esbarra na política " +
         "de origem do navegador. Rode `python -m http.server` dentro de `web/`.");
  });
})();
