// «Caja»: ideas sueltas, prompts maestros para encargar, la cola de encargos y los retoques.
// Es un segundo cajón lateral, como el de decisiones. Todo con textContent (nada de innerHTML).
import { app, el, button, getJSON, q, send, run, status, textarea, drafts, toast, when } from "./util.js";
import { icon } from "./icons.js";

const $ = (id) => document.getElementById(id);
let from = null;
let prompts = null;        // caché de /api/prompts (por proyecto)
let promptsPid = null;
const shown = new Set();   // prompts desplegados
let versions = null;       // caché de /api/versions (se pide al abrir la caja)
let versionsSig = "";

function box(open) {
  const d = $("box");
  if (open === !d.hidden) return;
  d.hidden = !open;
  $("box-scrim").hidden = !open;
  $("boxb").setAttribute("aria-expanded", String(open));
  if (open) {
    from = document.activeElement;
    $("box-close").focus();
    loadPrompts();
    loadVersions();
  } else {
    const f = from; from = null;
    (f && f.isConnected ? f : $("boxb")).focus?.();
  }
}

async function loadPrompts() {
  if (promptsPid === app.pid && prompts) return;
  try {
    const pid = app.pid;
    const data = await getJSON(q("/api/prompts"));
    if (pid !== app.pid) return;
    prompts = data.prompts || [];
    promptsPid = pid;
    if (app.plan) renderBox(app.plan);
  } catch { /* sin conexión: se reintenta al abrir otra vez */ }
}

async function loadVersions() {
  try {
    const pid = app.pid;
    const data = await getJSON(q("/api/versions"));
    if (pid !== app.pid) return;
    versions = data;
    if (app.plan) renderBox(app.plan);
  } catch { /* sin conexión: se queda lo último que hubo */ }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copiado. Pégalo en el chat de tu agente.");
  } catch {
    toast("No se pudo copiar: selecciona el texto y cópialo a mano.");
  }
}

function section(title, ...kids) {
  const s = el("section", "bx-sec");
  s.append(el("h3", "bx-h", title), ...kids);
  return s;
}

// ── Ideas ─────────────────────────────────────────────────────────────

function ideasSection(plan) {
  const ideas = plan.ideas || [];
  const open = ideas.filter((i) => i.state === "open").reverse();
  const rest = ideas.filter((i) => i.state !== "open").reverse().slice(0, 8);
  const ta = textarea("idea:new", "Algo que se te ocurra, aunque sea a medias…", "Idea nueva", 2);
  const [msg, say] = status("idea:new");
  const add = button("Guardar idea", "pill primary", async () => {
    const text = ta.value.trim();
    if (!text) { say("Escribe la idea primero."); return; }
    await run(add, say, async () => {
      await send("/api/plan/ideas", { text });
      drafts.delete("idea:new");
      toast("Idea guardada. Tu agente la verá en su próximo turno.");
    });
  });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) add.click(); });
  const form = el("div", "bx-form");
  form.append(ta, el("div", "bx-row"));
  form.lastChild.append(add, msg);

  const list = el("ul", "bx-list");
  for (const i of open) list.append(ideaItem(i, plan));
  if (!open.length) list.append(el("li", "muted bx-empty", "No hay ideas abiertas."));
  const kids = [form, list];
  if (rest.length) {
    const det = el("details", "bx-more");
    det.append(el("summary", "", `Ya planificadas o descartadas (${rest.length})`));
    const l2 = el("ul", "bx-list");
    for (const i of rest) l2.append(ideaItem(i, plan));
    det.append(l2);
    kids.push(det);
  }
  return section("💡 Ideas", ...kids);
}

function ideaItem(i, plan) {
  const li = el("li", `bx-item idea ${i.state}`);
  const top = el("div", "bx-top");
  top.append(el("strong", "bx-id", i.id), el("span", "muted", `${i.by === "persona" ? "Tú" : "Agente"} · ${when(i.at)}`));
  li.append(top, el("p", "bx-text", i.text));
  if (i.state === "planned") {
    const b = (plan.branches || []).find((x) => x.key === i.branch);
    li.append(el("p", "bx-tag", `→ En la rama «${b ? b.name : i.branch}»`));
  } else if (i.state === "dropped") {
    li.append(el("p", "bx-tag", `Descartada${i.note ? `: ${i.note}` : ""}`));
  }
  const [msg, say] = status(`idea:${i.id}`);
  const row = el("div", "bx-row");
  if (i.state === "open") {
    const drop = button("Descartar", "pill", () => run(drop, say, () => send(`/api/plan/ideas/${encodeURIComponent(i.id)}/drop`, {})));
    row.append(drop);
  } else if (i.state === "dropped") {
    const back = button("Recuperar", "pill", () => run(back, say, () => send(`/api/plan/ideas/${encodeURIComponent(i.id)}/reopen`, {})));
    row.append(back);
  }
  row.append(msg);
  if (row.children.length > 1) li.append(row);
  return li;
}

