// Chat: agentes, conversaciones, envío en streaming. Todo el DOM se construye con textContent.
const $ = (id) => document.getElementById(id);
const api = (url, opt) => fetch(url, opt);
export const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

let project = null;           // {name, agents, settings}
let settings = { agent: "", agents: {} };
let sessions = [];
let active = { agent: "", session: null };
let turns = [];
let run = null;               // {id} mientras el agente responde desde aquí
let notices = [];             // avisos dentro del chat (errores, mensajes)
let listOpen = false;

const storeKey = () => `unificador:chat:${project ? project.path || project.name : ""}`;
const remember = () => { try { localStorage.setItem(storeKey(), JSON.stringify(active)); } catch { /* sin almacenamiento */ } };
const recall = () => { try { return JSON.parse(localStorage.getItem(storeKey()) || "null"); } catch { return null; } };

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
const agentInfo = (id) => (project.agents || []).find((a) => a.id === id) || { id, name: id, icon: "🤖", models: [], efforts: [], modes: [] };
const prefs = () => (settings.agents[settings.agent] ||= {});

function ago(iso) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (isNaN(s)) return "";
  if (s < 60) return "ahora mismo";
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} d`;
}
const ORIGIN = { terminal: "💻 terminal", web: "🌐 web", antigravity: "🪐 Antigravity" };

// ── Markdown mínimo y seguro ────────────────────────────────────────────────
function inline(parent, text) {
  for (const part of text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/)) {
    if (!part) continue;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) parent.append(el("code", null, part.slice(1, -1)));
    else if (part.startsWith("**") && part.endsWith("**") && part.length > 4) parent.append(el("strong", null, part.slice(2, -2)));
    else parent.append(part);
  }
}

function markdown(text) {
  const box = el("div", "md");
  text.split(/```[^\n]*\n?/).forEach((chunk, i) => {
    if (i % 2) { box.append(el("pre", null, chunk.replace(/\n$/, ""))); return; }
    let list = null, para = null;
    const flush = () => { list = null; para = null; };
    for (const line of chunk.split("\n")) {
      const li = /^\s*(?:[-*]|\d+[.)])\s+(.*)$/.exec(line);
      if (li) {
        if (!list) { list = el("ul"); box.append(list); para = null; }
        const item = el("li"); inline(item, li[1]); list.append(item);
      } else if (!line.trim()) flush();
      else {
        if (!para) { para = el("p"); box.append(para); list = null; } else para.append(el("br"));
        inline(para, line);
      }
    }
  });
  return box;
}

// ── Barra: agente, modelo, esfuerzo, modo ───────────────────────────────────
function select(label, options, value, onChange) {
  const s = el("select", "pill");
  s.setAttribute("aria-label", label);
  for (const o of options) { const op = el("option", null, o.name); op.value = o.id; s.append(op); }
  s.value = value || (options[0] && options[0].id) || "";
  s.addEventListener("change", () => onChange(s.value));
  return s;
}

function saveSettings() { post("/api/settings", settings).catch(() => {}); }

function setAgent(id) {
  settings.agent = id;
  if (active.agent !== id) { active = { agent: id, session: null }; turns = []; remember(); }
  saveSettings();
  renderBar(); renderLog();
}

function renderBar() {
  const bar = $("chat-bar"), a = agentInfo(settings.agent);
  const agents = el("div", "agents");
  for (const ag of project.agents || []) {
    const b = el("button", "pill agent", `${ag.icon || "🤖"} ${ag.name}${ag.installed ? "" : " · no instalado"}`);
    b.type = "button";
    b.disabled = !ag.installed;
    b.setAttribute("aria-pressed", String(ag.id === settings.agent));
    b.addEventListener("click", () => setAgent(ag.id));
    agents.append(b);
  }
  const opts = el("div", "opts");
  const set = (k) => (v) => { prefs()[k] = v; saveSettings(); };
  const p = prefs();
  if (a.models.length) opts.append(select("Modelo", a.models, p.model, set("model")));
  if (a.efforts && a.efforts.length) opts.append(select("Esfuerzo", a.efforts, p.effort, set("effort")));
  if (a.modes && a.modes.length) opts.append(select("Modo", a.modes, p.mode, set("mode")));
  const tools = el("div", "opts");
  const hist = el("button", "pill", `🕘 Conversaciones (${sessions.length})`);
  hist.type = "button";
  hist.setAttribute("aria-expanded", String(listOpen));
  hist.addEventListener("click", () => { listOpen = !listOpen; renderBar(); renderList(); });
  const nw = el("button", "pill", "➕ Nueva");
  nw.type = "button";
  nw.addEventListener("click", newChat);
  tools.append(hist, nw);
  if (active.session) {
    const nat = el("button", "pill", "↗ Abrir en la terminal");
    nat.type = "button";
    nat.addEventListener("click", openNative);
    tools.append(nat);
  }
  bar.replaceChildren(agents, opts, tools);
}

