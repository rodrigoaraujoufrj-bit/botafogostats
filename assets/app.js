/* Dashboard da campanha do Botafogo — lê data/dashboard.json (gerado por scripts/coletar.py). */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const TZ = "America/Sao_Paulo";
  const num = (v, casas = 0) =>
    v == null ? "–" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const pct = (v, casas = 1) => (v == null ? "–" : `${num(v, casas)}%`);
  const sinal = (v) => (v == null ? "–" : v > 0 ? `+${v}` : `${v}`);
  const dataCurta = (iso) =>
    new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", timeZone: TZ }).replace(".", "");
  const dataHora = (iso) =>
    new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: TZ });
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const img = (src, alt = "") => (src ? `<img src="${esc(src)}" alt="${esc(alt)}" loading="lazy" onerror="this.remove()">` : "");
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const NOME_RES = { V: "Vitória", E: "Empate", D: "Derrota" };

  let D = null;
  let recorte = "todos";
  const graficos = {};

  // ------------------------------------------------------------------------
  // Carga
  // ------------------------------------------------------------------------
  fetch(`data/dashboard.json?v=${Date.now()}`)
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then((dados) => {
      D = dados;
      renderTudo();
      ligarEventos();
      revelar();
    })
    .catch((e) => {
      const el = $("erro");
      el.hidden = false;
      el.textContent = `Não foi possível carregar os dados (${e.message}). Rode a coleta para gerar data/dashboard.json.`;
    });

  function renderTudo() {
    renderHero();
    renderRecorte();
    renderCenarios();
    renderGraficos();
    renderMandos();
    renderChegada();
    renderJogoAJogo();
    renderClassificacao();
  }

  function ligarEventos() {
    document.querySelectorAll(".segmento button").forEach((b) =>
      b.addEventListener("click", () => {
        recorte = b.dataset.recorte;
        document.querySelectorAll(".segmento button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
        renderRecorte();
      })
    );
    $("busca").addEventListener("input", renderTabelaJogos);
    $("c-meta").addEventListener("input", renderAlvo);
    // Recolore os gráficos quando o tema do sistema muda
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      renderGraficos();
      renderRecorte();
    });
  }

  function revelar() {
    if (!("IntersectionObserver" in window)) return;
    const obs = new IntersectionObserver(
      (itens) => itens.forEach((i) => i.isIntersecting && (i.target.classList.add("visivel"), obs.unobserve(i.target))),
      { threshold: 0.08 }
    );
    document.querySelectorAll(".secao").forEach((s) => {
      s.classList.add("revelar");
      obs.observe(s);
    });
  }

  // ------------------------------------------------------------------------
  // Hero
  // ------------------------------------------------------------------------
  function renderHero() {
    const r = D.recortes.todos.resumo;
    if (D.time.escudo) {
      $("escudo").src = D.time.escudo;
      $("escudo").hidden = false;
    }
    $("h-temporada").textContent = D.temporada;
    $("h-pos").textContent = D.posicao ?? "–";
    $("h-pontos").textContent = `${r.pontos} pts`;
    $("h-jogos").textContent = `${r.jogos} de 38`;
    $("h-periodo").textContent = D.periodo.inicio ? `${dataCurta(D.periodo.inicio)} a ${dataCurta(D.periodo.fim)}` : "–";
    $("h-atualizado").textContent = D.atualizado_em ? dataHora(D.atualizado_em) : "–";
  }

  // ------------------------------------------------------------------------
  // Blocos que mudam com o filtro Todos / Casa / Fora
  // ------------------------------------------------------------------------
  function renderRecorte() {
    const R = D.recortes[recorte];
    const r = R.resumo;
    const rotulo = { todos: "geral", casa: "em casa", fora: "fora" }[recorte];

    // KPIs
    $("k-aprov-tag").textContent = rotulo;
    $("k-aprov").textContent = pct(r.aproveitamento);
    $("k-aprov-barra").style.width = `${r.aproveitamento ?? 0}%`;
    $("k-aprov-nota").textContent = `${r.pontos} de ${r.jogos * 3} pontos possíveis`;
    $("k-v").textContent = r.vitorias;
    $("k-e").textContent = r.empates;
    $("k-d").textContent = r.derrotas;
    $("k-media").textContent = num(r.media_pontos, 2);
    $("k-media-barra").style.width = `${((r.media_pontos ?? 0) / 3) * 100}%`;
    $("k-saldo").textContent = sinal(r.saldo);
    $("k-gp").textContent = r.gols_pro;
    $("k-gc").textContent = r.gols_contra;

    // Resultados
    $("r-aprov").textContent = pct(r.aproveitamento);
    $("r-lista").innerHTML = ["V", "E", "D"]
      .map((k) => {
        const n = { V: r.vitorias, E: r.empates, D: r.derrotas }[k];
        return `<li><i class="ponto ${k}"></i><span>${NOME_RES[k]}s</span><span class="pct">${pct(r.jogos ? (100 * n) / r.jogos : null)}</span><b>${n}</b></li>`;
      })
      .join("");
    $("r-taxa").textContent = pct(r.taxa_vitoria);
    $("r-invicto").textContent = pct(r.sem_derrota);
    const u5 = R.sequencias.ultimos5;
    $("r-forma").innerHTML = u5.resultados.map((x) => `<span class="chip ${x}" title="${NOME_RES[x]}">${x}</span>`).join("");
    $("r-forma-pts").textContent = `${u5.pontos}/${u5.disputados} pts`;
    donut(r);

    // Sequências
    const s = R.sequencias;
    $("j-seqs").innerHTML = [
      ["bom", "Regularidade", s.maior_invicta, "jogos", "Maior sequência invicta"],
      ["bom", "Vitórias", s.maior_vitorias, "jogos", "Maior sequência de vitórias"],
      ["ruim", "Jejum", s.maior_sem_vencer, "jogos", "Maior sequência sem vencer"],
      ["neutro", "Solidez defensiva", s.sem_sofrer_gol, `de ${r.jogos}`, "Jogos sem sofrer gol"],
      ["", "Momento recente", u5.pontos, `de ${u5.disputados} pts`, "Pontos nos últimos 5 jogos"],
    ]
      .map(([c, t, v, u, d]) => `<div class="seq ${c}"><span>${t}</span><b>${v}<small>${u}</small></b><p>${d}</p></div>`)
      .join("");

    renderIntervalo(R);
    renderTabelaJogos();
  }

  function donut(r) {
    const dados = [r.vitorias, r.empates, r.derrotas];
    const cores = [css("--bom"), css("--neutro"), css("--ruim")];
    if (graficos.donut) {
      graficos.donut.data.datasets[0].data = dados;
      graficos.donut.data.datasets[0].backgroundColor = cores;
      graficos.donut.data.datasets[0].borderColor = css("--card");
      graficos.donut.update();
      return;
    }
    graficos.donut = new Chart($("g-donut"), {
      type: "doughnut",
      data: { labels: ["Vitórias", "Empates", "Derrotas"], datasets: [{ data: dados, backgroundColor: cores, borderColor: css("--card"), borderWidth: 3, borderRadius: 4 }] },
      options: { cutout: "74%", plugins: { legend: { display: false }, tooltip: tooltip() }, animation: { duration: 600 } },
    });
  }

  function renderIntervalo(R) {
    const t = R.tempos;
    const iv = R.intervalo;
    const max = Math.max(1, t.primeiro.pro, t.primeiro.contra, t.segundo.pro, t.segundo.contra);
    const cartao = (nome, sub, x) => `
      <div class="tempo">
        <div class="tempo-topo"><div><h4>${nome}</h4><span class="nota">${sub}</span></div>
          <span class="tag ${x.saldo > 0 ? "bom" : x.saldo < 0 ? "ruim" : ""}">${sinal(x.saldo)} saldo</span></div>
        <div class="placar"><div><b>${x.pro}</b><span>marcados</span></div><i>×</i><div><b>${x.contra}</b><span>sofridos</span></div></div>
        <div class="barras-tempo">
          <div><span>Pró</span><div class="t"><span style="width:${(100 * x.pro) / max}%"></span></div><b>${x.pro}</b></div>
          <div><span>Contra</span><div class="t contra"><span style="width:${(100 * x.contra) / max}%"></span></div><b>${x.contra}</b></div>
        </div>
        <div class="participacao"><span>Participação nos gols marcados</span><b>${pct(x.participacao_pro)}</b></div>
      </div>`;
    $("t-tempos").innerHTML = cartao("1º tempo", "até o intervalo", t.primeiro) + cartao("2º tempo", "após o intervalo", t.segundo);

    const prod = t.primeiro.pro === t.segundo.pro ? "Equilibrado" : t.primeiro.pro > t.segundo.pro ? "1º tempo" : "2º tempo";
    const vuln = t.primeiro.contra === t.segundo.contra ? "Equilibrado" : t.primeiro.contra > t.segundo.contra ? "1º tempo" : "2º tempo";
    $("t-tiles").innerHTML = [
      ["", "Mais produtivo", prod, "", "tempo com mais gols marcados"],
      ["ruim", "Mais vulnerável", vuln, "", "tempo com mais gols sofridos"],
      ["", "Mudança após o intervalo", `${iv.melhoraram} ↑ · ${iv.pioraram} ↓`, "", `${iv.melhoraram} jogos melhoraram, ${iv.pioraram} pioraram`],
      [iv.saldo_pontos >= 0 ? "bom" : "ruim", "Saldo das reações", `${sinal(iv.saldo_pontos)}`, "pts", "pontos finais menos pontos no intervalo"],
    ]
      .map(([c, t1, v, u, d]) => `<div class="seq ${c}"><span>${t1}</span><b>${v}<small>${u}</small></b><p>${d}</p></div>`)
      .join("");

    // Matriz intervalo x final
    const linhas = { V: "Vencendo", E: "Empatando", D: "Perdendo" };
    const cols = { V: "Venceu", E: "Empatou", D: "Perdeu" };
    const valores = Object.values(iv.matriz).flatMap((o) => Object.values(o));
    const mx = Math.max(1, ...valores);
    const seq = ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4"].map(css);
    const cor = (v) => (v === 0 ? seq[0] : seq[Math.min(4, 1 + Math.floor((3 * v) / mx))]);
    const tinta = (v) => (v === 0 ? css("--tinta-3") : Math.min(4, 1 + Math.floor((3 * v) / mx)) >= 3 ? css("--card") : css("--tinta"));
    $("t-matriz").innerHTML = `<table class="matriz"><thead><tr><th></th>${Object.values(cols).map((c) => `<th scope="col">${c}</th>`).join("")}</tr></thead><tbody>${Object.entries(linhas)
      .map(
        ([k, n]) =>
          `<tr><th scope="row">${n}</th>${["V", "E", "D"]
            .map((c) => {
              const v = iv.matriz[k][c];
              return `<td style="background:${cor(v)};color:${tinta(v)}" title="${n} no intervalo e ${cols[c].toLowerCase()}: ${v} jogo(s)">${v}</td>`;
            })
            .join("")}</tr>`
      )
      .join("")}</tbody></table>`;

    const n = iv.melhoraram + iv.pioraram + iv.mantiveram;
    $("t-leitura").innerHTML = n
      ? `<b>Leitura por tempo:</b> em ${n} jogos, o Botafogo terminou melhor do que estava no intervalo em <b>${iv.melhoraram}</b>, pior em <b>${iv.pioraram}</b> e manteve a situação em ${iv.mantiveram}. ` +
        `Viradas: ${iv.viradas_a_favor} a favor e ${iv.viradas_contra} contra. O segundo tempo ${iv.saldo_pontos >= 0 ? "rendeu" : "custou"} <b>${Math.abs(iv.saldo_pontos)} pontos</b> em relação ao placar do intervalo.`
      : "Sem jogos com placar do intervalo neste recorte.";
  }

  // ------------------------------------------------------------------------
  // Cenários (simulação)
  // ------------------------------------------------------------------------
  function nivel(p, invertido = false) {
    const t = p < 5 ? "baixa" : p < 30 ? "moderada" : p < 70 ? "alta" : "muito alta";
    const ruimSeAlta = invertido ? (p >= 30 ? "ruim" : "") : "";
    return { t, c: ruimSeAlta };
  }

  function renderCenarios() {
    const S = D.simulacao;
    if (!S) {
      $("cen-grade").hidden = true;
      $("cen-dist-card").hidden = true;
      $("cen-vazio").hidden = false;
      return;
    }
    $("cen-titulo").textContent = `As ${D.jogos_restantes} rodadas finais`;
    $("cen-nota").textContent = `Probabilidades estimadas em ${num(S.simulacoes)} simulações dos ${S.jogos_restantes_liga} jogos restantes do campeonato, com base nos gols marcados e sofridos de cada time em casa e fora.`;
    const set = (id, p, inv = false) => {
      $(id).textContent = pct(p);
      $(`${id}-barra`).style.width = `${Math.max(p, p > 0 ? 1 : 0)}%`;
      const n = nivel(p, inv);
      $(`${id}-tag`).textContent = n.t;
      $(`${id}-tag`).className = `tag ${n.c}`;
    };
    set("p-titulo", S.prob.titulo);
    set("p-g4", S.prob.g4);
    set("p-z4", S.prob.z4, true);
    $("p-g6").textContent = `Top 6: ${pct(S.prob.g6)} · 7º ao 12º: ${pct(S.prob.sul_americana)}`;

    const P = S.pontos;
    $("p-faixa").textContent = `${P.p25}–${P.p75}`;
    const pos = (v) => (P.max === P.min ? 50 : (100 * (v - P.min)) / (P.max - P.min));
    $("p-faixa-vis").innerHTML = `<div class="base"></div><div class="miolo" style="left:${pos(P.p25)}%;width:${pos(P.p75) - pos(P.p25)}%"></div>
      <div class="med" style="left:${pos(P.mediana)}%" title="Mediana: ${P.mediana} pts"></div>
      <span class="ext" style="left:0">${P.min}</span><span class="ext" style="right:0">${P.max}</span>`;
    $("p-faixa-nota").textContent = `Metade das simulações termina nessa faixa. Mediana: ${P.mediana} pontos.`;
    $("dist-nota").textContent = `Posição mais provável: ${S.posicao_mais_provavel}º`;
  }

  // ------------------------------------------------------------------------
  // Gráficos de linha / barras (Chart.js)
  // ------------------------------------------------------------------------
  function tooltip(extra = {}) {
    return {
      backgroundColor: css("--tinta"),
      titleColor: css("--card"),
      bodyColor: css("--card"),
      padding: 10,
      cornerRadius: 10,
      displayColors: true,
      boxWidth: 8,
      boxHeight: 8,
      usePointStyle: true,
      titleFont: { family: "Inter", weight: "600" },
      bodyFont: { family: "Inter" },
      ...extra,
    };
  }

  function eixos(yExtra = {}) {
    const cor = css("--tinta-3");
    return {
      x: { grid: { display: false }, border: { color: css("--eixo") }, ticks: { color: cor, font: { family: "Inter", size: 11 }, maxRotation: 0, autoSkipPadding: 12 } },
      y: { grid: { color: css("--linha") }, border: { display: false }, ticks: { color: cor, font: { family: "Inter", size: 11 }, precision: 0 }, ...yExtra },
    };
  }

  // Rótulo no fim de cada série (identidade sem depender só da cor)
  const rotulosFinais = {
    id: "rotulosFinais",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      ctx.save();
      ctx.font = "600 11px Inter, sans-serif";
      ctx.textBaseline = "middle";
      const usados = [];
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.hidden || !ds.rotuloFinal) return;
        const p = meta.data[meta.data.length - 1];
        if (!p) return;
        let y = p.y;
        while (usados.some((u) => Math.abs(u - y) < 13)) y += 13;
        usados.push(y);
        ctx.fillStyle = ds.corRotulo || css("--tinta-3");
        ctx.fillText(ds.rotuloFinal, p.x + 8, y);
      });
      ctx.restore();
    },
  };

  // Faixas G4 e Z4 no gráfico de posição
  const faixasPosicao = {
    id: "faixasPosicao",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: a, scales } = chart;
      const y = scales.y;
      const faixa = (de, ate, cor, texto) => {
        const y1 = y.getPixelForValue(de - 0.5);
        const y2 = y.getPixelForValue(ate + 0.5);
        ctx.fillStyle = cor;
        ctx.fillRect(a.left, Math.min(y1, y2), a.right - a.left, Math.abs(y2 - y1));
        ctx.fillStyle = css("--tinta-3");
        ctx.font = "600 10px Inter, sans-serif";
        ctx.textAlign = "right";
        ctx.textBaseline = "middle";
        ctx.fillText(texto, a.right - 6, (y1 + y2) / 2);
      };
      ctx.save();
      faixa(1, 4, css("--acento-suave"), "G4");
      faixa(17, 20, css("--ruim-suave"), "Z4");
      ctx.restore();
    },
  };

  function renderGraficos() {
    Object.entries(graficos).forEach(([k, g]) => {
      if (k !== "donut") {
        g.destroy();
        delete graficos[k];
      }
    });
    if (graficos.donut) {
      graficos.donut.destroy();
      delete graficos.donut;
    }
    Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    Chart.defaults.color = css("--tinta-3");

    const ev = D.evolucao;
    const rotulos = ev.map((e) => `R${e.rodada}`);
    const acento = css("--acento");
    const ref = css("--ref");

    // Evolução dos pontos
    const ctx = $("g-pontos").getContext("2d");
    const grad = ctx.createLinearGradient(0, 0, 0, 300);
    grad.addColorStop(0, css("--acento-suave").replace(/[\d.]+\)$/, "0.14)"));
    grad.addColorStop(1, css("--acento-suave").replace(/[\d.]+\)$/, "0)"));
    const linhaRef = (label, campo, dash, rot) => ({
      label, data: ev.map((e) => e[campo]), borderColor: ref, borderWidth: 1.5, borderDash: dash,
      pointRadius: 0, pointHoverRadius: 4, cubicInterpolationMode: "monotone", rotuloFinal: rot,
    });
    graficos.pontos = new Chart(ctx, {
      type: "line",
      data: {
        labels: rotulos,
        datasets: [
          {
            label: "Botafogo", data: ev.map((e) => e.pontos), borderColor: acento, backgroundColor: grad, fill: true,
            borderWidth: 2.5, cubicInterpolationMode: "monotone", pointRadius: (c) => (c.dataIndex === ev.length - 1 ? 5 : 0),
            pointBackgroundColor: acento, pointBorderColor: css("--card"), pointBorderWidth: 2, pointHoverRadius: 5,
            rotuloFinal: `${ev.at(-1)?.pontos ?? ""} pts`, corRotulo: css("--tinta"), order: 0,
          },
          linhaRef("Líder", "pontos_lider", [], "Líder"),
          linhaRef("4º colocado", "pontos_g4", [6, 4], "4º"),
          linhaRef("17º colocado", "pontos_z4", [2, 3], "17º"),
        ],
      },
      options: {
        maintainAspectRatio: false,
        layout: { padding: { right: 44 } },
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: tooltip({ callbacks: { label: (c) => ` ${c.dataset.label}: ${c.parsed.y} pts` } }) },
        scales: eixos({ beginAtZero: true }),
      },
      plugins: [rotulosFinais],
    });
    $("leg-pontos").innerHTML =
      `<span><i class="linha-leg forte"></i>Botafogo</span><span><i class="linha-leg"></i>Líder</span>` +
      `<span><i class="linha-leg" style="background:repeating-linear-gradient(90deg,var(--ref) 0 5px,transparent 5px 8px)"></i>4º</span>` +
      `<span><i class="linha-leg" style="background:repeating-linear-gradient(90deg,var(--ref) 0 2px,transparent 2px 4px)"></i>17º</span>`;

    const ult = ev.at(-1);
    if (ult) {
      $("e-atual").textContent = `${ult.pontos} pts`;
      const dG4 = ult.pontos_g4 - ult.pontos;
      $("e-g4").textContent = dG4 > 0 ? `-${dG4} pts` : `+${-dG4} pts`;
      $("e-z4").textContent = `${sinal(ult.pontos - ult.pontos_z4)} pts`;
      $("e-leitura").innerHTML =
        `Após ${ult.rodada} rodadas, o Botafogo soma <b>${ult.pontos} pontos</b>: ` +
        `${ult.pontos_lider - ult.pontos === 0 ? "é o líder ou divide a liderança" : `<b>${ult.pontos_lider - ult.pontos}</b> atrás do líder`}, ` +
        `${dG4 > 0 ? `<b>${dG4}</b> abaixo do 4º colocado` : `<b>${-dG4}</b> acima da linha do G4`} e ` +
        `<b>${ult.pontos - ult.pontos_z4}</b> acima do 17º, primeiro time da zona de rebaixamento.`;
    }

    // Posição rodada a rodada
    graficos.posicao = new Chart($("g-posicao"), {
      type: "line",
      data: {
        labels: rotulos,
        datasets: [{
          label: "Posição", data: ev.map((e) => e.posicao), borderColor: acento, borderWidth: 2, cubicInterpolationMode: "monotone",
          pointRadius: 4, pointBackgroundColor: acento, pointBorderColor: css("--card"), pointBorderWidth: 2, pointHoverRadius: 6,
        }],
      },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: false }, tooltip: tooltip({ displayColors: false, callbacks: { label: (c) => `${c.parsed.y}º lugar` } }) },
        scales: eixos({ reverse: true, min: 1, max: 20, ticks: { color: css("--tinta-3"), stepSize: 1, autoSkip: false, callback: (v) => ([1, 4, 8, 12, 16, 20].includes(v) ? `${v}º` : "") } }),
      },
      plugins: [faixasPosicao],
    });

    // Distribuição da posição final
    const S = D.simulacao;
    if (S) {
      const moda = S.posicao_mais_provavel;
      graficos.dist = new Chart($("g-dist"), {
        type: "bar",
        data: {
          labels: S.distribuicao_posicao.map((_, i) => `${i + 1}º`),
          datasets: [{
            data: S.distribuicao_posicao,
            backgroundColor: S.distribuicao_posicao.map((_, i) => (i + 1 === moda ? acento : i >= 16 ? css("--ruim") : css("--seq-2"))),
            borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: "bottom", maxBarThickness: 24,
          }],
        },
        options: {
          maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: tooltip({ displayColors: false, callbacks: { title: (c) => `${c[0].label} lugar`, label: (c) => `${num(c.parsed.y, 1)}% das simulações` } }) },
          scales: eixos({ beginAtZero: true, ticks: { color: css("--tinta-3"), callback: (v) => `${v}%` } }),
        },
      });
    }

    donut(D.recortes[recorte].resumo);
  }

  // ------------------------------------------------------------------------
  // Mando de campo
  // ------------------------------------------------------------------------
  function renderMandos() {
    const c = D.recortes.casa.resumo;
    const f = D.recortes.fora.resumo;
    const cartao = (nome, sub, r, escuro) => `
      <div class="mando ${escuro ? "escuro" : ""}">
        <div class="m-topo"><div><b>${pct(r.aproveitamento)}</b><div class="m-sub">aproveitamento</div></div><div style="text-align:right"><strong>${nome}</strong><div class="m-sub">${sub}</div></div></div>
        <div class="trilho"><span style="width:${r.aproveitamento ?? 0}%"></span></div>
        <div class="m-grid"><div><span>Pontos</span><b>${r.pontos}</b></div><div><span>Por jogo</span><b>${num(r.media_pontos, 2)}</b></div><div><span>Saldo</span><b>${sinal(r.saldo)}</b></div></div>
        <div class="m-sub" style="margin-top:8px">${r.vitorias}V · ${r.empates}E · ${r.derrotas}D · ${r.gols_pro} gols pró, ${r.gols_contra} contra</div>
      </div>`;
    $("mandos").innerHTML = cartao("Em casa", `${c.jogos} jogos`, c, false) + cartao("Como visitante", `${f.jogos} jogos`, f, true);
    const tot = c.pontos + f.pontos || 1;
    $("m-div-casa").style.width = `${(100 * c.pontos) / tot}%`;
    $("m-div-fora").style.width = `${(100 * f.pontos) / tot}%`;
    $("m-div-txt").textContent = `${c.pontos} em casa · ${f.pontos} fora`;
    const dif = (c.aproveitamento ?? 0) - (f.aproveitamento ?? 0);
    $("m-leitura").innerHTML =
      Math.abs(dif) < 0.05
        ? "<b>Leitura do mando:</b> o aproveitamento é igual em casa e fora."
        : `<b>Leitura do mando:</b> o Botafogo rende mais <b>${dif > 0 ? "em casa" : "fora de casa"}</b>, com <b>${num(Math.abs(dif), 1)} pontos percentuais</b> de diferença no aproveitamento.`;
  }

  // ------------------------------------------------------------------------
  // Cenário de chegada (projeção linear + simulador de meta)
  // ------------------------------------------------------------------------
  function renderChegada() {
    const r = D.recortes.todos.resumo;
    const rest = D.jogos_restantes;
    const proj = Math.round(r.pontos + (r.media_pontos ?? 0) * rest);
    $("c-proj-tag").textContent = `${proj} pts`;
    $("c-texto").innerHTML =
      `Mantendo a média atual de <b>${num(r.media_pontos, 2)} ponto por jogo</b>, a projeção é terminar as 38 rodadas com aproximadamente <b>${proj} pontos</b>. Restam <b>${rest}</b> partidas.` +
      (D.simulacao ? ` A simulação, que considera a força de cada adversário, aponta mediana de <b>${D.simulacao.pontos.mediana} pontos</b>.` : "");
    const meta = $("c-meta");
    meta.min = r.pontos;
    meta.max = r.pontos + 3 * rest;
    meta.value = Math.min(Number(meta.max), Math.max(Number(meta.min), D.simulacao ? D.simulacao.pontos.p75 : proj));
    renderAlvo();
    $("c-proximos").innerHTML = D.proximos.length
      ? D.proximos.map((j) => `<span class="adv" title="${esc(j.adversario)} · ${j.mando} · ${dataCurta(j.data)}">${img(j.adversario_escudo)}${esc(j.adversario)} <small>${j.mando === "casa" ? "C" : "F"}</small></span>`).join("")
      : '<span class="nota">Sem jogos restantes.</span>';
  }

  function renderAlvo() {
    const r = D.recortes.todos.resumo;
    const rest = D.jogos_restantes;
    const alvo = Number($("c-meta").value);
    $("c-meta-val").textContent = alvo;
    const falta = alvo - r.pontos;
    let txt;
    if (falta <= 0) txt = `Meta de <b>${alvo} pontos</b> já atingida.`;
    else if (falta > 3 * rest) txt = `Meta inalcançável: faltam <b>${falta} pontos</b> e só há ${3 * rest} em disputa.`;
    else {
      const v = Math.ceil(falta / 3);
      const vAlt = Math.floor(falta / 3);
      const eAlt = falta % 3;
      const alt = eAlt && vAlt + eAlt <= rest ? ` (ou ${vAlt} vitórias e ${eAlt} empate${eAlt > 1 ? "s" : ""})` : "";
      txt = `Faltam <b>${falta} pontos</b>, ${pct((100 * falta) / (3 * rest))} de aproveitamento no que resta. Caminho mínimo: <b>${v} vitórias</b> nos ${rest} jogos restantes${alt}.`;
    }
    $("c-alvo").innerHTML = txt;
  }

  // ------------------------------------------------------------------------
  // Jogo a jogo
  // ------------------------------------------------------------------------
  function titulo(j) {
    const casa = j.mando === "casa";
    const pl = j.gp == null ? " x " : casa ? ` ${j.gp} x ${j.gc} ` : ` ${j.gc} x ${j.gp} `;
    return `R${j.rodada ?? "?"} · ${casa ? "Botafogo" : j.adversario}${pl}${casa ? j.adversario : "Botafogo"} · ${dataCurta(j.data)}`;
  }

  function renderJogoAJogo() {
    $("j-grade").innerHTML = D.jogos
      .map((j) => `<div class="jg ${j.resultado ?? "futuro"}" title="${esc(titulo(j))}"><small>R${String(j.rodada ?? "?").padStart(2, "0")}</small><b>${j.resultado ?? "·"}</b></div>`)
      .join("");
    $("j-blocos").innerHTML = D.blocos
      .map((b) => `<div class="bloco"><span>${b.rotulo}</span><b>${pct(b.aproveitamento)}</b><div class="trilho" style="margin-top:8px"><span style="width:${b.aproveitamento}%"></span></div><small>${b.pontos} de ${b.disputados} pontos</small></div>`)
      .join("");
  }

  function renderTabelaJogos() {
    const q = $("busca").value.trim().toLowerCase();
    const lista = D.jogos.filter((j) => (recorte === "todos" || j.mando === recorte) && (!q || j.adversario.toLowerCase().includes(q)));
    const linhas = lista
      .map((j) => {
        const casa = j.mando === "casa";
        const fim = j.gp != null;
        const placar = fim ? (casa ? `${j.gp} : ${j.gc}` : `${j.gc} : ${j.gp}`) : "x";
        const inter = j.gp_int != null ? (casa ? `${j.gp_int} : ${j.gc_int}` : `${j.gc_int} : ${j.gp_int}`) : "–";
        const adv = `<span class="time-cel">${img(j.adversario_escudo)}${esc(j.adversario)}</span>`;
        const bota = `<span class="time-cel">${img(D.time.escudo)}Botafogo</span>`;
        return `<tr class="${j.resultado ?? "futuro"}">
          <td class="faixa-cel"><i></i></td>
          <td>${String(j.rodada ?? "–").padStart(2, "0")}</td>
          <td>${dataCurta(j.data)}</td>
          <td><span class="partida">${casa ? bota : adv}<span class="pl ${fim ? "" : "vazio"}">${placar}</span>${casa ? adv : bota}</span></td>
          <td><span class="pilula">${casa ? "Casa" : "Fora"}</span></td>
          <td class="centro">${inter}</td>
          <td>${j.resultado ? `<span class="res"><span class="chip ${j.resultado}">${j.resultado}</span>${NOME_RES[j.resultado]}</span>` : `<span class="nota">${j.status === "POSTPONED" ? "adiado" : "a jogar"}</span>`}</td>
          <td class="num"><span class="mais ${j.resultado ?? ""}">${j.pontos != null ? `+${j.pontos}` : ""}</span></td>
          <td class="num">${j.acumulado ?? ""}</td>
        </tr>`;
      })
      .join("");
    $("t-jogos").innerHTML = `<thead><tr><th></th><th>Rodada</th><th>Data</th><th>Partida</th><th>Mando</th><th class="centro">Intervalo</th><th>Resultado</th><th class="num">Pontos</th><th class="num">Acumulado</th></tr></thead>
      <tbody>${linhas || `<tr><td colspan="9" class="nota">Nenhum jogo encontrado.</td></tr>`}</tbody>`;
  }

  // ------------------------------------------------------------------------
  // Classificação
  // ------------------------------------------------------------------------
  function renderClassificacao() {
    const zona = (p) => (p <= 4 ? "z-g4" : p <= 6 ? "z-g6" : p >= 17 ? "z-z4" : "");
    $("t-classif").innerHTML = `<thead><tr><th></th><th>#</th><th>Time</th><th class="num">Pts</th><th class="num">J</th><th class="num">V</th><th class="num">E</th><th class="num">D</th><th class="num">GP</th><th class="num">GC</th><th class="num">SG</th><th class="num">Aprov.</th></tr></thead><tbody>${D.tabela
      .map(
        (l) => `<tr class="${zona(l.posicao)} ${l.destaque ? "destaque" : ""}">
          <td class="faixa-cel"><i></i></td><td>${l.posicao}</td>
          <td><span class="time-cel">${img(l.escudo)}${esc(l.time)}</span></td>
          <td class="num"><b>${l.pontos}</b></td><td class="num">${l.jogos}</td><td class="num">${l.vitorias}</td><td class="num">${l.empates}</td><td class="num">${l.derrotas}</td>
          <td class="num">${l.gols_pro}</td><td class="num">${l.gols_contra}</td><td class="num">${sinal(l.saldo)}</td>
          <td class="num">${l.jogos ? pct((100 * l.pontos) / (3 * l.jogos)) : "–"}</td></tr>`
      )
      .join("")}</tbody>`;
  }
})();
