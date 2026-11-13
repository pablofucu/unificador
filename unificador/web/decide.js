// Lo que la persona decide: revisar fases, responder preguntas y elegir entre propuestas.
// Lo que se decide aquí se guarda «sin ver»: el agente lo recibe solo la próxima vez que mire.
import { app, el, button, q, send, run, drafts, status, textarea, toast, when } from "./util.js";
import { icon } from "./icons.js";
import { auditFor, auditChip } from "./audit.js";

const LOGICAL = 1280;                 // ancho al que se pintan las miniaturas antes de reducirlas
const editing = new Set();            // preguntas ya respondidas que se están cambiando
const SAVED = "Guardado. Tu agente lo recibirá solo.";

const branchOf = (plan, key) => (plan.branches || []).find((b) => b.key === key);
const stepOf = (plan, id) => {
  for (const b of plan.branches || []) for (const p of b.phases) for (const s of p.steps) if (s.id === id) return [b, s];
  return [null, null];
};

// ── Markdown ligero ──────────────────────────────────────────────────
// Solo párrafos, **negrita**, *cursiva*, `código` y listas con "- ". Todo con createElement/textContent:
// el texto lo escribe el agente y nunca se interpreta como HTML. Lo que no encaja sale literal.

const INLINE = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g;

function inline(parent, text) {
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) parent.append(text.slice(last, m.index));
    if (m[1] != null) parent.append(el("code", null, m[1]));
    else if (m[2] != null) parent.append(el("strong", null, m[2]));
    else parent.append(el("em", null, m[3]));
    last = m.index + m[0].length;
  }
  if (last < text.length) parent.append(text.slice(last));
}

// mdLite(text: string) -> DocumentFragment
export function mdLite(text) {
  const frag = document.createDocumentFragment();
  for (const block of String(text || "").replace(/\r\n?/g, "\n").split(/\n[ \t]*\n/)) {
    let para = null, list = null;
    for (const line of block.split("\n")) {
      if (!line.trim()) continue;
      const li = /^\s*- (.*)$/.exec(line);
      if (li) {
        para = null;
        if (!list) { list = el("ul"); frag.append(list); }
        const item = el("li");
        inline(item, li[1]);
        list.append(item);
      } else {
        list = null;
        if (!para) { para = el("p"); frag.append(para); }
        else para.append(el("br"));
        inline(para, line.trim());
      }
    }
  }
  return frag;
}

// ── Revisión de una fase ─────────────────────────────────────────────

export function reviewBox(b, p) {
  const key = `rev:${b.key}:${p.name}`;
  const box = el("div", "review");
  const [msg, say] = status(key);
  const approve = button("Aprobar", "pill primary big", () => run(approve, say, async () => {
    await send("/api/plan/phases/review", { branch: b.key, phase: p.name, verdict: "approved", text: "" });
    toast(`Fase «${p.name}» aprobada. ${SAVED}`);
  }), `Aprobar la fase ${p.name}`);
  const ask = button("Pedir cambios", "pill big", () => {
    drafts.set(key, drafts.get(key) || "");
    form.hidden = false; row.hidden = true; ta.focus();
  }, `Pedir cambios en la fase ${p.name}`);
  approve.prepend(icon("check"));
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

const recommended = (ask, n) => ask.recommend === n;
function recBadge() {
  const b = el("span", "rec-badge");
  b.append(icon("star"), "Recomendada");
  return b;
}

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
  const fig = el("figure", `mock${chosen ? " chosen" : ""}${recommended(ask, n) ? " rec" : ""}`);
  const box = el("div", "thumb");
  const f = frame(ask, n, o.label);
  f.tabIndex = -1;
  f.setAttribute("aria-hidden", "true");
  const zoom = button("", "thumb-zoom", () => openViewer(ask, i, plan), `Ver «${o.label}» a pantalla completa`);
  const hint = el("span", "zoom-hint");
  hint.append(icon("eye"), "Ver");
  zoom.append(hint);
  box.append(f, zoom);
  sizer.observe(box);
  const cap = el("figcaption");
  cap.append(el("span", "mock-n", String(n)), el("span", "mock-label", o.label));
  if (chosen) { const c = el("span", "chip ok"); c.append(icon("check"), "Elegida"); cap.append(c); }
  fig.append(box, cap);
  if (recommended(ask, n)) fig.append(recBadge());
  if (o.desc) fig.append(el("p", "opt-desc", o.desc));
  return fig;
}