function newChat() {
  active = { agent: settings.agent, session: null };
  turns = []; notices = []; listOpen = false;
  remember(); renderBar(); renderList(); renderLog();
  $("chat-input").focus();
}

async function openNative() {
  try {
    const r = await post("/api/open-native", { agent: active.agent, session: active.session });
    const d = await r.json();
    toast(d.message || d.error || "Hecho.");
  } catch { toast("No he podido abrirla."); }
}

function toast(text) {
  const t = $("chat-toast");
  t.textContent = text; t.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { t.hidden = true; }, 5000);
}

// ── Lista de conversaciones ─────────────────────────────────────────────────
function renderList() {
  const box = $("chat-list");
  box.hidden = !listOpen;
  if (!listOpen) return;
  if (!sessions.length) { box.replaceChildren(el("p", "muted pad", "Aún no hay conversaciones.")); return; }
  box.replaceChildren(...sessions.map((s) => {
    const b = el("button", "sess");
    b.type = "button";
    if (s.id === active.session) b.setAttribute("aria-current", "true");
    const info = el("span", "sess-info");
    info.append(el("strong", null, s.title || "Sin título"),
      el("small", null, `${ago(s.updated)} · ${ORIGIN[s.origin] || s.origin || ""}`));
    b.append(el("span", "sess-icon", agentInfo(s.agent).icon || "🤖"), info);
    b.addEventListener("click", () => openSession(s.agent, s.id));
    return b;
  }));
}

async function loadSessions() {
  try { sessions = (await (await api("/api/sessions")).json()).sessions || []; } catch { return; }
  renderBar(); renderList();
}

