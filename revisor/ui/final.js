/* Revisor de Vídeos — etapa 5: Resumo final, Levar a revisão para outro computador,
   Relatório do mês e Configurações. Usa as utilidades de app.js e revisao.js. */
"use strict";

// ====================================================================== utilidades

RV_ICONS.down = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v10M8 10l4 4 4-4M5 19h14"/></svg>';
const CHECK_W = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';

/** 0:42h (horas e minutos) */
function fmtHm(s) {
  const m = Math.round((s || 0) / 60);
  return `${Math.floor(m / 60)}:${pad(m % 60)}h`;
}
/** 1,84 GB · 312 MB · 840 KB */
function fmtBytes(b) {
  b = b || 0;
  if (b >= 1e9) return num(b / 1e9, 2) + " GB";
  if (b >= 1e6) return num(b / 1e6, b >= 1e8 ? 0 : 1) + " MB";
  return Math.max(1, Math.round(b / 1e3)) + " KB";
}
const escHtml = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
const nlist = (ns) => ns.map((n) => pad(n)).join(", ");

/** Caixa de marcar no estilo do desenho (azul com ✓ / contorno cinza). */
function checkbox(on, label, onchange, mixed) {
  const b = h("button", { class: "cbx" + (on ? " on" : "") + (mixed ? " mixed" : ""), role: "checkbox",
    "aria-checked": mixed ? "mixed" : on ? "true" : "false", "aria-label": label, onclick: () => onchange(!on) });
  if (on || mixed) {
    const t = document.createElement("template");
    t.innerHTML = mixed
      ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" aria-hidden="true"><path d="M6 12h12"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
    b.appendChild(t.content.firstChild);
  }
  return b;
}
/** Ícone de "sim" fixo (lista do que vai no pacote). */
function tick(on) {
  const el = h("span", { class: "cbx static" + (on ? " on" : ""), "aria-hidden": "true" });
  if (on) el.innerHTML = CHECK_W;
  return el;
}

/** Frame de um comentário (do vídeo, do cache ou do pacote) como data URL JPEG até 1280 px. */
async function commentImage(r) {
  const res = await fetch(`/api/cframe.jpg?id=${r.vid}&f=${r.frame}&s=full&v=${r.ver || ""}`);
  if (!res.ok) return null;
  const bmp = await createImageBitmap(await res.blob());
  const k = Math.min(1, 1280 / bmp.width);
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.88);
}

/** Copia vários comentários: texto puro (uma linha cada) + HTML com as imagens onde pedido. */
async function copyComments(rows, withFrame) {
  if (!rows.length) { toast("Nenhum comentário para copiar.", true); return; }
  const lineOf = (r) => `Vídeo ${pad(r.n)} · ${r.tc} · ${r.text}`;
  const text = rows.map(lineOf).join("\n");
  const anyFrame = rows.some((r) => withFrame(r) && !r.general);
  if (!anyFrame || !window.ClipboardItem || !navigator.clipboard || !navigator.clipboard.write) {
    try {
      await navigator.clipboard.writeText(text);
      toast(rows.length === 1 ? "Comentário copiado." : `${rows.length} comentários copiados.`);
    } catch (e) { toast("O navegador não deixou copiar.", true); }
    return;
  }
  // as imagens são buscadas dentro do ClipboardItem (o Safari exige isso para manter o clique)
  const html = (async () => {
    const parts = [];
    for (const r of rows) {
      parts.push(`<p style="margin:0 0 6px">${escHtml(lineOf(r)).replace(/\n/g, "<br>")}</p>`);
      if (withFrame(r) && !r.general) {
        let u = null;
        try { u = await commentImage(r); } catch (e) { u = null; }
        if (u) parts.push(`<p style="margin:0 0 16px"><img src="${u}" width="640" alt="Vídeo ${pad(r.n)} · ${escHtml(r.tc)}"></p>`);
      }
    }
    return new Blob([parts.join("")], { type: "text/html" });
  })();
  try {
    await navigator.clipboard.write([new ClipboardItem({ "text/html": html, "text/plain": new Blob([text], { type: "text/plain" }) })]);
    toast(`${plural(rows.length, "comentário copiado", "comentários copiados")}${anyFrame ? " com os frames" : ""}. Cole no e-mail ou na conversa com o editor.`);
  } catch (e) {
    try { await navigator.clipboard.writeText(text); toast("Copiado só o texto (o navegador não deixou copiar as imagens).", true); }
    catch (e2) { toast("O navegador não deixou copiar.", true); }
  }
}

// ====================================================================== 5 · Resumo final

