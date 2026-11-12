// Lo que la persona decide: revisar fases, responder preguntas y elegir entre propuestas.
// Lo que se decide aquí se guarda «sin ver»: el agente lo recibe solo la próxima vez que mire.
import { app, el, button, q, send, run, drafts, status, textarea, toast, when } from "./util.js";

const LOGICAL = 1280;                 // ancho al que se pintan las miniaturas antes de reducirlas
const editing = new Set();            // preguntas ya respondidas que se están cambiando
const SAVED = "Guardado. Tu agente lo recibirá solo.";

const branchOf = (plan, key) => (plan.branches || []).find((b) => b.key === key);
const stepOf = (plan, id) => {
  for (const b of plan.branches || []) for (const p of b.phases) for (const s of p.steps) if (s.id === id) return [b, s];
  return [null, null];
};

// ── Revisión de una fase ─────────────────────────────────────────────

export function reviewBox(b, p) {
  const key = `rev:${b.key}:${p.name}`;
  const box = el("div", "review");
  const [msg, say] = status(key);
  const approve = button("✓ Aprobar", "pill primary big", () => run(approve, say, async () => {
    await send("/api/plan/phases/review", { branch: b.key, phase: p.name, verdict: "approved", text: "" });
    toast(`Fase «${p.name}» aprobada. ${SAVED}`);
  }), `Aprobar la fase ${p.name}`);
  const ask = button("Pedir cambios", "pill big", () => {
    drafts.set(key, drafts.get(key) || "");
    form.hidden = false; row.hidden = true; ta.focus();
  }, `Pedir cambios en la fase ${p.name}`);
  const row = el("div", "act-row");
  row.append(approve, ask);

  const form = el("div", "change-form");
  const ta = textarea(key, "¿Qué quieres que cambie antes de seguir?", `Cambios que pides en la fase ${p.name}`, 3);
  const close = () => { drafts.delete(key); ta.value = ""; form.hidden = true; row.hidden = false; ask.focus(); };
  const go = button("Enviar", "pill primary", () => {
    const text = ta.value.trim();
    if (!text) { say("Escribe primero qué quieres cambiar."); ta.focus(); return; }
    run(go, say, async () => {
      await send("/api/plan/phases/review", { branch: b.key, phase: p.name, verdict: "changes", text });
      drafts.delete(key);
      toast(`Cambios pedidos en «${p.name}». ${SAVED}`);
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
  row.hidden = !form.hidden;
  box.append(row, form, msg);
  return box;
}

// ── Miniaturas y visor de propuestas ────────────────────────────────

const frameSrc = (ask, n) => q(`/propuestas/${encodeURIComponent(ask.id)}/${n}.html`);

function frame(ask, n, label) {
  const f = el("iframe");
  f.setAttribute("sandbox", "allow-scripts");   // sin allow-same-origin: no toca la página
  f.setAttribute("referrerpolicy", "no-referrer");
  f.title = `Propuesta ${n}: ${label}`;
  f.src = frameSrc(ask, n);
  return f;
}

const sizer = new ResizeObserver((entries) => {
  for (const e of entries) e.target.style.setProperty("--s", String(e.contentRect.width / LOGICAL));
});

function thumb(ask, i, plan) {
  const o = ask.options[i], n = i + 1;
  const chosen = ask.answer && ask.answer.option === n;
  const fig = el("figure", `mock${chosen ? " chosen" : ""}`);
  const box = el("div", "thumb");
  const f = frame(ask, n, o.label);
  f.tabIndex = -1;
  f.setAttribute("aria-hidden", "true");
  const zoom = button("", "thumb-zoom", () => openViewer(ask, i, plan), `Ver «${o.label}» a pantalla completa`);
  zoom.append(el("span", "zoom-hint", "⤢ Ampliar"));
  box.append(f, zoom);
  sizer.observe(box);
  const cap = el("figcaption");
  cap.append(el("span", "mock-n", String(n)), el("span", "mock-label", o.label));
  if (chosen) cap.append(el("span", "chip ok", "Elegida"));
  fig.append(box, cap);
  return fig;
}

const viewer = { ask: null, i: 0, width: 0, plan: null };

function fitViewer() {
  const stage = document.getElementById("v-stage");
  const box = stage.firstElementChild;
  if (!box) return;
  const w = viewer.width, avail = stage.clientWidth - 16, h = stage.clientHeight - 16;
  const s = Math.min(1, avail / w);
  box.style.width = `${w * s}px`;
  box.style.height = `${h}px`;
  const f = box.firstElementChild;
  f.style.width = `${w}px`;
  f.style.height = `${h / s}px`;
  f.style.transform = `scale(${s})`;
}

function showViewer() {
  const { ask, i } = viewer, o = ask.options[i];
  document.getElementById("v-title").textContent = o.label;
  document.getElementById("v-count").textContent = `${ask.title} · ${i + 1} de ${ask.options.length}`;
  const chosen = ask.answer && ask.answer.option === i + 1;
  const pick = document.getElementById("v-pick");
  pick.textContent = chosen ? "✓ Elegida" : "Elegir esta";
  pick.disabled = !!chosen;
  for (const b of document.querySelectorAll("#viewer [data-w]")) b.setAttribute("aria-pressed", String(Number(b.dataset.w) === viewer.width));
  const box = el("div", "v-frame");
  box.append(frame(ask, i + 1, o.label));
  document.getElementById("v-stage").replaceChildren(box);
  fitViewer();
}

export function openViewer(ask, i, plan) {
  Object.assign(viewer, { ask, i, plan });
  if (!viewer.width) viewer.width = window.innerWidth < 600 ? 390 : LOGICAL;  // empieza con el ancho de la pantalla
  const d = document.getElementById("viewer");
  if (!d.open) d.showModal();
  showViewer();
}

function step(delta) {
  const n = viewer.ask.options.length;
  viewer.i = (viewer.i + delta + n) % n;
  showViewer();
}

export function setupViewer() {
  const d = document.getElementById("viewer");
  document.getElementById("v-prev").addEventListener("click", () => step(-1));
  document.getElementById("v-next").addEventListener("click", () => step(1));
  document.getElementById("v-close").addEventListener("click", () => d.close());
  for (const b of d.querySelectorAll("[data-w]")) b.addEventListener("click", () => { viewer.width = Number(b.dataset.w); showViewer(); });
  const pick = document.getElementById("v-pick");
  pick.addEventListener("click", () => run(pick, toast, async () => {
    const a = viewer.ask;
    await answer(a, viewer.i + 1);
    d.close();
  }));
  d.addEventListener("keydown", (e) => {
    if (e.target.closest("textarea, input")) return;
    if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
  });
  d.addEventListener("close", () => { document.getElementById("v-stage").replaceChildren(); viewer.ask = null; });
  window.addEventListener("resize", () => { if (d.open) fitViewer(); });
}

// ── Preguntas y propuestas ───────────────────────────────────────────

async function answer(ask, option) {
  const key = `ask:${ask.id}`;
  const text = (drafts.get(key) || "").trim();
  if (option == null && !text) throw new Error("escribe primero tu respuesta");
  await send(`/api/plan/asks/${encodeURIComponent(ask.id)}/answer`, { option, text });
  drafts.delete(key);
  editing.delete(ask.id);
  const label = option ? `«${ask.options[option - 1].label}»` : "tu respuesta";
  toast(`Elegido ${label}. ${SAVED}`);
}

function context(ask, plan) {
  const parts = [];
  const [b, s] = ask.step ? stepOf(plan, ask.step) : [branchOf(plan, ask.branch), null];
  if (b) parts.push(`${b.icon || "📌"} ${b.name}`);
  if (s) parts.push(`${s.id} · ${s.title}`);
  return parts.join(" · ");
}

function chosenText(ask) {
  const a = ask.answer;
  if (!a) return "";
  return a.option ? ask.options[a.option - 1]?.label || `Opción ${a.option}` : "";
}

// Tarjeta de una pregunta o propuesta. `compact`: versión corta para el detalle de un paso.
export function askCard(ask, plan, compact = false) {
  const card = el("article", `ask ${ask.kind}${ask.answer ? " answered" : ""}`);
  if (!compact) card.id = `ask-${ask.id}`;
  const head = el("div", "ask-head");
  head.append(el("span", `chip ${ask.kind === "proposal" ? "prop" : "quest"}`, ask.kind === "proposal" ? "Propuesta" : "Pregunta"),
    el("span", "ask-id", ask.id));
  const ctx = context(ask, plan);
  if (ctx) head.append(el("span", "ask-ctx", ctx));
  card.append(head, el(compact ? "h4" : "h3", "ask-title", ask.title));
  if (ask.text) card.append(el("p", "ask-text", ask.text));

  if (ask.answer && !editing.has(ask.id)) {
    const done = el("div", "answer");
    const pick = chosenText(ask);
    if (pick) done.append(el("p", "answer-pick", `✓ Elegiste «${pick}»`));
    if (ask.answer.text) done.append(el("p", "answer-text", pick ? `Comentario: ${ask.answer.text}` : `Respondiste: ${ask.answer.text}`));
    done.append(el("p", "muted small", `${ask.answer.seen ? "Tu agente ya lo ha visto" : "Tu agente aún no lo ha visto"} · ${when(ask.answer.at)}`));
    const row = el("div", "act-row");
    if (ask.kind === "proposal" && ask.options.length)
      row.append(button("Ver las propuestas", "pill", () => openViewer(ask, Math.max(0, (ask.answer.option || 1) - 1), plan)));
    row.append(button("Cambiar mi respuesta", "pill", () => {
      editing.add(ask.id);
      app.rerender();
      const again = document.getElementById(`ask-${ask.id}`);
      if (again) { again.scrollIntoView({ block: "center" }); again.querySelector("button")?.focus({ preventScroll: true }); }
    }));
    done.append(row);
    card.append(done);
    return card;
  }

  const key = `ask:${ask.id}`;
  const [msg, say] = status(key);
  const opts = ask.options || [];
  if (ask.kind === "proposal" && opts.length) {
    const gal = el("div", "gallery");
    opts.forEach((o, i) => {
      const fig = thumb(ask, i, plan);
      const b = button(`Elegir «${o.label}»`, "pill primary choose", null);
      b.addEventListener("click", () => run(b, say, () => answer(ask, i + 1)));
      fig.append(b);
      gal.append(fig);
    });
    card.append(gal);
  } else if (opts.length) {
    const list = el("div", "choices");
    list.setAttribute("role", "group");
    list.setAttribute("aria-label", "Opciones");
    opts.forEach((o, i) => {
      const b = button(o.label, "choice", null);
      b.prepend(el("span", "choice-n", String(i + 1)));
      if (ask.answer && ask.answer.option === i + 1) b.setAttribute("aria-pressed", "true");
      b.addEventListener("click", () => run(b, say, () => answer(ask, i + 1)));
      list.append(b);
    });
    card.append(list);
  }
  const ta = textarea(key, opts.length ? "Comentario (opcional): se envía con lo que elijas" : "Escribe tu respuesta",
    opts.length ? `Comentario para ${ask.id}` : `Respuesta a ${ask.id}`, opts.length ? 2 : 3);
  const row = el("div", "act-row");
  const free = button(opts.length ? "Ninguna: enviar solo el comentario" : "Enviar", opts.length ? "pill" : "pill primary", null);
  free.addEventListener("click", () => run(free, say, () => answer(ask, null)));
  row.append(free);
  if (editing.has(ask.id)) row.append(button("Cancelar", "pill", () => { editing.delete(ask.id); app.rerender(); }));
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); free.click(); } });
  card.append(ta, row, msg);
  return card;
}

