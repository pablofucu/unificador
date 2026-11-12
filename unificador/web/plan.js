// El lienzo de un proyecto: una línea por rama (placa, nombre, progreso) y, en ella, un andén por fase con sus pasos.
// Las vías y los enlaces entre fases se dibujan en una capa SVG sobre el lienzo; el zoom y el desplazamiento son del lienzo.
// Por debajo de 760 px no hay zoom ni vías: las líneas y los andenes se apilan.
import { app, el, button, send, run, drafts, status, textarea, toast, when, reduce, allSteps, count, pctOf, paint } from "./util.js";
import { reviewBox, askCard, renderInbox, renderDecided, inboxKey, waitingPhases, openAsks } from "./decide.js";
import { icon, CATS } from "./icons.js";
import { auditFor, auditChip } from "./audit.js";

const STATE = { pending: "Pendiente", doing: "En curso", done: "Hecho" };
const KIND = { start: "Empezó", done: "Terminó", reopen: "Reabrió", change: "Pidió un cambio", note: "Nota" };
const NS = "http://www.w3.org/2000/svg";
const ST = { approved: "d", done: "d", waiting: "r", changes: "w", doing: "w", pending: "p" };
const ZMIN = 0.3, ZMAX = 1.6;

let openId = null;             // paso con el detalle abierto (sobrevive a los repintados)
const prevState = new Map();   // id de paso -> último estado pintado (para resaltar cambios)
const prevPct = new Map();     // rama -> último % pintado
let lastInbox = "";
let filter = null;             // categoría activa (null = todas)
let showDone = false;          // ramas terminadas desplegadas
let zoom = 1;
let zoomPid = undefined;       // proyecto cuyo zoom está cargado
const narrow = () => window.matchMedia("(max-width: 760px)").matches;
const $ = (id) => document.getElementById(id);

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

const phaseKey = (b, p) => `${b.key || b.name}/${p.name}`;

function ibtn(name, text, cls, fn, label) {
  const b = button("", cls, fn, label);
  b.append(icon(name), el("span", null, text));
  return b;
}

// ── Detalle y acciones de un paso ────────────────────────────────────

function section(title, ...kids) {
  const d = el("div", "d-sec");
  d.append(el("h5", null, title), ...kids);
  return d;
}