const viewer = { ask: null, i: 0, j: 1, width: 0, plan: null, mode: "one", active: 0, sel: [0, 1], pos: { x: 0, y: 0 }, frames: [], setSel: null };
const MODES = ["one", "side", "slider"];
const MODE_KEY = "unificador.viewer.mode";
const savedMode = () => { try { const m = localStorage.getItem(MODE_KEY); return MODES.includes(m) ? m : "one"; } catch { return "one"; } };
const saveMode = (m) => { try { localStorage.setItem(MODE_KEY, m); } catch { /* sin almacenamiento: se olvida */ } };

// Ajusta el iframe (o los dos, en el deslizador) de `body` a su ancho: ancho lógico = viewer.width, escalado si no cabe.
function fitBody(body, pad) {
  const box = body && body.firstElementChild;
  if (!box) return;
  const w = viewer.width, avail = body.clientWidth - pad, h = body.clientHeight - pad;
  const s = Math.min(1, avail / w);
  box.style.width = `${w * s}px`;
  box.style.height = `${h}px`;
  for (const f of box.querySelectorAll("iframe")) {
    f.style.width = `${w}px`;
    f.style.height = `${h / s}px`;
    f.style.transform = `scale(${s})`;
  }
}

function fitViewer() {
  if (viewer.mode === "one") fitBody(document.getElementById("v-stage"), 16);
  else for (const b of document.querySelectorAll("#v-stage .v-body")) fitBody(b, 0);
}

// Scroll sincronizado: cada propuesta (script inyectado por el servidor) avisa por postMessage y aquí se reenvía a las demás.
function post(f, msg) { try { if (f.contentWindow) f.contentWindow.postMessage(msg, "*"); } catch { /* aún sin cargar */ } }
window.addEventListener("message", (e) => {
  const d = e.data;
  if (!d || d.uni !== "scroll" || viewer.frames.length < 2) return;
  const from = viewer.frames.find((f) => f.contentWindow === e.source);
  if (!from) return;
  viewer.pos = { x: Number(d.x) || 0, y: Number(d.y) || 0 };
  for (const f of viewer.frames) if (f !== from) post(f, { uni: "scrollTo", ...viewer.pos });
});

// Marco de una opción en comparación: recuerda el scroll y lo repone al cargar.
function viewFrame(ask, idx) {
  const f = frame(ask, idx + 1, ask.options[idx].label);
  viewer.frames.push(f);
  f.addEventListener("load", () => post(f, { uni: "scrollTo", ...viewer.pos }));
  return f;
}

const optText = (ask, k) => `${recommended(ask, k + 1) ? "★ " : ""}${k + 1} · ${ask.options[k].label}`;