// ── Bandeja «Te toca» ────────────────────────────────────────────────

export function waitingPhases(plan) {
  const out = [];
  for (const b of plan.branches || []) if (!b.archived) for (const p of b.phases) if (p.review && p.review.state === "waiting") out.push([b, p]);
  return out;
}
export const openAsks = (plan) => (plan.asks || []).filter((a) => !a.answer || editing.has(a.id));

function reviewCard(b, p) {
  const c = el("article", "todo-review");
  const head = el("div", "ask-head");
  head.append(el("span", "chip wait", "Revisar fase"), el("span", "ask-ctx", `${b.icon || "📌"} ${b.name}`));
  const [done, total] = [p.steps.filter((s) => s.state === "done").length, p.steps.length];
  const ul = el("ul", "mini-steps");
  for (const s of p.steps) ul.append(el("li", s.state === "done" ? "done" : "", `${s.state === "done" ? "✓" : "·"} ${s.title}`));
  c.append(head, el("h3", "ask-title", `«${p.name}» está lista: ${done} de ${total} pasos`),
    el("p", "ask-text", "Tu agente ha parado aquí. Dale el visto bueno o dile qué cambiar."), ul, reviewBox(b, p));
  return c;
}

// Firma de lo que hay en la bandeja: si no cambia, no se repinta (las miniaturas no se recargan).
export function inboxKey(plan) {
  return JSON.stringify([waitingPhases(plan).map(([b, p]) => [b.key, p.name, p.steps.map((s) => s.state)]),
    openAsks(plan).map((a) => [a.id, a.title, a.text, a.options, a.answer]), app.pid]);
}