function actions(s) {
  const key = `step:${s.id}`;
  const box = el("div", "actions");
  const [msg, say] = status(key);
  const ask = ibtn("edit", "Pedir un cambio", "pill", () => {
    drafts.set(key, drafts.get(key) || ""); say("");
    form.hidden = false; ask.hidden = true; ta.focus();
  }, `Pedir un cambio en el paso ${s.title}`);
  const target = s.state === "done" ? "pending" : "done";
  const mark = ibtn(s.state === "done" ? "left" : "check", s.state === "done" ? "Reabrir" : "Marcar hecho", "pill",
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
  if (s.change) {
    const c = el("div", "change-box");
    c.append(icon("edit"), el("span", null, `Corrección pedida: ${s.change}`));
    d.append(c);
  }
  if (s.desc) d.append(section("Qué hay que hacer", el("p", null, s.desc)));
  if (s.result) d.append(section("Cómo quedó", el("p", null, s.result)));
  const answered = (plan.asks || []).filter((a) => a.step === s.id && a.answer);
  if (answered.length) {
    const box = el("div", "d-asks");
    for (const a of answered) box.append(askCard(a, plan, true));
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

// ── Un paso, con sus preguntas debajo ────────────────────────────────

function stepItem(s, plan) {
  const known = prevState.get(s.id);
  const asks = (plan.asks || []).filter((a) => a.step === s.id);
  const waiting = asks.some((a) => !a.answer);
  const state = STATE[s.state] ? s.state : "pending";
  const li = el("li", `step ${state}${s.change ? " changed" : ""}${waiting && state !== "done" ? " asking" : ""}${s.id === openId ? " open" : ""}`);
  li.dataset.id = s.id;
  const row = el("div", "srow");
  const cat = CATS[s.cat] ? s.cat : null;
  if (cat) { row.dataset.cat = cat; row.style.setProperty("--k", CATS[cat].color); }

  const btn = el("button", "s-btn");
  btn.type = "button";
  btn.setAttribute("aria-expanded", String(s.id === openId));
  const label = `${s.title}. ${STATE[state]}${s.change ? ", pide cambios" : ""}${waiting ? ", te pregunta" : ""}`;
  btn.setAttribute("aria-label", label);
  btn.title = `${s.id} · ${STATE[state]}${cat ? " · " + CATS[cat].name : ""}`;
  const bx = el("span", "bx");
  if (s.change) bx.append(icon("edit"));
  else if (waiting && state !== "done") bx.append(icon("ask"));
  else if (state === "done") bx.append(icon("check"));
  btn.append(bx, el("span", "tt", s.title));
  if (cat) { const ci = el("span", "ci"); ci.append(icon(cat)); btn.append(ci); }
  btn.addEventListener("click", () => {
    openId = openId === s.id ? null : s.id;
    app.rerender();
    const again = [...document.querySelectorAll("#branches .step")].find((x) => x.dataset.id === s.id);
    again?.querySelector(".s-btn").focus({ preventScroll: true });
  });
  row.append(btn);
  const chip = auditChip(auditFor(plan, s.id));
  if (chip) row.append(chip);
  li.append(row);
  for (const a of asks) if (!a.answer) li.append(askCard(a, plan, true));
  if (s.id === openId) li.append(detail(s, plan));
  if (known && known !== s.state && !reduce()) { li.classList.add("flash"); setTimeout(() => li.classList.remove("flash"), 1600); }
  prevState.set(s.id, s.state);
  return li;
}

// Los pasos con `together` van a la vez que el anterior: se agrupan en un bloque.
function groupSteps(steps) {
  const groups = [];
  for (const s of steps) {
    if (s.together && groups.length) groups[groups.length - 1].push(s);
    else groups.push([s]);
  }
  return groups;
}

// ── Un andén (fase) ──────────────────────────────────────────────────

function dependencies(plan, p) {
  return (p.after || []).map((a) => {
    const tb = (plan.branches || []).find((x) => (x.key || x.name) === a.branch);
    const tp = tb && tb.phases.find((x) => x.name === a.phase);
    return tp ? { b: tb, p: tp, ok: ["approved", "done"].includes(phaseStatus(tp)[0]) } : null;
  }).filter(Boolean);
}

function mix(steps) {
  const m = el("div", "mix");
  m.setAttribute("aria-hidden", "true");
  for (const c in CATS) {
    const n = steps.filter((s) => s.cat === c).length;
    if (n) { const i = el("i"); i.style.setProperty("--k", CATS[c].color); i.style.flex = String(n); m.append(i); }
  }
  return m;
}

function platform(plan, b, p, k) {
  const [status, label] = phaseStatus(p);
  const st = ST[status];
  const deps = dependencies(plan, p), blocked = deps.filter((d) => !d.ok);
  const card = el("li", `pc st-${st}${blocked.length ? " waits" : ""}`);
  card.dataset.ph = phaseKey(b, p);
  card.dataset.node = st;
  if (deps.length) card.dataset.after = JSON.stringify(deps.map((d) => phaseKey(d.b, d.p)));

  const head = el("div", "pch");
  const nb = el("span", "nb");
  if (status === "approved" || status === "done") nb.append(icon("check")); else nb.textContent = String(k + 1);
  const name = el("span", "pcn");
  name.append(el("small", null, `Fase ${k + 1}`), el("span", null, p.name));
  head.append(nb, name);
  if (status === "approved") { const t = el("span", "ok-tag"); t.append(icon("check"), "Aprobada"); head.append(t); }
  else if (status !== "doing" && status !== "pending") head.append(el("span", "ok-tag", status === "done" ? "Hecha" : label));
  const chip = auditChip(auditFor(plan, phaseKey(b, p)));
  if (chip) head.append(chip);
  card.append(head);

  for (const d of blocked) {
    const l = el("div", "lock");
    l.append(icon("lock"), el("span", null, `Espera a «${d.p.name}» de ${d.b.key || d.b.name}`));
    card.append(l);
  }
  if (status === "changes" && p.review.text) card.append(el("p", "p-note", `Pediste: ${p.review.text}`));

  const body = el("ul", "pcb");
  body.setAttribute("aria-label", `Pasos de ${p.name}`);
  for (const g of groupSteps(p.steps)) {
    if (g.length === 1) { body.append(stepItem(g[0], plan)); continue; }
    const li = el("li", "pg-wrap"), pg = el("ul", "pg");
    pg.setAttribute("aria-label", "A la vez");
    pg.append(...g.map((s) => stepItem(s, plan)));
    li.append(el("span", "parcap", "A la vez"), pg);
    body.append(li);
  }
  card.append(body);

  if (status === "waiting") {
    const gate = el("div", "gate");
    gate.append(el("p", null, "Fase terminada. El agente se ha parado a esperarte."), reviewBox(b, p));
    card.append(gate);
  }
  const [done, total] = count(p.steps);
  const foot = el("div", "pcf");
  foot.append(mix(p.steps), el("span", null, `${done} de ${total}${status === "approved" && p.review.at ? ` · ${when(p.review.at)}` : ""}`));
  card.append(foot);
  return card;
}

// ── Una línea (rama) ─────────────────────────────────────────────────

function nonstopSwitch(b) {
  const key = `ns:${b.key}`;
  const on = !!b.nonstop;
  const wrap = el("div", "nonstop");
  const sw = button("", "switch", null, `Sin paradas en ${b.name}`);
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

const finished = (b) => {
  const [done, total] = count(allSteps(b));
  return b.archived || (total > 0 && done === total && !b.phases.some((p) => p.review && p.review.state === "waiting"));
};

function line(plan, b, i) {
  const [done, total] = count(allSteps(b));
  const key = b.key || b.name, pct = pctOf(done, total);
  const row = el("section", "row");
  row.dataset.br = key;
  row.setAttribute("aria-label", `Rama ${b.name}`);
  paint(row, b, i);

  const head = el("div", "head");
  if (b.goal) head.title = b.goal;
  head.append(el("span", "code", key), el("b", null, b.name), el("small", null, `${done} de ${total} pasos`));
  const bar = el("span", "hbar"), fill = el("i");
  fill.style.width = `${prevPct.has(key) ? prevPct.get(key) : 0}%`;
  bar.append(fill);
  requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = `${pct}%`; }));
  head.append(bar);
  if (!b.archived) head.append(nonstopSwitch(b));

  const phases = el("ol", "phases");
  phases.setAttribute("aria-label", `Fases de ${b.name}`);
  b.phases.forEach((p, k) => phases.append(platform(plan, b, p, k)));

  const end = el("div", `end${finished(b) ? " ok" : ""}`);
  end.dataset.node = finished(b) ? "d" : "p";
  end.setAttribute("role", "img");
  end.setAttribute("aria-label", finished(b) ? "Rama terminada" : "Fin de la rama");
  end.append(icon("flag"));
  row.append(head, phases, end);
  prevPct.set(key, pct);
  return row;
}

// ── Capa de vías y enlaces ───────────────────────────────────────────

const svgEl = (tag, attrs) => {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, String(attrs[k]));
  return n;
};