async function screenFinal(root) {
  const F5 = await api("final");
  if (!F5.review) { location.hash = "#/inicio"; return; }
  const rv = F5.review;
  let rows = F5.rows;
  const nVideosWith = new Set(rows.map((r) => r.vid)).size;

  const countEl = h("span");
  const allBox = h("span");
  const list = h("div", { class: "panel f-list" });

  async function mark(cid, upd) {
    try { await api("final/mark", { cid, ...upd }); }
    catch (e) { toast(e.message, true); }
    rows.forEach((r) => { if (cid === "all" || r.cid === cid) Object.assign(r, upd); });
    drawList();
  }
  function drawHead() {
    const sel = rows.filter((r) => r.selected).length;
    fill(allBox, checkbox(sel === rows.length && rows.length > 0, "Marcar todos", (on) => mark("all", { selected: on }),
      sel > 0 && sel < rows.length), h("span", { text: "Todos" }));
    countEl.textContent = `${sel} marcados de ${rows.length}`;
  }
  function seg(r) {
    const mk = (val, label) => h("button", { class: r.with_frame === val ? "on" : "", "aria-pressed": r.with_frame === val ? "true" : "false",
      text: label, onclick: () => { if (r.with_frame !== val) mark(r.cid, { with_frame: val }); } });
    return h("div", { class: "seg f-seg", role: "group", "aria-label": "Com ou sem frame" }, mk(true, "Com frame"), mk(false, "Sem frame"));
  }
  // situação do vídeo e etiqueta do comentário (22/10): só aparecem, a cópia continua igual
  const TAGL = { audio: "Áudio", cor: "Cor", texto: "Texto", corte: "Corte", tarja: "Tarja", slide: "Slide", vinheta: "Vinheta", outro: "Outro" };
  const stOf = Object.fromEntries((F5.videos || []).map((v) => [v.id, v.status]));
  const stBadge = (vid) => stOf[vid] ? h("span", { class: "f-st " + stOf[vid], text: stOf[vid] === "aprovado" ? "✓ aprovado" : "↩ volta" }) : null;
  function drawList() {
    drawHead();
    if (!rows.length) {
      fill(list, h("div", { class: "empty-state" },
        h("p", { text: "Nenhum comentário nesta revisão ainda. Os comentários feitos na tela de revisão aparecem aqui." }),
        h("a", { class: "btn", href: "#/revisao/1", text: "Ir para a revisão" })));
      return;
    }
    fill(list, rows.map((r) => h("div", { class: "f-row" + (r.selected ? "" : " off") },
      checkbox(r.selected, r.general ? `Incluir o comentário geral do vídeo ${pad(r.n)}` : `Incluir o comentário do vídeo ${pad(r.n)} em ${r.tc}`,
        (on) => mark(r.cid, { selected: on })),
      r.general ? h("div", { class: "f-th none gen", text: "geral" }) : r.with_frame
        ? h("div", { class: "f-th" }, h("img", { src: `/api/cframe.jpg?id=${r.vid}&f=${r.frame}&s=thumb&v=${r.ver || ""}`, alt: "Frame do comentário",
            loading: "lazy", onerror: (e) => { e.target.replaceWith(h("span", { class: "f-noimg", text: "sem imagem neste computador" })); } }))
        : h("div", { class: "f-th none", text: "sem imagem" }),
      h("a", { class: "f-when", href: `#/revisao/${r.n}`, title: `Abrir o vídeo ${pad(r.n)} na revisão` },
        h("b", {}, `Vídeo ${pad(r.n)}`, stBadge(r.vid)), h("span", { class: "mono", text: r.tc })),
      h("span", { class: "f-text" }, r.tag && TAGL[r.tag] ? h("span", { class: "f-tag", text: TAGL[r.tag] }) : null, r.text),
      r.general ? h("span", { class: "f-gen faint", text: "vale para o vídeo todo" }) : seg(r))));
  }

  // ---- coluna da direita
  const copyCard = h("div", { class: "card f-card" },
    h("span", { class: "caps", text: "Copiar comentários" }),
    h("button", { class: "btn primary", onclick: () => copyComments(rows.filter((r) => r.selected), (r) => r.with_frame) },
      rvIcon("copy"), "Copiar selecionados, como marcado"),
    h("div", { class: "row" },
      h("button", { class: "btn f-half", text: "Todos, com frame", onclick: () => copyComments(rows, () => true) }),
      h("button", { class: "btn f-half", text: "Todos, sem frame", onclick: () => copyComments(rows, () => false) })),
    h("span", { class: "hint", text: "Todo texto copiado leva o vídeo e o tempo: “Vídeo 02 · 00:00:44 · …”" }));

  const sr = F5.srt;
  const srtNote = h("span", { class: "hint", style: { lineHeight: "1.5" } });
  const srtBtn = h("button", { class: "btn" });
  const srtZip = h("a", { class: "btn ghost small", href: "/api/final/srt.zip", download: "", text: "Baixar em .zip" });
  function drawSrt(done) {
    const n = sr.videos;
    const where = sr.where === "subfolder" ? "numa subpasta “Correções” da pasta dos vídeos" : "ao lado dos vídeos";
    fill(srtBtn, rvIcon("down"), sr.folder_found ? "Gerar SRT de cada vídeo" : "Baixar SRT de cada vídeo (.zip)");
    srtBtn.disabled = !n;
    srtNote.textContent = !n ? "Nenhum comentário marcado: não há SRT para gerar." :
      `${plural(n, "arquivo", "arquivos")} (só vídeos com comentários marcados), blocos de ${sr.block_s} s, ` +
      (sr.folder_found ? `salvos ${where} com o mesmo nome. ` : "A pasta dos vídeos não está neste computador: vai um .zip para a pasta Downloads. ") +
      "Importe na timeline e desligue a faixa antes de exportar.";
    if (done) srtNote.textContent = done;
    srtZip.classList.toggle("hidden", !sr.folder_found || !n);
  }
  srtBtn.addEventListener("click", async () => {
    try {
      const r = await api("final/srt", {});
      if (r.zip) { location.href = "/api/final/srt.zip"; toast("SRT baixados em .zip (pasta Downloads)."); return; }
      toast(`${plural(r.files.length, "SRT gravado", "SRT gravados")} na pasta dos vídeos.`);
      drawSrt(`Gravados: ${r.files.map((f) => f.file).join(", ")}. Gerar de novo substitui os arquivos.`);
    } catch (e) { toast(e.message, true); }
  });
  drawSrt();
  const srtCard = h("div", { class: "card f-card" }, h("span", { class: "caps", text: "Para o editor" }),
    srtBtn, srtNote, srtZip);

  const H = F5.hours;
  const hoursCard = h("div", { class: "card f-card" },
    h("span", { class: "caps", text: "Horas por editor desta revisão" }),
    H.editors.map((g) => h("div", { class: "f-kv" + (g.none ? " warn" : "") },
      h("span", {}, g.name, h("span", { class: "muted f-small", text: ` · ${plural(g.videos.length, "vídeo", "vídeos")} (${nlist(g.videos)})` })),
      h("span", { class: "mono" }, fmtHm(g.seconds), h("span", { class: "muted f-small", text: ` (${fmtClock(g.seconds)})` })))),
    H.without_editor ? h("span", { class: "hint warn", text: "Marque o editor desses vídeos no Resumo geral ou na aba de cada vídeo." }) : null,
    h("div", { class: "f-kv sm sep-t" }, h("span", { class: "t3", text: "Total editado" }), h("span", { class: "mono", text: fmtHMS(H.total_s) })),
    h("div", { class: "f-kv sm" }, h("span", { class: "t3", text: "Gravado (bruto)" }), h("span", { class: "mono", text: H.raw_s == null ? "—" : fmtHMS(H.raw_s) })),
    h("div", { class: "f-kv sm" }, h("span", { class: "t3", text: "Aproveitamento" }),
      h("span", { class: "mono", style: { color: "var(--accent-text)" }, text: fmtPct(H.usage_pct) })),
    !H.from_report ? h("span", { class: "hint", text: "Sem relatório de tempo: as horas vêm da duração dos arquivos." }) : null,
    h("div", { class: "lock sep-t" }, icon("lock"), `Entrega da edição: ${fmtDateBR(H.entrega) || "—"}${H.entrega_locked ? " (travada)" : ""}`),
    h("a", { class: "btn f-mid", href: "/api/final/horas.txt", download: "", text: "Gerar txt de horas",
      onclick: () => toast("txt de horas baixado (pasta Downloads).") }));

  root.appendChild(h("div", { class: "final" },
    h("section", {},
      h("div", { class: "page-title" }, h("h1", { text: "Resumo final" }),
        h("p", { text: [rv.professor ? `Prof. ${rv.professor}` : rv.project,
          `${plural(rows.length, "comentário", "comentários")} em ${plural(nVideosWith, "vídeo", "vídeos")}. ` +
          "Marque o que vai entrar na cópia e escolha com ou sem frame em cada um."].join(" · ") })),
      h("div", { class: "f-top" }, h("span", { class: "f-all" }, allBox), h("span", { style: { flex: 1 } }), countEl),
      list),
    h("aside", { class: "final-side" }, copyCard, srtCard, hoursCard, h("div", { style: { flex: 1 } }),
      h("a", { class: "btn primary", href: "#/pacote", text: "Salvar e exportar revisão" }),
      h("a", { class: "btn linkish", href: "#/revisao/1", text: "← Voltar à revisão" }))));
  drawList();
}

// ====================================================================== modo editor · Pronto para enviar
// O editor vê o que ainda falta olhar em cada vídeo, gera o relatório de tempo e confere as horas.