function renderCompare() {
  const { ask } = viewer, stage = document.getElementById("v-stage");
  const slider = viewer.mode === "slider";
  viewer.sel = [viewer.i, viewer.j];
  const bodies = [], selects = [], picks = [];

  const mount = () => {
    viewer.frames = [];
    if (slider) {
      const box = el("div", "v-frame v-slide");
      box.style.setProperty("--x", "50%");
      const under = viewFrame(ask, viewer.sel[0]);
      const over = viewFrame(ask, viewer.sel[1]);
      over.classList.add("v-over");
      const handle = el("div", "v-handle");
      handle.setAttribute("aria-hidden", "true");
      handle.append(el("span", "v-grip", "‹›"));
      const range = el("input", "v-range");
      range.type = "range"; range.min = "0"; range.max = "100"; range.value = "50";
      range.setAttribute("aria-label", "Deslizador de comparación: cuánto se ve de cada propuesta");
      range.addEventListener("input", () => box.style.setProperty("--x", `${range.value}%`));
      box.addEventListener("wheel", (e) => { e.preventDefault(); post(under, { uni: "scrollBy", dy: e.deltaY }); }, { passive: false });
      box.append(under, over, handle, range);
      bodies[0].replaceChildren(box);
    } else {
      for (const k of [0, 1]) {
        const box = el("div", "v-frame");
        box.append(viewFrame(ask, viewer.sel[k]));
        bodies[k].replaceChildren(box);
      }
    }
    fitViewer();
  };
  const refresh = () => {
    selects.forEach((s, k) => { s.value = String(viewer.sel[k]); });
    picks.forEach((b, k) => {
      const done = ask.answer && ask.answer.option === viewer.sel[k] + 1;
      b.replaceChildren(...(done ? [icon("check"), "Elegida"] : [`Elegir «${ask.options[viewer.sel[k]].label}»`]));
      b.disabled = !!done;
    });
  };
  const change = (k, idx) => { viewer.sel[k] = idx; viewer.active = k; refresh(); mount(); };
  viewer.setSel = (n) => { if (n < ask.options.length) change(viewer.active, n); };

  const heads = [];
  for (const k of [0, 1]) {
    const sel = el("select", "v-select");
    sel.setAttribute("aria-label", k === 0 ? "Propuesta de la izquierda" : "Propuesta de la derecha");
    ask.options.forEach((o, n) => { const op = el("option", "", optText(ask, n)); op.value = String(n); sel.append(op); });
    sel.addEventListener("change", () => change(k, Number(sel.value)));
    const pk = button("", "pill primary v-choose", null);
    pk.addEventListener("click", () => run(pk, toast, async () => {
      await answer(ask, viewer.sel[k] + 1);
      document.getElementById("viewer").close();
    }));
    selects.push(sel); picks.push(pk);
    const h = el("div", "v-colhead");
    h.addEventListener("pointerdown", () => { viewer.active = k; });
    h.addEventListener("focusin", () => { viewer.active = k; });
    h.append(sel, pk);
    heads.push(h);
  }
  const wrap = el("div", `v-cols${slider ? " slider" : ""}`);
  if (slider) {
    const hd = el("div", "v-heads");
    hd.append(...heads);
    const body = el("div", "v-body");
    bodies.push(body);
    wrap.append(hd, body);
  } else {
    for (const k of [0, 1]) {
      const col = el("div", "v-col");
      const body = el("div", "v-body");
      body.addEventListener("pointerdown", () => { viewer.active = k; });
      bodies.push(body);
      col.append(heads[k], body);
      wrap.append(col);
    }
  }
  stage.replaceChildren(wrap);
  refresh();
  mount();
}

function showViewer() {
  const { ask, i } = viewer, o = ask.options[i];
  const d = document.getElementById("viewer");
  for (const b of d.querySelectorAll("[data-mode]")) b.setAttribute("aria-pressed", String(b.dataset.mode === viewer.mode));
  for (const b of d.querySelectorAll("[data-w]")) b.setAttribute("aria-pressed", String(Number(b.dataset.w) === viewer.width));
  const one = viewer.mode === "one";
  for (const id of ["v-prev", "v-next", "v-pick"]) document.getElementById(id).hidden = !one;
  const extra = document.getElementById("v-extra");
  extra.replaceChildren();
  if (!one) {
    document.getElementById("v-title").textContent = viewer.mode === "side" ? "Comparar lado a lado" : "Comparar con deslizador";
    document.getElementById("v-count").textContent = ask.title;
    extra.hidden = true;
    renderCompare();
    return;
  }
  viewer.frames = [];
  viewer.setSel = null;
  document.getElementById("v-title").textContent = o.label;
  document.getElementById("v-count").textContent = `${ask.title} · ${i + 1} de ${ask.options.length}`;
  const chosen = ask.answer && ask.answer.option === i + 1;
  const pick = document.getElementById("v-pick");
  if (chosen) pick.replaceChildren(icon("check"), "Elegida");
  else pick.replaceChildren("Elegir esta");
  pick.disabled = !!chosen;
  if (recommended(ask, i + 1)) extra.append(recBadge());
  if (o.desc) extra.append(el("span", "v-desc", o.desc));
  extra.hidden = !extra.childElementCount;
  const box = el("div", "v-frame");
  box.append(frame(ask, i + 1, o.label));
  document.getElementById("v-stage").replaceChildren(box);
  fitViewer();
}

// Abre el visor. mode: "one" (una a una), "side" (lado a lado) o "slider"; en comparación i y j son las dos opciones.
export function openViewer(ask, i, plan, mode, j) {
  const n = ask.options.length;
  mode = mode || savedMode();
  if (n < 2) mode = "one";
  if (j == null) j = (i + 1) % n;
  Object.assign(viewer, { ask, i, j, plan, mode, active: 0, pos: { x: 0, y: 0 } });
  if (mode !== "one") saveMode(mode);
  if (!viewer.width) viewer.width = window.innerWidth < 600 ? 390 : LOGICAL;  // empieza con el ancho de la pantalla
  const d = document.getElementById("viewer");
  if (!d.open) d.showModal();
  showViewer();
}

