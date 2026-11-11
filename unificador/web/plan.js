// Pinta el plan con createElement/textContent (nunca innerHTML con datos del plan).
// Cada rama es una línea (carril); sus fases van de izquierda a derecha y los pasos son estaciones.
import { post, sendToActive } from "./chat.js";
const STATE = { pending: ["", "Pendiente"], doing: ["", "En curso"], done: ["✓", "Hecho"] };
const KIND = { start: "Empezó", done: "Terminó", reopen: "Reabrió", change: "Pidió un cambio", note: "Nota" };
const NS = "http://www.w3.org/2000/svg";
let openId = null;             // paso con el detalle abierto (sobrevive a los repintados)
const prevState = new Map();   // id de paso -> último estado pintado (para animar los cambios)
const prevPct = new Map();     // rama -> último % pintado

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

const reduce = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const steps = (b) => b.phases.flatMap((p) => p.steps);
const count = (list) => [list.filter((s) => s.state === "done").length, list.length];
const pctOf = (done, total) => (total ? Math.round((done / total) * 100) : 0);
const phaseState = (p) => (p.steps.every((s) => s.state === "done") ? "done" : p.steps.some((s) => s.state !== "pending") ? "doing" : "pending");
const glyph = (s, state) => (s.change ? "✎" : (STATE[state] || STATE.pending)[0]);

function when(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  return d.toLocaleString("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function section(title, ...kids) {
  const d = el("div");
  d.append(el("h4", null, title), ...kids);
  return d;
}

function detail(s) {
  const d = el("div", "detail");
  d.setAttribute("role", "region");
  d.setAttribute("aria-label", `Detalle: ${s.title}`);
  if (s.change) d.append(el("div", "change-box", `✏️ Corrección pedida: ${s.change}`));
  if (s.desc) d.append(section("Qué hay que hacer", el("p", null, s.desc)));
  if (s.result) d.append(section("Cómo quedó", el("p", null, s.result)));
  if (s.notes && s.notes.length) {
    const ul = el("ul", "notes");
    for (const n of s.notes) {
      const li = el("li");
      const who = el("b", null, `${KIND[n.kind] || "Nota"}${n.by ? ` · ${n.by}` : ""}`);
      const txt = el("span", null, n.text ? `: ${n.text}` : "");
      const body = el("span");
      body.append(who, txt);
      li.append(el("time", null, when(n.at)), body);
      ul.append(li);
    }
    d.append(section("Historia", ul));
  }
  d.append(actions(s));
  return d;
}

// Borradores de corrección por paso: sobreviven a los repintados del plan (SSE).
const drafts = new Map(); // id -> texto (existe = formulario abierto)
const notes = new Map();  // id -> último aviso/error

async function call(url, body) {
  const r = await post(url, body);
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.error || `Error ${r.status}`);
  }
}

function actions(s) {
  const box = el("div", "actions");
  const msg = el("span", "act-msg", notes.get(s.id) || "");
  msg.setAttribute("role", "status");
  const say = (t) => { notes.set(s.id, t); msg.textContent = t; };
  const pill = (text, label, fn) => {
    const b = el("button", "pill", text);
    b.type = "button";
    if (label) b.setAttribute("aria-label", label);
    b.addEventListener("click", fn);
    return b;
  };
  const run = async (b, fn) => {
    b.disabled = true; say("");
    try { await fn(); } catch (e) { say(`No se pudo: ${e.message}`); b.disabled = false; }
  };

  const ask = pill("✏️ Pedir un cambio", `Pedir un cambio en el paso ${s.title}`, () => {
    drafts.set(s.id, drafts.get(s.id) || ""); say("");
    form.hidden = false; ask.hidden = true; ta.focus();
  });
  const mark = s.state === "done"
    ? pill("↩ Reabrir", `Reabrir el paso ${s.title}`, () => run(mark, () => call(`/api/plan/steps/${s.id}/state`, { state: "pending" })))
    : pill("✓ Marcar hecho", `Marcar hecho el paso ${s.title}`, () => run(mark, () => call(`/api/plan/steps/${s.id}/state`, { state: "done" })));

  const form = el("div", "change-form");
  const ta = el("textarea");
  ta.rows = 2;
  ta.placeholder = "¿Qué quieres que cambie en este paso?";
  ta.setAttribute("aria-label", `Cambio que pides en el paso ${s.title}`);
  ta.value = drafts.get(s.id) || "";
  ta.addEventListener("input", () => drafts.set(s.id, ta.value));
  const close = () => { drafts.delete(s.id); ta.value = ""; form.hidden = true; ask.hidden = false; ask.focus(); };
  const send = pill("Enviar", null, async () => {
    const text = ta.value.trim();
    if (!text) { say("Escribe primero qué quieres cambiar."); ta.focus(); return; }
    send.disabled = true; say("");
    try {
      await call(`/api/plan/steps/${s.id}/change`, { text });
    } catch (e) { say(`No se pudo: ${e.message}`); send.disabled = false; return; }
    send.disabled = false;
    close();
    const sent = await sendToActive(`Corrige el paso ${s.id} «${s.title}»: ${text}. Míralo en el plan (unificador.json) y retómalo.`);
    say(sent ? "" : "La IA está ocupada; la corrección queda apuntada en el paso.");
  });
  const cancel = pill("Cancelar", null, close);
  form.append(ta, el("div", "change-btns"));
  form.lastChild.append(send, cancel);
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send.click(); }
  });
  form.hidden = !drafts.has(s.id);
  ask.hidden = !form.hidden;

  const row = el("div", "act-row");
  row.append(ask, mark, msg);
  box.append(row, form);
  return box;
}