async function screenEnviar(root) {
  const view = await api("review");
  if (!view.review) { location.hash = "#/inicio"; return; }
  const rv = view.review;
  const vids = view.videos;
  let F5 = null;
  try { F5 = await api("final"); } catch (e) { /* horas ficam de fora */ }
  const job = view.job;
  const running = job && ["running", "paused", "idle"].includes(job.state);
  const pending = vids.filter((v) => v.row).reduce((n, v) => n + v.row.warnings.length, 0);
  const waiting = vids.filter((v) => !v.row && !v.missing).length;
  const ignored = vids.reduce((n, v) => n + (v.ignored || 0), 0);

  // ---- lista: cada vídeo com os avisos que ainda faltam (clicar abre o vídeo no aviso)
  const list = h("div", { class: "panel en-list" }, vids.map((v) => {
    const w = v.row ? v.row.warnings : [];
    const state = !v.row ? (v.missing ? "vídeo não está na pasta" : "ainda analisando…")
      : w.length ? plural(w.length, "aviso para olhar", "avisos para olhar") : "tudo certo";
    return h("div", { class: "en-v" + (v.row && !w.length ? " ok" : "") },
      h("div", { class: "en-vh" },
        h("a", { class: "en-name", href: `#/revisao/${v.n}`, title: v.file, text: vlabel(v) }),
        h("span", { class: "en-st", text: state }),
        v.ignored ? h("span", { class: "faint en-ig", text: `${plural(v.ignored, "ignorado", "ignorados")}` }) : null),
      w.length ? h("div", { class: "en-ws" }, w.map((x) => h("button", { class: "en-w", type: "button",
        title: "Abrir o vídeo neste aviso", onclick: () => { RV.jump = { n: v.n, frame: x.frame }; location.hash = `#/revisao/${v.n}`; } },
        h("span", { class: "mono faint", text: x.tc }), h("span", { class: "en-k", text: x.label }),
        x.note ? h("span", { class: "en-note", text: x.note }) : null))) : null);
  }));

  // ---- situação geral
  const allOk = !running && !waiting && !pending;
  const head = allOk
    ? h("div", { class: "notice info en-big" }, icon("check"), h("span", {}, h("b", { text: "Tudo conferido." }),
        ignored ? ` ${plural(ignored, "aviso foi ignorado", "avisos foram ignorados")} (você decidiu que não era erro).` : "",
        " Pode enviar a pasta."))
    : h("div", { class: "notice en-big" }, icon("alert"), h("span", {},
        pending ? h("b", { text: `Falta olhar ${plural(pending, "aviso", "avisos")}.` }) : null,
        waiting ? ` ${plural(waiting, "vídeo ainda está", "vídeos ainda estão")} na análise.` : "",
        " Corrija no Premiere e exporte com o mesmo nome (o app percebe e analisa de novo), ou use “Ignorar” quando não for erro."));

  // ---- relatório de tempo
  const r = rv.report;
  const trCard = h("div", { class: "card f-card" },
    h("span", { class: "caps", text: "Relatório de tempo" }),
    r ? [h("div", { class: "f-kv sm" }, h("span", { class: "t3", text: "Gravado (bruto)" }), h("span", { class: "mono", text: fmtHMS(r.total_raw_s) })),
         h("div", { class: "f-kv sm" }, h("span", { class: "t3", text: "Editado" }), h("span", { class: "mono", text: fmtHMS(r.total_edited_s) })),
         h("div", { class: "f-kv sm" }, h("span", { class: "t3", text: "Aproveitamento" }),
           h("span", { class: "mono", style: { color: "var(--accent-text)" }, text: fmtPct(r.usage_pct) })),
         h("span", { class: "hint mono", text: r.file })]
      : h("span", { class: "hint", text: "Ainda não há o txt de tempo nesta pasta. Gere aqui: ele fica na pasta dos editados, como o do “Calculo de tempo”." }),
    h("button", { class: r ? "btn" : "btn primary", type: "button", text: r ? "Gerar de novo" : "Gerar relatório de tempo",
      onclick: () => timeReportDialog({ edited: rv.folder || "", raw: rv.raw_folder || "", onDone: () => render() }) }),
    (rv.folder_warnings || []).length ? h("div", { class: "notice", style: { fontSize: "12px" } }, icon("alert"),
      h("div", {}, h("span", { text: "Conferir:" }), h("ul", {}, rv.folder_warnings.map((x) => h("li", { text: x }))))) : null);

  // ---- horas (o editor também vê as próprias horas)
  const H = F5 && F5.hours;
  const hoursCard = H ? h("div", { class: "card f-card" },
    h("span", { class: "caps", text: "Horas de vídeo editado" }),
    H.editors.map((g) => h("div", { class: "f-kv" + (g.none ? " warn" : "") },
      h("span", {}, g.none ? "Sem nome" : g.name, h("span", { class: "muted f-small", text: ` · ${plural(g.videos.length, "vídeo", "vídeos")}` })),
      h("span", { class: "mono", text: fmtHm(g.seconds) }))),
    H.without_editor ? h("span", { class: "hint warn" }, "Escreva o seu nome em ", h("a", { href: "#/config/modo", text: "Configurações → Modo do app" }),
      " e confira a pasta de novo para as horas irem com o seu nome.") : null,
    h("div", { class: "f-kv sm sep-t" }, h("span", { class: "t3", text: "Total desta pasta" }), h("span", { class: "mono", text: fmtHMS(H.total_s) })),
    h("a", { class: "btn ghost small", href: "#/relatorio", text: "Ver o mês todo" })) : null;

  root.appendChild(h("div", { class: "final" },
    h("section", {},
      h("div", { class: "page-title" }, h("h1", { text: "Pronto para enviar?" }),
        h("p", { text: [rv.professor ? `Prof. ${rv.professor}` : rv.project, plural(vids.length, "vídeo", "vídeos"),
          running ? "a análise continua" : null].filter(Boolean).join(" · ") })),
      head, list),
    h("aside", { class: "final-side" }, trCard, hoursCard, h("div", { style: { flex: 1 } }),
      h("a", { class: "btn linkish", href: "#/revisao/1", text: "← Voltar à checagem" }))));

  if (running) poll = setInterval(async () => {
    try { const j = await api("job"); if (j.videos.filter((v) => v.status === "ok").length !== vids.filter((v) => v.row).length || j.state === "done") render(); }
    catch (e) { /* tenta de novo */ }
  }, 3000);
}

// ====================================================================== 6 · Levar a revisão para outro computador

const PK = { dest: "", path: "", videos_folder: "", info: null, choice: null };