async function openSession(agent, id, keepScroll) {
  try {
    const r = await api(`/api/sessions/${encodeURIComponent(agent)}/${encodeURIComponent(id)}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "");
    turns = d.turns || [];
  } catch { if (!keepScroll) { notices = ["No he podido abrir esa conversación."]; turns = []; } else return; }
  const changed = active.agent !== agent;
  active = { agent, session: id };
  if (changed) { settings.agent = agent; saveSettings(); }
  if (!keepScroll) { notices = []; listOpen = false; }
  remember(); renderBar(); renderList(); renderLog(keepScroll);
}

// ── Conversación ────────────────────────────────────────────────────────────
function bubble(t) {
  const row = el("div", `msg ${t.role}`);
  const b = el("div", "bubble");
  if (t.role === "user") b.append(el("p", null, t.text));
  else {
    if (t.tools && t.tools.length) {
      const d = el("details", "tools");
      d.append(el("summary", null, `🔧 ${t.tools.length === 1 ? t.tools[0] : `${t.tools.length} acciones`}`));
      if (t.tools.length > 1) d.append(...t.tools.map((x) => el("div", null, `🔧 ${x}`)));
      b.append(d);
    }
    if (t.text) b.append(markdown(t.text));
    else if (t.pending) b.append(el("span", "typing", "Pensando…"));
    if (t.model) b.append(el("small", "model", t.model));
  }
  row.append(b);
  return row;
}

function renderLog(keep) {
  const log = $("chat-log");
  const stick = !keep || log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  const items = turns.map(bubble);
  for (const n of notices) items.push(el("div", "notice", n));
  if (!items.length) {
    const e = el("div", "chat-empty");
    e.append(el("div", "big", "💬"), el("p", null, "¡Hola! Cuéntale al agente qué quieres hacer."),
      el("p", "muted", "Escribe abajo y pulsa Enter. También puedes retomar una conversación de la lista."));
    items.push(e);
  }
  log.replaceChildren(...items);
  if (stick) log.scrollTop = log.scrollHeight;
}

// ── Envío ───────────────────────────────────────────────────────────────────
function setBusy(on) {
  const b = $("chat-send");
  b.textContent = on ? "⏹ Parar" : "Enviar ➤";
  b.classList.toggle("stop", on);
  b.dataset.mode = on ? "stop" : "send";
}

async function stop() {
  if (run && run.id) try { await post("/api/chat/stop", { run: run.id }); } catch { /* ya terminó */ }
}

export async function sendToActive(text) {
  text = (text || "").trim();
  if (!text || run) return false;
  document.querySelector('.tabs [data-tab="chat"]')?.click();
  const agent = active.session ? active.agent : settings.agent;
  const p = settings.agents[agent] || {};
  const body = { text, agent, model: p.model || "", effort: p.effort || "", mode: p.mode || "" };
  if (active.session) body.session = active.session;
  notices = [];
  turns.push({ role: "user", text }, { role: "assistant", text: "", tools: [], pending: true });
  const reply = turns[turns.length - 1];
  run = {};
  setBusy(true); renderLog();
  let ok = true;
  try {
    const r = await post("/api/chat", body);
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.error || `Error ${r.status}`);
    }
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "";
    const handle = (line) => {
      if (!line.trim()) return;
      let ev; try { ev = JSON.parse(line); } catch { return; }
      if (ev.type === "run") run.id = ev.id;
      else if (ev.type === "session") { active = { agent, session: ev.id }; remember(); renderBar(); }
      else if (ev.type === "model") reply.model = ev.id;
      else if (ev.type === "text") reply.text += ev.text;
      else if (ev.type === "tool") reply.tools.push(ev.text);
      else if (ev.type === "error") notices.push(`⚠️ ${ev.text}`);
      else if (ev.type === "stopped") notices.push("⏹ Parado. Puedes seguir cuando quieras.");
      reply.pending = ev.type !== "done" && ev.type !== "stopped";
      renderLog(true);
    };
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n"); buf = lines.pop();
      lines.forEach(handle);
    }
    handle(buf);
  } catch (e) {
    ok = false;
    turns.splice(-2, 2);
    notices = [`⚠️ ${e.message || "No he podido enviarlo."} Tu mensaje sigue en el cuadro.`];
    const inp = $("chat-input");
    if (!inp.value) { inp.value = text; grow(); }
  }
  reply.pending = false;
  run = null; setBusy(false); renderLog(true);
  loadSessions();
  if (ok && active.session) openSession(active.agent, active.session, true);
  return ok;
}

// ── En vivo ─────────────────────────────────────────────────────────────────
export function onSessionsChanged() {
  if (!project) return;
  loadSessions();
  if (!run && active.session) openSession(active.agent, active.session, true);
}

// ── Arranque ────────────────────────────────────────────────────────────────
function grow() {
  const t = $("chat-input");
  t.style.height = "auto";
  t.style.height = `${Math.min(t.scrollHeight, 180)}px`;
}

export async function initChat(info) {
  project = info;
  settings = { agent: "", agents: {}, ...(info.settings || {}) };
  settings.agents ||= {};
  if (!settings.agent) settings.agent = ((info.agents || []).find((a) => a.installed) || (info.agents || [])[0] || {}).id || "";
  active = { agent: settings.agent, session: null };

  const form = $("chat-form"), input = $("chat-input");
  input.addEventListener("input", grow);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (run) { stop(); return; }
    const text = input.value;
    if (!text.trim()) return;
    input.value = ""; grow();
    if (!(await sendToActive(text))) input.value = input.value || text;
  });

  renderBar(); renderLog();
  await loadSessions();
  const last = recall();
  if (last && last.session && sessions.some((s) => s.id === last.session)) openSession(last.agent, last.session);
}
