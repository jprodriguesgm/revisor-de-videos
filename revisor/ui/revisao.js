/* Revisor de Vídeos — tela de revisão (etapa 4).
   Usa as utilidades de app.js (h, api, toast, icon, pad, plural, stem, vlabel, openModal…).
   Atalhos: ← → (itens) · ↑ ↓ (cortes) · Shift+← → (1 frame) · C comentar · V ver o trecho ·
   G gráficos · P conta-gotas · F tela cheia · ⌘C/Ctrl+C copiar · + − zoom · Z caber/100% ·
   T copiar para o Trello · N próxima aula · Esc fecha. */
"use strict";

// estado que continua ao trocar de item e de vídeo
const RV = {
  zoom: { fit: true, s: 1, tx: 0, ty: 0 },
  mode: null,          // null | "graphs" | "pick"
  graph: "luma",       // luma | parade
  picks: [],           // pontos fixados do conta-gotas: [{x, y}] em pixels do vídeo
  showBg: true,        // conta-gotas: gráfico completo do frame ao fundo
};
const PICK_COLORS = ["#4d8cf5", "#e8a33d", "#58c28a", "#e06cb0"];
const IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
const RV_ICONS = {
  list: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/></svg>',
  copy: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/></svg>',
  play: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5v14l12-7z"/></svg>',
  pause: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>',
  sliders: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/></svg>',
  trash: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12"/></svg>',
};
/** Troca o conteúdo de um elemento (ignora null/false, ao contrário de replaceChildren). */
function fill(el, ...kids) {
  el.replaceChildren();
  return add(el, kids);
}
function rvIcon(name) {
  const t = document.createElement("template");
  t.innerHTML = RV_ICONS[name] || ICONS[name];
  return t.content.firstChild;
}

// ====================================================================== tempo (igual ao timecode.py)

