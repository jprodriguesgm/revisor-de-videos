/* Revisor de Vídeos — telas (Início, Análise, Resumo geral; a revisão fica em revisao.js).
   Página local servida por revisor/server.py. Sem bibliotecas externas. */
"use strict";

// ====================================================================== utilidades

const $ = (sel, el = document) => el.querySelector(sel);

// replaceChildren(a, null, b) escreveria "null" na tela: aqui null/undefined/false são ignorados,
// como no h() (visto no teste do JP no Safari: "null" no cartão de progresso).
{
  const rc = Element.prototype.replaceChildren;
  Element.prototype.replaceChildren = function (...kids) {
    return rc.apply(this, kids.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  };
}

/** Cria um elemento: h("div", {class: "x", onclick: fn}, "texto", outroElemento) */
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  add(el, kids);
  return el;
}
function add(el, kids) {
  for (const c of kids.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
/** Ícones (texto fixo do próprio app, nunca dado do usuário). */
const ICONS = {
  check: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#7aa9ff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  alert: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.5"/></svg>',
  info: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/></svg>',
  lock: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
  folder: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  film: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5v5l4-2.5z" fill="currentColor"/></svg>',
  up: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>',
  close: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
};
function icon(name) {
  const t = document.createElement("template");
  t.innerHTML = ICONS[name];
  return t.content.firstChild;
}

async function api(path, body) {
  const opt = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  let r;
  try {
    r = await fetch("/api/" + path, opt);
  } catch (e) {
    throw new Error("O app parou de responder. Abra o Revisor de novo.");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ("Erro " + r.status));
  return data;
}

let toastTimer = null;
function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "show" + (err ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.className = ""), err ? 6000 : 3000);
}

const pad = (n) => String(n).padStart(2, "0");
/** 13:18 ou 1:02:03 (duração de um vídeo) */
function fmtClock(s) {
  if (s === null || s === undefined) return "—";
  s = Math.round(s);
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return hh ? `${hh}:${pad(mm)}:${pad(ss)}` : `${pad(mm)}:${pad(ss)}`;
}
/** 1:08:46 (totais do relatório de tempo) */
function fmtHMS(s) {
  if (s === null || s === undefined) return "—";
  s = Math.round(s);
  return `${Math.floor(s / 3600)}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}
/** 55 min 04 s / 2 h 18 min */
function fmtLong(s) {
  s = Math.round(s || 0);
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return hh ? `${hh} h ${pad(mm)} min` : `${mm} min ${pad(ss)} s`;
}
const num = (v, d = 1) => v.toFixed(d).replace(".", ",").replace("-", "−");
const fmtDb = (v) => (v === null || v === undefined ? "—" : num(v) + " dB");
const fmtPct = (v) => (v === null || v === undefined ? "—" : num(v) + "%");
function fmtDateBR(iso) {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}
function fmtUpdated(t) {
  if (!t) return "";
  const [d, hm] = t.split(" ");
  return `${fmtDateBR(d)} às ${hm.slice(0, 5)}`;
}
const stem = (f) => f.replace(/\.(mp4|mov|m4v)$/i, "");
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
/** Nome do vídeo nas listas: o arquivo já começa com o número ("01 Apresentação")? Usa como está. */
const vlabel = (v) => (/^\d/.test(stem(v.file)) ? stem(v.file) : `${pad(v.n)} · ${stem(v.file)}`);

// ====================================================================== navegação

const STEPS = [
  ["inicio", "Início"], ["analise", "Análise"], ["resumo", "Resumo"], ["revisao", "Revisão"], ["final", "Resumo final"],
];
let S = null;          // /api/state
let poll = null;       // timer da tela atual
let screenCleanup = null;   // a tela de revisão tira atalhos e timers ao sair

function route() {
  const parts = (location.hash || "#/inicio").slice(2).split("/");
  return { name: parts[0] || "inicio", arg: parts[1] };
}

function drawSteps(active) {
  const nav = $("#steps");
  nav.replaceChildren();
  const idx = STEPS.findIndex((s) => s[0] === active);
  STEPS.forEach(([key, label], i) => {
    const enabled = key === "inicio" || (S && S.review_open);
    const cls = "step " + (i === idx ? "active" : idx >= 0 && i < idx ? "done" : "");
    const a = h("a", { class: cls, href: enabled ? `#/${key}` : null, "aria-disabled": enabled ? null : "true",
                       "aria-current": i === idx ? "step" : null },
      h("span", { class: "n", text: String(i + 1) }), h("span", { class: "l", text: label }));
    nav.appendChild(a);
    if (i < STEPS.length - 1) nav.appendChild(h("span", { class: "sep", "aria-hidden": "true" }));
  });
}

// Uma tela de cada vez: se outra for pedida enquanto uma ainda carrega (trocar de aba ou apertar N
// rápido), a nova espera a anterior terminar e só a última pedida é desenhada. Antes as duas podiam
// se misturar na página, e os atalhos da tela antiga continuavam ligados.
let renderBusy = null, renderAgain = false;
async function render() {
  if (renderBusy) { renderAgain = true; return renderBusy; }
  renderBusy = (async () => {
    try {
      do { renderAgain = false; await renderNow(); } while (renderAgain);
    } finally { renderBusy = null; }
  })();
  return renderBusy;
}

async function renderNow() {
  clearInterval(poll);
  poll = null;
  if (screenCleanup) {
    try { screenCleanup(); } catch (e) { /* nada */ }
    screenCleanup = null;
  }
  closeModal();
  const r = route();
  try {
    S = await api("state");
  } catch (e) {
    toast(e.message, true);
  }
  drawSteps(r.name === "pacote" ? "final" : r.name);
  const screen = $("#screen");
  screen.replaceChildren();
  const fn = SCREENS[r.name] || SCREENS.inicio;
  try {
    await fn(screen, r.arg);
  } catch (e) {
    screen.replaceChildren(h("div", { class: "screen-center" },
      h("div", { class: "panel empty-state" }, h("p", { text: e.message }),
        h("a", { class: "btn", href: "#/inicio", text: "Voltar ao início" }))));
  }
}
window.addEventListener("hashchange", render);

// ====================================================================== janelas (modal)

function openModal(title, body, footer, wide) {
  closeModal();
  const back = h("div", { class: "modal-back", onclick: (e) => { if (e.target === back) closeModal(); } },
    h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": title,
               style: wide ? { width: "860px" } : null },
      h("header", {}, h("h2", { text: title }),
        h("button", { class: "icon-btn", "aria-label": "Fechar", onclick: closeModal }, icon("close"))),
      h("div", { class: "body" }, body),
      footer ? h("footer", {}, footer) : null));
  $("#modal-root").replaceChildren(back);
  const f = back.querySelector("button, input, select");
  if (f) f.focus();
}
function closeModal() { $("#modal-root").replaceChildren(); }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