function rect(box, e) {
  const w = box.getBoundingClientRect(), r = e.getBoundingClientRect();
  const l = (r.left - w.left) / zoom, t = (r.top - w.top) / zoom, W = r.width / zoom, H = r.height / zoom;
  return { l, t, r: l + W, b: t + H, cx: l + W / 2, cy: t + H / 2 };
}
const hlink = (a, b) => { const m = (a.r + b.l) / 2; return `M${a.r - 3},${a.cy}C${m},${a.cy} ${m},${b.cy} ${b.l + 3},${b.cy}`; };

// Las fases que dependen de otra se empujan a la derecha de su origen, para que el enlace no vaya hacia atrás.
function alignDeps(box) {
  const dep = [...box.querySelectorAll("[data-after]")];
  for (const to of dep) to.style.marginLeft = "";
  if (narrow()) return;
  for (let pass = 0; pass < 2; pass++) {
    for (const to of dep) {
      let need = 0;
      for (const k of JSON.parse(to.dataset.after)) {
        const from = box.querySelector(`[data-ph="${CSS.escape(k)}"]`);
        if (from && from.closest(".row") !== to.closest(".row")) need = Math.max(need, rect(box, from).r + 54 - rect(box, to).l + (parseFloat(to.style.marginLeft) || 0));
      }
      to.style.marginLeft = need > 0 ? `${Math.round(need)}px` : "";
    }
  }
}