// ── Prompts maestros y cola ───────────────────────────────────────────

function targetSelect(plan, key) {
  const sel = el("select", "bx-sel");
  sel.setAttribute("aria-label", "Sobre qué rama");
  const none = el("option", "", "Todo el proyecto");
  none.value = "";
  sel.append(none);
  for (const b of (plan.branches || []).filter((x) => !x.archived)) {
    const o = el("option", "", `${b.icon || ""} ${b.name}`.trim());
    o.value = b.key;
    sel.append(o);
  }
  sel.value = drafts.get(key) || "";
  sel.addEventListener("change", () => drafts.set(key, sel.value));
  return sel;
}

function promptsSection(plan) {
  const list = el("ul", "bx-list");
  if (!prompts) list.append(el("li", "muted bx-empty", "Cargando…"));
  for (const p of prompts || []) {
    const li = el("li", "bx-item prompt");
    const open = shown.has(p.name);
    const head = button("", "bx-ph", () => { open ? shown.delete(p.name) : shown.add(p.name); renderBox(plan); });
    head.setAttribute("aria-expanded", String(open));
    head.append(el("strong", "", p.title), el("span", "muted", p.source === "proyecto" ? "del proyecto" : "de serie"));
    li.append(head);
    if (open) li.append(el("pre", "bx-pre", p.text));
    const key = `job:${p.name}`;
    const sel = targetSelect(plan, key);
    const [msg, say] = status(key);
    const go = button("Encargar", "pill primary", () => run(go, say, async () => {
      await send("/api/plan/queue", { prompt: p.name, branch: sel.value });
      toast("Encargado. Tu agente lo hará cuando acabe lo que tenga entre manos.");
    }));
    const cp = button("Copiar", "pill", () => copy(p.text));
    const row = el("div", "bx-row");
    row.append(sel, go, cp, msg);
    li.append(row);
    list.append(li);
  }
  const hint = el("p", "muted bx-hint", "Añade los tuyos como ficheros .md en .unificador/prompts/ (la primera línea, «# Título»).");
  return section("📜 Prompts maestros", list, hint);
}

function queueSection(plan) {
  const jobs = (plan.queue || []).slice().reverse();
  const pending = jobs.filter((j) => j.state === "pending");
  const done = jobs.filter((j) => j.state === "done").slice(0, 6);
  const list = el("ul", "bx-list");
  if (!pending.length) list.append(el("li", "muted bx-empty", "Nada en cola."));
  for (const j of pending) list.append(jobItem(j, plan));
  const kids = [list];
  if (done.length) {
    const det = el("details", "bx-more");
    det.append(el("summary", "", `Hechos (${done.length})`));
    const l2 = el("ul", "bx-list");
    for (const j of done) l2.append(jobItem(j, plan));
    det.append(l2);
    kids.push(det);
  }
  return section(`🧾 Encargos en cola${pending.length ? ` (${pending.length})` : ""}`, ...kids);
}

function jobItem(j, plan) {
  const li = el("li", `bx-item job ${j.state}`);
  const top = el("div", "bx-top");
  const b = j.branch && (plan.branches || []).find((x) => x.key === j.branch);
  const where = j.branch ? ` · ${b ? b.name : j.branch}${j.phase ? ` › ${j.phase}` : ""}` : "";
  top.append(el("strong", "bx-id", j.id), el("span", "", j.title), el("span", "muted", `${when(j.at)}${where}`));
  li.append(top);
  if (j.state === "done") {
    li.append(el("p", "bx-text", j.result || "Hecho."));
  } else {
    const [msg, say] = status(`job:${j.id}`);
    const drop = button("Quitar", "pill", () => run(drop, say, () => send(`/api/plan/queue/${encodeURIComponent(j.id)}/drop`, {})));
    const row = el("div", "bx-row");
    row.append(drop, msg);
    li.append(row);
  }
  return li;
}

// ── Versiones ─────────────────────────────────────────────────────────

const KINDS = { nuevo: "✨", arreglo: "🐛", cambio: "🔧", fase: "🏁" };