/** Navegador de pastas do próprio app (quando a janela do sistema não abre). */
function browse(kind, start, onPick) {
  let cur = null, selFile = null;
  const roots = h("div", { class: "roots" });
  const list = h("div", { class: "list" });
  const where = h("input", { class: "input mono", "aria-label": "Caminho" });
  const pickBtn = h("button", { class: "btn primary", style: { height: "44px", fontSize: "14px" },
    text: kind === "folder" ? "Escolher esta pasta" : "Escolher este vídeo",
    onclick: () => { const p = kind === "folder" ? cur : selFile; if (p) { closeModal(); onPick(p); } } });
  async function go(path) {
    try {
      const d = await api("ls?path=" + encodeURIComponent(path || ""));
      if (d.roots && !roots.childElementCount) {
        d.roots.forEach((r) => roots.appendChild(h("button", { class: "item", onclick: () => go(r.path) },
          icon("folder"), r.name)));
      }
      if (!d.path) { if (d.roots && d.roots[0]) return go(d.roots[0].path); return; }
      cur = d.path; selFile = null; where.value = d.path;
      list.replaceChildren();
      if (d.parent) list.appendChild(h("button", { class: "item", onclick: () => go(d.parent) }, icon("up"), ".. (voltar)"));
      d.dirs.forEach((x) => list.appendChild(h("button", { class: "item", ondblclick: () => go(x.path),
        onclick: () => go(x.path) }, icon("folder"), x.name)));
      d.videos.forEach((x) => {
        const b = h("button", { class: "item", disabled: kind === "folder" ? true : null,
          onclick: () => { selFile = x.path; list.querySelectorAll(".item.sel").forEach((y) => y.classList.remove("sel")); b.classList.add("sel"); } },
          icon("film"), x.name);
        list.appendChild(b);
      });
      if (!d.dirs.length && !d.videos.length) list.appendChild(h("div", { class: "item faint", text: "Pasta vazia" }));
      if (kind === "folder" && d.videos.length) pickBtn.textContent = `Escolher esta pasta (${plural(d.videos.length, "vídeo", "vídeos")})`;
      else if (kind === "folder") pickBtn.textContent = "Escolher esta pasta";
    } catch (e) { toast(e.message, true); }
  }
  where.addEventListener("keydown", (e) => { if (e.key === "Enter") go(where.value); });
  openModal(kind === "folder" ? "Escolher a pasta dos vídeos" : "Escolher o arquivo da vinheta",
    [where, h("div", { class: "browser" }, roots, list)],
    [h("button", { class: "btn ghost", text: "Cancelar", onclick: closeModal }), pickBtn], true);
  go(start || "");
}

/** Janela do sistema; se não der, o navegador do app.
    Enquanto a janela do sistema está aberta, a página mostra um aviso (no Windows ela chegou a abrir
    atrás do navegador e parecia que o app tinha travado) com o navegador de pastas do app como saída. */
async function choose(kind, prompt, start, onPick) {
  let gaveUp = false;
  const what = kind === "folder" ? "a pasta" : "o arquivo";
  const waitBox = setTimeout(() => {
    openModal(kind === "folder" ? "Escolha a pasta na janela que abriu" : "Escolha o arquivo na janela que abriu", [
      h("p", { style: { margin: 0 }, text: `Abri a janela do sistema para você escolher ${what}.` }),
      h("p", { class: "muted", style: { margin: 0, fontSize: "13px" },
        text: "Não está vendo? Ela pode ter aberto atrás do navegador: procure na barra de tarefas (Windows) ou no Dock (Mac). " +
              "Ou use o navegador de pastas do próprio app." })],
      [h("button", { class: "btn", type: "button", text: "Usar o navegador do app", onclick: () => {
        gaveUp = true; closeModal(); browse(kind, start, onPick);
      } })]);
  }, 700);
  try {
    const r = await api("dialog", { kind, prompt, start });
    clearTimeout(waitBox);
    if (gaveUp) return;                   // já escolheu pelo navegador do app
    closeModal();
    if (r.unsupported) return browse(kind, start, onPick);
    if (r.path) onPick(r.path);
  } catch (e) {
    clearTimeout(waitBox);
    if (gaveUp) return;
    closeModal();
    browse(kind, start, onPick);
  }
}

// ====================================================================== fila de pastas (pedido do JP, 21/10)
// Várias pastas analisadas uma depois da outra, em segundo plano. A revisão aberta pode ser trocada
// a qualquer hora sem parar a análise.

/** Abre a revisão de uma pasta da fila (ou salva) e vai para o 1º vídeo pronto. */
async function openQueued(project) {
  const r = await api("reviews/open", { project });
  const target = r.ready_n ? `#/revisao/${r.ready_n}` : r.folder_found ? "#/analise" : "#/resumo";
  if (location.hash === target) render(); else location.hash = target;
}

function queueStatus(e) {
  const pctTxt = `${Math.round((e.pct || 0) * 100)}%`;
  return {
    wait: [e.position === 1 ? "Na fila · é a próxima" : `Na fila · ${e.position}ª`, "var(--faint)"],
    running: [`Analisando · ${e.done} de ${plural(e.total, "vídeo", "vídeos")} · ${pctTxt}`, "var(--text)"],
    paused: [`Pausada · ${pctTxt}`, "var(--warn)"],
    done: [e.failed ? `Pronta · ${plural(e.failed, "vídeo", "vídeos")} com erro` : "Pronta", "var(--accent-text)"],
    cancelled: ["Interrompida", "var(--warn)"],
    error: ["Erro na análise", "var(--bad)"],
  }[e.status] || [e.status, "var(--faint)"];
}

/** Cartão com a lista da fila. onChange: chamado depois de mexer na fila. */
function queueCard(q, onChange) {
  const rows = q.entries.map((e) => {
    const [txt, color] = queueStatus(e);
    const remove = async () => {
      const doIt = async () => {
        try { await api("queue/remove", { project: e.project }); closeModal(); onChange(); }
        catch (err) { toast(err.message, true); }
      };
      if (e.status === "running" || e.status === "paused") {
        openModal("Tirar da fila?", h("p", { style: { margin: 0 }, text: `A análise de “${e.project}” para agora. ` +
          "Os vídeos que já ficaram prontos continuam guardados, e a revisão (comentários, editores) não muda." }),
          [h("button", { class: "btn", type: "button", text: "Cancelar", onclick: closeModal }),
           h("button", { class: "btn primary", type: "button", text: "Tirar da fila", onclick: doIt })]);
      } else doIt();
    };
    return h("div", { class: "q-row" + (e.open ? " open" : "") },
      h("div", { class: "q-main" },
        h("div", { class: "q-name" }, h("b", { title: e.folder, text: e.project }),
          e.open ? h("span", { class: "q-tag", text: "aberta" }) : null),
        h("span", { class: "q-st", style: { color }, text: txt }),
        e.status === "running" || e.status === "paused" ? h("div", { class: "bar" }, h("i", { style: { width: `${Math.round(e.pct * 100)}%` } })) : null),
      h("div", { class: "q-act" + (e.open && e.status !== "wait" ? " few" : "") },
        e.status === "wait" ? h("button", { class: "btn ghost small", type: "button", text: "Analisar agora",
          title: "Passa na frente; a pasta que está analisando continua logo depois",
          onclick: async () => { try { await api("queue/now", { project: e.project }); onChange(); } catch (err) { toast(err.message, true); } } }) : null,
        !e.open ? h("button", { class: "btn ghost-blue small", type: "button", text: "Abrir",
          onclick: async () => { try { await openQueued(e.project); } catch (err) { toast(err.message, true); } } }) : null,
        h("button", { class: "icon-btn q-x", type: "button", title: "Tirar da fila", "aria-label": `Tirar “${e.project}” da fila`, onclick: remove },
          icon("close"))));
  });
  const left = q.entries.filter((e) => ["wait", "running", "paused"].includes(e.status)).length;
  return h("div", { class: "card q-card" },
    h("div", { class: "q-head" }, h("span", { class: "caps", text: "Fila de análise" }),
      h("span", { class: "muted", style: { fontSize: "12px" }, text: left ? `tudo pronto em ~${Math.max(1, Math.round((q.eta_total_s || 0) / 60))} min` : "tudo analisado" })),
    rows,
    h("a", { class: "btn ghost small", href: "#/inicio", text: "+ Adicionar outra pasta" }));
}

