// El tablero de un proyecto: cada rama es un carril con su color; sus fases son tarjetas en secuencia
// (de izquierda a derecha, o apiladas en pantallas estrechas) con los pasos dentro.
import { app, el, button, send, run, drafts, status, textarea, toast, when, reduce, allSteps, count, pctOf, paint } from "./util.js";
import { reviewBox, askCard, renderInbox, renderDecided, inboxKey, waitingPhases } from "./decide.js";

const STATE = { pending: ["", "Pendiente"], doing: ["", "En curso"], done: ["✓", "Hecho"] };
const KIND = { start: "Empezó", done: "Terminó", reopen: "Reabrió", change: "Pidió un cambio", note: "Nota" };
const NS = "http://www.w3.org/2000/svg";
let openId = null;             // paso con el detalle abierto (sobrevive a los repintados)
const prevState = new Map();   // id de paso -> último estado pintado (para resaltar cambios)
const prevPct = new Map();     // rama -> último % pintado
let lastInbox = "";

const glyph = (s) => (s.change ? "✎" : (STATE[s.state] || STATE.pending)[0]);

// Estado visible de una fase: la revisión manda sobre el avance de sus pasos.
export function phaseStatus(p) {
  const [done, total] = count(p.steps);
  const rs = p.review && p.review.state;
  if (rs === "waiting") return ["waiting", "Espera tu revisión"];
  if (rs === "changes") return ["changes", "Pide cambios"];
  if (rs === "approved") return ["approved", "Aprobada"];
  if (total && done === total) return ["done", "Hecha"];
  if (p.steps.some((s) => s.state !== "pending")) return ["doing", `En curso · ${done}/${total}`];
  return ["pending", "Pendiente"];
}

function section(title, ...kids) {
  const d = el("div", "d-sec");
  d.append(el("h5", null, title), ...kids);
  return d;
}

function actions(s) {
  const key = `step:${s.id}`;
  const box = el("div", "actions");
  const [msg, say] = status(key);
  const ask = button("✏️ Pedir un cambio", "pill", () => {
    drafts.set(key, drafts.get(key) || ""); say("");
    form.hidden = false; ask.hidden = true; ta.focus();
  }, `Pedir un cambio en el paso ${s.title}`);
  const target = s.state === "done" ? "pending" : "done";
  const mark = button(s.state === "done" ? "↩ Reabrir" : "✓ Marcar hecho", "pill",
    () => run(mark, say, () => send(`/api/plan/steps/${s.id}/state`, { state: target })),
    `${s.state === "done" ? "Reabrir" : "Marcar hecho"} el paso ${s.title}`);

  const form = el("div", "change-form");
  const ta = textarea(key, "¿Qué quieres que cambie en este paso?", `Cambio que pides en el paso ${s.title}`);
  const close = () => { drafts.delete(key); ta.value = ""; form.hidden = true; ask.hidden = false; ask.focus(); };
  const go = button("Enviar", "pill primary", () => {
    const text = ta.value.trim();
    if (!text) { say("Escribe primero qué quieres cambiar."); ta.focus(); return; }
    run(go, say, async () => {
      await send(`/api/plan/steps/${s.id}/change`, { text });
      drafts.delete(key);
      toast("Cambio apuntado. Tu agente lo verá la próxima vez que mire el plan.");
    });
  });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); go.click(); }
  });
  const btns = el("div", "change-btns");
  btns.append(go, button("Cancelar", "pill", close));
  form.append(ta, btns);
  form.hidden = !drafts.has(key);
  ask.hidden = !form.hidden;
  const row = el("div", "act-row");
  row.append(ask, mark);
  box.append(row, form, msg);
  return box;
}