async function screenPacote(root, arg) {
  const info = await api("package");
  const R = info.review;
  if (!PK.dest) PK.dest = info.export_dir || "";

  // ---- A · exportar
  const destIn = h("input", { class: "input mono", value: PK.dest, "aria-label": "Salvar em", autocomplete: "off" });
  destIn.addEventListener("input", () => { PK.dest = destIn.value; });
  const result = h("div");
  const expBtn = h("button", { class: "btn primary", text: "Exportar pacote", disabled: R ? null : true });
  expBtn.addEventListener("click", async () => {
    expBtn.disabled = true; expBtn.textContent = "Exportando…";
    try {
      const r = await api("package/export", { dest: destIn.value });
      fill(result, h("div", { class: "notice info" }, icon("check"), h("div", {},
        h("b", { text: "Pacote salvo. " }), `${plural(r.frames, "imagem", "imagens")} · ${fmtBytes(r.bytes)}. `,
        h("span", { class: "mono", style: { wordBreak: "break-all" }, text: r.folder }),
        r.frames_missing ? h("div", { text: `${plural(r.frames_missing, "frame comentado ficou", "frames comentados ficaram")} sem imagem (vídeo e cache não estão neste computador).` }) : null,
        h("div", { class: "hint", style: { marginTop: "4px" }, text: "Leve a pasta inteira (pendrive, Google Drive) e abra no outro computador em “Abrir revisão”." }))));
      toast("Pacote exportado.");
    } catch (e) { toast(e.message, true); }
    expBtn.disabled = false; expBtn.textContent = "Exportar pacote";
  });
  const secA = h("section", { class: "panel pk-sec" },
    h("div", { class: "pk-h" }, h("span", { class: "pk-n on", text: "A" }), h("span", { text: "Exportar revisão" })),
    !R ? h("div", { class: "notice info" }, icon("info"), h("span", { text: "Abra uma revisão (Início → Abrir revisão salva) para exportar." })) : [
      h("div", { class: "pk-proj" }, h("b", { text: R.project }),
        h("span", { class: "muted", text: `Entrega da edição ${fmtDateBR(R.entrega)} · ${plural(R.videos, "vídeo", "vídeos")}` })),
      h("div", { class: "field" }, h("span", { class: "label", text: "Salvar em" }),
        h("div", { class: "row" }, destIn, h("button", { class: "btn", text: "Escolher pasta",
          onclick: () => choose("folder", "Escolha onde salvar o pacote", destIn.value, (p) => { destIn.value = p; PK.dest = p; }) }))),
      h("div", { class: "field" }, h("span", { class: "label", text: "O que vai no pacote" }),
        h("div", { class: "pk-what" },
          h("div", {}, tick(true), h("span", {}, "Comentários e marcações ",
            h("span", { class: "faint f-small", text: `· ${plural(R.comments, "comentário", "comentários")}, ${plural(R.editors_marked, "editor marcado", "editores marcados")}` }))),
          h("div", {}, tick(true), h("span", {}, "Imagens dos frames comentados ",
            h("span", { class: "faint f-small", text: `· ${plural(R.frames, "imagem", "imagens")} · cerca de ${fmtBytes(R.est_bytes)}` }))),
          h("div", {}, tick(true), h("span", {}, "Horas por editor ", h("span", { class: "faint f-small", text: "· txt legível" }))),
          h("div", { class: "faint" }, tick(false), h("span", {}, "Vídeos ", h("span", { class: "f-small", text: "· nunca incluídos (são grandes)" }))),
          h("div", { class: "faint" }, tick(false), h("span", {}, "Cache da análise ", h("span", { class: "f-small", text: "· o outro computador refaz sozinho" }))))),
      h("div", { class: "pk-tree mono" }, `📁 ${R.name}/`, h("br"), "  ├ revisao.json", h("br"), "  ├ frames/ ",
        h("span", { class: "faint", text: `(${plural(R.frames, "imagem", "imagens")})` }), h("br"), "  └ horas.txt"),
      result]);
  secA.appendChild(h("div", { style: { flex: 1 } }));
  secA.appendChild(expBtn);

  // ---- B · abrir
  const pathIn = h("input", { class: "input mono", value: PK.path, "aria-label": "Pacote", autocomplete: "off",
    placeholder: "Pasta do pacote (ou o revisao.json dentro dela)" });
  const detail = h("div", { class: "pk-detail" });
  const openBtn = h("button", { class: "btn primary", text: "Abrir revisão", disabled: true });

  async function inspect() {
    PK.path = pathIn.value.trim();
    if (!PK.path) return;
    fill(detail, h("span", { class: "faint", text: "Lendo o pacote…" }));
    try {
      PK.info = await api("package/inspect", { path: PK.path, videos_folder: PK.videos_folder || null });
      if (PK.info.videos_folder) PK.videos_folder = PK.info.videos_folder;
      drawDetail();
    } catch (e) {
      PK.info = null;
      fill(detail, h("div", { class: "notice" }, icon("alert"), h("span", { text: e.message })));
      openBtn.disabled = true;
    }
  }
  function drawDetail() {
    const I = PK.info;
    if (!I) return;
    const found = I.videos.filter((v) => v.found).length;
    const conflict = I.local && !I.local.same;
    if (!conflict) PK.choice = I.local ? "keep" : null;
    const choiceBtn = (val, label) => h("button", { class: "btn f-choice" + (PK.choice === val ? " on" : ""),
      "aria-pressed": PK.choice === val ? "true" : "false", text: label, onclick: () => { PK.choice = val; drawDetail(); } });
    fill(detail,
      h("div", { class: "pk-proj box" }, h("b", { text: `Revisão ${I.project}` }),
        h("span", { class: "muted f-small", text: [I.entrega ? `Entrega da edição ${fmtDateBR(I.entrega)}` : "",
          plural(I.videos.length, "vídeo", "vídeos"), plural(I.comments, "comentário", "comentários"),
          I.updated ? `salva em ${fmtUpdated(I.updated)}` : ""].filter(Boolean).join(" · ") })),
      h("div", { class: "field" }, h("span", { class: "label", text: "Vídeos neste computador" }),
        h("div", { class: "pk-vids" }, I.videos.map((v) => h("div", { class: "pk-v" },
          h("span", { class: "nm", title: v.file, text: vlabel(v) }), h("span", { class: "mono muted", text: fmtClock(v.duration) }),
          h("span", { class: "st " + (v.found ? "ok" : "no"), text: v.found ? "encontrado" : "não encontrado" })))),
        h("div", { class: "row", style: { flexWrap: "wrap" } },
          h("button", { class: "btn small", text: found === I.videos.length ? "Trocar pasta dos vídeos" : "Localizar pasta dos vídeos",
            onclick: () => choose("folder", "Escolha a pasta com os vídeos desta revisão", PK.videos_folder || "", (p) => { PK.videos_folder = p; inspect(); }) }),
          h("span", { class: "hint", text: I.videos_folder ? `Pasta: ${I.videos_folder}` :
            "Os comentários abrem mesmo sem o vídeo; zoom, gráficos e o trecho de 8 s precisam dele." }))),
      conflict ? h("div", { class: "rv-warn pk-conf" },
        h("span", { class: "warn", style: { fontWeight: 600 }, text: "Já existe uma revisão deste projeto neste computador" }),
        h("span", { text: `Neste computador: salva em ${fmtUpdated(I.local.updated)} · ${plural(I.local.comments, "comentário", "comentários")}. ` +
          `No pacote: ${plural(I.comments, "comentário", "comentários")}.` }),
        h("div", { class: "row" }, choiceBtn("keep", "Manter a deste computador"), choiceBtn("package", "Usar a do pacote"),
          choiceBtn("merge", "Juntar as duas")),
        h("span", { class: "hint", text: "Juntar: ficam os comentários dos dois; no mesmo frame, vale o editado por último." }))
        : I.local ? h("div", { class: "notice info" }, icon("info"), h("span", { text: "Este computador já tem esta revisão, igual à do pacote." })) : null);
    openBtn.disabled = !!(conflict && !PK.choice);
  }
  pathIn.addEventListener("change", inspect);
  pathIn.addEventListener("keydown", (e) => { if (e.key === "Enter") inspect(); });
  openBtn.addEventListener("click", async () => {
    openBtn.disabled = true; openBtn.textContent = "Abrindo…";
    try {
      const r = await api("package/open", { path: PK.path, choice: PK.choice, videos_folder: PK.videos_folder || null });
      toast(`Revisão aberta: ${plural(r.comments, "comentário", "comentários")}.`);
      PK.info = null; PK.path = ""; PK.choice = null; PK.videos_folder = "";
      location.hash = r.folder_found ? "#/analise" : "#/final";
    } catch (e) { toast(e.message, true); openBtn.disabled = false; }
    openBtn.textContent = "Abrir revisão";
  });
  const secB = h("section", { class: "panel pk-sec" + (arg === "abrir" ? " focus" : "") },
    h("div", { class: "pk-h" }, h("span", { class: "pk-n", text: "B" }), h("span", { text: "Abrir revisão" })),
    h("div", { class: "row" }, pathIn, h("button", { class: "btn", text: "Escolher pacote",
      onclick: () => choose("folder", "Escolha a pasta do pacote (Revisão …)", PK.path || "", (p) => { pathIn.value = p; inspect(); }) })),
    detail, h("div", { style: { flex: 1 } }), openBtn);

  root.appendChild(h("div", { class: "screen-center" },
    h("div", { class: "wide pk" },
      h("div", {}, h("h1", { text: "Levar a revisão para outro computador" }),
        h("p", { text: "O pacote leva só comentários, frames comentados e horas. Os vídeos ficam onde estão: o app reencontra pelo nome e pela duração." })),
      h("div", { class: "pk-cols" }, secA, secB))));
  if (PK.path) { pathIn.value = PK.path; if (PK.info) drawDetail(); else inspect(); }
  if (arg === "abrir") pathIn.focus();
}

// ====================================================================== 7 · Relatório do mês

let MONTH = null;