/** Aviso da fila que ficou da última vez que o app fechou. */
function restoreNotice(q, onChange) {
  if (!q.restore || !q.restore.length) return null;
  const names = q.restore.map((x) => `“${x.project}”`).join(", ");
  const act = async (keep) => {
    try {
      const r = await api("queue/restore", { keep });
      if (keep && r.missing.length) toast(`Não achei a pasta de ${r.missing.join(", ")} neste computador.`, true);
      else if (keep) toast(`${plural(r.added, "pasta voltou", "pastas voltaram")} para a fila.`);
      onChange();
    } catch (e) { toast(e.message, true); }
  };
  return h("div", { class: "notice info q-restore" }, icon("info"),
    h("div", { style: { flex: 1 } }, `Da última vez ficaram na fila, sem terminar: ${names}.`),
    h("button", { class: "btn small", type: "button", text: "Continuar a fila", onclick: () => act(true) }),
    h("button", { class: "btn ghost small", type: "button", text: "Descartar", onclick: () => act(false) }));
}

/** Aviso no topo: a fila está andando (aparece em todas as telas). */
let queueChipTimer = null;
async function updateQueueChip() {
  const chip = $("#queue-chip");
  if (!chip || appGone) return;
  let q;
  try { q = await api("queue"); } catch (e) { return; }
  const running = q.entries.find((e) => e.status === "running" || e.status === "paused");
  const waiting = q.entries.filter((e) => e.status === "wait").length;
  const show = q.entries.length > 1 || (q.entries.length === 1 && !q.entries[0].open) || q.restore.length;
  chip.classList.toggle("hidden", !show);
  if (!show) return;
  // curto no topo (não empurra as etapas para 2 linhas); o detalhe aparece ao passar o mouse
  const done = q.entries.filter((e) => e.status === "done").length;
  let t, title;
  if (running) title = `Analisando “${running.project}”` + (waiting ? ` · mais ${plural(waiting, "pasta esperando", "pastas esperando")}` : "");
  else if (waiting) title = plural(waiting, "pasta esperando", "pastas esperando");
  else if (q.restore.length) title = "Pastas que ficaram na fila da última vez";
  else title = "Tudo analisado";
  t = q.entries.length ? `Fila ${done}/${q.entries.length}` : "Fila";
  chip.querySelector(".lb").textContent = t;
  chip.title = `Fila de análise: ${title}. Clique para ver.`;
  chip.setAttribute("aria-label", chip.title);
  chip.classList.toggle("busy", !!running && running.status === "running");
}

// ====================================================================== 1 · Início

const F = {               // o que está preenchido na tela de início (fica ao navegar)
  folder: "", info: null, professor: "", curso: "", disciplina: "", entrega: "", nome_tarja: "",
  sensitivity: null, group_gap_s: null, spell: null, transcribe: null, busy: false,
};