function newsList(news) {
  const ul = el("ul", "bx-news");
  for (const n of news) ul.append(el("li", "", `${KINDS[n.kind] || "·"} ${n.text}`));
  return ul;
}

function versionsSection() {
  if (!versions) return section("🏷️ Versiones", el("p", "muted bx-empty", "Cargando…"));
  const v = versions;
  const next = el("li", "bx-item version next");
  const top = el("div", "bx-top");
  top.append(el("strong", "bx-id", `v${v.next}`), el("span", "", "Próxima versión"),
    el("span", "muted", v.last ? `la última es v${v.last}` : "será la primera"));
  next.append(top);
  next.append(v.news.length ? newsList(v.news) : el("p", "muted bx-text", "Sin novedades apuntadas todavía."));
  if (v.unreleased.length) {
    const det = el("details", "bx-more");
    det.append(el("summary", "", `Comiteado sin publicar (${v.unreleased.length})`));
    const ul = el("ul", "bx-news mono");
    for (const c of v.unreleased.slice(0, 30)) {
      ul.append(el("li", c.refs.length ? "" : "unlogged", `${c.sha}  ${c.subject}`));
    }
    det.append(ul);
    next.append(det);
  }
  const list = el("ul", "bx-list");
  list.append(next);
  const kids = [list];
  if (v.versions.length) {
    const det = el("details", "bx-more");
    det.append(el("summary", "", `Historial (${v.versions.length})`));
    const l2 = el("ul", "bx-list");
    for (const old of v.versions) {
      const li = el("li", "bx-item version");
      const t = el("div", "bx-top");
      t.append(el("strong", "bx-id", `v${old.version}`), el("span", "muted", when(old.at)));
      li.append(t, newsList(old.news || []));
      l2.append(li);
    }
    det.append(l2);
    kids.push(det);
  }
  kids.push(el("p", "muted bx-hint", "Tu agente la publica cuando se lo pidas (uni.py release)."));
  return section("🏷️ Versiones", ...kids);
}

// ── Retoques ──────────────────────────────────────────────────────────

function tweaksSection(plan) {
  const items = (plan.tweaks || []).slice(-12).reverse();
  const list = el("ul", "bx-list");
  if (!items.length) list.append(el("li", "muted bx-empty", "Aún no hay retoques apuntados."));
  for (const t of items) {
    const li = el("li", "bx-item tweak");
    const top = el("div", "bx-top");
    top.append(el("strong", "bx-id", t.id), el("span", "muted", when(t.at)));
    li.append(top, el("p", "bx-text", t.title));
    if ((t.commits || []).length) li.append(el("p", "bx-tag mono", t.commits.map((c) => c.slice(0, 7)).join(" · ")));
    list.append(li);
  }
  return section("✎ Retoques", list);
}

// ── Pintar ────────────────────────────────────────────────────────────

export function renderBox(plan) {
  const btn = $("boxb");
  if (!btn) return;
  const openIdeas = (plan.ideas || []).filter((i) => i.state === "open").length;
  const pending = (plan.queue || []).filter((j) => j.state === "pending").length;
  const n = openIdeas + pending;
  const cnt = el("span", "n", String(n));
  btn.classList.toggle("zero", !n);
  btn.setAttribute("aria-label", `Caja: ${openIdeas} ideas abiertas, ${pending} encargos en cola`);
  btn.replaceChildren(icon("bulb"), el("span", "decb-t", "Caja"), cnt);
  if ($("box").hidden) return;
  const sig = `${app.pid}:${(plan.news || []).length}:${(plan.versions || []).length}`;
  if (versions && sig !== versionsSig) loadVersions();
  versionsSig = sig;
  const body = $("box-body");
  const keep = body.scrollTop;
  body.replaceChildren(ideasSection(plan), promptsSection(plan), queueSection(plan), versionsSection(), tweaksSection(plan));
  body.scrollTop = keep;
}

export function resetBox() {
  prompts = null;
  promptsPid = null;
  versions = null;
  shown.clear();
  if ($("box") && !$("box").hidden) box(false);
}

export function initBox() {
  $("box-close").append(icon("x"));
  $("box-close").addEventListener("click", () => box(false));
  $("box-scrim").addEventListener("click", () => box(false));
  $("boxb").addEventListener("click", () => { if (!$("scrim").hidden) $("scrim").click(); box($("box").hidden); if (app.plan) renderBox(app.plan); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("box").hidden && !document.querySelector("dialog[open]")) { e.preventDefault(); box(false); }
  });
}