function drawLayer(box) {
  box.querySelector("svg.layer")?.remove();
  if (narrow()) return;
  const svg = svgEl("svg", { class: "layer", width: box.offsetWidth, height: box.offsetHeight, "aria-hidden": "true" });
  for (const row of box.querySelectorAll(".row")) {
    const c = getComputedStyle(row).getPropertyValue("--accent").trim() || "#7c5cff";
    const nodes = [row.querySelector(".head"), ...row.querySelectorAll(".pc"), row.querySelector(".end")];
    for (let i = 1; i < nodes.length; i++) {
      const a = nodes[i - 1], b = nodes[i];
      const hold = a.dataset.node === "r", on = !hold && (b.dataset.node || "p") !== "p";
      svg.append(svgEl("path", { class: `rail${on ? " on" : ""}${hold ? " hold" : ""}`, stroke: hold ? "#8b5cf6" : c, d: hlink(rect(box, a), rect(box, b)) }));
    }
  }
  for (const to of box.querySelectorAll("[data-after]")) {
    for (const k of JSON.parse(to.dataset.after)) {
      const from = box.querySelector(`[data-ph="${CSS.escape(k)}"]`);
      if (!from) continue;
      const a = rect(box, from), b = rect(box, to), c = getComputedStyle(from.closest(".row")).getPropertyValue("--accent").trim() || "#7c5cff";
      const met = !to.classList.contains("waits");
      let d, p1, p2;
      if (b.l >= a.r + 20 && Math.abs(b.cy - a.cy) < 40) { d = hlink(a, b); p1 = [a.r, a.cy]; p2 = [b.l, b.cy]; }
      else {
        const down = b.t > a.t, x1 = a.r - 36, y1 = down ? a.b : a.t, x2 = b.l + 36, y2 = down ? b.t : b.b, m = (y1 + y2) / 2;
        d = `M${x1},${y1}C${x1},${m} ${x2},${m} ${x2},${y2}`; p1 = [x1, y1]; p2 = [x2, y2];
      }
      svg.append(svgEl("path", { class: "dep0", d }), svgEl("path", { class: `dep${met ? " met" : ""}`, stroke: c, d }));
      for (const [x, y] of [p1, p2]) svg.append(svgEl("rect", { class: "dep-end", x: x - 8, y: y - 8, width: 16, height: 16, rx: 5, stroke: c }));
    }
  }
  box.append(svg);
}

// ── Zoom y desplazamiento ────────────────────────────────────────────

const zkey = () => `unificador:zoom:${app.pid || "-"}`;
function loadZoom() {
  try { const v = parseFloat(localStorage.getItem(zkey())); zoom = v >= ZMIN && v <= ZMAX ? v : 1; } catch { zoom = 1; }
}
function saveZoom() { try { localStorage.setItem(zkey(), String(Math.round(zoom * 100) / 100)); } catch { /* sin almacenamiento */ } }

function layout() {
  const box = $("branches"), sizer = $("sizer");
  if (!box || !sizer || $("board").hidden) return;
  const z = narrow() ? 1 : zoom;
  alignDeps(box);
  box.style.transform = z === 1 ? "" : `scale(${z})`;
  sizer.style.width = narrow() ? "" : `${Math.ceil(box.offsetWidth * z)}px`;
  sizer.style.height = narrow() ? "" : `${Math.ceil(box.offsetHeight * z)}px`;
  drawLayer(box);
  const lab = $("z-label");
  if (lab) lab.textContent = `${Math.round(z * 100)}%`;
  document.querySelector(".zoom")?.toggleAttribute("hidden", narrow());
}