function detail(s, plan) {
  const d = el("div", "detail");
  d.setAttribute("role", "region");
  d.setAttribute("aria-label", `Detalle: ${s.title}`);
  if (s.change) d.append(el("div", "change-box", `✏️ Corrección pedida: ${s.change}`));
  if (s.desc) d.append(section("Qué hay que hacer", el("p", null, s.desc)));
  if (s.result) d.append(section("Cómo quedó", el("p", null, s.result)));
  const asks = (plan.asks || []).filter((a) => a.step === s.id);
  if (asks.length) {
    const box = el("div", "d-asks");
    for (const a of asks) {
      if (a.answer) box.append(askCard(a, plan, true));
      else box.append(el("p", "pending-ask", `${a.kind === "proposal" ? "Propuesta" : "Pregunta"} ${a.id} «${a.title}»: espera tu respuesta en «Te toca», arriba.`));
    }
    d.append(section("Preguntas y propuestas", box));
  }
  if (s.notes && s.notes.length) {
    const ul = el("ul", "notes");
    for (const n of s.notes) {
      const li = el("li"), body = el("span");
      body.append(el("b", null, `${KIND[n.kind] || "Nota"}${n.by ? ` · ${n.by}` : ""}`), el("span", null, n.text ? `: ${n.text}` : ""));
      li.append(el("time", null, when(n.at)), body);
      ul.append(li);
    }
    d.append(section("Historia", ul));
  }
  d.append(actions(s));
  return d;
}

function stepItem(s, plan) {
  const known = prevState.get(s.id);
  const li = el("li", `step ${s.state}${s.change ? " changed" : ""}${s.id === openId ? " open" : ""}`);
  const btn = el("button", "s-btn");
  btn.type = "button";
  btn.setAttribute("aria-expanded", String(s.id === openId));
  btn.title = `${s.title} · ${(STATE[s.state] || STATE.pending)[1]}${s.change ? " · pide cambios" : ""}`;
  const text = el("span", "s-text");
  text.append(el("span", "s-title", s.title));
  const meta = el("span", "s-meta", `${s.id} · ${(STATE[s.state] || STATE.pending)[1]}`);
  text.append(meta);
  btn.append(el("span", "node", glyph(s)), text);
  if (s.change) btn.append(el("span", "badge warn", "Pide cambios"));
  const waiting = (plan.asks || []).some((a) => a.step === s.id && !a.answer);
  if (waiting) btn.append(el("span", "badge ask", "Te pregunta"));
  li.dataset.id = s.id;
  btn.addEventListener("click", () => {
    openId = openId === s.id ? null : s.id;
    app.rerender();
    const again = [...document.querySelectorAll("#branches .step")].find((x) => x.dataset.id === s.id);
    again?.querySelector(".s-btn").focus({ preventScroll: true });
  });
  li.append(btn);
  if (s.id === openId) li.append(detail(s, plan));
  if (known && known !== s.state && !reduce()) { li.classList.add("flash"); setTimeout(() => li.classList.remove("flash"), 1600); }
  prevState.set(s.id, s.state);
  return li;
}

function phaseCard(b, p, k) {
  const [st, label] = phaseStatus(p);
  const li = el("li", `phase ${st}`);
  const head = el("div", "p-head");
  head.append(el("span", "p-num", st === "done" || st === "approved" ? "✓" : String(k + 1)),
    el("h3", null, `${p.icon ? p.icon + " " : ""}${p.name}`));
  li.append(head, el("span", `p-state ${st}`, label));
  if (st === "changes" && p.review.text) li.append(el("p", "p-note", `Pediste: ${p.review.text}`));
  const ul = el("ul", "steps");
  ul.append(...p.steps.map((s) => stepItem(s, app.plan)));
  li.append(ul);
  if (st === "waiting") li.append(reviewBox(b, p));
  if (st === "approved" && p.review.at) li.append(el("p", "p-foot", `Aprobada ${when(p.review.at)}`));
  return li;
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
  const fg = mk("ring-fg"), len = 2 * Math.PI * 18;
  fg.style.strokeDasharray = String(len);
  const set = (p) => { fg.style.strokeDashoffset = String(len * (1 - p / 100)); };
  set(prevPct.has(key) ? prevPct.get(key) : 0);
  requestAnimationFrame(() => requestAnimationFrame(() => set(pct)));
  return svg;
}

function nonstopSwitch(b) {
  const key = `ns:${b.key}`;
  const on = !!b.nonstop;
  const wrap = el("div", "nonstop");
  const sw = button("", "switch", null, "Sin paradas");
  sw.setAttribute("role", "switch");
  sw.setAttribute("aria-checked", String(on));
  sw.title = on ? "El agente sigue de una fase a la siguiente sin esperar tu revisión."
    : "Al acabar cada fase, el agente para y espera tu revisión (sin bloquear lo demás).";
  sw.append(el("span", "knob"));
  const lab = el("span", "switch-label", "Sin paradas");
  const [msg, say] = status(key);
  sw.addEventListener("click", () => run(sw, say, async () => {
    await send(`/api/plan/branches/${encodeURIComponent(b.key)}/nonstop`, { on: !on });
    toast(!on ? `«${b.name}»: sin paradas entre fases.` : `«${b.name}»: parará al acabar cada fase para que la revises.`);
  }));
  lab.addEventListener("click", () => sw.click());
  wrap.append(sw, lab, msg);
  return wrap;
}