async function screenInicio(root) {
  const st = S.settings;
  if (F.sensitivity === null) {
    F.sensitivity = st.sensitivity; F.group_gap_s = st.group_gap_s; F.spell = st.spell; F.transcribe = st.transcribe;
  }
  // Voltando ao Início com uma pasta analisando (visto no Mac do JP, 21/10): o formulário ainda tinha a
  // MESMA pasta e o botão continuava "Analisar vídeos". Agora vem vazio, pronto para a próxima da fila.
  const qs0 = S.queue || {};
  if (qs0.running && F.info && F.info.scan.ok && F.info.scan.name === qs0.running) {
    Object.assign(F, { folder: "", info: null, professor: "", curso: "", disciplina: "", entrega: "", nome_tarja: "" });
  }

  // ---- coluna 1: dados da revisão
  const folderIn = h("input", { id: "pasta", class: "input mono", value: F.folder,
    placeholder: "Escolha ou cole o caminho da pasta", autocomplete: "off" });
  const checks = h("div", { class: "checks", "aria-live": "polite" });
  const prevBox = h("div");
  const prof = h("input", { id: "prof", class: "input", value: F.professor, list: "dl-prof", autocomplete: "off" });
  const curso = h("input", { id: "curso", class: "input", value: F.curso, list: "dl-curso", autocomplete: "off" });
  const disc = h("input", { id: "disc", class: "input", value: F.disciplina, list: "dl-disc", autocomplete: "off" });
  const ent = h("input", { id: "entrega", class: "input", value: F.entrega, placeholder: "dd/mm/aaaa",
    inputmode: "numeric", style: { width: "180px" }, autocomplete: "off" });
  const entNote = h("span", { class: "lock" });
  const tag = h("input", { id: "tarja", class: "input", value: F.nome_tarja, autocomplete: "off",
    placeholder: "Como o professor quer o nome na tarja" });
  const dl = (id, arr) => h("datalist", { id }, (arr || []).map((v) => h("option", { value: v })));

  [[prof, "professor"], [curso, "curso"], [disc, "disciplina"], [ent, "entrega"], [tag, "nome_tarja"]].forEach(([el, k]) =>
    el.addEventListener("input", () => { F[k] = el.value; }));
  prof.addEventListener("change", () => {
    if (!tag.value.trim() && prof.value.trim()) { tag.value = prof.value.trim(); F.nome_tarja = tag.value; }
  });

  function drawChecks() {
    checks.replaceChildren();
    prevBox.replaceChildren();
    const inf = F.info;
    if (!inf) return;
    const sc = inf.scan;
    if (sc.error) {
      checks.appendChild(h("div", { class: "bad" }, icon("alert"), sc.error));
    } else {
      checks.appendChild(h("div", { class: "ok" }, icon("check"),
        `${plural(sc.count, "vídeo", "vídeos")} · ${fmtLong(sc.total_s)} no total`));
      sc.videos.filter((v) => v.error).forEach((v) =>
        checks.appendChild(h("div", { class: "bad", title: v.detail || "" }, icon("alert"), `${v.file}: ${v.error}. Fica de fora da análise.`)));
    }
    if (sc.report) {
      const r = sc.report;
      checks.appendChild(h("div", { class: "ok" }, icon("check"), "Relatório de tempo lido ",
        h("span", { class: "mono faint", style: { fontSize: "12px" }, text: r.file })));
      checks.appendChild(h("div", { class: "sub",
        text: `bruto ${fmtHMS(r.total_raw_s)} · editado ${fmtHMS(r.total_edited_s)} · aproveitamento ${fmtPct(r.usage_pct)}` }));
    } else if (sc.ok) {
      checks.appendChild(h("div", { class: "sub", style: { paddingLeft: 0 },
        text: "Sem relatório de tempo nesta pasta: a análise roda e gravado/editado ficam vazios." }));
    }
    if (sc.warnings && sc.warnings.length) {
      checks.appendChild(h("div", { class: "notice", style: { marginTop: "6px" } }, icon("alert"),
        h("div", {}, sc.warnings.length === 1 ? sc.warnings[0] :
          [h("span", { text: "Conferir no relatório de tempo:" }), h("ul", {}, sc.warnings.map((w) => h("li", { text: w })))])));
    }
    if (inf.prev) {
      const p = inf.prev;
      prevBox.appendChild(h("div", { class: "notice info" }, icon("info"),
        h("span", { text: `Esta pasta já tem uma revisão (salva em ${fmtUpdated(p.updated)}` +
          (p.comments ? `, ${plural(p.comments, "comentário", "comentários")}` : "") +
          "). Analisar continua a mesma revisão: editores e comentários ficam." })));
    }
    drawEntrega();
  }
  function drawEntrega() {
    const inf = F.info;
    const locked = !!(inf && inf.prev && inf.prev.entrega_locked);
    ent.readOnly = locked;
    entNote.replaceChildren(icon("lock"), locked ? "Travada: é a data salva nesta revisão." :
      `Sugerida ${inf && inf.suggest.entrega_from === "data dos arquivos" ? "pela data dos arquivos" : "pelo relatório de tempo"}. Depois de salva, não muda mais.`);
  }

  async function loadFolder(path, fromPicker) {
    path = (path || "").trim();
    if (!path) return;
    F.folder = path; folderIn.value = path;
    checks.replaceChildren(h("div", { class: "faint", text: "Lendo a pasta…" }));
    try {
      const inf = await api("folder?path=" + encodeURIComponent(path));
      const changed = !F.info || F.info.scan.folder !== inf.scan.folder;
      F.info = inf;
      if (inf.scan.ok && (changed || fromPicker)) {
        const sg = inf.suggest;
        F.professor = sg.professor || ""; F.curso = sg.curso; F.disciplina = sg.disciplina;
        F.entrega = fmtDateBR(sg.entrega); F.nome_tarja = sg.nome_tarja || sg.professor || "";
        if (inf.prev && inf.prev.sensitivity != null) F.sensitivity = inf.prev.sensitivity;
        if (inf.prev && inf.prev.group_gap_s != null) F.group_gap_s = inf.prev.group_gap_s;
        prof.value = F.professor; curso.value = F.curso; disc.value = F.disciplina; ent.value = F.entrega;
        tag.value = F.nome_tarja; sens.value = F.sensitivity; grp.value = String(F.group_gap_s);
      }
      drawChecks();
      drawGo();
    } catch (e) {
      F.info = null;
      checks.replaceChildren(h("div", { class: "bad" }, icon("alert"), e.message));
    }
  }
  folderIn.addEventListener("change", () => loadFolder(folderIn.value));
  folderIn.addEventListener("keydown", (e) => { if (e.key === "Enter") loadFolder(folderIn.value); });

  const colA = h("div", { class: "col" },
    h("span", { class: "caps", text: "Dados da revisão" }),
    h("div", { class: "field" },
      h("label", { for: "pasta", text: "Pasta dos vídeos" }),
      h("div", { class: "row" }, folderIn,
        h("button", { class: "btn", text: "Escolher pasta",
          onclick: () => choose("folder", "Escolha a pasta com os vídeos editados", F.folder || st.last_folder,
            (p) => loadFolder(p, true)) })),
      checks),
    prevBox,
    h("div", { class: "row", style: { gap: "14px", alignItems: "flex-start" } },
      h("div", { class: "field", style: { flex: "0.8" } }, h("label", { for: "prof", text: "Professor" }), prof),
      h("div", { class: "field", style: { flex: "1.2" } },
        h("label", { for: "curso" }, "Curso ", h("span", { class: "opt", text: "(opcional)" })), curso)),
    h("div", { class: "field" },
      h("label", { for: "disc" }, "Disciplina ", h("span", { class: "opt", text: "(opcional)" })), disc,
      h("span", { class: "hint", text: "Professor, curso e disciplina sugerem valores já usados em revisões anteriores." })),
    h("div", { class: "field" }, h("label", { for: "entrega", text: "Entrega da edição" }),
      h("div", { class: "row", style: { gap: "12px" } }, ent, entNote)),
    h("div", { class: "field" }, h("label", { for: "tarja", text: "Nome na tarja" }), tag,
      h("span", { class: "hint", text: "A tarja de cada vídeo é comparada com este nome. Fica lembrado para o próximo vídeo deste professor." })),
    dl("dl-prof", st.history.professores), dl("dl-curso", st.history.cursos), dl("dl-disc", st.history.disciplinas));

  // ---- coluna 2: análise
  const vrow = (label, key) => {
    const path = st[key];
    const ok = S.vinhetas_ok[key === "vinheta_in" ? "in" : "out"];
    return h("div", { class: "v" },
      h("span", { class: "k", text: label }),
      h("span", { class: "f" + (ok ? "" : " missing"), title: path || "",
        text: ok ? path.split(/[\\/]/).pop() : path ? "arquivo não encontrado" : "não escolhida" }),
      h("button", { class: "btn ghost small", text: path ? "Trocar" : "Escolher",
        "aria-label": `${path ? "Trocar" : "Escolher"} a vinheta ${label.toLowerCase()}`,
        onclick: () => choose("file", `Escolha o arquivo da vinheta ${label.toLowerCase()}`,
          path ? path.replace(/[\\/][^\\/]*$/, "") : st.last_folder,
          async (p) => {
            try { await api("settings", { [key]: p }); toast("Vinheta salva."); render(); }
            catch (e) { toast(e.message, true); }
          }) }));
  };
  const sens = h("input", { id: "sens", type: "range", min: "0", max: "100", value: String(F.sensitivity) });
  sens.addEventListener("input", () => { F.sensitivity = Number(sens.value); });
  const grp = h("select", { id: "grupo", class: "input" },
    [[4, "Mudanças na mesma região em até 4 s"], [8, "Mudanças na mesma região em até 8 s"],
     [12, "Mudanças na mesma região em até 12 s"], [0, "Não juntar"]].map(([v, t]) =>
      h("option", { value: String(v), text: t })));
  grp.value = String(F.group_gap_s);
  grp.addEventListener("change", () => { F.group_gap_s = Number(grp.value); });
  const spell = h("input", { type: "checkbox", checked: F.spell ? true : null });
  spell.addEventListener("change", () => { F.spell = spell.checked; });
  const talk = h("input", { type: "checkbox", checked: F.transcribe ? true : null });
  talk.addEventListener("change", () => { F.transcribe = talk.checked; });

  // com outra pasta analisando, "Analisar" vira "Adicionar à fila" (a revisão aberta não muda)
  const qs = S.queue || {};
  const sameRunning = () => !!(qs.running && F.info && F.info.scan.ok && F.info.scan.name === qs.running);
  const busyOther = () => !!qs.running && !sameRunning();
  const goLabel = () => (sameRunning() ? "Ver a análise" : busyOther() ? "Adicionar à fila" : "Analisar vídeos");
  const go = h("button", { class: "btn primary", text: goLabel(), onclick: start });
  const goHint = h("span", { class: "hint", style: { textAlign: "center" } });
  // pasta que já está analisando: recomeçar só se pedir (ex.: desligar "Ouvir as falas" no meio)
  const restart = h("button", { class: "btn ghost small hidden", type: "button", text: "Recomeçar a análise desta pasta com estas escolhas",
    onclick: () => start(true) });
  function drawGo() {
    go.textContent = goLabel();
    goHint.textContent = sameRunning()
      ? "Esta pasta já está sendo analisada agora. Para pôr outra pasta na fila, escolha outra pasta."
      : busyOther()
        ? `A análise de “${qs.running}” continua. Esta pasta entra na fila e é analisada logo depois, sozinha.`
        : "A análise roda em segundo plano. Você começa a revisar assim que o primeiro vídeo ficar pronto.";
    restart.classList.toggle("hidden", !sameRunning());
  }
  async function start(force) {
    if (sameRunning() && force !== true) { location.hash = "#/analise"; return; }
    if (!F.info || !F.info.scan.ok) {
      if (folderIn.value.trim() && (!F.info || F.info.scan.folder !== folderIn.value.trim())) await loadFolder(folderIn.value);
      if (!F.info || !F.info.scan.ok) { toast("Escolha uma pasta com vídeos.", true); folderIn.focus(); return; }
    }
    if (!prof.value.trim()) { toast("Preencha o professor.", true); prof.focus(); return; }
    if (!ent.readOnly && !/^\d{2}\/\d{2}\/\d{4}$/.test(ent.value.trim())) {
      toast("Preencha a entrega da edição no formato dd/mm/aaaa.", true); ent.focus(); return;
    }
    go.disabled = true; go.textContent = "Começando…";
    try {
      const r = await api("start", {
        folder: F.info.scan.folder, professor: prof.value, curso: curso.value, disciplina: disc.value,
        entrega: ent.value, nome_tarja: tag.value, sensitivity: F.sensitivity, group_gap_s: F.group_gap_s,
        spell: F.spell, transcribe: F.transcribe,
      });
      if (r.queued) {
        toast(`“${r.project}” entrou na fila (${r.position === 1 ? "é a próxima" : r.position + "ª"}). Pode escolher outra pasta.`);
        Object.assign(F, { folder: "", info: null, professor: "", curso: "", disciplina: "", entrega: "", nome_tarja: "" });
        render();
        return;
      }
      location.hash = "#/analise";
    } catch (e) {
      toast(e.message, true);
      go.disabled = false; drawGo();
    }
  }

  const colB = h("div", { class: "col" },
    h("span", { class: "caps", text: "Análise" }),
    h("div", { class: "field" },
      h("span", { class: "label", text: "Vinhetas de referência" }),
      h("div", { class: "vinhetas" }, vrow("Inicial", "vinheta_in"), vrow("Final", "vinheta_out")),
      h("span", { class: "hint", text: "Salvas uma vez. O app usa os arquivos para achar as vinhetas em cada vídeo." })),
    h("div", { class: "field" },
      h("label", { for: "sens", text: "Sensibilidade da detecção de frames" }), sens,
      h("div", { class: "ends" }, h("span", { text: "Só as mudanças mais fortes" }), h("span", { text: "Mais frames marcados" }))),
    h("div", { class: "field" }, h("label", { for: "grupo", text: "Juntar listas e textos que entram aos poucos" }), grp),
    h("div", { class: "field", style: { gap: "6px" } },
      h("label", { class: "check" }, spell, "Conferir a ortografia do texto na tela"),
      h("span", { class: "hint", style: { paddingLeft: "30px" }, text: "Português (Brasil), inglês, latim e a sua lista de termos." })),
    h("div", { class: "field", style: { gap: "6px" } },
      h("label", { class: "check" }, talk, "Ouvir as falas"),
      h("span", { class: "hint", style: { paddingLeft: "30px" },
        text: "Procura “errei”, “retomando”, takes repetidos e corte no meio da fala. Deixa a análise mais demorada." })),
    go, goHint, restart);

  const openSaved = h("button", { class: "btn ghost", style: { fontSize: "14px" }, onclick: savedDialog },
    icon("folder"), "Abrir revisão salva");

  // fila (quando há mais de uma pasta) embaixo do formulário; fila antiga em cima
  const qBox = h("div", { class: "start-q" });
  async function drawQueue() {
    let q;
    try { q = await api("queue"); } catch (e) { return; }
    const others = q.entries.length > 1 || (q.entries.length === 1 && !q.entries[0].open);
    qBox.replaceChildren(restoreNotice(q, () => render()), others ? queueCard(q, drawQueue) : null);
  }
  // primeira vez numa unidade: sem equipe cadastrada
  const firstTime = !(S.editors || []).length ? h("div", { class: "notice info" }, icon("info"),
    h("span", { style: { flex: 1 } }, "Primeira vez? Cadastre os editores da sua equipe em ",
      h("a", { href: "#/config/equipe", text: "Configurações → Equipe" }),
      ". Eles aparecem na escolha de quem editou cada vídeo e no relatório do mês.")) : null;
  root.appendChild(h("div", { class: "screen-center" }, h("div", { class: "start-wrap" }, firstTime,
    h("section", { class: "panel start" },
      h("div", { class: "start-head" },
        h("div", {}, h("h1", { text: busyOther() ? "Nova revisão · fila" : "Nova revisão" }),
          h("p", { text: busyOther() ? "Enquanto a análise roda, escolha a próxima pasta: ela entra na fila e é analisada em seguida."
            : "Escolha a pasta com os vídeos editados e confirme os dados. O resto o app lê sozinho." })),
        openSaved),
      h("div", { class: "cols" }, colA, h("div", { class: "vline" }), colB)),
    qBox)));

  drawGo();
  drawQueue();
  drawEntrega();
  if (F.folder) loadFolder(F.folder);   // relê: a revisão pode ter sido salva desde a última vez
}