async function screenRelatorio(root) {
  const M = await api("month" + (MONTH ? "?m=" + MONTH : ""));
  MONTH = M.month;
  const sel = h("select", { class: "input", "aria-label": "Mês", style: { width: "auto", minWidth: "190px" } },
    (M.months.length ? M.months : [{ key: M.month, label: M.label }]).map((m) => h("option", { value: m.key, text: m.label })));
  sel.value = M.month;
  sel.addEventListener("change", () => { MONTH = sel.value; render(); });
  const stat = (k, v, w, color) => h("div", { class: "card stat" }, h("span", { class: "k", text: k }),
    h("span", { class: "v", style: color ? { color } : null, text: v }), h("span", { class: "w", text: w }));
  const hm = (s) => { const m = Math.round((s || 0) / 60); return `${Math.floor(m / 60)}:${pad(m % 60)}`; };

  const edTable = h("div", { class: "panel rel-t" },
    h("div", { class: "rel-hd" }, h("span", { class: "c1", text: "Editor" }), h("span", { class: "c2", text: "Vídeos" }),
      h("span", { class: "c3", text: "Horas editadas" }), h("span", { class: "c4", text: "Parte" })),
    M.editors.length ? M.editors.map((e) => h("div", { class: "rel-r" + (e.none ? " warn" : "") },
      h("span", { class: "c1", text: e.name }), h("span", { class: "c2 mono", text: String(e.videos) }),
      h("span", { class: "c3 mono", text: hm(e.seconds) }), h("span", { class: "c4 mono muted", text: Math.round(e.share) + "%" })))
      : h("div", { class: "rel-r", style: { color: "var(--faint)" }, text: "Nenhum vídeo entregue neste mês nas revisões salvas." }),
    h("div", { class: "rel-r total" }, h("span", { class: "c1", text: "Total" }), h("span", { class: "c2 mono", text: String(M.videos) }),
      h("span", { class: "c3 mono", text: hm(M.edited_s) }), h("span", { class: "c4" })));

  // revisão por editor (22/10): aprovados de primeira, voltaram e correções por tipo (etiquetas dos comentários)
  const TAGL = { audio: "Áudio", cor: "Cor", texto: "Texto", corte: "Corte", tarja: "Tarja", slide: "Slide", vinheta: "Vinheta", outro: "Outro", sem: "Sem etiqueta" };
  const revEds = M.editors.filter((e) => e.comments || e.approved_first || e.returned);
  const revCard = revEds.length ? h("div", { class: "card rel-card" }, h("span", { class: "caps", text: "Revisão por editor" }),
    revEds.map((e) => h("div", { class: "rel-rev" },
      h("div", { class: "rel-rev-h" }, h("b", { text: e.name }),
        h("span", { class: "muted", text: `${plural(e.approved_first || 0, "aprovado de primeira", "aprovados de primeira")} · ${plural(e.returned || 0, "voltou", "voltaram")} · ${plural(e.comments || 0, "correção", "correções")}` })),
      h("div", { class: "rel-tags" }, Object.entries(e.tags || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) =>
        h("span", { class: "f-tag", text: `${TAGL[k] || k} ${n}` }))))),
    h("span", { class: "hint", text: "“Voltou” = o vídeo teve 2ª rodada ou foi marcado “volta para o editor”. Os tipos vêm das etiquetas dos comentários." }))
    : null;

  const maxC = Math.max(1, ...M.courses.map((c) => c.seconds));
  const courses = h("div", { class: "card rel-card" }, h("span", { class: "caps", text: "Por curso" }),
    M.courses.length ? M.courses.map((c) => h("div", { class: "rel-bar" },
      h("span", { class: "n", title: c.name, text: c.name }),
      h("div", { class: "b" }, h("i", { style: { width: `${(100 * c.seconds) / maxC}%` } })),
      h("span", { class: "mono v", text: hm(c.seconds) }))) : h("span", { class: "faint", text: "—" }));

  const maxW = Math.max(1, ...M.weeks.map((w) => w.seconds));
  const weeks = h("div", { class: "card rel-card" }, h("span", { class: "caps", text: "Horas editadas por semana" }),
    h("div", { class: "rel-weeks", role: "img", "aria-label": "Horas editadas por semana do mês: " +
      M.weeks.map((w) => `${w.label} (dias ${w.days}) ${hm(w.seconds)}`).join(", ") },
      M.weeks.map((w) => h("div", { class: "wk", title: `dias ${w.days}` },
        h("span", { class: "mono v", text: w.seconds ? hm(w.seconds) : "" }),
        h("div", { class: "b", style: { height: `${Math.max(w.seconds ? 4 : 0, (110 * w.seconds) / maxW)}px` } }),
        h("span", { class: "l", text: w.label })))),
    h("span", { class: "hint", text: "Semana pela data de entrega da edição (Sem 1 = dias 1 a 7)." }));

  const extra = M.report_dir;
  const src = h("div", { class: "card rel-card" }, h("span", { class: "caps", text: "De onde vêm os números" }),
    h("div", { class: "row" }, h("span", { class: "input mono rel-path", title: M.reviews_dir, text: M.reviews_dir })),
    h("div", { class: "row" },
      h("span", { class: "input mono rel-path" + (extra ? "" : " faint"), title: extra || "", text: extra || "Também ler pacotes de outra pasta (opcional)" }),
      h("button", { class: "btn small", text: extra ? "Trocar pasta" : "Escolher",
        onclick: () => choose("folder", "Pasta com pacotes de revisão de outros computadores", extra || "", async (p) => {
          try { await api("settings/folder", { kind: "report_dir", path: p }); render(); } catch (e) { toast(e.message, true); } }) }),
      extra ? h("button", { class: "btn ghost small", text: "Tirar", onclick: async () => {
        try { await api("settings/folder", { kind: "report_dir", path: null }); render(); } catch (e) { toast(e.message, true); } } }) : null),
    h("div", { style: { fontSize: "13px", color: "var(--text-3)", lineHeight: 1.6 } },
      `${plural(M.reviews_read, "revisão lida", "revisões lidas")}` + (M.duplicates ? ` · ${plural(M.duplicates, "repetida ignorada", "repetidas ignoradas")}` : ""),
      h("br"), h("span", { class: "faint f-small", text: "A mesma revisão em dois lugares conta uma vez. Revisões repetidas do mesmo vídeo (rodada 2, 3) não contam de novo." }),
      M.repeated ? [h("br"), h("span", { class: "faint f-small", text: `${plural(M.repeated, "vídeo já contado", "vídeos já contados")} em outra entrega ficou de fora.` })] : null));

  root.appendChild(h("div", { class: "screen-center" },
    h("div", { class: "wide rel" },
      h("div", { class: "rel-head" },
        h("div", {}, h("h1", { text: "Relatório do mês" }),
          h("p", { text: "Horas de vídeo editado por editor. O mês vem da data de entrega da edição, não do dia da revisão." })),
        h("div", { class: "row" }, sel,
          h("a", { class: "btn", href: `/api/month.txt?m=${M.month}`, download: "", text: "Exportar txt" }),
          h("a", { class: "btn", href: `/api/month.csv?m=${M.month}`, download: "", text: "Exportar CSV" }))),
      h("div", { class: "stats" },
        stat("Gravado no mês", hm(M.recorded_s), "horas de gravação, no mês em que gravou"),
        stat("Horas de vídeo editado", hm(M.edited_s), "entregues no mês"),
        stat("Aproveitamento", fmtPct(M.usage_pct), "editado ÷ gravado", "var(--accent-text)"),
        stat("Vídeos", String(M.videos), "cada vídeo é contado uma vez")),
      h("div", { class: "rel-cols" },
        h("div", { class: "rel-l" }, edTable, revCard, courses),
        h("div", { class: "rel-rc" }, weeks, src)))));
}

// ====================================================================== Configurações

const CFG_SECTIONS = [["modo", "Modo do app"], ["cache", "Cache"], ["pastas", "Pastas"], ["analise", "Análise"], ["equipe", "Equipe"],
  ["copia", "Cópia e envio ao editor"], ["ortografia", "Ortografia e dicionário"]];
const CFG_SECTIONS_EDITOR = ["modo", "cache", "pastas", "analise", "ortografia"];   // o editor não usa Equipe nem Cópia