function setMode(mode) {
  if (!viewer.ask || viewer.mode === mode) return;
  const n = viewer.ask.options.length;
  if (mode !== "one" && n < 2) return;
  if (viewer.mode === "one") viewer.j = (viewer.i + 1) % n;
  else if (mode === "one") viewer.i = viewer.sel[viewer.active];
  else { viewer.i = viewer.sel[0]; viewer.j = viewer.sel[1]; }
  viewer.mode = mode;
  viewer.pos = { x: 0, y: 0 };
  saveMode(mode);
  showViewer();
}

function step(delta) {
  const n = viewer.ask.options.length;
  viewer.i = (viewer.i + delta + n) % n;
  showViewer();
}

export function setupViewer() {
  const d = document.getElementById("viewer");
  const put = (node, name, text) => node.replaceChildren(...[icon(name), text].filter(Boolean));
  put(document.getElementById("v-prev"), "left");
  put(document.getElementById("v-next"), "right");
  put(document.getElementById("v-close"), "x");
  for (const [w, name, text] of [["390", "phone", "Móvil"], ["820", "tablet", "Tableta"], ["1280", "desktop", "Escritorio"]])
    put(d.querySelector(`[data-w="${w}"]`), name, text);
  for (const b of d.querySelectorAll("[data-mode]")) b.addEventListener("click", () => setMode(b.dataset.mode));
  if (!document.getElementById("v-extra")) {
    const x = el("div", "v-extra");
    x.id = "v-extra";
    x.hidden = true;
    d.querySelector(".v-info").append(x);
  }
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
    if (e.target.closest("textarea, input, select")) return;
    if (viewer.mode === "one") {
      if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    } else if (/^[1-9]$/.test(e.key) && viewer.setSel) {
      e.preventDefault();
      viewer.setSel(Number(e.key) - 1);
    }
  });
  d.addEventListener("close", () => { document.getElementById("v-stage").replaceChildren(); viewer.ask = null; viewer.frames = []; });
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

function chosenText(ask) {
  const a = ask.answer;
  if (!a) return "";
  return a.option ? ask.options[a.option - 1]?.label || `Opción ${a.option}` : "";
}

function context(ask, plan) {
  const [b, s] = ask.step ? stepOf(plan, ask.step) : [branchOf(plan, ask.branch), null];
  const parts = [];
  if (b) parts.push(b.name);
  if (s) parts.push(`${s.id} · ${s.title}`);
  return parts.join(" · ");
}

// Cuerpo de una opción de pregunta: título (con insignia si es la recomendada) y debajo su línea de explicación.
function optionBody(ask, o, n) {
  const body = el("span", "opt-body");
  const t = el("span", "opt-title");
  t.append(el("span", "opt-label", o.label));
  if (recommended(ask, n)) t.append(recBadge());
  body.append(t);
  if (o.desc) body.append(el("span", "opt-desc", o.desc));
  return body;
}

// Tira compacta del andén: una fila de miniaturas pequeñas, "Comparar" y la recomendación. Elegir se hace desde el visor.
function strip(ask, plan) {
  const opts = ask.options, wrap = el("div", "strip-wrap");
  const row = el("div", "strip");
  row.setAttribute("role", "group");
  row.setAttribute("aria-label", "Propuestas");
  opts.forEach((o, i) => {
    const n = i + 1;
    const b = button("", `strip-item${recommended(ask, n) ? " rec" : ""}`, () => openViewer(ask, i, plan, "one"), `Ver «${o.label}» a pantalla completa`);
    const box = el("div", "thumb");
    const f = frame(ask, n, o.label);
    f.tabIndex = -1;
    f.setAttribute("aria-hidden", "true");
    box.append(f);
    sizer.observe(box);
    const cap = el("span", "strip-cap");
    cap.append(el("b", "", String(n)));
    if (recommended(ask, n)) cap.append(icon("star"));
    cap.append(el("span", "strip-label", o.label));
    b.append(box, cap);
    row.append(b);
  });
  wrap.append(row);
  const act = el("div", "act-row");
  if (opts.length > 1) {
    const r = ask.recommend > 0 && ask.recommend <= opts.length ? ask.recommend - 1 : 0;
    act.append(button("Comparar", "pill primary", () => openViewer(ask, r, plan, "side", (r + 1) % opts.length)));
  }
  if (ask.recommend > 0) act.append(el("span", "strip-rec", `★ Recomienda la ${ask.recommend}`));
  wrap.append(act);
  return wrap;
}