export function renderInbox(root, plan, colorOf) {
  const phases = waitingPhases(plan), asks = openAsks(plan);
  const n = phases.length + asks.length;
  root.hidden = !n;
  if (!n) { root.replaceChildren(); return; }
  const head = el("div", "inbox-head");
  head.append(el("h2", null, "Te toca"), el("span", "count", String(n)),
    el("p", "muted", "Nada se bloquea: tu agente sigue con lo demás y recibe tu respuesta solo."));
  const list = el("div", "inbox-list");
  for (const [b, p] of phases) {
    const c = reviewCard(b, p);
    colorOf(c, b);
    list.append(c);
  }
  for (const a of asks) list.append(askCard(a, plan));
  root.replaceChildren(head, list);
}

// Decisiones ya tomadas (para verlas o cambiarlas).
export function renderDecided(root, plan) {
  const done = (plan.asks || []).filter((a) => a.answer && !editing.has(a.id));
  root.hidden = !done.length;
  if (!done.length) { root.replaceChildren(); return; }
  const wasOpen = root.querySelector("details")?.open || false;
  const d = el("details", "decided");
  d.open = wasOpen;
  d.append(el("summary", null, `Decisiones tomadas (${done.length})`));
  const list = el("div", "decided-list");
  for (const a of done.slice().reverse()) list.append(askCard(a, plan, true));
  d.append(list);
  root.replaceChildren(d);
}