// Color de la rama: índice 0-7 de la paleta, o un color CSS si viene como texto.
function paint(c, b, i) {
  const raw = b.color;
  if (typeof raw === "string" && /^#[0-9a-f]{3,8}$/i.test(raw)) { c.style.setProperty("--accent", raw); return; }
  const n = raw === "" || raw == null || isNaN(Number(raw)) ? i : Number(raw);
  c.dataset.color = String(((n % 8) + 8) % 8);
}

function ring(key, pct) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 44 44");
  svg.setAttribute("class", "ring");
  svg.setAttribute("aria-hidden", "true");
  const mk = (cls) => {
    const c = document.createElementNS(NS, "circle");
    c.setAttribute("class", cls); c.setAttribute("cx", "22"); c.setAttribute("cy", "22"); c.setAttribute("r", "18");
    svg.append(c);
    return c;
  };
  mk("ring-bg");
  const fg = mk("ring-fg");
  const len = 2 * Math.PI * 18;
  fg.style.strokeDasharray = String(len);
  const set = (p) => { fg.style.strokeDashoffset = String(len * (1 - p / 100)); };
  set(prevPct.has(key) ? prevPct.get(key) : 0);
  requestAnimationFrame(() => requestAnimationFrame(() => set(pct)));
  return svg;
}

function fillDetail(lane, s) {
  const slot = lane.querySelector(".lane-detail");
  if (!s) { slot.replaceChildren(); slot.hidden = true; return; }
  const d = detail(s);
  const x = el("button", "d-close", "✕");
  x.type = "button";
  x.setAttribute("aria-label", "Cerrar el detalle");
  x.addEventListener("click", () => lane.querySelector(".step.open .s-btn")?.click());
  d.prepend(el("h3", "d-title", s.title), x);
  slot.replaceChildren(d);
  slot.hidden = false;
}

function step(s, idx) {
  const known = prevState.get(s.id);
  const shown = known || "pending";   // primera vez: se pinta pendiente y se «rellena» hasta su estado
  const li = el("li", `step ${shown}`);
  li.dataset.id = s.id;
  if (s.change) li.classList.add("changed");
  const btn = el("button", "s-btn");
  btn.type = "button";
  btn.setAttribute("aria-expanded", "false");
  btn.title = `${s.title} · ${(STATE[s.state] || STATE.pending)[1]}${s.change ? " · pide cambios" : ""}`;
  const node = el("span", "node", glyph(s, shown));
  btn.append(node, el("span", "s-title", s.title));
  if (s.change) btn.append(el("span", "badge", "Pide cambios"));
  btn.addEventListener("click", () => {
    openId = openId === s.id ? null : s.id;
    const lane = li.closest(".lane");
    for (const x of document.querySelectorAll(".s-btn[aria-expanded='true']")) x.setAttribute("aria-expanded", "false");
    for (const x of document.querySelectorAll(".lane.has-open")) { x.classList.remove("has-open"); fillDetail(x, null); }
    for (const x of document.querySelectorAll(".step.open")) x.classList.remove("open");
    if (openId) {
      btn.setAttribute("aria-expanded", "true");
      li.classList.add("open");
      lane.classList.add("has-open");
      fillDetail(lane, s);
    }
  });
  if (s.state !== shown) {
    li.style.setProperty("--d", reduce() ? "0ms" : `${Math.min(idx, 12) * 70}ms`);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      li.classList.remove(shown); li.classList.add(s.state);
      node.textContent = glyph(s, s.state);
      if (known && !reduce()) { li.classList.add("flash"); setTimeout(() => li.classList.remove("flash"), 1600); }
    }));
  }
  prevState.set(s.id, s.state);
  li.append(btn);
  return li;
}