// Tarjeta de una pregunta o propuesta. `compact`: versión más apretada para el andén o el detalle de un paso.
export function askCard(ask, plan, compact = false) {
  const prop = ask.kind === "proposal";
  const card = el("article", `ask ficha ${ask.kind}${ask.answer ? " answered" : ""}${compact ? " compact" : ""}`);
  if (!compact) card.id = `ask-${ask.id}`;
  const head = el("div", "ask-head");
  const kind = el("span", `chip ${prop ? "prop" : "quest"}`);
  kind.append(icon(prop ? "eye" : "ask"), prop ? "Propuesta" : "Pregunta");
  head.append(kind, el("span", "ask-id", ask.id));
  const ctx = context(ask, plan);
  if (ctx) head.append(el("span", "ask-ctx", ctx));
  const chip = auditChip(auditFor(plan, ask.id));
  if (chip) head.append(chip);
  card.append(head, el(compact ? "h4" : "h3", "ask-title", ask.title));
  if (ask.text) {
    const t = el("div", "ask-text md");
    t.append(mdLite(ask.text));
    card.append(t);
  }
  const opts = ask.options || [];

  if (ask.answer && !editing.has(ask.id)) {
    const chosenN = ask.answer.option || 0;
    if (opts.length && !prop) {
      const list = el("div", "choices done");
      opts.forEach((o, i) => {
        const on = chosenN === i + 1;
        const r = el("div", `choice${on ? " on" : ""}`);
        const n = el("span", `choice-n${on ? " ok" : ""}`);
        if (on) n.append(icon("check")); else n.append(String(i + 1));
        r.append(n, optionBody(ask, o, i + 1));
        if (on) r.setAttribute("aria-label", `Elegida: ${o.label}`);
        list.append(r);
      });
      card.append(list);
    }
    const done = el("div", "answer");
    const pick = chosenText(ask);
    if (pick && prop) {
      const p = el("p", "answer-pick");
      p.append(icon("check"), `Elegiste «${pick}»`);
      done.append(p);
    }
    if (ask.answer.text) done.append(el("p", "answer-text", pick ? `Comentario: ${ask.answer.text}` : `Respondiste: ${ask.answer.text}`));
    done.append(el("p", "muted small", `${ask.answer.seen ? "Tu agente ya lo ha visto" : "Tu agente aún no lo ha visto"} · ${when(ask.answer.at)}`));
    const row = el("div", "act-row");
    if (prop && opts.length)
      row.append(button("Ver las propuestas", "pill", () => openViewer(ask, Math.max(0, chosenN - 1), plan)));
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
  if (prop && opts.length && compact) {
    card.append(strip(ask, plan));
    if (ask.recommend === 0) card.append(el("p", "no-pref", "Sin preferencia del agente"));
    return card;
  }
  if (prop && opts.length) {
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
      const b = button("", `choice${recommended(ask, i + 1) ? " rec" : ""}`, null);
      b.append(el("span", "choice-n", String(i + 1)), optionBody(ask, o, i + 1));
      if (ask.answer && ask.answer.option === i + 1) b.setAttribute("aria-pressed", "true");
      b.addEventListener("click", () => run(b, say, () => answer(ask, i + 1)));
      list.append(b);
    });
    card.append(list);
  }
  if (opts.length && ask.recommend === 0) card.append(el("p", "no-pref", "Sin preferencia del agente"));
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
  head.append(el("span", "chip wait", "Revisar fase"), el("span", "ask-ctx", b.name));
  const [done, total] = [p.steps.filter((s) => s.state === "done").length, p.steps.length];
  const ul = el("ul", "mini-steps");
  for (const s of p.steps) ul.append(el("li", s.state === "done" ? "done" : "", s.title));
  c.append(head, el("h3", "ask-title", `«${p.name}» está lista: ${done} de ${total} pasos`),
    el("p", "ask-text", "Tu agente ha parado aquí. Dale el visto bueno o dile qué cambiar."), ul, reviewBox(b, p));
  return c;
}

// Firma de lo que hay en la bandeja: si no cambia, no se repinta (las miniaturas no se recargan).
export function inboxKey(plan) {
  return JSON.stringify([waitingPhases(plan).map(([b, p]) => [b.key, p.name, p.steps.map((s) => s.state)]),
    openAsks(plan).map((a) => [a.id, a.title, a.text, a.options, a.recommend, a.answer, (plan.audit || []).filter((x) => x.ref === a.id)]), app.pid]);
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