async function screenConfig(root, arg) {
  const C = await api("settings/all");
  const st = C.settings;
  async function save(upd, msg) {
    try {
      const r = await api("settings/save", upd);
      Object.assign(st, upd);
      toast(msg || (r.refreshed ? `Salvo. Avisos refeitos em ${plural(r.refreshed, "vídeo", "vídeos")} da revisão aberta.` : "Salvo."));
      return true;
    } catch (e) { toast(e.message, true); return false; }
  }
  const sec = (id, ...kids) => h("section", { class: "card cfg-sec", id: "cfg-" + id, "data-sec": id }, ...kids);
  const h2 = (t, p) => h("div", {}, h("h2", { text: t }), p ? h("p", { class: "cfg-p", text: p }) : null);
  const selectOf = (id, opts, val, onchange) => {
    const s = h("select", { id, class: "input cfg-sel" }, opts.map(([v, t]) => h("option", { value: String(v), text: t })));
    s.value = String(val);
    s.addEventListener("change", () => onchange(s.value));
    return s;
  };
  const line = (label, hint, ctl, forId) => h("div", { class: "cfg-line" },
    h("div", { class: "l" }, h("label", { for: forId || null, text: label }), hint ? h("span", { class: "hint", text: hint }) : null), ctl);

  // ---- Modo do app (pedido do JP, 26/10): revisor (completo) ou editor (conferir antes de entregar)
  const modeOpt = (val, title, desc) => {
    const r = h("input", { type: "radio", name: "cfg-mode", value: val, checked: st.mode === val ? true : null });
    r.addEventListener("change", async () => {
      if (await save({ mode: val }, val === "editor" ? "Modo editor ligado." : "Modo revisor ligado.")) { await render(); }
    });
    return h("label", { class: "cfg-mode" + (st.mode === val ? " on" : "") }, r,
      h("span", {}, h("b", { text: title }), h("span", { class: "hint", text: desc })));
  };
  const myName = h("input", { id: "cfg-myname", class: "input cfg-sel", value: st.my_name || "", maxlength: "40", autocomplete: "off",
    placeholder: "Seu nome" });
  myName.addEventListener("change", () => save({ my_name: myName.value }, "Nome salvo."));
  const sModo = sec("modo", h2("Modo do app", "O mesmo app serve para quem revisa e para o editor conferir os próprios vídeos antes de entregar."),
    h("div", { class: "cfg-modes" },
      modeOpt("revisor", "Revisor", "Tudo: comentários, SRT, Trello, equipe, relatório do mês e pacote para outro computador."),
      modeOpt("editor", "Editor", "Mais simples: só os avisos de cada vídeo para corrigir antes de mandar, o relatório de tempo e as suas horas.")),
    st.mode === "editor" ? line("Seu nome", "Os vídeos que você conferir ficam com este nome no relatório do mês.", myName, "cfg-myname") : null);

  // ---- Cache
  const cacheBox = h("div", { class: "cfg-cache" });
  const cacheTotal = h("div", { class: "cfg-big mono", text: "…" });
  const cacheSub = h("div", { class: "hint" });
  async function loadCache() {
    try {
      const c = await api("cache");
      cacheTotal.textContent = fmtBytes(c.total_bytes);
      cacheSub.textContent = `em uso · ${plural(c.groups.filter((g) => g.project).length, "revisão", "revisões")}`;
      fill(cacheBox, c.groups.length ? c.groups.map((g) => h("div", { class: "cfg-crow" },
        h("span", { class: "d mono", text: g.entrega ? fmtDateBR(g.entrega) : fmtDateBR(new Date(g.newest * 1000).toISOString()) }),
        h("span", { class: "p", title: g.project, text: g.label + (g.open ? " (aberta agora)" : "") }),
        h("span", { class: "v", text: plural(g.videos, "vídeo", "vídeos") }),
        h("span", { class: "s mono", text: fmtBytes(g.bytes) }),
        h("button", { class: "btn ghost small", text: "Limpar", "aria-label": `Limpar o cache de ${g.label}`,
          onclick: async () => {
            try { const r = await api("cache/clear", { project: g.project }); toast(`Cache limpo: ${fmtBytes(r.freed)} liberados.`); loadCache(); }
            catch (e) { toast(e.message, true); }
          } })))
        : h("div", { class: "cfg-crow", style: { color: "var(--faint)" }, text: "O cache está vazio." }));
    } catch (e) { toast(e.message, true); }
  }
  const autoOn = h("input", { type: "checkbox", checked: st.cache_auto_days ? true : null });
  const autoDays = h("select", { class: "cfg-mini", "aria-label": "Dias" },
    [7, 15, 30, 60].map((d) => h("option", { value: String(d), text: `${d} dias` })));
  autoDays.value = String(st.cache_auto_days || 30);
  const saveAuto = () => save({ cache_auto_days: autoOn.checked ? Number(autoDays.value) : 0 });
  autoOn.addEventListener("change", saveAuto);
  autoDays.addEventListener("change", () => { if (autoOn.checked) saveAuto(); });
  const sCache = sec("cache",
    h("div", { class: "cfg-hrow" }, h2("Cache de análise", "Guarda os frames marcados e as curvas de áudio, para abrir uma revisão sem reprocessar os vídeos."),
      h("div", { style: { textAlign: "right" } }, cacheTotal, cacheSub)),
    cacheBox,
    h("div", { class: "cfg-hrow", style: { alignItems: "center" } },
      h("label", { class: "check" }, autoOn, "Apagar automaticamente o que não é usado há mais de", autoDays),
      h("button", { class: "btn cfg-danger", text: "Limpar todo o cache", onclick: () => {
        openModal("Limpar todo o cache?", h("p", { class: "muted", text: "As revisões e os comentários não são apagados. Os vídeos só precisam ser analisados de novo se você quiser ver os frames marcados outra vez." }),
          [h("button", { class: "btn ghost", text: "Cancelar", onclick: closeModal }),
           h("button", { class: "btn cfg-danger", text: "Limpar tudo", onclick: async () => {
             closeModal();
             try { const r = await api("cache/clear", { all: true }); toast(`Cache limpo: ${fmtBytes(r.freed)} liberados.`); loadCache(); }
             catch (e) { toast(e.message, true); }
           } })]);
      } })),
    h("div", { class: "cfg-note" }, icon("info"),
      h("span", { text: "Seus comentários ficam numa pasta separada. Limpar o cache nunca apaga uma revisão; o vídeo só precisa ser analisado de novo se você quiser ver os frames marcados outra vez." })));

  // ---- Pastas
  const folderRow = (label, kind, val, isDefault, hint) => h("div", { class: "cfg-frow" },
    h("span", { class: "k", text: label }),
    h("span", { class: "input mono rel-path" + (val ? "" : " faint"), title: val || "", text: val || hint }),
    h("button", { class: "btn small", text: val ? "Alterar" : "Escolher",
      onclick: () => choose("folder", `Escolha a pasta: ${label}`, val || "", async (p) => {
        try {
          const r = await api("settings/folder", { kind, path: p });
          toast(r.copied ? `Pasta trocada. ${plural(r.copied, "revisão copiada", "revisões copiadas")} para a pasta nova.` : "Pasta trocada.");
          render();
        } catch (e) { toast(e.message, true); }
      }) }),
    !isDefault ? h("button", { class: "btn ghost small", text: kind === "report_dir" ? "Tirar" : "Padrão", onclick: async () => {
      try { await api("settings/folder", { kind, path: null }); toast("Pasta trocada."); render(); } catch (e) { toast(e.message, true); } } }) : null);
  const sPastas = sec("pastas", h2("Pastas"),
    folderRow("Cache de análise", "cache_dir", C.folders.cache_dir, !C.folders.custom.cache_dir),
    folderRow("Comentários e revisões", "reviews_dir", C.folders.reviews_dir, !C.folders.custom.reviews_dir),
    folderRow("Revisões para o relatório do mês", "report_dir", C.folders.report_dir, !C.folders.report_dir,
      "só as revisões deste computador"),
    h("span", { class: "hint", text: "Trocar a pasta das revisões copia as revisões já salvas para a pasta nova. Trocar a do cache começa um cache novo (o antigo fica onde está). " +
      "Para o relatório do mês juntar os dois computadores, aponte a última para a pasta onde ficam os pacotes exportados (por exemplo, no Google Drive)." }));

  // ---- Análise
  const sens = h("input", { id: "cfg-sens", type: "range", min: "0", max: "100", value: String(st.sensitivity) });
  sens.addEventListener("change", () => save({ sensitivity: Number(sens.value) }));
  const sAnalise = sec("analise", h2("Análise"),
    h("label", { for: "cfg-sens", class: "cfg-lab", text: "Sensibilidade padrão da detecção de frames" }), sens,
    h("div", { class: "ends" }, h("span", { text: "Só as mudanças mais fortes" }), h("span", { text: "Mais frames marcados" })),
    h("div", { class: "cfg-sep" }),
    line("Juntar listas e textos que entram aos poucos", "Mudanças na mesma região, em até este tempo, viram um só frame. Não muda a sensibilidade.",
      selectOf("cfg-grp", [[4, "até 4 s"], [8, "até 8 s"], [12, "até 12 s"], [0, "não juntar"]], st.group_gap_s,
        (v) => save({ group_gap_s: Number(v) })), "cfg-grp"),
    line("Ouvir as falas", "Padrão da tela de início: procura “errei”, “retomando” e takes repetidos.",
      (() => { const c = h("input", { type: "checkbox", class: "cfg-cb", "aria-label": "Ouvir as falas", checked: st.transcribe ? true : null });
        c.addEventListener("change", () => save({ transcribe: c.checked })); return c; })()),
    h("div", { class: "cfg-sep" }),
    chipEditor("Frases de erro na fala", "Quando o professor diz uma destas, vira aviso “conferir”. Palavra inteira, sem diferença de acento.",
      st.error_phrases, "Nova frase (ex.: vou repetir)", (items) => save({ error_phrases: items })),
    chipEditor("Nomes genéricos na tarja", "Tarja com um destes textos vira aviso (o editor esqueceu de trocar o nome).",
      st.generic_names, "Novo texto genérico", (items) => save({ generic_names: items })));

  // ---- Equipe
  const team = h("div", { class: "cfg-team" });
  function drawTeam(eds) {
    fill(team, eds.map((e) => h("div", { class: "cfg-trow" + (e.active === false ? " off" : "") },
      h("span", { class: "n", text: e.name }), h("span", { class: "s", text: e.active === false ? "inativa" : "ativa" }),
      h("button", { class: "btn ghost small", text: "Renomear", onclick: () => renameDialog(e.name) }),
      h("button", { class: "btn ghost small", text: e.active === false ? "Ativar" : "Desativar",
        onclick: () => teamOp({ op: "toggle", name: e.name }) }))));
  }
  async function teamOp(body, msg) {
    try { const r = await api("settings/editors", body); drawTeam(r.editors); toast(msg || "Equipe salva."); return true; }
    catch (e) { toast(e.message, true); return false; }
  }
  function renameDialog(name) {
    const inp = h("input", { class: "input", value: name, "aria-label": "Novo nome" });
    const ok = async () => { if (await teamOp({ op: "rename", name, new: inp.value }, "Nome trocado (também nas revisões salvas).")) closeModal(); };
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") ok(); });
    openModal(`Renomear ${name}`, [inp, h("span", { class: "hint", text: "As revisões salvas passam a usar o nome novo, e as horas continuam juntas no relatório." })],
      [h("button", { class: "btn ghost", text: "Cancelar", onclick: closeModal }), h("button", { class: "btn", text: "Renomear", onclick: ok })]);
    inp.select();
  }
  drawTeam(C.editors);
  const newEd = h("input", { id: "cfg-newed", class: "input", placeholder: "Adicionar editor", autocomplete: "off" });
  const addEd = async () => { if (newEd.value.trim() && await teamOp({ op: "add", name: newEd.value }, "Editor adicionado.")) newEd.value = ""; };
  newEd.addEventListener("keydown", (e) => { if (e.key === "Enter") addEd(); });
  // exportar / importar a equipe (pedido do JP, 27/10): equipes grandes cadastram uma vez e passam o arquivo
  const exportTeam = () => {
    if (!team.querySelector(".cfg-trow:not(.off)")) { toast("Cadastre a equipe antes de exportar.", true); return; }
    location.href = "/api/settings/equipe.txt";
    toast("Arquivo da equipe baixado (pasta Downloads). Mande para as outras pessoas importarem.");
  };
  const sEquipe = sec("equipe",
    h("div", { class: "cfg-hrow" }, h2("Equipe", "Quem aparece na escolha de editor de cada vídeo e no relatório do mês."),
      h("div", { class: "row", style: { gap: "8px", flex: "none" } },
        h("button", { class: "btn small", type: "button", text: "Importar equipe", onclick: () => importTeamDialog((eds) => drawTeam(eds)) }),
        h("button", { class: "btn small", type: "button", text: "Exportar equipe", onclick: exportTeam }))),
    team,
    h("div", { class: "row" }, h("label", { for: "cfg-newed", class: "sr", text: "Novo editor" }), newEd,
      h("button", { class: "btn", text: "Adicionar", onclick: addEd })),
    h("span", { class: "hint", text: "Desativar não apaga o histórico: as horas já registradas continuam no relatório. " +
      "Exportar equipe baixa um arquivo com os nomes ativos; nos outros computadores, Importar equipe junta esses nomes aos que já estão lá (ninguém é apagado)." }));

  // ---- Cópia e envio
  const preview = h("div", { class: "cfg-prev mono" });
  function drawPreview() {
    const tc = { seconds: "00:00:44,000", ndf: "00:00:44,000", df: "00:00:44,000" }[st.time_format];
    const end = `00:00:${pad(44 + Number(st.srt_block_s))},000`;
    const copied = { seconds: "00:00:44", ndf: "00:00:44:12", df: "00:00:44;12" }[st.time_format];
    fill(preview, h("span", { class: "faint", text: "SRT:" }), h("br"), "1", h("br"), `${tc} --> ${end}`, h("br"),
      `${st.srt_prefix ? st.srt_prefix + " " : ""}“Bolsa Família” entra depois do início da fala.`, h("br"), h("br"),
      h("span", { class: "faint", text: "Texto copiado:" }), h("br"), `Vídeo 02 · ${copied} · “Bolsa Família” entra depois do início da fala.`);
  }
  const prefix = h("input", { id: "cfg-pre", class: "input cfg-sel", value: st.srt_prefix, maxlength: "30", autocomplete: "off" });
  prefix.addEventListener("change", async () => { if (await save({ srt_prefix: prefix.value })) { st.srt_prefix = prefix.value.trim(); drawPreview(); } });
  const sCopia = sec("copia", h2("Cópia e envio ao editor", "Como o tempo aparece nos comentários copiados e nos arquivos SRT."),
    line("Formato do tempo", "Use o mesmo da timeline de vocês.",
      selectOf("cfg-tc", [["seconds", "Segundos · 00:00:44"], ["ndf", "Com frames, sem drop frame · 00:00:44:12"],
        ["df", "Com frames, drop frame · 00:00:44;12"]], st.time_format, async (v) => { if (await save({ time_format: v })) drawPreview(); }), "cfg-tc"),
    line("Duração de cada bloco do SRT", "Quanto tempo a correção fica visível na timeline.",
      selectOf("cfg-srt", [[2, "2 s"], [3, "3 s"], [5, "5 s"]], st.srt_block_s, async (v) => { if (await save({ srt_block_s: Number(v) })) drawPreview(); }), "cfg-srt"),
    line("Início do texto de cada bloco", "Aparece antes do comentário.", prefix, "cfg-pre"),
    line("Salvar os SRT", "Com o mesmo nome do vídeo, mais .srt.",
      selectOf("cfg-where", [["beside", "Ao lado dos vídeos"], ["subfolder", "Numa subpasta “Correções”"]], st.srt_where,
        (v) => save({ srt_where: v })), "cfg-where"),
    preview);
  drawPreview();

  // ---- Ortografia
  const langBox = (label, key, extra) => {
    const c = h("input", { type: "checkbox", checked: st[key] ? true : null });
    c.addEventListener("change", () => save({ [key]: c.checked }));
    return h("label", { class: "check" }, c, label, extra ? h("span", { class: "faint f-small", text: extra }) : null);
  };
  const words = h("div", { class: "chips" });
  function drawWords(list) {
    fill(words, list.length ? list.map((w) => h("span", { class: "chip" }, w,
      h("button", { "aria-label": `Remover ${w}`, text: "×", onclick: () => wordOp("remove", w) })))
      : h("span", { class: "faint f-small", text: "Nenhuma palavra ainda. Use “Aceitar” num aviso de ortografia ou adicione abaixo." }));
  }
  async function wordOp(op, w) {
    try {
      const r = await api("settings/words", { op, word: w });
      drawWords(r.words);
      toast((op === "add" ? "Palavra adicionada." : "Palavra removida.") + (r.refreshed ? " Ortografia refeita na revisão aberta." : ""));
      return true;
    } catch (e) { toast(e.message, true); return false; }
  }
  drawWords(C.words);
  const newW = h("input", { id: "cfg-neww", class: "input", placeholder: "Adicionar palavra ou expressão", autocomplete: "off" });
  const addW = async () => { if (newW.value.trim() && await wordOp("add", newW.value)) newW.value = ""; };
  newW.addEventListener("keydown", (e) => { if (e.key === "Enter") addW(); });
  const sOrto = sec("ortografia",
    h2("Ortografia e dicionário", "O texto na tela é lido por OCR e conferido no próprio computador. Uma palavra só é marcada como erro se não existir em nenhum idioma ou lista ativados abaixo."),
    h("div", { class: "cfg-langs" },
      h("label", { class: "check" }, h("input", { type: "checkbox", checked: true, disabled: true }), "Português (Brasil) ",
        h("span", { class: "faint f-small", text: "sempre ativo" })),
      langBox("Inglês ", "spell_en", "EUA e Reino Unido"),
      langBox("Latim ", "spell_la")),
    h("div", { class: "field" }, h("span", { class: "label", text: "Palavras e expressões aceitas" }), words),
    h("div", { class: "row" }, h("label", { for: "cfg-neww", class: "sr", text: "Nova palavra ou expressão" }), newW,
      h("button", { class: "btn", text: "Adicionar", onclick: addW })),
    h("span", { class: "hint", text: "Ao tocar em “Aceitar” num aviso da revisão, a palavra entra nesta lista automaticamente. A lista vale para todos os cursos." }));

  // ---- navegação lateral
  const editorMode = st.mode === "editor";
  const secs = CFG_SECTIONS.filter(([id]) => !editorMode || CFG_SECTIONS_EDITOR.includes(id));
  const nav = h("nav", { class: "cfg-nav", "aria-label": "Seções" }, secs.map(([id, label]) =>
    h("button", { "data-sec": id, text: label, onclick: () => {
      const el = document.getElementById("cfg-" + id);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#/config/" + id);
      setActive(id);
    } })),
    // versão do app: para conferir se é a mesma da página de versões no GitHub
    h("span", { class: "cfg-ver faint", text: `Revisor de Vídeos ${S && S.version ? S.version : ""}` }));
  function setActive(id) { nav.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.sec === id)); }
  const body = h("div", { class: "cfg-body" }, sModo, sCache, sPastas, sAnalise,
    editorMode ? null : sEquipe, editorMode ? null : sCopia, sOrto);
  root.appendChild(h("div", { class: "cfg" }, nav, body));
  setActive(arg || "modo");
  if (arg && document.getElementById("cfg-" + arg)) document.getElementById("cfg-" + arg).scrollIntoView({ block: "start" });
  const obs = new IntersectionObserver((es) => {
    const vis = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
    if (vis) setActive(vis.target.dataset.sec);
  }, { rootMargin: "-80px 0px -60% 0px" });
  body.querySelectorAll(".cfg-sec").forEach((s) => obs.observe(s));
  screenCleanup = () => obs.disconnect();
  loadCache();
}