async function savedDialog() {
  let d;
  try { d = await api("reviews"); } catch (e) { return toast(e.message, true); }
  const list = h("div", { class: "saved" });
  if (!d.reviews.length) list.appendChild(h("p", { class: "muted", text: "Nenhuma revisão salva neste computador ainda." }));
  d.reviews.forEach((r) => list.appendChild(h("button", { class: "item", onclick: async () => {
    try {
      const res = await api("reviews/open", { project: r.project });
      closeModal();
      if (res.folder_found) location.hash = res.queued && res.ready_n ? `#/revisao/${res.ready_n}` : "#/analise";
      else { toast("A pasta dos vídeos não está neste computador. Os dados da revisão abriram mesmo assim.", true); location.hash = "#/resumo"; }
      if (res.queued) toast("Outra pasta está analisando: esta entrou na fila. Os vídeos já analisados antes abrem normalmente.");
    } catch (e) { toast(e.message, true); }
  } },
    h("b", { text: r.project }),
    h("span", { class: "muted", text: [r.professor, r.curso, r.disciplina].filter(Boolean).join(" · ") }),
    h("span", { class: "faint", text: `Entrega ${fmtDateBR(r.entrega)} · ${plural(r.videos, "vídeo", "vídeos")} · ` +
      `${plural(r.comments, "comentário", "comentários")} · salva em ${fmtUpdated(r.updated)}` }))));
  openModal("Abrir revisão salva", list, [
    h("a", { class: "btn ghost", href: "#/pacote/abrir", onclick: closeModal, text: "Abrir pacote de outro computador" }),
    h("span", { style: { flex: 1 } }),
    h("button", { class: "btn ghost", text: "Fechar", onclick: closeModal })]);
}

// ====================================================================== 2 · Análise