function rateOf(fps) {
  const [n, d0] = String(fps || "30000/1001").split("/").map(Number);
  const d = d0 || 1;
  return { n, d, fps: n / d, nominal: Math.round(n / d), drop: Math.round(n / d) % 30 === 0 && d === 1001 };
}
const secondsOf = (r, f) => (f * r.d) / r.n;
const frameAt = (r, t) => Math.floor((t * r.n) / r.d + 1e-4);
function hms(s) { return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`; }
/** Timecode no formato das configurações: segundos (padrão, meio do frame), NDF ou DF. */
function fmtTC(r, frame, style) {
  if (style === "ndf" || (style === "df" && !r.drop)) {
    const n = r.nominal;
    return `${hms(Math.floor(frame / n))}:${pad(frame % n)}`;
  }
  if (style === "df") {
    const n = r.nominal, drop = n === 30 ? 2 : 4;
    const per10 = n * 600 - drop * 9, per1 = n * 60 - drop;
    const d = Math.floor(frame / per10), m = frame % per10;
    let f = frame + drop * 9 * d + (m > drop ? drop * Math.floor((m - drop) / per1) : 0);
    return `${hms(Math.floor(f / n))};${pad(f % n)}`;
  }
  return hms(Math.floor(((2 * frame + 1) * r.d) / (2 * r.n)));
}

// ====================================================================== a tela

async function screenRevisao(root, arg) {
  let V = await api("video?n=" + (Number(arg) || 1));
  if (!V.review) { location.hash = "#/inicio"; return; }
  if (String(V.n) !== String(arg)) history.replaceState(null, "", `#/revisao/${V.n}`);
  document.body.classList.add("rv-on");

  const vid = V.video.id;
  const nn = pad(V.n);
  let R = rateOf(V.meta ? V.meta.fps : "30000/1001");
  const timers = [];
  const cleanups = [];
  // estado usado também ao sair da tela (declarado antes de qualquer "return")
  let cmtTimer = null, cmtFrame = null, cmtEl = null, savedEl = null;
  let clip = null;
  screenCleanup = () => {
    flushComment();
    closeClip();
    timers.forEach(clearInterval);
    cleanups.forEach((f) => { try { f(); } catch (e) { /* nada */ } });
    document.body.classList.remove("rv-on");
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  };
  const listen = (el, ev, fn, opt) => { el.addEventListener(ev, fn, opt); cleanups.push(() => el.removeEventListener(ev, fn, opt)); };

  // ------------------------------------------------------------------ barra: abas e editor
  const tabs = h("div", { class: "rv-tabs", role: "tablist", "aria-label": "Vídeos" });
  // A barra de abas volta a ficar onde estava (a tela é refeita a cada troca de vídeo) e depois
  // desliza até deixar a aula aberta no meio. Com o polling (vídeo analisando) ela não mexe sozinha.
  let tabsCentered = false;
  listen(tabs, "scroll", () => { RV.tabsScroll = tabs.scrollLeft; });
  function centerTab(smooth) {
    const on = tabs.querySelector(".rv-tab.on");
    if (!on || tabs.scrollWidth <= tabs.clientWidth) return;
    const tr = tabs.getBoundingClientRect(), or = on.getBoundingClientRect();
    const target = tabs.scrollLeft + (or.left - tr.left) - (tabs.clientWidth - or.width) / 2;
    const max = tabs.scrollWidth - tabs.clientWidth;
    const left = Math.max(0, Math.min(max, target));
    if (smooth && tabs.scrollTo) tabs.scrollTo({ left, behavior: "smooth" }); else tabs.scrollLeft = left;
  }
  function drawTabs() {
    const keep = tabs.scrollLeft;
    tabs.replaceChildren(...V.tabs.map((t) => {
      const on = t.n === V.n;
      const b = h("button", { class: "rv-tab" + (on ? " on" : "") + (t.missing ? " missing" : ""), role: "tab",
        "aria-selected": on ? "true" : "false", title: t.file,
        onclick: () => { if (!on) location.hash = `#/revisao/${t.n}`; } },
        h("span", { class: "nm", text: vlabel(t) }),
        !t.ready ? h("span", { class: "faint", text: "…" }) :
          t.warnings ? h("span", { class: "badge", "aria-label": plural(t.warnings, "aviso", "avisos"), text: String(t.warnings) }) : null);
      return b;
    }));
    if (tabsCentered) { tabs.scrollLeft = keep; return; }
    tabsCentered = true;
    tabs.scrollLeft = RV.tabsScroll || 0;          // onde estava na tela anterior
    requestAnimationFrame(() => requestAnimationFrame(() => centerTab(true)));
  }
  const edSel = h("select", { class: "rv-ed", "aria-label": "Editor deste vídeo" });
  const teamLink = h("a", { class: "btn ghost-blue small hidden", href: "#/config/equipe", text: "Cadastrar a equipe",
    title: "Nenhum editor cadastrado: cadastre em Configurações → Equipe" });
  function drawEditor() {
    const eds = V.editors.slice();
    if (V.video.editor && !eds.includes(V.video.editor)) eds.push(V.video.editor);
    const none = !eds.length;
    teamLink.classList.toggle("hidden", !none);
    edSel.classList.toggle("hidden", none);
    applyAll.classList.toggle("hidden", none);
    edSel.replaceChildren(h("option", { value: "", text: "Escolher" }), ...eds.map((e) => h("option", { value: e, text: e })));
    edSel.value = V.video.editor || "";
    edSel.classList.toggle("empty", !V.video.editor);
  }
  edSel.addEventListener("change", async () => {
    try { await api("review/editor", { id: vid, editor: edSel.value || null }); V.video.editor = edSel.value || null; drawEditor(); }
    catch (e) { toast(e.message, true); }
  });
  const applyAll = h("button", { class: "btn ghost small", text: "Aplicar a todos", onclick: async () => {
    if (!edSel.value) { toast("Escolha o editor deste vídeo primeiro.", true); edSel.focus(); return; }
    try { await api("review/editor", { id: "all", editor: edSel.value }); toast(`${edSel.value} marcada em todos os vídeos.`); }
    catch (e) { toast(e.message, true); }
  } });
  const countTxt = h("span", { class: "rv-count" });
  // opcional (pedido do JP): ← → passam também por cada slide em tela cheia, para conferir o texto
  const slideBtn = h("button", { class: "btn ghost small rv-slides hidden", type: "button", "aria-pressed": "false",
    title: "Incluir cada slide em tela cheia na navegação com ← → (vale para todas as revisões)" },
    h("i", { class: "sw-slide" }), h("span", { class: "lb", text: "Navegar slides" }));
  slideBtn.addEventListener("click", async () => {
    const on = !V.nav_slides;
    try {
      await api("settings", { nav_slides: on });
      await reload();
      toast(on ? "Os slides entraram na navegação (← →)." : "Os slides saíram da navegação.");
    } catch (e) { toast(e.message, true); }
  });
  function drawSlideBtn() {
    slideBtn.classList.toggle("hidden", !(V.slides || []).length);
    slideBtn.classList.toggle("on", !!V.nav_slides);
    slideBtn.setAttribute("aria-pressed", V.nav_slides ? "true" : "false");
  }
  const adjBtn = h("button", { class: "btn ghost small", onclick: adjustDialog, "aria-label": "Ajustes da detecção" },
    rvIcon("sliders"), "Ajustes");
  // "Próxima aula" (pedido do JP): o vídeo seguinte; no último, a próxima pasta da fila; sem fila, o Resumo final
  const nextBtn = h("button", { class: "btn ghost-blue small rv-next", type: "button", onclick: () => nextLesson() });
  function drawNext() {
    const nf = V.next_folder;
    let label, title;
    if (V.n < V.total) {
      const t = V.tabs[V.n];
      label = "Próxima aula";
      title = `Abrir ${vlabel(t)} (N)`;
    } else if (nf) {
      label = "Próxima pasta";
      title = `Abrir a revisão de “${nf.project}” · ${nf.status_text} (N)`;
    } else {
      label = "Resumo final";
      title = "Última aula desta pasta: abrir o Resumo final (N)";
    }
    nextBtn.replaceChildren(h("span", { class: "lb", text: label }), h("span", { class: "ar", "aria-hidden": "true", text: "›" }));
    nextBtn.title = title;
    nextBtn.setAttribute("aria-label", title);
  }
  async function nextLesson() {
    flushComment();
    if (V.n < V.total) { location.hash = `#/revisao/${V.n + 1}`; return; }
    const nf = V.next_folder;
    if (!nf) { location.hash = "#/final"; return; }
    try { await openQueued(nf.project); }
    catch (e) { toast(e.message, true); }
  }

  // ------------------------------------------------------------------ estrutura
  const stage = h("section", { class: "rv-stage", "aria-label": "Frame" });
  const side = h("aside", { class: "rv-side" });
  const foot = h("footer", { class: "rv-foot" });
  root.appendChild(h("div", { class: "rv" },
    h("div", { class: "rv-bar" }, tabs,
      h("div", { class: "rv-bar-r" }, h("span", { class: "muted", text: "Editor deste vídeo" }), edSel, applyAll, teamLink,
        h("span", { class: "vsep" }), countTxt, slideBtn, adjBtn, nextBtn)),
    h("div", { class: "rv-main" }, stage, side),
    foot));
  drawTabs();
  drawEditor();
  drawNext();

  // ------------------------------------------------------------------ vídeo ainda analisando
  if (!V.ready) {
    countTxt.textContent = `Vídeo ${V.n} de ${V.total}`;
    const msg = h("p", { class: "muted" });
    const redoNow = h("button", { class: "btn primary hidden", type: "button", text: "Analisar este vídeo de novo",
      onclick: async () => {
        redoNow.disabled = true;
        try { const r = await api("reanalyze", { id: vid }); toast(r.queued ? `Vai analisar logo depois de “${r.running}”.` : "Analisando de novo…"); }
        catch (e) { toast(e.message, true); redoNow.disabled = false; }
      } });
    const showWait = () => {
      const j = V.job;
      redoNow.classList.toggle("hidden", !V.stale);
      if (V.stale) {
        msg.textContent = "O arquivo deste vídeo mudou depois da análise (voltou corrigido). A análise guardada é da versão " +
          "anterior, então os frames dela não valem mais. Analise de novo para ver a versão nova.";
        return;
      }
      msg.textContent = !j ? "Este vídeo ainda não foi analisado. Volte ao início e analise a pasta." :
        j.status === "erro" ? `Não foi possível analisar este vídeo: ${j.error || "erro"}.` :
        j.status === "run" ? `Analisando este vídeo · ${Math.round((j.pct || 0) * 100)}%` : "Este vídeo está na fila da análise.";
    };
    showWait();
    stage.appendChild(h("div", { class: "panel empty-state", style: { margin: "auto", maxWidth: "520px" } },
      h("h2", { style: { margin: 0, fontSize: "18px", color: "var(--text)" }, text: `${nn} · ${stem(V.video.file)}` }), msg,
      redoNow, h("a", { class: "btn ghost", href: "#/analise", text: "Ver a análise" })));
    side.appendChild(h("p", { class: "muted", style: { fontSize: "13px" }, text: "A revisão deste vídeo abre sozinha quando a análise dele terminar." }));
    timers.push(setInterval(async () => {
      try {
        const nv = await api("video?n=" + V.n);
        if (nv.ready) render(); else { V = nv; showWait(); drawTabs(); drawNext(); }
      } catch (e) { /* tenta de novo */ }
    }, 1500));
    return;
  }

  const M = V.meta;
  const W = M.width, H = M.height;
  let items = V.items;
  const itemByFrame = () => new Map(items.map((it) => [it.frame, it]));
  let byFrame = itemByFrame();
  const commentAt = (f) => V.comments.find((c) => c.frame === f);
  const cur = { i: items.length ? 0 : null, step: null, frame: items.length ? items[0].frame : (M.content ? M.content.first_frame : 0) };
  const curItem = () => (cur.i === null ? null : items[cur.i]);
  const tcOf = (f) => fmtTC(R, f, V.time_format);
  const frameUrl = (f, s) => `/api/frame.jpg?id=${vid}&f=${f}&s=${s}&v=${V.ver || ""}`;

  function drawCount() {
    const c = V.counts;
    countTxt.textContent = `Vídeo ${V.n} de ${V.total} · ${plural(c.frames, "frame marcado", "frames marcados")} · ` +
      `${plural(c.warnings, "aviso", "avisos")}`;
  }
  drawCount();
  drawSlideBtn();

  // ------------------------------------------------------------------ visor do frame
  const img = h("img", { class: "vw-img", alt: "", draggable: "false" });
  const ov = h("div", { class: "vw-ov" });
  const layer = h("div", { class: "vw-layer", style: { width: W + "px", height: H + "px" } }, img, ov);
  const hudTL = h("div", { class: "vw-hud tl mono" });
  const hudTR = h("div", { class: "vw-hud tr" });
  const stepsBox = h("div", { class: "vw-steps hidden" });
  const miniImg = h("img", { alt: "" });
  const miniRect = h("div", { class: "r" });
  const mini = h("button", { class: "vw-mini hidden", "aria-label": "Mini-mapa: clique para mover a área ampliada",
    style: { aspectRatio: `${W} / ${H}` } }, miniImg, miniRect);
  const zoomTxt = h("button", { class: "vw-zoomtxt hidden mono", title: "Z: caber na tela / 100%", onclick: () => toggleZoom() });
  const msgBox = h("div", { class: "vw-msg hidden" });
  const cross = h("div", { class: "vw-cross hidden" });
  const loupe = h("div", { class: "vw-loupe hidden" }, h("i"), h("span", { text: "área 9 × 9 px" }));
  const clipBox = h("div", { class: "vw-clip hidden" });
  const vw = h("div", { class: "vw", tabindex: "-1" }, layer, hudTL, hudTR, stepsBox, mini, zoomTxt, msgBox, cross, loupe, clipBox);
  const k = (key, label, fn, title, opt) => h("button", { class: "tool", onclick: fn, title: title || label,
    "aria-label": title || label }, h("kbd", { text: key }), h("span", { class: "l" + (opt ? " opt" : ""), text: label }));
  const tGraphs = k("G", "Gráficos", () => setMode(RV.mode === "graphs" ? null : "graphs"));
  const tPick = k("P", "Conta-gotas", () => setMode(RV.mode === "pick" ? null : "pick"));
  const tClip = k("V", "Ver trecho", () => toggleClip(), "Ver o trecho em volta deste frame");
  const tools = h("div", { class: "rv-tools" },
    k("←", "Anterior", () => go(-1), null, true), k("→", "Próximo", () => go(1), null, true),
    k("↑", "Corte", () => goCut(-1), "Corte anterior", true), k("↓", "Corte", () => goCut(1), "Próximo corte", true),
    k("C", "Comentar", () => focusComment()),
    tClip, tGraphs, tPick, k("F", "Tela cheia", () => fullscreen()),
    k(IS_MAC ? "⌘ C" : "Ctrl C", "Copiar", () => copyFrame(), "Copiar frame + comentário"));
  const hint = h("span", { class: "rv-hint" });
  stage.append(vw, tools, hint);
  if (!M.has_video) {
    stage.insertBefore(h("div", { class: "notice", style: { maxWidth: "820px" } }, icon("alert"),
      h("span", { text: "O vídeo não está neste computador: aparecem só as miniaturas guardadas. Zoom em resolução cheia, " +
        "gráficos, conta-gotas e o trecho precisam do vídeo na pasta." })), vw);
  }

  // ---- tamanho do visor (cabe no espaço, na proporção do vídeo)
  function layoutViewer() {
    if (document.fullscreenElement === vw) { applyZoom(); return; }
    const cs = getComputedStyle(stage);
    const padW = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    const padH = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
    // botões numa linha só: primeiro some o texto de ← →, depois o de todos (fica a tecla + dica)
    tools.classList.remove("compact", "tiny");
    if (tools.offsetHeight > 48) tools.classList.add("compact");
    if (tools.offsetHeight > 48) tools.classList.add("tiny");
    let used = 0;
    for (const el of stage.children) if (el !== vw) used += el.offsetHeight + 12;
    const aw = Math.max(200, stage.clientWidth - padW), ah = Math.max(120, stage.clientHeight - padH - used - 12);
    let w = aw, hh = (aw * H) / W;
    if (hh > ah) { hh = ah; w = (ah * W) / H; }
    vw.style.width = Math.floor(w) + "px";
    vw.style.height = Math.floor(hh) + "px";
    applyZoom();
  }

  // ---- zoom: roda / pinça / + − / Z; arrastar move; até 400%
  const dpr = () => window.devicePixelRatio || 1;
  const fitScale = () => Math.min(vw.clientWidth / W, vw.clientHeight / H) || 0.1;
  const maxScale = () => Math.max(4 / dpr(), fitScale());
  function clampZoom() {
    const z = RV.zoom, fs = fitScale(), w = vw.clientWidth, hh = vw.clientHeight;
    if (z.fit) { z.s = fs; }
    z.s = Math.min(Math.max(z.s, fs), maxScale());
    if (z.s <= fs * 1.0001) { z.fit = true; z.s = fs; }
    const iw = W * z.s, ih = H * z.s;
    z.tx = iw <= w ? (w - iw) / 2 : Math.min(0, Math.max(w - iw, z.tx));
    z.ty = ih <= hh ? (hh - ih) / 2 : Math.min(0, Math.max(hh - ih, z.ty));
  }
  function applyZoom() {
    clampZoom();
    const z = RV.zoom;
    layer.style.transform = `translate(${z.tx}px, ${z.ty}px) scale(${z.s})`;
    layer.style.setProperty("--inv", String(1 / z.s));
    const zoomed = !z.fit;
    vw.classList.toggle("zoomed", zoomed);
    zoomTxt.classList.toggle("hidden", !zoomed);
    zoomTxt.textContent = `${Math.round(z.s * dpr() * 100)}% · Z volta`;
    mini.classList.toggle("hidden", !zoomed);
    if (zoomed) {
      const vx = -z.tx / z.s, vy = -z.ty / z.s, vwid = vw.clientWidth / z.s, vhei = vw.clientHeight / z.s;
      Object.assign(miniRect.style, { left: `${Math.max(0, vx / W) * 100}%`, top: `${Math.max(0, vy / H) * 100}%`,
        width: `${Math.min(1, vwid / W) * 100}%`, height: `${Math.min(1, vhei / H) * 100}%` });
    }
  }
  function zoomAt(px, py, factor) {
    const z = RV.zoom;
    clampZoom();
    const s0 = z.s, s1 = Math.min(Math.max(s0 * factor, fitScale()), maxScale());
    if (s1 === s0) return;
    z.tx = px - ((px - z.tx) * s1) / s0;
    z.ty = py - ((py - z.ty) * s1) / s0;
    z.s = s1;
    z.fit = false;
    applyZoom();
  }
  function toggleZoom() {
    const z = RV.zoom;
    if (!z.fit) { z.fit = true; applyZoom(); return; }
    const target = 1 / dpr();      // 100% = 1 pixel do vídeo = 1 pixel da tela
    zoomAt(vw.clientWidth / 2, vw.clientHeight / 2, target / fitScale());
    if (RV.zoom.fit) toast("O frame já aparece em 100% (ou maior) nesta tela.");
  }
  listen(vw, "wheel", (e) => {
    if (clipOpen()) return;
    e.preventDefault();
    const r = vw.getBoundingClientRect();
    const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
    zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0015)));
  }, { passive: false });
  // gesto de pinça do Safari
  let gs = 1;
  listen(vw, "gesturestart", (e) => { e.preventDefault(); gs = 1; });
  listen(vw, "gesturechange", (e) => {
    e.preventDefault();
    const r = vw.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, e.scale / gs);
    gs = e.scale;
  });
  // arrastar para mover / clique do conta-gotas
  let drag = null;
  listen(vw, "pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest(".vw-steps, .vw-mini, .vw-clip, .vw-zoomtxt")) return;
    drag = { x: e.clientX, y: e.clientY, tx: RV.zoom.tx, ty: RV.zoom.ty, moved: false, id: e.pointerId };
    vw.setPointerCapture(e.pointerId);
  });
  listen(vw, "pointermove", (e) => {
    if (drag && e.pointerId === drag.id) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) > 4) drag.moved = true;
      if (drag.moved && !RV.zoom.fit) {
        RV.zoom.tx = drag.tx + dx; RV.zoom.ty = drag.ty + dy;
        applyZoom();
      }
    }
    if (RV.mode === "pick" && !clipOpen()) pickHover(e);
  });
  listen(vw, "pointerup", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const moved = drag.moved;
    drag = null;
    if (!moved && RV.mode === "pick" && !clipOpen()) pickFix(e);
  });
  listen(vw, "pointerleave", () => { if (RV.mode === "pick") { cross.classList.add("hidden"); loupe.classList.add("hidden"); } });
  mini.addEventListener("click", (e) => {
    const r = mini.getBoundingClientRect();
    const vx = ((e.clientX - r.left) / r.width) * W, vy = ((e.clientY - r.top) / r.height) * H;
    RV.zoom.tx = vw.clientWidth / 2 - vx * RV.zoom.s;
    RV.zoom.ty = vw.clientHeight / 2 - vy * RV.zoom.s;
    applyZoom();
  });
  const toVideo = (e) => {
    const r = vw.getBoundingClientRect();
    return { x: Math.floor((e.clientX - r.left - RV.zoom.tx) / RV.zoom.s), y: Math.floor((e.clientY - r.top - RV.zoom.ty) / RV.zoom.s),
      cx: e.clientX - r.left, cy: e.clientY - r.top };
  };

  // ---- imagem do frame: miniatura na hora, frame cheio (para o zoom) logo depois
  const loadedFull = new Set();
  let loadToken = 0;
  function showImage(f) {
    const token = ++loadToken;
    const full = frameUrl(f, "full");
    msgBox.classList.add("hidden");
    if (loadedFull.has(full)) { img.src = full; vw.classList.remove("loading"); return; }
    vw.classList.add("loading");
    if (byFrame.has(f)) img.src = frameUrl(f, "thumb");
    miniImg.src = frameUrl(f, "thumb");
    const im = new Image();
    im.onload = () => {
      loadedFull.add(full);
      if (token !== loadToken) return;
      img.src = full;
      vw.classList.remove("loading");
    };
    im.onerror = () => {
      if (token !== loadToken) return;
      vw.classList.remove("loading");
      if (!byFrame.has(f)) img.removeAttribute("src");
      msgBox.textContent = M.has_video ? "Não consegui ler este frame do vídeo." : "Sem miniatura deste frame (o vídeo não está neste computador).";
      msgBox.classList.remove("hidden");
    };
    im.src = full;
  }
  function prefetch() {
    if (!M.has_video || cur.i === null) return;
    [cur.i + 1, cur.i - 1].forEach((j) => {
      if (j < 0 || j >= items.length) return;
      const u = frameUrl(items[j].frame, "full");
      if (loadedFull.has(u)) return;
      const im = new Image();
      im.onload = () => loadedFull.add(u);
      im.src = u;
    });
  }

  // ---- marcações por cima do frame (acompanham o zoom)
  const pct = (v) => `${(v * 100).toFixed(3)}%`;
  function box(reg, cls, label) {
    const b = h("div", { class: "vw-box " + (cls || ""), style: { left: pct(reg[0]), top: pct(reg[1]), width: pct(reg[2]), height: pct(reg[3]) } });
    if (label) b.appendChild(h("span", { class: "vw-box-l", text: label }));
    return b;
  }
  function drawOverlay() {
    ov.replaceChildren();
    const it = curItem();
    if (it && it.frame === cur.frame || (it && it.steps && cur.step !== null)) {
      if (it.steps) {
        it.steps.forEach((s, j) => { if (s.region && j !== (cur.step ?? it.steps.length - 1)) ov.appendChild(box(s.region, "faint")); });
        const s = it.steps[cur.step ?? it.steps.length - 1];
        if (s.region) ov.appendChild(box(s.region, "", "Região que mudou"));
      } else if (it.region && !(it.region[2] >= 0.999 && it.region[3] >= 0.999)) {
        let label = it.warn ? null : "Região que mudou";
        if (it.kind === "spelling") {
          const w = it.extra.word, sg = (it.extra.suggestions || [])[0];
          label = sg ? `“${w}” → ${sg}` : `“${w}” não está no dicionário`;
        } else if (it.kind === "name_tag") label = "tarja";
        ov.appendChild(box(it.region, it.warn ? "warn" : "", label));
      }
    }
    RV.picks.forEach((p, j) => ov.appendChild(h("div", { class: "vw-pt", style: {
      left: pct(p.x / W), top: pct(p.y / H), borderColor: PICK_COLORS[j] } }, h("b", { style: { background: PICK_COLORS[j] }, text: String(j + 1) }))));
  }
  function drawHud() {
    const it = curItem();
    const onItem = it && (it.frame === cur.frame || (it.steps && cur.step !== null));
    let t = tcOf(cur.frame);
    if (onItem) {
      t += ` · ${cur.i + 1} de ${items.length} · ${it.label}`;
      if (it.steps) t += ` · passo ${(cur.step ?? it.steps.length - 1) + 1} de ${it.steps.length}`;
    } else t += ` · frame ${cur.frame}`;
    const cl = cutLabel();
    if (cl) t += ` · ${cl}`;
    hudTL.textContent = t;
    hudTR.replaceChildren();
    hudTR.className = "vw-hud tr hidden";
    if (onItem && it.warn) {
      hudTR.className = "vw-hud tr " + (it.dismissed ? "off" : "warn");
      hudTR.append(icon("alert"), it.dismissed ? `${it.label} · ignorado` : it.label);
    } else if (onItem && it.steps) {
      hudTR.className = "vw-hud tr warn";
      hudTR.append(rvIcon("list"), it.label);
    }
    // passos da lista
    stepsBox.replaceChildren();
    stepsBox.classList.toggle("hidden", !(onItem && it.steps));
    if (onItem && it.steps) {
      const sc = cur.step ?? it.steps.length - 1;
      stepsBox.append(h("span", { class: "t", text: "Passos da lista" }),
        h("div", { class: "row", style: { gap: "8px" } }, it.steps.map((s, j) =>
          h("button", { class: "st" + (j === sc ? " on" : ""), "aria-label": `Passo ${j + 1}: ${tcOf(s.frame)}`,
            onclick: () => goStep(j) },
            h("img", { src: frameUrl(s.frame, "thumb"), alt: "" }), h("span", { class: "mono", text: tcOf(s.frame) })))));
    }
  }

  // ------------------------------------------------------------------ navegação
  function show() {
    showImage(cur.frame);
    drawHud();
    drawOverlay();
    drawSide();
    markStrip();
    drawWave();
    prefetch();
    if (RV.mode === "pick") repick();
  }
  function goItem(i, step) {
    if (i === null || i < 0 || i >= items.length) return;
    flushComment();
    if (clipOpen()) closeClip();
    const it = items[i];
    cur.i = i;
    cur.step = it.steps ? (step ?? null) : null;
    cur.frame = it.steps && step != null ? it.steps[step].frame : it.frame;
    show();
  }
  function goStep(j) { goItem(cur.i, j); }
  function goFrame(f, snap) {
    f = Math.max(0, Math.min(M.frames - 1, Math.round(f)));
    if (snap) {
      const near = items.reduce((b, it, j) => (Math.abs(it.frame - f) < snap && (b === null || Math.abs(it.frame - f) < Math.abs(items[b].frame - f)) ? j : b), null);
      if (near !== null) return goItem(near);
    }
    flushComment();
    if (clipOpen()) closeClip();
    const exact = items.findIndex((it) => it.frame === f && !it.steps);
    if (exact >= 0) return goItem(exact);
    // fica "entre" itens: ← → continuam a partir daqui
    let j = null;
    for (let x = 0; x < items.length; x++) if (items[x].start <= f) j = x;
    cur.i = j; cur.step = null; cur.frame = f;
    show();
  }
  function go(d) {
    if (!items.length) return;
    const it = curItem();
    const onItem = it && (it.frame === cur.frame || (it.steps && cur.step !== null));
    if (cur.i === null) return goItem(d > 0 ? 0 : null);
    if (!onItem) {               // num frame solto: o próximo item depois dele / o anterior
      if (d > 0) { const j = items.findIndex((x) => x.start > cur.frame); return goItem(j >= 0 ? j : null); }
      return goItem(cur.i);
    }
    goItem(Math.max(0, Math.min(items.length - 1, cur.i + d)));
  }
  // ↑ ↓ (pedido do JP): de corte em corte da linha do tempo, para dar uma olhada em cada emenda.
  // Mostra o 1º frame depois do corte; Shift + ← vê o frame de antes.
  const cutFrames = () => V.cuts.map((c) => c.frame).sort((a, b) => a - b);
  function goCut(d) {
    const cf = cutFrames();
    if (!cf.length) { toast("Este vídeo não tem cortes marcados."); return; }
    const f = d > 0 ? cf.find((x) => x > cur.frame) : [...cf].reverse().find((x) => x < cur.frame);
    if (f === undefined) { toast(d > 0 ? "Este é o último corte do vídeo." : "Este é o primeiro corte do vídeo."); return; }
    goFrame(f);
  }
  function cutLabel() {
    const cf = cutFrames(), j = cf.indexOf(cur.frame);
    return j < 0 ? "" : `corte ${j + 1} de ${cf.length}`;
  }

  // ------------------------------------------------------------------ painel da direita
  async function saveComment(frame, text) {
    try {
      const it = curItem();
      const r = await api("comment", { id: vid, frame, text, source: it && it.frame === frame ? it.key : "livre",
        label: it && it.frame === frame ? it.label : "" });
      V.comments = r.comments;
      if (savedEl && cmtFrame === frame) savedEl.textContent = text.trim() ? "Salvo" : "";
      drawCommentList();
      markStrip();
      drawWave();
    } catch (e) { toast(e.message, true); }
  }
  // ---- comentário geral do vídeo (pedido do JP, 21/10): sem tempo, vale para o vídeo todo
  // ("aumentar o áudio geral", "ajustar a cor da pele"). Vai para o Resumo final, a cópia e o SRT.
  let genTimer = null, genEl = null, genSaved = null;
  async function saveGeneral(text) {
    try {
      const r = await api("general", { id: vid, text });
      V.general = r.general;
      if (genSaved && genEl && genEl.value.trim() === (r.general || "")) genSaved.textContent = r.general ? "Salvo" : "";
    } catch (e) { toast(e.message, true); }
  }
  function flushGeneral() {
    if (genTimer && genEl) { clearTimeout(genTimer); genTimer = null; saveGeneral(genEl.value); }
  }
  function generalBox() {
    genEl = h("textarea", { id: "cmt-geral", class: "rv-ta rv-ta-gen", value: V.general || "",
      placeholder: "Vale para o vídeo todo, sem tempo. Ex.: aumentar o áudio geral; ajustar a cor da pele." });
    genSaved = h("span", { class: "rv-saved", "aria-live": "polite", text: V.general ? "Salvo" : "" });
    genEl.addEventListener("input", () => {
      genSaved.textContent = "";
      clearTimeout(genTimer);
      const el = genEl;
      genTimer = setTimeout(() => { genTimer = null; saveGeneral(el.value); }, 700);
    });
    genEl.addEventListener("blur", flushGeneral);
    const copyGen = h("button", { class: "btn ghost small", type: "button", text: "Copiar", title: "Copiar o comentário geral",
      onclick: async () => {
        flushGeneral();
        const t = genEl.value.trim();
        if (!t) { toast("Escreva o comentário geral primeiro.", true); genEl.focus(); return; }
        try { await navigator.clipboard.writeText(`Vídeo ${nn} · Geral · ${t}`); toast("Comentário geral copiado."); }
        catch (e) { toast("O navegador não deixou copiar.", true); }
      } });
    return h("div", { class: "rv-gen" },
      h("div", { class: "rv-gen-h" }, h("span", { class: "tt", text: "Comentário geral do vídeo" }), copyGen),
      h("label", { for: "cmt-geral", class: "sr", text: "Comentário geral do vídeo" }), genEl,
      h("div", { class: "rv-saved-row" }, genSaved));
  }
  function flushComment() {
    flushGeneral();
    if (cmtTimer && cmtEl && cmtFrame !== null) {
      clearTimeout(cmtTimer); cmtTimer = null;
      saveComment(cmtFrame, cmtEl.value);
    }
  }
  function focusComment() {
    if (RV.mode) setMode(null);          // redesenha o painel na hora: o campo já existe
    if (cmtEl) { cmtEl.focus(); cmtEl.setSelectionRange(cmtEl.value.length, cmtEl.value.length); }
  }
  const listBox = h("div", { class: "rv-clist" });
  function drawCommentList() {
    if (!listBox.isConnected && RV.mode) return;
    const cs = V.comments;
    listBox.replaceChildren(h("span", { class: "rv-sub", text: `Neste vídeo · ${plural(cs.length, "comentário", "comentários")}` }),
      ...cs.map((c) => h("div", { class: "rv-c" + (c.frame === cur.frame ? " on" : "") },
        h("button", { class: "go", onclick: () => goFrame(c.frame), "aria-label": `Ir para ${tcOf(c.frame)}` },
          h("span", { class: "mono t", text: tcOf(c.frame) }), h("span", { class: "x", text: c.text })),
        h("button", { class: "del", "aria-label": `Apagar o comentário de ${tcOf(c.frame)}`, title: "Apagar",
          onclick: async () => { await saveComment(c.frame, ""); if (c.frame === cur.frame && cmtEl) cmtEl.value = ""; } },
          rvIcon("trash")))));
  }
  function suggestion(it) {
    if (it.kind === "spelling") {
      const sg = (it.extra.suggestions || [])[0];
      return sg ? `Ortografia: “${it.extra.word}” → “${sg}”.` : `Ortografia: conferir “${it.extra.word}”.`;
    }
    if (it.kind === "name_tag") return `Tarja: ${it.note}.`;
    const lab = it.label.charAt(0).toUpperCase() + it.label.slice(1);
    return it.note && it.note !== it.label ? `${lab}: ${it.note}.` : `${lab}.`;
  }
  function warnCard(it) {
    const dis = !!it.dismissed;
    const act = (label, fn, cls) => h("button", { class: "mini" + (cls ? " " + cls : ""), text: label, onclick: fn });
    let body;
    if (it.kind === "spelling") {
      const sg = (it.extra.suggestions || [])[0];
      body = [h("div", {}, `“${it.extra.word}” não está nos dicionários.`, sg ? ` Sugestão: ` : "", sg ? h("b", { text: sg }) : null,
        it.note.includes("aparece") ? h("span", { class: "faint", text: ` (${it.note.split("(").pop()}` }) : null),
        it.extra.line ? h("div", { class: "faint", style: { fontSize: "12px" }, text: `Linha lida: “${it.extra.line}”` }) : null];
    } else body = [h("div", { text: it.note || it.label })];
    const btns = dis ? [act("Desfazer “Ignorar”", () => dismiss(it, true))] :
      [act("Ignorar", () => dismiss(it)), it.kind === "spelling" ? act("Aceitar", () => accept(it)) : null,
       act("Comentar", () => { cmtEl.value = suggestion(it); saveComment(cur.frame, cmtEl.value); focusComment(); })];
    return h("div", { class: "rv-warn" + (dis ? " off" : "") },
      h("div", { class: "hd" }, h("span", { class: "k", text: `${it.label} · ${dis ? "ignorado" : "conferir"}` }),
        h("span", { class: "faint", text: it.source || "" })),
      body, h("div", { class: "row", style: { gap: "6px" } }, btns),
      it.kind === "spelling" && !dis ? h("span", { class: "faint", style: { fontSize: "11px" },
        text: "Aceitar: a palavra entra na sua lista e deixa de ser avisada em todas as aulas." }) : null);
  }
  async function dismiss(it, undo) {
    try { await api("dismiss", { id: vid, key: it.key, undo: !!undo }); await reload(); }
    catch (e) { toast(e.message, true); }
  }
  async function accept(it) {
    try {
      toast("Refazendo a ortografia…");
      const r = await api("accept", { word: it.extra.word });
      await reload();
      toast(`“${it.extra.word}” entrou na sua lista de palavras (ortografia refeita em ${plural(r.videos, "vídeo", "vídeos")}).`);
    } catch (e) { toast(e.message, true); }
  }
  function drawComment() {
    side.className = "rv-side";
    const it = curItem();
    const onItem = it && (it.frame === cur.frame || (it.steps && cur.step !== null));
    const c = commentAt(cur.frame);
    cmtFrame = cur.frame;
    cmtEl = h("textarea", { id: "cmt", class: "rv-ta", placeholder: "O que o editor precisa corrigir neste frame?", value: c ? c.text : "" });
    savedEl = h("span", { class: "rv-saved", "aria-live": "polite", text: c ? "Salvo" : "" });
    cmtEl.addEventListener("input", () => {
      savedEl.textContent = "";
      clearTimeout(cmtTimer);
      const f = cmtFrame, el = cmtEl;
      cmtTimer = setTimeout(() => { cmtTimer = null; saveComment(f, el.value); }, 700);
    });
    cmtEl.addEventListener("blur", flushComment);
    const clipBtn = clipOpen() ? h("button", { class: "btn ghost-blue", onclick: () => closeClip(), text: "Voltar ao frame · Esc" })
      : h("button", { class: "btn ghost", onclick: () => openClip() }, rvIcon("play"), `Ver momento (${secTxt(RV.clipHalf)} s antes e depois)`);
    fill(side, 
      h("div", { class: "rv-head" }, h("span", { class: "tt", text: "Comentário do frame" }),
        h("span", { class: "mono faint", text: `${nn} · ${tcOf(cur.frame)}` })),
      onItem && it.warn ? warnCard(it) : null,
      h("label", { for: "cmt", class: "sr", text: "Comentário" }), cmtEl,
      h("div", { class: "rv-saved-row" }, savedEl),
      h("button", { class: "btn primary", onclick: () => copyFrame() }, rvIcon("copy"), "Copiar frame + comentário"),
      h("button", { class: "btn", onclick: () => copyTrello(), title: "Uma imagem só, com o que está na tela (com zoom: a parte ampliada) e o comentário escrito embaixo (T)" },
        rvIcon("copy"), "Copiar para o Trello"),
      h("button", { class: "btn", onclick: () => copyText(), text: "Copiar só o comentário" }),
      M.has_video ? clipBtn : null,
      generalBox(),
      listBox);
    drawCommentList();
  }

  // ---- G: gráficos do frame
  function graticule(kind) {
    const NS = "http://www.w3.org/2000/svg";
    const s = (tag, a, text) => { const el = document.createElementNS(NS, tag); for (const [k2, v] of Object.entries(a)) el.setAttribute(k2, v); if (text) el.textContent = text; return el; };
    const svg = s("svg", { viewBox: "0 0 1000 256", preserveAspectRatio: "none", "aria-hidden": "true" });
    const lines = kind === "luma" ? [[16, "0"], [71, "25"], [126, "50"], [180, "75"], [235, "100"]]
      : [[0, "0"], [64, "25"], [128, "50"], [191, "75"], [255, "100"]];
    lines.forEach(([code, lab]) => {
      const y = 255.5 - code;
      svg.appendChild(s("line", { x1: 0, x2: 1000, y1: y, y2: y, stroke: lab === "0" || lab === "100" ? "#5a5a5a" : "#333",
        "stroke-width": 1, "vector-effect": "non-scaling-stroke", "stroke-dasharray": lab === "0" || lab === "100" ? "" : "4 4" }));
    });
    return { svg, labels: lines.map(([code, lab]) => h("span", { style: { top: `${((255.5 - code) / 256) * 100}%` }, text: lab })) };
  }
  function scopeImg(kind) {
    return h("img", { alt: "", src: `/api/fscope.png?id=${vid}&f=${cur.frame}&k=${kind}&v=${V.ver || ""}`,
      onerror: (e) => { e.target.replaceWith(h("div", { class: "faint scope-err", text: "Gráfico indisponível" })); } });
  }
  function drawGraphs() {
    side.className = "rv-side wide";
    const tab = (key, label) => h("button", { role: "tab", class: RV.graph === key ? "on" : "", "aria-selected": RV.graph === key ? "true" : "false",
      onclick: () => { RV.graph = key; drawGraphs(); }, text: label });
    const g = graticule(RV.graph);
    fill(side, 
      h("div", { class: "rv-head two" },
        h("div", {}, h("span", { class: "tt", text: "Gráficos do frame" }), h("br"),
          h("span", { class: "mono faint", text: `${nn} · ${tcOf(cur.frame)}` })),
        h("span", { class: "pill", text: "lido do vídeo original · Rec.709 faixa limitada" })),
      !M.has_video ? h("div", { class: "notice" }, icon("alert"), h("span", { text: "Os gráficos leem o vídeo original, que não está neste computador." })) : null,
      h("div", { class: "seg", role: "tablist", "aria-label": "Forma de onda" }, tab("luma", "Luma"), tab("parade", "Parade RGB")),
      h("div", { class: "gbox" }, h("div", { class: "gt", text: RV.graph === "luma" ? "Forma de onda (waveform) · Y′ em %" : "Parade RGB · %" }),
        h("div", { class: "wf" }, M.has_video ? scopeImg(RV.graph) : null, g.svg, h("div", { class: "lab" }, g.labels))),
      h("div", { class: "gbox row", style: { gap: "18px", alignItems: "center" } },
        h("div", { class: "vs" }, M.has_video ? scopeImg("vector") : null, scopeOverlay(V.scope)),
        h("div", { class: "muted", style: { fontSize: "12px", lineHeight: 1.5, flex: 1 } },
          h("b", { style: { color: "var(--text-2)" }, text: "Vectorscope YUV deste frame" }), h("br"),
          "Quadrados coloridos: alvos de cor Rec.709 a 75%. Linha tracejada: tom de pele (123°).", h("br"),
          "O vectorscope do resumo geral (cor média de todos os vídeos) não muda.")));
  }

  // ---- P: conta-gotas
  let hover = null;            // leitura sob o mouse
  let pickBusy = false, pickNext = null;
  async function pickHover(e) {
    const p = toVideo(e);
    const inside = p.x >= 0 && p.y >= 0 && p.x < W && p.y < H;
    cross.classList.toggle("hidden", !inside);
    loupe.classList.toggle("hidden", !inside || !M.has_video);
    if (!inside) return;
    Object.assign(cross.style, { left: p.cx + "px", top: p.cy + "px" });
    const L = 3;                      // 3 pixels da tela por pixel do vídeo na lupa
    const lx = p.cx + 150 > vw.clientWidth ? p.cx - 150 : p.cx + 30;
    const ly = Math.max(6, Math.min(vw.clientHeight - 150, p.cy - 140));
    Object.assign(loupe.style, { left: lx + "px", top: ly + "px", backgroundImage: `url("${frameUrl(cur.frame, "full")}")`,
      backgroundSize: `${W * L}px ${H * L}px`, backgroundPosition: `${-(p.x + 0.5) * L + 60}px ${-(p.y + 0.5) * L + 60}px` });
    if (!M.has_video) return;
    pickNext = { x: p.x, y: p.y, f: cur.frame };
    if (pickBusy) return;
    pickBusy = true;
    while (pickNext) {
      const q = pickNext; pickNext = null;
      try {
        const r = await api("pick", { id: vid, f: q.f, x: q.x, y: q.y });
        if (RV.mode === "pick" && q.f === cur.frame) { hover = r; drawPickValues(); }
      } catch (err) { /* sem leitura */ }
    }
    pickBusy = false;
  }
  function pickFix(e) {
    if (!M.has_video) { toast("O conta-gotas lê o vídeo original, que não está neste computador.", true); return; }
    const p = toVideo(e);
    if (p.x < 0 || p.y < 0 || p.x >= W || p.y >= H) return;
    if (RV.picks.length >= 4) { toast("Já há 4 pontos fixados. Use “Limpar pontos” para começar de novo.", true); return; }
    RV.picks.push({ x: p.x, y: p.y, r: null });
    drawOverlay();
    repick();
  }
  async function repick() {
    if (!M.has_video) return;
    const f = cur.frame;
    await Promise.all(RV.picks.map(async (p) => {
      try { const r = await api("pick", { id: vid, f, x: p.x, y: p.y }); if (f === cur.frame) p.r = r; } catch (e) { p.r = null; }
    }));
    if (RV.mode === "pick" && f === cur.frame) drawPick();
  }
  let pv = null;             // partes do painel do conta-gotas
  function drawPick() {
    side.className = "rv-side wide";
    pv = { head: h("span", { class: "mono faint" }), sw: h("div", { class: "swatch" }), vals: h("div", { class: "pvals" }),
      skin: h("div", { class: "skin" }), vs: h("div", { class: "vs small" }), wf: h("div", { class: "wf tall" }),
      fixed: h("div", { class: "plist" }), count: h("span", { class: "muted", style: { fontSize: "12px" } }) };
    const bg = h("input", { type: "checkbox", checked: RV.showBg ? true : null });
    bg.addEventListener("change", () => { RV.showBg = bg.checked; drawPick(); });
    fill(side, 
      h("div", { class: "rv-head two" },
        h("div", {}, h("span", { class: "tt", text: "Conta-gotas" }), h("br"), pv.head),
        h("span", { class: "pill", text: "vídeo original · média 9 × 9 px" })),
      !M.has_video ? h("div", { class: "notice" }, icon("alert"), h("span", { text: "O conta-gotas lê o vídeo original, que não está neste computador." })) : null,
      h("div", { class: "row", style: { gap: "14px", alignItems: "stretch" } }, pv.sw, pv.vals),
      pv.skin,
      h("div", { class: "row", style: { gap: "12px", alignItems: "stretch" } },
        h("div", { class: "gbox", style: { flex: "none" } }, h("div", { class: "gt", text: "Vectorscope" }), pv.vs),
        h("div", { class: "gbox", style: { flex: 1, minWidth: 0 } }, h("div", { class: "gt", text: "Waveform (luma)" }), pv.wf)),
      h("div", { class: "row", style: { gap: "10px" } },
        h("button", { class: "btn small", text: "Limpar pontos", onclick: () => { RV.picks = []; drawOverlay(); drawPick(); } }),
        h("span", { style: { flex: 1 } }), pv.count),
      pv.fixed,
      h("label", { class: "check", style: { fontSize: "13px" } }, bg, "Mostrar o gráfico completo do frame ao fundo"));
    // vectorscope: gráfico do frame + alvos + pontos
    if (RV.showBg && M.has_video) pv.vs.appendChild(scopeImg("vector"));
    pv.vs.appendChild(scopeOverlay(V.scope));
    pv.vsDots = h("div", { class: "dots" });
    pv.vs.appendChild(pv.vsDots);
    const g = graticule("luma");
    if (RV.showBg && M.has_video) pv.wf.appendChild(scopeImg("luma"));
    pv.wf.append(g.svg, h("div", { class: "lab" }, g.labels));
    pv.wfDots = h("div", { class: "dots" });
    pv.wf.appendChild(pv.wfDots);
    drawPickValues();
  }
  function drawPickValues() {
    if (!pv || RV.mode !== "pick") return;
    const r = hover || (RV.picks.length ? RV.picks[RV.picks.length - 1].r : null);
    pv.head.textContent = `${nn} · ${tcOf(cur.frame)}` + (r ? ` · ponto em (${r.x}, ${r.y})` : "");
    pv.count.textContent = `Fixados: ${RV.picks.length} de 4 · clique no frame para fixar`;
    const kv = (k2, v) => [h("span", { class: "muted", text: k2 }), h("span", { class: "mono", text: v })];
    if (r) {
      pv.sw.style.background = `rgb(${r.rgb.join(",")})`;
      pv.vals.replaceChildren(...kv("Y′ (brilho)", `${Math.round(r.Y)} · ${num(r.luma_pct, 0)} %`),
        ...kv("Cb / Cr", `${Math.round(r.Cb)} / ${Math.round(r.Cr)}`), ...kv("RGB", r.rgb.join(" · ")),
        ...kv("Ângulo", `${Math.round(r.angle)}°`), ...kv("Saturação", `${num(r.saturation_pct, 0)} %`));
      const d = Math.abs(r.skin_delta);
      pv.skin.className = "skin " + (d <= 15 ? "ok" : "far");
      pv.skin.replaceChildren(h("b", { text: d < 1 ? "Em cima da linha de pele." : `${Math.round(d)}° da linha de pele` }),
        d < 1 ? "" : `, ${r.skin_text.replace(/^\d+° /, "")}. `,
        r.saturation_pct < 3 ? "Cor quase neutra (cinza): o ângulo não diz muito." :
          d <= 15 ? "Se o ponto é pele, está dentro do normal." : "Se o ponto é pele, vale um olhar (passou de uns 15°).");
    } else {
      pv.sw.style.background = "transparent";
      pv.vals.replaceChildren(h("span", { class: "muted", style: { gridColumn: "1 / -1" }, text: "Passe o mouse sobre o frame." }));
      pv.skin.className = "skin hidden";
    }
    // pontos nos gráficos
    const dot = (x, y, color, label) => h("i", { style: { left: `${x * 100}%`, top: `${y * 100}%`, borderColor: color, background: label ? color : "transparent" }, text: label || "" });
    const vsPos = (q) => [(128 + 224 * q.pb) / 256, 1 - (128 + 224 * q.pr) / 256];
    const wfPos = (q) => [(q.x + 0.5) / W, (255.5 - q.Y) / 256];
    const pts = RV.picks.map((p, j) => [p.r, PICK_COLORS[j], String(j + 1)]).filter((x) => x[0]);
    if (hover) pts.push([hover, "#ffffff", ""]);
    pv.vsDots.replaceChildren(...pts.map(([q, c, l]) => dot(...vsPos(q), c, l)));
    pv.wfDots.replaceChildren(...pts.map(([q, c, l]) => dot(...wfPos(q), c, l)));
    pv.fixed.replaceChildren(...RV.picks.map((p, j) => h("div", { class: "pt" },
      h("b", { style: { background: PICK_COLORS[j] }, text: String(j + 1) }),
      h("span", { class: "mono", text: p.r ? `(${p.x}, ${p.y}) · Y′ ${num(p.r.luma_pct, 0)} % · ${Math.round(p.r.angle)}° · sat. ${num(p.r.saturation_pct, 0)} %` : `(${p.x}, ${p.y}) · lendo…` }),
      h("button", { class: "del", "aria-label": `Tirar o ponto ${j + 1}`, onclick: () => { RV.picks.splice(j, 1); drawOverlay(); drawPick(); } }, icon("close")))));
  }

  function drawSide() {
    if (RV.mode === "graphs") drawGraphs();
    else if (RV.mode === "pick") drawPick();
    else drawComment();
    tGraphs.classList.toggle("on", RV.mode === "graphs");
    tPick.classList.toggle("on", RV.mode === "pick");
    tClip.classList.toggle("on", clipOpen());
    vw.classList.toggle("picking", RV.mode === "pick");
    hint.textContent = RV.mode === "graphs" ? "Os gráficos acompanham o frame: com ← → eles se atualizam. G ou Esc fecha." :
      RV.mode === "pick" ? "Mova o mouse sobre o vídeo. Clique para fixar o ponto (até 4) · arraste para mover com zoom · P ou Esc sai." :
      "↑ ↓ de corte em corte · Shift + ← → anda 1 frame · roda do mouse ou pinça: zoom · Z: caber / 100% · T copiar para o Trello · N próxima aula";
    requestAnimationFrame(layoutViewer);
  }
  function setMode(m) {
    flushComment();
    RV.mode = m;
    hover = null;
    cross.classList.add("hidden"); loupe.classList.add("hidden");
    drawSide();
    if (m === "pick") repick();
  }

  // ------------------------------------------------------------------ V: trecho em volta do frame
  // Duração escolhida na caixa do trecho (pedido do JP: às vezes 4 s é muito, às vezes pouco).
  // Fica lembrada nas configurações para as próximas revisões.
  if (!RV.clipHalf) RV.clipHalf = Number(V.clip_half_s) || 4;
  const clipChoices = V.clip_choices || [1, 2, 3, 4, 6, 8, 10, 15];
  const secTxt = (x) => String(x).replace(".", ",");
  const clipOpen = () => !!clip;
  function openClip() {
    if (!M.has_video) { toast("O trecho precisa do vídeo na pasta deste computador.", true); return; }
    flushComment();
    const half = RV.clipHalf;
    const t = secondsOf(R, cur.frame);
    const start = Math.max(0, t - half), end = Math.min(M.duration, t + half);
    const video = h("video", { playsinline: true, preload: "auto" });
    const playBtn = h("button", { class: "icon-btn", "aria-label": "Tocar / pausar (espaço)" });
    const fill = h("i");
    const bar = h("div", { class: "cb" }, fill, h("b", { style: { left: `${((t - start) / (end - start)) * 100}%` } }));
    const meter = vuMeter();
    const c = clip = { video, start, end, base: 0, tries: [], meter };
    const live = () => clip === c;          // depois de fechar, os eventos do <video> não fazem nada
    const setIcon = () => playBtn.replaceChildren(rvIcon(video.paused ? "play" : "pause"));
    // 1º o vídeo original; se o navegador não tocar, um trecho em MP4 (H.264); por último, WebM
    const fallbacks = ["mp4", "webm"];
    const useClipFile = () => {
      const fmt = fallbacks.shift();
      if (!fmt) return false;
      c.base = start;
      video.src = `/api/clip?id=${vid}&f=${cur.frame}&fmt=${fmt}&h=${half}`;
      return true;
    };
    video.addEventListener("loadedmetadata", () => { if (!live()) return; video.currentTime = start - c.base; video.play().catch(() => {}); });
    video.addEventListener("timeupdate", () => {
      if (!live()) return;
      const now = video.currentTime + c.base;
      fill.style.width = `${Math.max(0, Math.min(1, (now - start) / (end - start))) * 100}%`;
      if (now >= end - 0.02 && !video.paused) { video.pause(); }
    });
    video.addEventListener("play", setIcon);
    video.addEventListener("pause", setIcon);
    video.addEventListener("playing", () => { if (live()) meterAttach(c); });
    video.addEventListener("error", () => {
      if (!live()) return;
      if (useClipFile()) return;
      toast("Não consegui tocar este trecho neste navegador.", true);
    });
    playBtn.addEventListener("click", () => togglePlay());
    bar.addEventListener("click", (e) => {
      const r = bar.getBoundingClientRect();
      if (!live()) return;
      video.currentTime = start + ((e.clientX - r.left) / r.width) * (end - start) - c.base;
      video.play().catch(() => {});
    });
    const lenSel = h("select", { class: "clip-len", "aria-label": "Duração do trecho", title: "Quanto tempo antes e depois do frame" },
      clipChoices.map((x) => h("option", { value: String(x), text: `${secTxt(x)} s antes e depois` })));
    lenSel.value = String(half);
    lenSel.addEventListener("change", async () => {
      RV.clipHalf = Number(lenSel.value);
      lenSel.blur();                          // o teclado (espaço, Esc) volta para o trecho
      closeClip(); openClip();
      try { await api("settings", { clip_half_s: RV.clipHalf }); } catch (e) { /* vale só agora */ }
    });
    clipBox.replaceChildren(video, meter.el, h("div", { class: "cc" },
      h("div", { class: "row", style: { gap: "12px", flexWrap: "wrap" } }, playBtn,
        h("span", { class: "mono", style: { color: "#fff", fontSize: "12px" }, text: `${tcOf(frameAt(R, start))} – ${tcOf(frameAt(R, end))}` }),
        lenSel,
        h("span", { style: { fontSize: "12px", color: "#d0d0d0" }, text: "espaço toca/pausa · Esc volta" })),
      bar));
    clipBox.classList.remove("hidden");
    setIcon();
    // o áudio do navegador precisa ser "acordado" no clique/tecla que abriu o trecho
    const ac = audioCtx();
    if (ac && ac.state !== "running") ac.resume().catch(() => {});
    if (M.playable) video.src = `/api/media?id=${vid}`; else useClipFile();
    drawSide();
  }
  function togglePlay() {
    if (!clip) return;
    const v = clip.video;
    if (v.paused) {
      if (v.currentTime + clip.base >= clip.end - 0.05) v.currentTime = clip.start - clip.base;
      v.play().catch(() => {});
    } else v.pause();
  }
  function closeClip() {
    if (!clip) return;
    const c = clip;
    clip = null;
    c.video.pause();
    meterDetach(c);
    c.video.removeAttribute("src");
    c.video.load();
    clipBox.replaceChildren();
    clipBox.classList.add("hidden");
    if (side.isConnected) drawSide();
  }

  // ---- medidor de áudio (pedido do JP): nível do trecho em tempo real, em dBFS (0 = máximo digital).
  // Usa o áudio do próprio navegador (Web Audio). Só liga o medidor quando o áudio do navegador está
  // funcionando: se não estiver, o trecho toca normal, só sem o medidor.
  const VU_MIN = -60;
  const vuPos = (db) => Math.max(0, Math.min(1, (db - VU_MIN) / -VU_MIN));
  function vuMeter() {
    const fillEl = h("i"), holdEl = h("b"), clipEl = h("span", { class: "vu-clip", text: "0 dB" });
    const ticks = [0, -6, -12, -18, -24, -36, -48].map((db) =>
      h("span", { class: "vu-t", style: { bottom: `${vuPos(db) * 100}%` }, text: db === 0 ? "0" : String(db).replace("-", "−") }));
    const peakTxt = h("span", { class: "vu-n mono", text: "—" });
    const el = h("div", { class: "vu", role: "meter", "aria-label": "Nível do áudio (dBFS)", "aria-valuemin": String(VU_MIN), "aria-valuemax": "0" },
      clipEl, h("div", { class: "vu-track" }, h("div", { class: "vu-scale" }, ticks), h("div", { class: "vu-bar" }, fillEl, holdEl)),
      h("span", { class: "vu-k", text: "pico" }), peakTxt);
    return { el, fillEl, holdEl, clipEl, peakTxt, level: VU_MIN, hold: VU_MIN, holdAt: 0, max: VU_MIN, overs: false, raf: 0, last: 0 };
  }
  function audioCtx() {
    if (RV.actx) return RV.actx;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { RV.actx = new AC(); } catch (e) { return null; }
    return RV.actx;
  }
  function meterAttach(c) {
    const ac = audioCtx(), m = c.meter;
    if (!ac || m.src) return;
    const go = () => {
      if (clip !== c || m.src || ac.state !== "running") return;
      try {
        m.src = ac.createMediaElementSource(c.video);
        m.an = ac.createAnalyser();
        m.an.fftSize = 2048;
        m.src.connect(m.an);
        m.an.connect(ac.destination);
      } catch (e) {
        m.el.classList.add("off");
        m.peakTxt.textContent = "indisp.";
        return;
      }
      m.buf = new Float32Array(m.an.fftSize);
      m.last = performance.now();
      const loop = (now) => {
        if (clip !== c) return;
        meterStep(m, now);
        m.raf = requestAnimationFrame(loop);
      };
      m.raf = requestAnimationFrame(loop);
    };
    if (ac.state === "running") go(); else ac.resume().then(go).catch(() => {});
  }
  function meterStep(m, now) {
    const dt = Math.min(0.1, (now - m.last) / 1000);
    m.last = now;
    let peak = 0;
    if (m.an.getFloatTimeDomainData) {
      m.an.getFloatTimeDomainData(m.buf);
      for (let i = 0; i < m.buf.length; i++) { const a = Math.abs(m.buf[i]); if (a > peak) peak = a; }
    } else {
      const b = m.bytes || (m.bytes = new Uint8Array(m.an.fftSize));
      m.an.getByteTimeDomainData(b);
      for (let i = 0; i < b.length; i++) { const a = Math.abs(b[i] - 128) / 128; if (a > peak) peak = a; }
    }
    const db = peak > 0 ? 20 * Math.log10(peak) : VU_MIN;
    // sobe na hora, desce 24 dB por segundo (como um medidor de pico)
    m.level = db >= m.level ? db : Math.max(db, m.level - 24 * dt, VU_MIN);
    if (db >= m.hold || now - m.holdAt > 1500) { m.hold = db; m.holdAt = now; }
    if (db > m.max) { m.max = db; m.peakTxt.textContent = `${num(Math.max(db, -99), 1)}`; }
    if (peak >= 0.999 && !m.overs) { m.overs = true; m.clipEl.classList.add("on"); }
    m.fillEl.style.clipPath = `inset(${(1 - vuPos(m.level)) * 100}% 0 0 0)`;
    m.holdEl.style.bottom = `${vuPos(m.hold) * 100}%`;
    m.holdEl.style.opacity = m.hold > VU_MIN + 1 ? "1" : "0";
    m.el.setAttribute("aria-valuenow", String(Math.round(m.level)));
  }
  function meterDetach(c) {
    const m = c.meter;
    cancelAnimationFrame(m.raf);
    try { if (m.src) m.src.disconnect(); if (m.an) m.an.disconnect(); } catch (e) { /* nada */ }
  }
  function toggleClip() { if (clipOpen()) closeClip(); else openClip(); }

  // ------------------------------------------------------------------ F, copiar
  function fullscreen() {
    if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); return; }
    if (vw.requestFullscreen) vw.requestFullscreen().catch(() => toast("Este navegador não deixou abrir em tela cheia.", true));
  }
  listen(document, "fullscreenchange", () => requestAnimationFrame(layoutViewer));

  function clipText() {
    const c = commentAt(cur.frame);
    const txt = cmtEl && cmtFrame === cur.frame ? cmtEl.value.trim() : (c ? c.text : "");
    return `Vídeo ${nn} · ${tcOf(cur.frame)}` + (txt ? ` · ${txt}` : "");
  }
  // ---- Trello (pedido do JP, 22/10): o Trello só aceita UMA coisa colada; e-mail e WhatsApp aceitam o pacote
  // imagem + texto. Então: uma imagem só, com o que está NA TELA (com zoom: só a parte ampliada, em
  // resolução cheia, e um mini-mapa no canto) e uma faixa embaixo com "Vídeo 01 · 00:00:44 · comentário".
  // Ideia da ferramenta "conferevideo" (colagem com o texto escrito na imagem).
  async function trelloPng(f) {
    const r = await fetch(frameUrl(f, "full"));
    if (!r.ok) throw new Error("frame");
    const bmp = await createImageBitmap(await r.blob());
    const fx = bmp.width / W, fy = bmp.height / H;          // a imagem pode ser a miniatura (vídeo fora daqui)
    const z = RV.zoom;
    let cx = 0, cy = 0, cw = W, ch = H;
    if (!z.fit) {
      cx = Math.max(0, -z.tx / z.s); cy = Math.max(0, -z.ty / z.s);
      cw = Math.min(W - cx, vw.clientWidth / z.s); ch = Math.min(H - cy, vw.clientHeight / z.s);
    }
    // largura da imagem final: o recorte em pixels do vídeo, entre 960 e 1600 (legível no Trello, arquivo leve)
    const ow = Math.round(Math.min(1600, Math.max(960, cw))), oh = Math.round((ow * ch) / cw);
    const pad = 24, fs = Math.round(ow / 48), lh = Math.round(fs * 1.4);
    const head = `Vídeo ${nn} · ${tcOf(f)}`;
    const c0 = commentAt(f);
    const txt = (cmtEl && cmtFrame === f ? cmtEl.value : (c0 ? c0.text : "")).trim();
    const c = document.createElement("canvas");
    const g = c.getContext("2d");
    try { await document.fonts.load(`600 ${fs}px "IBM Plex Sans"`); await document.fonts.load(`${fs}px "IBM Plex Sans"`); } catch (e) { /* fonte do sistema */ }
    const font = (w) => `${w} ${fs}px "IBM Plex Sans", -apple-system, "Segoe UI", sans-serif`;
    // quebra o comentário em linhas (respeita as linhas em branco que o JP digitar)
    g.font = font(400);
    const lines = [];
    for (const para of txt ? txt.split(/\n/) : []) {
      let line = "";
      for (const word of para.split(/\s+/).filter(Boolean)) {
        const test = line ? line + " " + word : word;
        if (g.measureText(test).width > ow - 2 * pad && line) { lines.push(line); line = word; } else line = test;
      }
      lines.push(line);
    }
    const band = pad + lh + lines.length * lh + Math.round(pad * 0.7);
    c.width = ow; c.height = oh + band;
    g.fillStyle = "#161616"; g.fillRect(0, 0, c.width, c.height);
    g.imageSmoothingQuality = "high";
    g.drawImage(bmp, cx * fx, cy * fy, cw * fx, ch * fy, 0, 0, ow, oh);
    if (!z.fit) {
      // mini-mapa: o frame inteiro pequeno no canto, com o retângulo da parte ampliada
      const mw = Math.round(ow * 0.2), mh = Math.round((mw * H) / W), mx = ow - mw - 14, my = 14;
      g.fillStyle = "rgba(0,0,0,.55)"; g.fillRect(mx - 3, my - 3, mw + 6, mh + 6);
      g.drawImage(bmp, 0, 0, bmp.width, bmp.height, mx, my, mw, mh);
      g.strokeStyle = "#7aa9ff"; g.lineWidth = 2;
      g.strokeRect(mx + (cx / W) * mw, my + (cy / H) * mh, Math.max(3, (cw / W) * mw), Math.max(3, (ch / H) * mh));
    }
    g.fillStyle = "#2a2a2a"; g.fillRect(0, oh, ow, 1);
    g.textBaseline = "top";
    g.font = font(600); g.fillStyle = "#7aa9ff";
    g.fillText(head, pad, oh + pad);
    g.font = font(400); g.fillStyle = "#ececec";
    lines.forEach((ln, i) => g.fillText(ln, pad, oh + pad + lh + i * lh));
    return await new Promise((ok, bad) => c.toBlob((b) => (b ? ok(b) : bad(new Error("png"))), "image/png"));
  }
  async function copyTrello() {
    flushComment();
    if (!window.ClipboardItem || !navigator.clipboard || !navigator.clipboard.write) {
      toast("Este navegador não deixa copiar imagem. Use o Chrome, o Edge ou o Safari.", true); return;
    }
    try {
      // a promessa vai dentro do ClipboardItem (o Safari exige)
      await navigator.clipboard.write([new ClipboardItem({ "image/png": trelloPng(cur.frame) })]);
      toast(RV.zoom.fit ? "Imagem para o Trello copiada (frame + comentário). Cole no cartão com ⌘V / Ctrl+V."
        : "Imagem para o Trello copiada: a parte ampliada + comentário. Cole no cartão com ⌘V / Ctrl+V.");
    } catch (e) {
      toast("Não foi possível copiar a imagem para o Trello.", true);
    }
  }
  async function copyText() {
    const t = clipText();
    try { await navigator.clipboard.writeText(t); toast("Comentário copiado."); }
    catch (e) { toast("O navegador não deixou copiar. Selecione o texto e copie à mão.", true); }
  }
  async function framePng(f) {
    const r = await fetch(frameUrl(f, "full"));
    if (!r.ok) throw new Error("frame");
    const bmp = await createImageBitmap(await r.blob());
    const c = document.createElement("canvas");
    c.width = bmp.width; c.height = bmp.height;
    c.getContext("2d").drawImage(bmp, 0, 0);
    return await new Promise((ok, bad) => c.toBlob((b) => (b ? ok(b) : bad(new Error("png"))), "image/png"));
  }
  async function copyFrame() {
    flushComment();
    const t = clipText();
    if (!window.ClipboardItem || !navigator.clipboard || !navigator.clipboard.write) { copyText(); return; }
    const png = framePng(cur.frame);
    const esc = (s) => s.replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
    const html = png.then((b) => new Promise((ok) => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.readAsDataURL(b); }))
      .then((u) => new Blob([`<p>${esc(t)}</p><img src="${u}" alt="">`], { type: "text/html" }));
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png, "text/html": html,
        "text/plain": new Blob([t], { type: "text/plain" }) })]);
      toast("Frame e comentário copiados. Cole no e-mail ou na conversa com o editor.");
    } catch (e) {
      try {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": framePng(cur.frame) })]);
        toast("Frame copiado (só a imagem). Use “Copiar só o comentário” para o texto.");
      } catch (e2) {
        copyText();
      }
    }
  }

  // ------------------------------------------------------------------ rodapé: vinhetas, filmstrip, áudio
  const strip = h("div", { class: "film", role: "list", "aria-label": "Frames marcados e avisos" });
  const vinBlock = (title, frames) => h("div", { class: "vin" }, h("span", { class: "caps", text: title }),
    h("div", { class: "row", style: { gap: "3px" } }, (frames || []).map((f) =>
      h("button", { class: "vt", "aria-label": `${title}: ${tcOf(f)}`, title: `${tcOf(f)} · frame ${f}`, onclick: () => goFrame(f) },
        h("img", { src: frameUrl(f, "thumb"), alt: "", loading: "lazy" })))),
    !(frames || []).length ? h("span", { class: "faint", style: { fontSize: "11px" }, text: "vinheta não achada" }) : null);
  function drawStrip() {
    strip.replaceChildren(...items.map((it, j) => h("button", { role: "listitem",
      class: "fi" + (it.warn ? " w" : "") + (it.dismissed ? " off" : "") + (it.steps ? " stack" : "") + (it.kind === "slide" ? " sl" : ""), "data-i": String(j),
      "aria-label": `${tcOf(it.frame)} · ${it.label}`, title: `${tcOf(it.frame)} · ${it.label}${it.note ? " · " + it.note : ""}`,
      onclick: () => goItem(j) },
      h("span", { class: "th" }, h("img", { src: frameUrl(it.frame, "thumb"), alt: "", loading: "lazy" }),
        it.warn && !it.dismissed ? h("i", { class: "dot" }) : null,
        it.steps ? h("span", { class: "ls", text: `lista · ${it.steps.length}` }) : null,
        h("i", { class: "cdot hidden" })),
      h("span", { class: "mono t", text: tcOf(it.frame) }))));
    if (!items.length) strip.appendChild(h("span", { class: "faint", style: { fontSize: "12px", alignSelf: "center" }, text: "Nada marcado neste vídeo." }));
  }
  function markStrip() {
    const cset = new Set(V.comments.map((c) => c.frame));
    strip.querySelectorAll(".fi").forEach((el) => {
      const j = Number(el.dataset.i);
      const on = j === cur.i && (items[j].frame === cur.frame || (items[j].steps && cur.step !== null));
      el.classList.toggle("on", on);
      el.querySelector(".cdot").classList.toggle("hidden", !cset.has(items[j].frame));
      if (on) el.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }
  const waveHead = h("div", { class: "wh" });
  const canvas = h("canvas", { class: "wc", role: "img", "aria-label": "Forma de onda do áudio do vídeo inteiro, com avisos e a posição atual. Clique para ir a um ponto." });
  const tip = h("div", { class: "wtip hidden" });
  const waveBox = h("div", { class: "wave" }, waveHead, h("div", { class: "wcw" }, canvas, tip));
  foot.append(h("div", { class: "strips" }, vinBlock("Vinheta → vídeo", V.vinheta.frames_in), h("span", { class: "vsep tall" }),
    h("div", { class: "filmw" }, h("span", { class: "caps", text: "Frames marcados e avisos" }), strip), h("span", { class: "vsep tall" }),
    vinBlock("Vídeo → vinheta", V.vinheta.frames_out)), waveBox);

  const audioWarns = () => items.filter((it) => it.source === "áudio" && !it.dismissed);
  function drawWaveHead() {
    const A = V.audio;
    const nSl = (V.slides || []).length;
    waveHead.replaceChildren(h("span", { class: "faint", text: A ? `Áudio · mínimo ${fmtDb(A.min_db)} · máximo ${fmtDb(A.peak_dbfs)} · média ${fmtDb(A.avg_db)}` : "Sem áudio neste vídeo" }),
      nSl ? h("span", { class: "wleg" }, h("i", { class: "sw-slide" }), plural(nSl, "slide na tela", "slides na tela")) : null);
    let lastX = -1e9;
    const wpx = canvas.clientWidth || 800;
    for (const it of audioWarns()) {
      const x = (secondsOf(R, it.frame) / M.duration) * wpx;
      if (x - lastX < 150 || x < (nSl ? 480 : 330)) continue;
      lastX = x;
      waveHead.appendChild(h("span", { class: "wl", style: x > wpx - 160 ? { right: "0" } : { left: `${x}px` }, text: `${it.label} ${tcOf(it.frame)}` }));
    }
  }
  function drawWave() {
    const A = V.audio;
    const cw = canvas.clientWidth, ch = canvas.clientHeight;
    if (!cw || !ch) return;
    const d = dpr();
    if (canvas.width !== Math.round(cw * d) || canvas.height !== Math.round(ch * d)) { canvas.width = Math.round(cw * d); canvas.height = Math.round(ch * d); }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(d, 0, 0, d, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    const D = M.duration || 1;
    const xOf = (t) => (t / D) * cw;
    const c0 = M.content ? secondsOf(R, M.content.first_frame) : 0, c1 = M.content ? secondsOf(R, M.content.end_frame) : D;
    // fora do conteúdo (vinhetas)
    ctx.fillStyle = "#202020";
    ctx.fillRect(0, 0, xOf(c0), ch);
    ctx.fillRect(xOf(c1), 0, cw - xOf(c1), ch);
    // slide em tela cheia: faixa roxa clara atrás da onda + linha roxa embaixo
    (V.slides || []).forEach(([f0, f1]) => {
      const x0 = xOf(secondsOf(R, f0)), x1 = Math.max(xOf(secondsOf(R, f1)), x0 + 2);
      ctx.fillStyle = "rgba(169,139,245,0.16)";
      ctx.fillRect(x0, 0, x1 - x0, ch);
      ctx.fillStyle = "#a98bf5";
      ctx.fillRect(x0, ch - 3, x1 - x0, 3);
    });
    const ranges = audioWarns().map((it) => [it.extra.start ?? secondsOf(R, it.frame), Math.max(it.extra.end ?? 0, (it.extra.start ?? 0) + 0.3)]);
    if (A && A.env && A.env.length) {
      const bw = 3, n = Math.floor(cw / bw), step = A.step || 0.1;
      for (let b = 0; b < n; b++) {
        const t0 = (b / n) * D, t1 = ((b + 1) / n) * D;
        let mx = -120;
        for (let q = Math.floor(t0 / step); q <= Math.min(A.env.length - 1, Math.floor(t1 / step)); q++) mx = Math.max(mx, A.env[q]);
        const hh = Math.max(1.5, Math.min(1, (mx + 60) / 60) * (ch - 10));
        const warn = ranges.some(([a, z]) => t1 >= a && t0 <= z);
        ctx.fillStyle = warn ? "#e8a33d" : (t1 < c0 || t0 > c1) ? "#4a4a4a" : "#6d6d6d";
        ctx.fillRect(b * bw, (ch - 2 - hh) / 2 + 4, bw - 1, hh);
      }
    }
    // cortes (marca curta no topo), avisos que não são de áudio (ponto âmbar), comentários (ponto azul)
    ctx.fillStyle = "#8f8f8f";
    V.cuts.forEach((c) => ctx.fillRect(Math.round(xOf(secondsOf(R, c.frame))), 0, 1, 5));
    ctx.fillStyle = "#e8a33d";
    items.filter((it) => it.warn && !it.dismissed && it.source !== "áudio").forEach((it) => {
      ctx.beginPath(); ctx.arc(xOf(secondsOf(R, it.frame)), 4, 2.5, 0, Math.PI * 2); ctx.fill();
    });
    ctx.fillStyle = "#7aa9ff";
    V.comments.forEach((c) => { ctx.beginPath(); ctx.arc(xOf(secondsOf(R, c.frame)), ch - 4, 2.5, 0, Math.PI * 2); ctx.fill(); });
    // "corte no meio da fala": só uma marca discreta (não é aviso)
    if (A && A.marks) {
      ctx.fillStyle = "#9a9a9a";
      A.marks.forEach((m) => { const x = xOf(m.time); ctx.beginPath(); ctx.moveTo(x - 3, ch); ctx.lineTo(x + 3, ch); ctx.lineTo(x, ch - 5); ctx.fill(); });
    }
    // posição atual
    ctx.fillStyle = "#4d8cf5";
    ctx.fillRect(Math.round(xOf(secondsOf(R, cur.frame))) - 1, 0, 2, ch);
  }
  function nearestAt(t) {
    const D = M.duration || 1, tol = (D / (canvas.clientWidth || 800)) * 6;
    const cands = [];
    items.forEach((it) => cands.push([Math.abs(secondsOf(R, it.frame) - t), `${it.label}${it.dismissed ? " (ignorado)" : ""}`]));
    V.cuts.forEach((c) => cands.push([Math.abs(secondsOf(R, c.frame) - t), "corte"]));
    V.comments.forEach((c) => cands.push([Math.abs(secondsOf(R, c.frame) - t), "comentário: " + c.text]));
    ((V.audio && V.audio.marks) || []).forEach((m) => cands.push([Math.abs(m.time - t), m.label + " (marca, não é aviso)"]));
    const near = cands.filter((c) => c[0] <= tol).sort((a, b) => a[0] - b[0]).map((c) => c[1]);
    const sl = (V.slides || []).findIndex(([f0, f1]) => t >= secondsOf(R, f0) && t <= secondsOf(R, f1));
    if (sl >= 0) near.push(`slide ${sl + 1} de ${V.slides.length} na tela`);
    return near;
  }
  canvas.addEventListener("mousemove", (e) => {
    const r = canvas.getBoundingClientRect();
    const t = ((e.clientX - r.left) / r.width) * M.duration;
    const near = nearestAt(t);
    tip.textContent = `${tcOf(frameAt(R, t))}${near.length ? " · " + near.slice(0, 2).join(" · ") : ""}`;
    tip.style.left = `${Math.min(e.clientX - r.left, r.width - 220)}px`;
    tip.classList.remove("hidden");
  });
  canvas.addEventListener("mouseleave", () => tip.classList.add("hidden"));
  canvas.addEventListener("click", (e) => {
    const r = canvas.getBoundingClientRect();
    const t = ((e.clientX - r.left) / r.width) * M.duration;
    const snap = Math.max(3, Math.round((M.duration / r.width) * 4 * R.fps));    // ~4 px
    goFrame(frameAt(R, t), snap);
  });

  // ------------------------------------------------------------------ ajustes (sem reanalisar)
  function adjustDialog() {
    const sens = h("input", { id: "adj-sens", type: "range", min: "0", max: "100", value: String(V.review.sensitivity) });
    const sv = h("b", { text: String(V.review.sensitivity) });
    sens.addEventListener("input", () => (sv.textContent = sens.value));
    const grp = h("select", { id: "adj-grp", class: "input" },
      [[4, "Mudanças na mesma região em até 4 s"], [8, "Mudanças na mesma região em até 8 s"],
       [12, "Mudanças na mesma região em até 12 s"], [0, "Não juntar"]].map(([v, t]) => h("option", { value: String(v), text: t })));
    grp.value = String(Number(V.review.group_gap_s));
    openModal("Ajustes da detecção", [
      h("p", { class: "muted", style: { margin: 0, fontSize: "13px" }, text: "Valem para todos os vídeos desta revisão e mudam na hora, sem analisar de novo." }),
      h("div", { class: "field" }, h("label", { for: "adj-sens" }, "Sensibilidade da detecção de frames · ", sv), sens,
        h("div", { class: "ends" }, h("span", { text: "Só as mudanças mais fortes" }), h("span", { text: "Mais frames marcados" }))),
      h("div", { class: "field" }, h("label", { for: "adj-grp", text: "Juntar listas e textos que entram aos poucos" }), grp),
      // pedido do JP (22/10): vídeo que voltou e abriu com a análise antiga
      h("div", { class: "adj-redo" },
        h("div", {}, h("b", { text: "Analisar de novo" }),
          h("span", { class: "muted", text: "Refaz a análise do zero, sem usar a guardada. Editor, comentários e horas do mês não mudam." })),
        M.has_video ? h("button", { class: "btn ghost small", onclick: () => reanalyzeDialog(vid, `vídeo ${nn}`, () => render()) },
          rvIcon("redo"), "Analisar de novo")
          : h("span", { class: "faint", style: { fontSize: "12px" }, text: "O vídeo não está neste computador." }))],
      [h("button", { class: "btn ghost", text: "Cancelar", onclick: closeModal }),
       h("button", { class: "btn", style: { background: "var(--accent)", borderColor: "var(--accent)" }, text: "Aplicar", onclick: async () => {
         try {
           await api("review/adjust", { sensitivity: Number(sens.value), group_gap_s: Number(grp.value) });
           closeModal();
           await reload();
           toast("Ajustes aplicados.");
         } catch (e) { toast(e.message, true); }
       } })]);
  }

  // ------------------------------------------------------------------ recarregar dados (depois de Ignorar/Aceitar/Ajustes)
  async function reload() {
    const keepKey = curItem() && curItem().key, keepFrame = cur.frame, onItem = curItem() && curItem().frame === cur.frame;
    const nv = await api("video?n=" + V.n);
    if (!nv.ready) { render(); return; }
    V = nv; items = V.items; byFrame = itemByFrame();
    drawTabs(); drawEditor(); drawNext(); drawCount(); drawSlideBtn(); drawStrip(); drawWaveHead(); drawWave();
    let j = onItem ? items.findIndex((it) => it.key === keepKey) : -1;
    if (j < 0 && onItem) j = items.findIndex((it) => it.frame === keepFrame);
    if (j >= 0) { cur.i = j; cur.frame = items[j].steps && cur.step != null ? items[j].steps[Math.min(cur.step, items[j].steps.length - 1)].frame : items[j].frame; show(); }
    else goFrame(keepFrame);
  }

  // ------------------------------------------------------------------ teclado
  listen(document, "keydown", (e) => {
    if (document.querySelector(".modal-back")) return;
    const t = e.target, tag = t && t.tagName;
    const typing = tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT" || (t && t.isContentEditable);
    if (e.key === "Escape") {
      if (typing) { t.blur(); return; }
      if (clipOpen()) { closeClip(); e.preventDefault(); return; }
      if (RV.mode) { setMode(null); e.preventDefault(); return; }
      return;
    }
    if (typing) return;
    if ((e.metaKey || e.ctrlKey) && !e.altKey && e.key.toLowerCase() === "c") {
      if (String(window.getSelection() || "").length) return;      // texto selecionado: cópia normal
      e.preventDefault(); copyFrame(); return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    const acts = {
      ArrowRight: () => (e.shiftKey ? goFrame(cur.frame + 1) : go(1)),
      ArrowLeft: () => (e.shiftKey ? goFrame(cur.frame - 1) : go(-1)),
      ArrowDown: () => goCut(1), ArrowUp: () => goCut(-1),
      n: () => nextLesson(), t: () => copyTrello(),
      c: () => focusComment(), v: () => toggleClip(), g: () => setMode(RV.mode === "graphs" ? null : "graphs"),
      p: () => setMode(RV.mode === "pick" ? null : "pick"), f: () => fullscreen(),
      "+": () => zoomAt(vw.clientWidth / 2, vw.clientHeight / 2, 1.25), "=": () => zoomAt(vw.clientWidth / 2, vw.clientHeight / 2, 1.25),
      "-": () => zoomAt(vw.clientWidth / 2, vw.clientHeight / 2, 0.8), "_": () => zoomAt(vw.clientWidth / 2, vw.clientHeight / 2, 0.8),
      z: () => toggleZoom(), " ": () => togglePlay(),
    };
    if (key === " " && !clipOpen()) return;
    if (acts[key]) { e.preventDefault(); acts[key](); }
  });
  let rz = null;
  listen(window, "resize", () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(() => { layoutViewer(); drawWaveHead(); drawWave(); }); });

  // ------------------------------------------------------------------ começar
  drawStrip();
  show();
  requestAnimationFrame(() => { layoutViewer(); drawWaveHead(); drawWave(); });
}