function lane(b, i) {
  const [done, total] = count(allSteps(b));
  const key = b.key || b.name, pct = pctOf(done, total);
  const c = el("article", "lane");
  c.setAttribute("aria-label", `Rama ${b.name}`);
  paint(c, b, i);
  const head = el("header", "b-head"), t = el("div", "b-text");
  t.append(el("h2", null, b.name));
  if (b.goal) t.append(el("p", "muted", b.goal));
  const prog = el("div", "b-prog");
  prog.append(ring(key, pct), el("span", "b-count", `${done} de ${total}`));
  const side = el("div", "b-side");
  side.append(prog);
  if (!b.archived) side.append(nonstopSwitch(b));
  head.append(el("div", "b-icon", b.icon || "📌"), t, side);
  const phases = el("ol", "phases");
  phases.setAttribute("aria-label", `Fases de ${b.name}`);
  b.phases.forEach((p, k) => phases.append(phaseCard(b, p, k)));
  c.append(head, phases);
  prevPct.set(key, pct);
  return c;
}

// Rama terminada: todos sus pasos hechos y nada pendiente de revisar.
const finished = (b) => {
  const [done, total] = count(allSteps(b));
  return b.archived || (total > 0 && done === total && !b.phases.some((p) => p.review && p.review.state === "waiting"));
};

export function renderPlan(plan) {
  app.plan = plan;
  const all = plan.branches || [];
  const colorIndex = new Map(all.map((b, i) => [b, i]));
  const live = all.filter((b) => !finished(b)), old = all.filter(finished);
  const [done, total] = count(all.filter((b) => !b.archived).flatMap(allSteps));
  if (openId && !all.some((b) => allSteps(b).some((s) => s.id === openId))) openId = null;

  document.getElementById("total").hidden = !total;
  document.getElementById("total-text").textContent = `${done} de ${total} pasos · ${pctOf(done, total)}%`;
  document.getElementById("total-bar").style.width = `${pctOf(done, total)}%`;
  document.getElementById("project-sub").textContent = plan.title && plan.title !== document.getElementById("project-name").textContent ? plan.title : "";

  const y = window.scrollY;
  const ik = inboxKey(plan);
  if (ik !== lastInbox) {
    lastInbox = ik;
    renderInbox(document.getElementById("inbox"), plan, (node, b) => paint(node, b, colorIndex.get(b)));
  }
  renderDecided(document.getElementById("decided"), plan);

  const root = document.getElementById("branches");
  const nodes = [];
  if (!all.length) {
    const e = el("div", "empty");
    e.append(el("div", "big", "🌱"), el("h2", null, "Todavía no hay plan"),
      el("p", "muted", "Pídele algo a tu agente (Claude Code, Antigravity o Codex), por ejemplo «propón un plan para esto». Aparecerá aquí al momento."));
    nodes.push(e);
  }
  nodes.push(...live.map((b) => lane(b, colorIndex.get(b))));
  if (old.length) {
    const d = el("details", "archived");
    d.append(el("summary", null, `🏁 Terminadas (${old.length})`), ...old.map((b) => lane(b, colorIndex.get(b))));
    d.open = root.querySelector(".archived")?.open || false;
    nodes.push(d);
  }
  const scrolls = [...root.querySelectorAll(".lane")].map((l) => [l.getAttribute("aria-label"), l.querySelector(".phases").scrollLeft]);
  root.replaceChildren(...nodes);
  for (const [name, left] of scrolls) {
    const l = [...root.querySelectorAll(".lane")].find((x) => x.getAttribute("aria-label") === name);
    if (l && left) l.querySelector(".phases").scrollLeft = left;
  }
  window.scrollTo(0, y);
  return waitingPhases(plan).length;
}

export function resetBoard() {
  openId = null;
  lastInbox = "";
  prevState.clear();
  prevPct.clear();
}