function setZoom(z, cx, cy) {
  const root = $("canvas"), old = zoom;
  zoom = Math.min(ZMAX, Math.max(ZMIN, z));
  const r = root.getBoundingClientRect();
  const px = cx == null ? r.width / 2 : cx - r.left, py = cy == null ? r.height / 2 : cy - r.top;
  const x = (root.scrollLeft + px) * (zoom / old) - px, y = (root.scrollTop + py) * (zoom / old) - py;
  layout();
  root.scrollLeft = x; root.scrollTop = y;
  saveZoom();
}

function fit() {
  const root = $("canvas"), box = $("branches");
  const z = Math.min(1, (root.clientWidth - 8) / box.offsetWidth, (root.clientHeight - 8) / box.offsetHeight);
  setZoom(z);
  root.scrollTo(0, 0);
}

function enablePan(root) {
  let d = null, moved = false;
  const skip = "button, a, textarea, input, select, summary, details, .pc, .head, .end";
  root.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "mouse" || e.button !== 0 || e.target.closest(skip)) return;
    d = { x: e.clientX, y: e.clientY, l: root.scrollLeft, t: root.scrollTop }; moved = false;
  });
  window.addEventListener("pointermove", (e) => {
    if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (!moved && Math.hypot(dx, dy) < 5) return;
    moved = true; root.classList.add("drag"); root.scrollLeft = d.l - dx; root.scrollTop = d.t - dy;
  });
  window.addEventListener("pointerup", () => { d = null; root.classList.remove("drag"); });
}

// ── Filtro por categoría, bandeja de decisiones y arranque ───────────

function applyFilter() {
  document.querySelectorAll("#branches [data-cat]").forEach((e) => e.classList.toggle("dim", !!filter && e.dataset.cat !== filter));
  document.querySelectorAll("#legend .chip-cat").forEach((e) => {
    const on = (e.dataset.c || null) === filter;
    e.classList.toggle("on", on);
    e.setAttribute("aria-pressed", String(on));
  });
}

let drawerFrom = null;
function drawer(open) {
  const d = $("drawer"), scrim = $("scrim");
  if (open === !d.hidden) return;
  d.hidden = !open; scrim.hidden = !open;
  $("decb").setAttribute("aria-expanded", String(open));
  if (open) { drawerFrom = document.activeElement; $("drawer-close").focus(); }
  else { const f = drawerFrom; drawerFrom = null; (f && f.isConnected ? f : $("decb")).focus?.(); }
}

export function initBoard() {
  const legend = $("legend");
  const mk = (key, text, ic) => {
    const b = el("button", "chip-cat");
    b.type = "button";
    b.dataset.c = key;
    if (key) b.style.setProperty("--k", CATS[key].color);
    if (ic) b.append(icon(ic));
    b.append(el("span", null, text));
    b.addEventListener("click", () => { filter = key || null; applyFilter(); });
    return b;
  };
  legend.replaceChildren(mk("", "Todas"), ...Object.keys(CATS).map((c) => mk(c, CATS[c].name, c)));
  applyFilter();

  for (const [id, name, fn] of [["z-out", "zoomout", () => setZoom(zoom / 1.2)], ["z-in", "zoomin", () => setZoom(zoom * 1.2)], ["z-fit", "fit", fit]]) {
    const b = $(id); b.prepend(icon(name)); b.addEventListener("click", fn);
  }
  $("drawer-close").append(icon("x"));
  $("drawer-close").addEventListener("click", () => drawer(false));
  $("scrim").addEventListener("click", () => drawer(false));
  $("decb").addEventListener("click", () => drawer($("drawer").hidden));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !$("drawer").hidden && !document.querySelector("dialog[open]")) { e.preventDefault(); drawer(false); }
  });

  const root = $("canvas");
  root.addEventListener("wheel", (e) => {
    if (!e.ctrlKey || narrow()) return;
    e.preventDefault();
    setZoom(zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1), e.clientX, e.clientY);
  }, { passive: false });
  root.addEventListener("keydown", (e) => {
    if (e.target !== root || narrow() || e.ctrlKey || e.metaKey) return;
    if (e.key === "+" || e.key === "=") setZoom(zoom * 1.2);
    else if (e.key === "-") setZoom(zoom / 1.2);
    else if (e.key === "0") fit();
  });
  enablePan(root);
  new ResizeObserver(() => layout()).observe($("branches"));
  window.addEventListener("resize", layout);
  document.fonts?.ready.then(layout);
}