/** Importar a equipe: o arquivo exportado em outro computador (.txt, um nome por linha) ou uma lista colada.
 *  Junta com a equipe deste computador: ninguém é apagado. done(editores) roda depois de importar. */
function importTeamDialog(done) {
  const ta = h("textarea", { class: "rv-ta", style: { minHeight: "160px" }, "aria-label": "Nomes da equipe",
    placeholder: "Ou cole aqui os nomes, um por linha (dá para copiar uma coluna da planilha)." });
  const info = h("span", { class: "hint" });
  const file = h("input", { type: "file", accept: ".txt,text/plain", class: "hidden" });
  const parse = (t) => {
    const seen = new Set(), out = [];
    String(t || "").split(/\r?\n|\r/).forEach((line) => {
      line = line.trim().replace(/^\ufeff/, "");
      if (!line || line.startsWith("#")) return;
      line.split(/[;\t]/).forEach((p) => {
        const n = p.split(/\s+/).join(" ").replace(/^[\s,\-•*]+|[\s,\-•*]+$/g, "");
        if (n && n.length <= 40 && !seen.has(n.toLowerCase())) { seen.add(n.toLowerCase()); out.push(n); }
      });
    });
    return out;
  };
  const go = h("button", { class: "btn primary", type: "button", style: { height: "40px", fontSize: "14px" }, text: "Importar", disabled: true });
  const refresh = () => {
    const n = parse(ta.value).length;
    info.textContent = n ? `${plural(n, "nome encontrado", "nomes encontrados")}.` : "Nenhum nome ainda.";
    go.disabled = !n;
    go.textContent = n ? `Importar ${plural(n, "nome", "nomes")}` : "Importar";
  };
  ta.addEventListener("input", refresh);
  file.addEventListener("change", () => {
    const f = file.files && file.files[0];
    if (!f) return;
    if (f.size > 200000) { toast("Esse arquivo é grande demais para ser uma lista de equipe.", true); return; }
    const fr = new FileReader();
    fr.onload = () => { ta.value = String(fr.result || ""); refresh(); };
    fr.onerror = () => toast("Não consegui ler o arquivo.", true);
    fr.readAsText(f, "utf-8");
  });
  go.addEventListener("click", async () => {
    go.disabled = true;
    try {
      const r = await api("settings/editors", { op: "import", text: ta.value });
      closeModal();
      const parts = [];
      if (r.added.length) parts.push(plural(r.added.length, "nome novo", "nomes novos"));
      if (r.reactivated.length) parts.push(plural(r.reactivated.length, "reativado", "reativados"));
      if (r.already.length) parts.push(`${r.already.length} já ${r.already.length === 1 ? "estava" : "estavam"} na equipe`);
      toast(`Equipe importada: ${parts.join(" · ")}.`);
      if (done) done(r.editors);
    } catch (e) { toast(e.message, true); go.disabled = false; }
  });
  openModal("Importar equipe", [
    h("p", { class: "muted", style: { margin: 0, fontSize: "13px" },
      text: "Escolha o arquivo que alguém exportou em Configurações → Equipe → Exportar equipe, ou cole a lista de nomes. " +
            "Os nomes se juntam aos que já estão aqui: ninguém é apagado e quem estava desativado volta a ficar ativo." }),
    h("button", { class: "btn", type: "button", text: "Escolher o arquivo da equipe (.txt)", onclick: () => file.click() }),
    file, ta, info],
    [h("button", { class: "btn ghost", type: "button", text: "Cancelar", onclick: closeModal }), go]);
  refresh();
}