function phase(p, off) {
  const st = p.steps.length ? phaseState(p) : "pending", [done, total] = count(p.steps);
  const sec = el("section", `phase ${st}`);
  const head = el("div", "p-head");
  head.append(el("span", "station", st === "done" ? "✓" : ""), el("h3", null, `${p.icon ? p.icon + " " : ""}${p.name}`),
    el("span", "p-state", st === "done" ? "Hecha" : st === "doing" ? `En curso · ${done}/${total}` : "Pendiente"));
  const ul = el("ul", "steps");
  ul.append(...p.steps.map((s, k) => step(s, off + k)));
  sec.append(head, ul);
  return sec;
}

function branch(b, i) {
  const [done, total] = count(steps(b));
  const key = b.key || b.name;
  const pct = pctOf(done, total);
  const c = el("article", "lane");
  paint(c, b, i);
  const head = el("div", "b-head"), t = el("div", "b-text");
  t.append(el("h2", null, b.name));
  if (b.goal) t.append(el("p", "muted", b.goal));
  const prog = el("div", "b-prog");
  prog.append(ring(key, pct), el("span", "b-count", `${done} de ${total}`));
  head.append(el("div", "b-icon", b.icon || "📌"), t, prog);
  const track = el("div", "track"), row = el("div", "phases");
  let off = 0;
  for (const p of b.phases) { row.append(phase(p, off)); off += p.steps.length; }
  track.append(row);
  const slot = el("div", "lane-detail");
  slot.hidden = true;
  c.append(head, track, slot);
  prevPct.set(key, pct);
  const open = steps(b).find((s) => s.id === openId);
  if (open) {
    c.classList.add("has-open");
    const li = [...c.querySelectorAll(".step")].find((x) => x.dataset.id === open.id);
    li.classList.add("open");
    li.querySelector(".s-btn").setAttribute("aria-expanded", "true");
    fillDetail(c, open);
  }
  return c;
}

export function renderPlan(plan) {
  const root = document.getElementById("branches");
  const all = plan.branches || [];
  const live = all.filter((b) => !b.archived), old = all.filter((b) => b.archived);
  const [done, total] = count(all.flatMap(steps));
  if (openId && !all.some((b) => steps(b).some((s) => s.id === openId))) openId = null;

  document.getElementById("total").hidden = !total;
  document.getElementById("total-text").textContent = `${done} de ${total} pasos · ${pctOf(done, total)}%`;
  document.getElementById("total-bar").style.width = `${pctOf(done, total)}%`;
  document.getElementById("project-sub").textContent = plan.title || "";

  // Recuerda el scroll horizontal de cada línea para que el repintado no la mueva.
  const scrolls = new Map([...root.querySelectorAll(".lane")].map((l) => [l.querySelector("h2")?.textContent, l.querySelector(".track").scrollLeft]));
  const nodes = [];
  if (!all.length) {
    const e = el("div", "empty");
    e.append(el("div", "big", "🌱"), el("h2", null, "Todavía no hay plan"),
      el("p", "muted", "Pídele algo al agente en el chat, por ejemplo «propón un plan para esto». Aparecerá aquí al momento."));
    nodes.push(e);
  }
  nodes.push(...live.map((b, i) => branch(b, i)));
  if (old.length) {
    const d = el("details", "archived");
    d.append(el("summary", null, `🏁 Terminadas (${old.length})`), ...old.map((b, i) => branch(b, live.length + i)));
    d.open = root.querySelector(".archived")?.open || false;
    nodes.push(d);
  }
  const y = window.scrollY;
  root.replaceChildren(...nodes);
  for (const l of root.querySelectorAll(".lane")) {
    const sl = scrolls.get(l.querySelector("h2")?.textContent);
    if (sl) l.querySelector(".track").scrollLeft = sl;
  }
  window.scrollTo(0, y);
}