async function screenAnalise(root) {
  const view = await api("review");
  if (!view.review) { location.hash = "#/inicio"; return; }
  const rv = view.review;
  const head = h("div", {}, h("h1", { text: "Analisando os vídeos" }),
    h("p", { text: `${[rv.professor, rv.curso, rv.disciplina].filter(Boolean).join(" · ")}. ` +
      "Você pode revisar os vídeos prontos enquanto o resto continua." }));
  const rows = h("div");
  const prog = h("div", { class: "card" });
  const rep = h("div", { class: "card" });
  const btnMain = h("button", { class: "btn primary" });
  const btnPause = h("button", { class: "btn ghost", style: { height: "44px", fontSize: "14px", borderRadius: "10px" } });

  const r = rv.report;
  rep.append(h("span", { class: "caps", text: "Relatório de tempo lido" }));
  if (r) {
    rep.append(
      h("div", { class: "kv" }, h("span", { text: "Gravado (bruto)" }), h("span", { text: fmtHMS(r.total_raw_s) })),
      h("div", { class: "kv" }, h("span", { text: "Editado" }), h("span", { text: fmtHMS(r.total_edited_s) })),
      h("div", { class: "kv" }, h("span", { text: "Descartado" }), h("span", { text: fmtHMS(r.discarded_s) })),
      h("div", { class: "kv total" }, h("span", { text: "Aproveitamento" }),
        h("span", { style: { color: "var(--accent-text)" }, text: fmtPct(r.usage_pct) })));
  } else {
    rep.append(h("span", { class: "muted", text: "Não há relatório de tempo nesta pasta." }));
  }

  const qBox = h("div", { class: "side-q" });
  const restoreBox = h("div");
  root.appendChild(h("div", { class: "screen-center", style: { padding: "32px 40px" } },
    h("div", { class: "wide" }, head, restoreBox,
      h("div", { class: "split" },
        h("section", { class: "panel table" },
          h("div", { class: "thead caps" }, h("span", { class: "c-n", text: "Nº" }), h("span", { class: "c-name", text: "Vídeo" }),
            h("span", { class: "c-dur", text: "Duração" }), h("span", { class: "c-st", text: "Situação" }),
            h("span", { class: "c-found", text: "Achados" })),
          rows),
        h("aside", { class: "side" }, prog, btnMain, btnPause, qBox, rep)))));

  let qSig = "";
  async function drawQueue(force) {
    let q;
    try { q = await api("queue"); } catch (e) { return; }
    const sig = JSON.stringify(q);
    if (!force && sig === qSig) return q;
    qSig = sig;
    const others = q.entries.length > 1 || (q.entries.length === 1 && !q.entries[0].open);
    qBox.replaceChildren(others ? queueCard(q, () => { drawQueue(true); tick(); }) : null);
    restoreBox.replaceChildren(restoreNotice(q, () => { drawQueue(true); tick(); }));
    return q;
  }

  async function tick() {
    let j;
    try { j = await api("job"); } catch (e) { toast(e.message, true); return; }
    const q = await drawQueue();
    if (j.state === "idle") {          // esta pasta está na fila, esperando a vez
      const me = q && q.entries.find((e) => e.open);
      rows.replaceChildren(...j.videos.map((v) => h("div", { class: "trow" },
        h("span", { class: "c-n", text: pad(v.n) }),
        h("span", { class: "c-name", title: v.file, style: { color: v.cached ? null : "var(--faint)" }, text: vlabel(v) }),
        h("span", { class: "c-dur", text: fmtClock(v.duration) }),
        h("div", { class: "c-st" }, h("span", { class: "s", style: { color: v.cached ? "var(--accent-text)" : "var(--faint)" },
          text: v.status === "erro" ? "Erro" : v.cached ? "Análise anterior" : "Na fila" })),
        h("span", { class: "c-found", text: v.cached ? "abre normalmente" : "—" }))));
      prog.replaceChildren(h("span", { class: "caps", text: "Esperando a vez" }),
        h("span", { style: { fontSize: "14px" }, text: q && q.running ? `Esta pasta começa quando “${q.running}” terminar` +
          (me && me.position > 1 ? ` (é a ${me.position}ª da fila).` : ".") : "Esta pasta começa em seguida." }),
        h("span", { class: "muted", style: { fontSize: "13px" }, text: me && me.eta_s ? `Análise desta pasta: cerca de ${Math.max(1, Math.round(me.eta_s / 60))} min` : "" }));
      const firstCached = j.videos.find((v) => v.cached);
      btnMain.textContent = firstCached ? `Revisar o vídeo ${pad(firstCached.n)} (análise anterior)` : "Revisar enquanto espera";
      btnMain.disabled = !firstCached;
      btnMain.onclick = () => firstCached && (location.hash = `#/revisao/${firstCached.n}`);
      btnPause.textContent = "Analisar esta agora";
      btnPause.onclick = async () => {
        try { await api("queue/now", { project: rv.project }); tick(); } catch (e) { toast(e.message, true); }
      };
      btnPause.classList.remove("hidden");
      return;
    }
    if (j.state === "none") {
      prog.replaceChildren(h("span", { class: "muted", text: "Nenhuma análise rodando." }));
      btnMain.textContent = "Ver resumo geral"; btnMain.onclick = () => (location.hash = "#/resumo");
      btnPause.classList.add("hidden");
      return;
    }
    rows.replaceChildren(...j.videos.map((v) => {
      const st = { ok: "Pronto", run: j.state === "paused" ? `Pausado · ${Math.round(v.pct * 100)}%` :
        `Analisando · ${Math.round(v.pct * 100)}%`, wait: "Na fila", erro: "Erro" }[v.status];
      const color = { ok: "var(--accent-text)", run: "var(--text)", wait: "var(--faint)", erro: "var(--bad)" }[v.status];
      let found = "—";
      if (v.row) {
        const c = v.row.counts;
        found = `${plural(c.frames, "frame", "frames")} · ${c.warnings ? plural(c.warnings, "aviso", "avisos") : "sem avisos"}`;
      } else if (v.status === "erro") found = v.error || "não foi possível analisar";
      return h("div", { class: "trow" + (v.status === "run" ? " run" : "") },
        h("span", { class: "c-n", text: pad(v.n) }),
        h("span", { class: "c-name", title: v.file, style: { color: v.status === "wait" ? "var(--faint)" : null }, text: vlabel(v) }),
        h("span", { class: "c-dur", text: fmtClock(v.duration) }),
        h("div", { class: "c-st" }, h("span", { class: "s", style: { color }, text: st }),
          v.status === "run" ? h("div", { class: "bar" }, h("i", { style: { width: `${Math.round(v.pct * 100)}%` } })) : null),
        h("span", { class: "c-found", title: v.status === "erro" ? (v.detail || v.error || "") : null,
          style: v.status === "erro" ? { color: "var(--bad)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } : null,
          text: found }));
    }));
    const finished = ["done", "cancelled", "error"].includes(j.state);
    let eta = "";
    if (j.state === "paused") eta = "Análise pausada";
    else if (j.state === "done") eta = "Análise concluída";
    else if (j.state === "cancelled") eta = "Análise interrompida";
    else if (j.state === "error") eta = "Erro: " + (j.error || "");
    else if (j.eta_s !== null) eta = j.eta_s < 60 ? "Falta menos de 1 min" : `Faltam cerca de ${Math.round(j.eta_s / 60)} min`;
    prog.replaceChildren(h("span", { class: "caps", text: "Progresso" }),
      h("div", { class: "bignum" }, h("b", { text: String(j.done) }), h("span", { text: `de ${plural(j.total, "vídeo", "vídeos")}` })),
      j.failed ? h("span", { style: { fontSize: "13px", color: "var(--bad)" },
        text: `${plural(j.failed, "vídeo", "vídeos")} com erro (fica de fora)` }) : null,
      h("div", { class: "bar big", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100",
                 "aria-valuenow": String(Math.round(j.pct * 100)) }, h("i", { style: { width: `${Math.round(j.pct * 100)}%` } })),
      h("span", { class: "muted", style: { fontSize: "13px" }, text: eta }));
    const firstReady = j.videos.find((v) => v.status === "ok");
    if (finished) {
      btnMain.textContent = "Ver resumo geral";
      btnMain.disabled = false;
      btnMain.onclick = () => (location.hash = "#/resumo");
      btnPause.textContent = j.state === "cancelled" ? "Analisar o que faltou" : "Revisar o vídeo 01";
      btnPause.onclick = j.state === "cancelled" ? () => (location.hash = "#/inicio") : () => (location.hash = "#/revisao/1");
      btnPause.classList.remove("hidden");
      // com outras pastas na fila, continua atualizando a lista da fila (mais devagar)
      const q2 = q || { entries: [] };
      if (!q2.entries.some((e) => ["wait", "running", "paused"].includes(e.status))) { clearInterval(poll); poll = null; }
    } else {
      btnMain.textContent = firstReady ? `Revisar o vídeo ${pad(firstReady.n)} enquanto analisa` : "Revisar enquanto analisa";
      btnMain.disabled = !firstReady;
      btnMain.onclick = () => firstReady && (location.hash = `#/revisao/${firstReady.n}`);
      btnPause.textContent = j.state === "paused" ? "Continuar análise" : "Pausar análise";
      btnPause.title = q && q.entries.length > 1 ? "Pausar também segura a fila: a próxima pasta só começa depois de continuar." : "";
      btnPause.onclick = async () => { await api(j.state === "paused" ? "job/resume" : "job/pause", {}); tick(); };
      btnPause.classList.remove("hidden");
    }
  }
  await tick();
  if (!poll) poll = setInterval(tick, 800);
}

// ====================================================================== 3 · Resumo geral

function scopeOverlay(scope) {
  const NS = "http://www.w3.org/2000/svg";
  const s = (tag, attrs, text) => {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    if (text) el.textContent = text;
    return el;
  };
  const W = 400, c = W / 2;
  const svg = s("svg", { viewBox: `0 0 ${W} ${W}`, role: "img",
    "aria-label": "Vectorscope YUV: cor média de todos os vídeos, com os alvos de cor Rec.709 a 75% e a linha de tom de pele" });
  const t = Object.values(scope.targets);
  const rmax = Math.max(...t.map((p) => Math.hypot(p.x * W - c, p.y * W - c)));
  const g = s("g", { fill: "none", stroke: "#2c2c2c", "stroke-width": "1" });
  [0.25, 0.5, 0.75].forEach((k) => g.appendChild(s("circle", { cx: c, cy: c, r: rmax * k })));
  g.appendChild(s("path", { d: `M${c - rmax * 1.25} ${c}H${c + rmax * 1.25}M${c} ${c - rmax * 1.25}V${c + rmax * 1.25}` }));
  svg.appendChild(g);
  svg.appendChild(s("circle", { cx: c, cy: c, r: rmax, fill: "none", stroke: "#3a3a3a", "stroke-width": "1.5" }));
  const sk = Math.hypot(scope.skin.x * W - c, scope.skin.y * W - c) || 1;
  svg.appendChild(s("path", { d: `M${c} ${c}L${c + (scope.skin.x * W - c) / sk * rmax} ${c + (scope.skin.y * W - c) / sk * rmax}`,
    stroke: "#b5b5b5", "stroke-width": "1.2", "stroke-dasharray": "5 4" }));
  for (const [name, p] of Object.entries(scope.targets)) {
    const x = p.x * W, y = p.y * W;
    svg.appendChild(s("rect", { x: x - 7, y: y - 7, width: 14, height: 14, fill: "none", stroke: "#8a8a8a", "stroke-width": "1.5" }));
    const dx = x - c, dy = y - c, d = Math.hypot(dx, dy) || 1;
    svg.appendChild(s("text", { x: x + (dx / d) * 22, y: y + (dy / d) * 22 + 4, "text-anchor": "middle",
      "font-size": "12", fill: "#a8a8a8", "font-family": "IBM Plex Sans, sans-serif" }, name));
  }
  return svg;
}

async function screenResumo(root) {
  const view = await api("review");
  if (!view.review) { location.hash = "#/inicio"; return; }
  const rv = view.review;
  const vids = view.videos;
  const ready = vids.filter((v) => v.row);
  const au = view.audio;
  const nameOf = (id) => { const v = vids.find((x) => x.id === id); return v ? vlabel(v) : ""; };
  const job = view.job;
  const running = job && ["running", "paused", "idle"].includes(job.state);

  const stat = (k, v, w, color) => h("div", { class: "card stat" }, h("span", { class: "k", text: k }),
    h("span", { class: "v", style: color ? { color } : null, text: v }), h("span", { class: "w", title: w, text: w }));
  const maxColor = au.max && au.max.db > -1 ? "var(--warn)" : null;

  const editors = view.editors;
  const edOptions = (cur) => [h("option", { value: "", text: "Escolher" }),
    ...editors.map((e) => h("option", { value: e, text: e })),
    ...(cur && !editors.includes(cur) ? [h("option", { value: cur, text: cur })] : [])];
  const allSel = h("select", { class: "input", "aria-label": "Editor de todos os vídeos", style: { width: "auto" } },
    editors.map((e) => h("option", { value: e, text: e })));
  const applyAll = h("button", { class: "btn", style: { height: "40px", fontSize: "13px" }, text: "Aplicar a todos",
    onclick: async () => {
      try { await api("review/editor", { id: "all", editor: allSel.value }); toast(`${allSel.value} marcada em todos os vídeos.`); render(); }
      catch (e) { toast(e.message, true); }
    } });

  // sem equipe cadastrada (app novo numa unidade): mostra onde cadastrar
  const noTeam = !editors.length;
  const grid = h("div", { class: "panel", style: { borderRadius: "12px", overflow: "hidden" } },
    h("div", { class: "grid-head" }, h("span", { text: "Vídeo" }), h("span", { text: "Duração" }),
      h("span", { class: "num", text: "Mín." }), h("span", { class: "num", text: "Máx." }), h("span", { class: "num", text: "Média" }),
      h("span", { text: "Editor" }), h("span", { text: "Avisos" })),
    vids.map((v) => {
      const a = v.row && v.row.audio;
      const sel = h("select", { "aria-label": `Editor do vídeo ${pad(v.n)}`, class: v.editor ? "" : "empty" }, edOptions(v.editor));
      sel.value = v.editor || "";
      sel.addEventListener("change", async () => {
        try { await api("review/editor", { id: v.id, editor: sel.value || null }); sel.className = sel.value ? "" : "empty"; }
        catch (e) { toast(e.message, true); }
      });
      let warn;
      if (!v.row) warn = h("span", { class: "avisos none", text: v.missing ? "vídeo não está na pasta" : "ainda analisando…" });
      else {
        const w = v.row.warnings;
        warn = w.length ? h("span", { class: "avisos" }, plural(w.length, "aviso", "avisos"),
          h("br"), h("span", { class: "faint", text: `${w[0].label} · ${w[0].tc}` }))
          : h("span", { class: "avisos none", text: "sem avisos" });
      }
      return h("div", { class: "grid-row" },
        h("span", { class: "name", title: v.file, text: vlabel(v) }),
        h("span", { class: "dur", "data-l": "duração", text: fmtClock(v.duration) }),
        h("span", { class: "num", "data-l": "mín.", text: a ? num(a.min_db) : "—" }),
        h("span", { class: "num", "data-l": "máx.", style: a && a.peak_dbfs > -1 ? { color: "var(--warn)" } : null, text: a ? num(a.peak_dbfs) : "—" }),
        h("span", { class: "num", "data-l": "média", text: a ? num(a.avg_db) : "—" }),
        h("span", {}, sel), warn);
    }));

  const r = rv.report;
  const strip = h("div", { class: "card strip" }, h("span", { class: "muted", text: "Do relatório de tempo:" }),
    r ? [h("span", {}, h("span", { class: "muted", text: "gravado " }), h("span", { class: "mono", text: fmtHMS(r.total_raw_s) })),
         h("span", {}, h("span", { class: "muted", text: "editado " }), h("span", { class: "mono", text: fmtHMS(r.total_edited_s) })),
         h("span", {}, h("span", { class: "muted", text: "aproveitamento " }),
           h("span", { class: "mono", style: { color: "var(--accent-text)" }, text: fmtPct(r.usage_pct) }))]
      : h("span", { class: "faint", text: "sem relatório nesta pasta" }));

  const fw = rv.folder_warnings || [];
  const scopeImg = h("img", { alt: "", src: "/api/scope.png?ids=" + view.scope.ids.join(",") + "&t=" + Date.now() });

  root.appendChild(h("div", { class: "resumo" },
    h("section", {},
      h("div", { class: "page-title" }, h("h1", { text: "Resumo geral" }),
        h("p", { text: [rv.professor ? `Prof. ${rv.professor}` : "", rv.curso, `entrega da edição em ${fmtDateBR(rv.entrega)}`,
          running ? `${ready.length} de ${plural(vids.length, "vídeo analisado", "vídeos analisados")} (a análise continua)`
            : plural(ready.length, "vídeo analisado", "vídeos analisados")].filter(Boolean).join(" · ") })),
      h("div", { class: "stats" },
        stat("Mínimo do áudio", au.min ? fmtDb(au.min.db) : "—", au.min ? `em ${nameOf(au.min.video)}` : ""),
        stat("Máximo do áudio", au.max ? fmtDb(au.max.db) : "—",
          au.max ? `em ${pad(vids.find((x) => x.id === au.max.video).n)} · ${fmtHMS(au.max.time).padStart(8, "0")}` : "", maxColor),
        stat("Volume médio", au.avg ? fmtDb(au.avg.db) : "—", "média de todos os vídeos")),
      strip,
      fw.length ? h("div", { class: "notice" }, icon("alert"), h("div", {},
        h("span", { text: "Conferir:" }), h("ul", {}, fw.map((w) => h("li", { text: w }))))) : null,
      h("div", { class: "ed-head" }, h("b", { text: "Quem editou cada vídeo" }), h("span", { style: { flex: 1 } }),
        noTeam ? h("a", { class: "btn ghost-blue small", href: "#/config/equipe", text: "Cadastrar a equipe" }) : null,
        noTeam ? null : h("span", { class: "muted", style: { fontSize: "13px" }, text: "Editor de todos:" }),
        noTeam ? null : allSel, noTeam ? null : applyAll),
      noTeam ? h("div", { class: "notice info" }, icon("info"),
        h("span", { text: "Ninguém da equipe foi cadastrado ainda. Cadastre os editores em Configurações → Equipe para marcar quem editou cada vídeo." })) : null,
      grid),
    h("aside", { class: "resumo-side" },
      h("div", { class: "card scope-card" },
        h("div", { style: { alignSelf: "stretch", display: "flex", flexDirection: "column", gap: "4px" } },
          h("span", { style: { fontSize: "14px", fontWeight: 600 }, text: "Vectorscope YUV" }),
          h("span", { class: "muted", style: { fontSize: "12px" }, text: "Cor média de todos os vídeos (Rec.709)" })),
        h("div", { class: "scope-box", style: { background: "#101010", borderRadius: "10px" } }, scopeImg, scopeOverlay(view.scope)),
        h("span", { class: "muted", style: { alignSelf: "stretch", fontSize: "12px" },
          text: "Quadrados: alvos de cor a 75 %. Linha tracejada: tom de pele." })),
      h("a", { class: "btn primary", href: "#/revisao/1", text: "Começar revisão pelo vídeo 01" }),
      h("span", { class: "muted", style: { fontSize: "12px", textAlign: "center" },
        text: "O editor pode ser marcado agora ou na aba de cada vídeo." }))));

  if (running) poll = setInterval(async () => {
    try { const j = await api("job"); if (j.videos.filter((v) => v.status === "ok").length !== ready.length || j.state === "done") render(); }
    catch (e) { /* tenta de novo */ }
  }, 3000);
}

// 4 · Revisão: ui/revisao.js (etapa 4) · 5, 6, 7 e Configurações: ui/final.js (etapa 5)

const SCREENS = {
  inicio: screenInicio,
  analise: screenAnalise,
  resumo: screenResumo,
  revisao: screenRevisao,
  final: screenFinal,
  pacote: screenPacote,
  relatorio: screenRelatorio,
  config: screenConfig,
};

// Imagem de frame que falhou (visto no Safari com a análise rodando: "?" no lugar da miniatura):
// tenta de novo sozinha até 3 vezes, com intervalo crescente.
document.addEventListener("error", (e) => {
  const img = e.target;
  if (!(img instanceof HTMLImageElement) || !/\/api\/(c?frame\.jpg|scope\.png)/.test(img.src)) return;
  const n = Number(img.dataset.retry || 0);
  if (n >= 3) return;
  img.dataset.retry = String(n + 1);
  setTimeout(() => {
    const u = new URL(img.src);
    u.searchParams.set("r", String(n + 1));
    img.src = u.toString();
  }, 800 * (n + 1));
}, true);

// ====================================================================== vida do app (etapa 6)
// A página avisa o app que está aberta; sem página aberta o app empacotado fecha sozinho.

const CLIENT_ID = Math.random().toString(36).slice(2, 12);
let appGone = false;

function showGone(byQuit) {
  if (appGone) return;
  appGone = true;
  clearInterval(poll);
  closeModal();
  const box = h("div", { class: "gone-back", role: "alertdialog", "aria-label": "Revisor fechado" },
    h("div", { class: "gone" },
      h("h2", { text: byQuit ? "O Revisor de Vídeos foi fechado." : "O Revisor de Vídeos não está aberto." }),
      h("p", { text: byQuit ? "Pode fechar esta aba. Tudo o que você fez já está salvo."
                            : "Abra o app de novo (dois cliques no Revisor de Vídeos). Ele abre esta página sozinho; esta aba pode ser fechada." }),
      byQuit ? null : h("button", { class: "btn", type: "button", onclick: () => location.reload(), text: "Tentar de novo" })));
  document.body.appendChild(box);
}

async function heartbeat() {
  if (appGone) return;
  try {
    const r = await fetch("/api/ping", { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify({ client: CLIENT_ID }) });
    if (!r.ok) throw new Error();
  } catch (e) {
    showGone(false);
  }
}
heartbeat();
setInterval(heartbeat, 20000);
updateQueueChip();
queueChipTimer = setInterval(updateQueueChip, 4000);
window.addEventListener("hashchange", updateQueueChip);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") heartbeat(); });
window.addEventListener("pagehide", () => {
  try {
    navigator.sendBeacon("/api/bye", new Blob([JSON.stringify({ client: CLIENT_ID })], { type: "application/json" }));
  } catch (e) { /* o app fecha sozinho depois de um tempo */ }
});

async function quitApp() {
  let running = false, waiting = 0;
  try {
    const q = await api("queue");
    running = q.entries.some((e) => e.status === "running" || e.status === "paused");
    waiting = q.entries.filter((e) => e.status === "wait").length;
  } catch (e) { /* nada */ }
  const go = h("button", { class: "btn primary", type: "button", text: "Sair", onclick: async () => {
    try { await api("quit", {}); } catch (e) { /* já fechou */ }
    showGone(true);
  } });
  openModal("Fechar o Revisor de Vídeos?", h("p", { style: { margin: 0 }, text: (running
      ? "A análise ainda está rodando. Ela para agora e continua de onde parou quando você abrir a mesma pasta de novo. Comentários e revisão já estão salvos."
      : "Comentários e revisão já estão salvos. Para abrir de novo, dois cliques no Revisor de Vídeos.") +
      (running || waiting ? " As pastas que estavam na fila aparecem no Início para você continuar a fila." : "") }),
    [h("button", { class: "btn", type: "button", text: "Cancelar", onclick: closeModal }), go]);
}
$("#quit-btn").addEventListener("click", quitApp);

render();