/** Lista editável em "chips" (frases de erro, nomes genéricos). onSave(lista) devolve true se salvou. */
function chipEditor(title, hint, items, placeholder, onSave) {
  let list = (items || []).slice();
  const box = h("div", { class: "chips" });
  const draw = () => fill(box, list.map((w) => h("span", { class: "chip" }, w,
    h("button", { "aria-label": `Remover ${w}`, text: "×", onclick: async () => {
      const nl = list.filter((x) => x !== w);
      if (await onSave(nl)) { list = nl; draw(); }
    } }))));
  const inp = h("input", { class: "input", placeholder, autocomplete: "off", "aria-label": placeholder });
  const addIt = async () => {
    const v = inp.value.trim();
    if (!v) return;
    if (list.some((x) => x.toLowerCase() === v.toLowerCase())) { toast("Já está na lista.", true); return; }
    const nl = list.concat([v]);
    if (await onSave(nl)) { list = nl; inp.value = ""; draw(); }
  };
  inp.addEventListener("keydown", (e) => { if (e.key === "Enter") addIt(); });
  draw();
  return h("div", { class: "field" }, h("span", { class: "label", text: title }), h("span", { class: "hint", text: hint }), box,
    h("div", { class: "row" }, inp, h("button", { class: "btn", text: "Adicionar", onclick: addIt })));
}