// ── Pintar el plan ───────────────────────────────────────────────────

export function renderPlan(plan) {
  app.plan = plan;
  if (zoomPid !== app.pid) { zoomPid = app.pid; loadZoom(); }
  const all = plan.branches || [];
  const colorIndex = new Map(all.map((b, i) => [b, i]));
  const live = all.filter((b) => !finished(b)), old = all.filter(finished);
  const [done, total] = count(all.filter((b) => !b.archived).flatMap(allSteps));
  if (openId && !all.some((b) => allSteps(b).some((s) => s.id === openId))) openId = null;

  $("total").hidden = !total;
  $("total-text").textContent = `${done} de ${total} pasos · ${pctOf(done, total)}%`;
  $("total-bar").style.width = `${pctOf(done, total)}%`;
  $("project-sub").textContent = plan.title && plan.title !== $("project-name").textContent ? plan.title : "";

  // Decisiones: preguntas abiertas y fases esperando revisión.
  const n = openAsks(plan).length + waitingPhases(plan).length;
  const decb = $("decb");
  decb.classList.toggle("zero", !n);
  decb.setAttribute("aria-label", n ? `Decisiones: ${n} esperan` : "Decisiones: nada pendiente");
  const cnt = el("span", "n", String(n));
  decb.replaceChildren(icon("inbox"), el("span", "decb-t", "Decisiones"), cnt);
  const ik = inboxKey(plan);
  if (ik !== lastInbox) {
    lastInbox = ik;
    renderInbox($("inbox"), plan, (node, b) => paint(node, b, colorIndex.get(b)));
  }
  $("drawer-empty").hidden = n > 0;
  renderDecided($("decided"), plan);

  const root = $("canvas"), sx = root.scrollLeft, sy = root.scrollTop, y = window.scrollY;
  const box = $("branches");
  const nodes = [];
  if (!all.length) {
    const e = el("div", "empty");
    const big = el("div", "big");
    big.append(icon("sprout"));
    e.append(big, el("h2", null, "Todavía no hay plan"),
      el("p", "muted", "Pídele algo a tu agente (Claude Code, Antigravity o Codex), por ejemplo «propón un plan para esto». Aparecerá aquí al momento."));
    nodes.push(e);
  }
  const shown = live.length ? (showDone ? [...live, ...old] : live) : old;
  nodes.push(...shown.map((b) => line(plan, b, colorIndex.get(b))));
  if (live.length && old.length) {
    const bar = el("div", "donebar");
    const t = ibtn(showDone ? "down" : "flag", showDone ? "Ocultar terminadas" : `${old.length} ${old.length === 1 ? "rama terminada" : "ramas terminadas"}`, "t",
      () => { showDone = !showDone; app.rerender(); }, showDone ? "Ocultar las ramas terminadas" : "Mostrar las ramas terminadas");
    t.setAttribute("aria-expanded", String(showDone));
    bar.append(t);
    nodes.push(bar);
  }
  box.replaceChildren(...nodes);
  layout();
  applyFilter();
  root.scrollLeft = sx; root.scrollTop = sy;
  window.scrollTo(0, y);
  return waitingPhases(plan).length;
}

export function resetBoard() {
  openId = null;
  lastInbox = "";
  showDone = false;
  filter = null;
  prevState.clear();
  prevPct.clear();
  zoomPid = undefined;
  if ($("drawer") && !$("drawer").hidden) drawer(false);
  const c = $("canvas");
  if (c) { c.scrollLeft = 0; c.scrollTop = 0; }
}
