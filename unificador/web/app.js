// Arranque: portada con todos los proyectos o tablero de uno (#p=<id>). Se repinta en vivo.
import { app, el, getJSON, q, pctOf, setOffline, logout } from "./util.js";
import { renderPlan, resetBoard, initBoard } from "./plan.js";
import { icon } from "./icons.js";
import { setupViewer } from "./decide.js";
import { renderBox, resetBox, initBox } from "./box.js";

const $ = (id) => document.getElementById(id);
let events = null, homeTimer = null, pending = null, last = null, swRegistered = false;

function syncChrome() {
  for (const id of ["logout-home", "logout-board"]) {
    const btn = $(id);
    if (btn) btn.hidden = !app.remote;
  }
  if (app.remote && !swRegistered && "serviceWorker" in navigator) {
    swRegistered = true;
    navigator.serviceWorker.register("./sw.js").catch(() => { swRegistered = false; });
  }
}

// Instalación como app (Chrome/Android): el navegador avisa con beforeinstallprompt.
let installEvt = null;
function syncInstall() {
  for (const id of ["install-home", "install-board"]) {
    const btn = $(id);
    if (btn) btn.hidden = !installEvt;
  }
}
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installEvt = e;
  syncInstall();
});
window.addEventListener("appinstalled", () => { installEvt = null; syncInstall(); });
for (const id of ["install-home", "install-board"]) {
  $(id)?.addEventListener("click", async () => {
    if (!installEvt) return;
    const evt = installEvt;
    installEvt = null;
    syncInstall();
    evt.prompt();
    await evt.userChoice.catch(() => {});
  });
}

async function loadProjects() {
  try {
    const data = await getJSON("/api/projects");
    app.projects = data.projects || [];
    app.remote = !!data.remote;
    syncChrome();
  } catch {
    if (app.projects.length) setOffline(true);
  }
  return app.projects;
}

// ── Portada ──────────────────────────────────────────────────────────

// Lo que se está tocando en una tarjeta (renombrar o confirmar quitar): el repintado periódico lo respeta.
const homeEdit = { id: null, mode: "", draft: "", msg: "" };

async function projectAction(id, what, body) {
  if (app.offline) throw new Error("Sin conexión con tu ordenador: solo lectura hasta que vuelva.");
  const r = await fetch(`/api/projects/${encodeURIComponent(id)}/${what}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (r.status === 401) { location.reload(); throw new Error("Sesión cerrada"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  app.projects = data.projects || [];
  return data;
}

function editProject(id, mode) {
  const p = app.projects.find((x) => x.id === id);
  Object.assign(homeEdit, { id, mode, draft: mode === "name" ? (p ? p.name : "") : "", msg: "" });
  renderHome();
  if (mode === "name") requestAnimationFrame(() => { const i = $("proj-name-input"); if (i) { i.focus(); i.select(); } });
}

function stopEdit() { Object.assign(homeEdit, { id: null, mode: "", draft: "", msg: "" }); renderHome(); }

async function doAction(btn, fn) {
  btn.disabled = true;
  try { await fn(); stopEdit(); } catch (e) { homeEdit.msg = `No se pudo: ${e.message}`; renderHome(); }
}

function cardTools(p) {
  const tools = el("div", "proj-tools");
  if (app.offline) return tools;
  const ren = el("button", "icon-btn", null);
  ren.type = "button"; ren.title = "Cambiar el nombre"; ren.setAttribute("aria-label", `Cambiar el nombre de ${p.name}`);
  ren.append(icon("edit"));
  ren.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); editProject(p.id, "name"); });
  tools.append(ren);
  if (!p.current) {
    const rm = el("button", "icon-btn", null);
    rm.type = "button"; rm.title = "Quitar de la lista"; rm.setAttribute("aria-label", `Quitar ${p.name} de la lista`);
    rm.append(icon("x"));
    rm.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); editProject(p.id, "forget"); });
    tools.append(rm);
  }
  return tools;
}

function renameForm(p) {
  const f = el("form", "proj-rename");
  const input = el("input");
  input.id = "proj-name-input"; input.maxLength = 60; input.value = homeEdit.draft;
  input.placeholder = p.folder || "Nombre"; input.setAttribute("aria-label", "Nombre del proyecto");
  input.addEventListener("input", () => { homeEdit.draft = input.value; });
  input.addEventListener("keydown", (e) => { if (e.key === "Escape") stopEdit(); });
  const save = el("button", "pill primary", "Guardar"); save.type = "submit";
  const cancel = el("button", "pill", "Cancelar"); cancel.type = "button"; cancel.addEventListener("click", stopEdit);
  f.addEventListener("submit", (e) => { e.preventDefault(); doAction(save, () => projectAction(p.id, "name", { name: input.value })); });
  f.append(input, save, cancel);
  const hint = el("p", "muted proj-hint", p.folder ? `Déjalo vacío para volver a «${p.folder}».` : "");
  const box = el("div", "proj-edit"); box.append(f, hint);
  return box;
}

function forgetConfirm(p) {
  const box = el("div", "proj-confirm");
  box.append(el("p", null, "¿Quitar de la lista? La carpeta y su plan no se tocan; si vuelves a trabajar en él, reaparece."));
  const row = el("div", "proj-confirm-row");
  const yes = el("button", "pill danger", "Quitar"); yes.type = "button";
  yes.addEventListener("click", () => doAction(yes, () => projectAction(p.id, "forget")));
  const no = el("button", "pill", "Cancelar"); no.type = "button"; no.addEventListener("click", stopEdit);
  row.append(yes, no); box.append(row);
  return box;
}

const STATE_LABEL = { doing: "en curso", pending: "por empezar", done: "terminadas" };

function branchList(p) {
  const list = p.branches || [];
  const wrap = el("div", "proj-branches");
  const c = p.counts || {};
  const parts = ["doing", "pending", "done"].filter((s) => c[s]).map((s) => `${c[s]} ${STATE_LABEL[s]}`);
  wrap.append(el("p", "proj-sum", `${list.length} ${list.length === 1 ? "rama" : "ramas"}${parts.length ? " · " + parts.join(" · ") : ""}`));
  const shown = list.filter((b) => b.state === "doing").concat(list.filter((b) => b.state === "pending")).slice(0, 4);
  if (shown.length) {
    const ul = el("ul", "mini-branches");
    for (const b of shown) {
      const li = el("li", `mini ${b.state}`);
      const name = el("span", "mini-name", `${b.icon ? b.icon + " " : ""}${b.name}`);
      const n = el("span", "mini-count", `${b.done}/${b.total}`);
      const bar = el("i", "mini-bar"), fill = el("b");
      fill.style.width = `${pctOf(b.done, b.total)}%`;
      bar.append(fill);
      li.append(name, n, bar);
      ul.append(li);
    }
    wrap.append(ul);
    const rest = list.filter((b) => b.state !== "done").length - shown.length;
    if (rest > 0) wrap.append(el("p", "muted proj-more", `y ${rest} más`));
  }
  return wrap;
}

function projectCard(p) {
  const ok = p.exists && !p.error;
  const editing = homeEdit.id === p.id;
  const c = el(ok && !editing ? "a" : "div", `proj${p.waiting ? " waiting" : ""}${ok ? "" : " missing"}${editing ? " editing" : ""}`);
  if (ok && !editing) c.href = `#p=${p.id}`;
  const head = el("div", "proj-head");
  if (editing && homeEdit.mode === "name") head.append(renameForm(p));
  else {
    const title = el("div", "proj-title");
    title.append(el("h2", null, p.name));
    if (p.active) title.append(el("span", "chip ok", "Activo"));
    else if (p.current) title.append(el("span", "chip", "Abierto aquí"));
    head.append(title, cardTools(p));
  }
  c.append(head);
  if (editing && homeEdit.mode === "forget") c.append(forgetConfirm(p));
  if (editing && homeEdit.msg) c.append(el("p", "proj-err", homeEdit.msg));
  if (p.path) c.append(el("p", "proj-path", p.path));
  if (!p.exists) { c.append(el("p", "muted", "No encuentro la carpeta.")); return c; }
  if (p.error) { c.append(el("p", "muted", p.error)); return c; }
  const pct = pctOf(p.done, p.total);
  const bar = el("div", "bar"), fill = el("i");
  fill.style.width = `${pct}%`;
  bar.append(fill);
  c.append(el("p", "proj-count", p.total ? `${p.done} de ${p.total} pasos · ${pct}%` : "Todavía sin plan"), bar);
  if (p.total) c.append(branchList(p));
  if (p.waiting) {
    const w = el("p", "proj-wait");
    w.append(icon("inbox"), `${p.waiting} ${p.waiting === 1 ? "cosa espera" : "cosas esperan"} tu respuesta`);
    c.append(w);
  } else c.append(el("p", "proj-calm", "Nada pendiente de ti"));
  return c;
}

// Las carpetas que ya no existen (pruebas, demos borradas) se quitan de una vez.
function cleanupBar() {
  const gone = app.projects.filter((p) => !p.exists && !p.current);
  const bar = el("div", "proj-cleanup");
  if (!gone.length || app.offline) { bar.hidden = true; return bar; }
  bar.append(el("span", null, `${gone.length} ${gone.length === 1 ? "carpeta ya no existe" : "carpetas ya no existen"}.`));
  const b = el("button", "pill", `Quitarlas de la lista`); b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { for (const p of gone) await projectAction(p.id, "forget"); } catch (e) { homeEdit.msg = e.message; }
    stopEdit();
  });
  bar.append(b);
  return bar;
}

// Activos primero, después los que esperan algo, después por nombre; los que no existen al final.
function ordered(list) {
  const rank = (p) => (!p.exists ? 3 : p.active || p.current ? 0 : p.waiting ? 1 : 2);
  return [...list].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name, "es"));
}

function renderHome() {
  $("projects").replaceChildren(cleanupBar(), ...ordered(app.projects).map(projectCard));
}

async function showHome() {
  closeEvents();
  app.pid = null;
  $("board").hidden = true;
  $("home").hidden = false;
  document.title = "Tus proyectos · Unificador";
  renderHome();
  clearInterval(homeTimer);
  homeTimer = setInterval(async () => { if (homeEdit.id) return; await loadProjects(); if (!$("home").hidden) renderHome(); }, 5000);
}

// ── Tablero ──────────────────────────────────────────────────────────

const typing = () => {
  const a = document.activeElement;
  return a && (a.tagName === "TEXTAREA" || a.tagName === "INPUT") && $("board").contains(a);
};

// Mientras se escribe no se repinta (se perdería el foco); se hace al salir del cuadro.
function paint(plan) {
  last = plan;
  if (typing()) { pending = plan; return; }
  pending = null;
  renderPlan(plan);
  renderBox(plan);
}
app.onPlan = paint;
app.rerender = () => last && renderPlan(last);
document.addEventListener("focusout", () => setTimeout(() => { if (pending && !typing()) paint(pending); }, 400));

async function loadPlan() {
  const pid = app.pid;
  try {
    const plan = await getJSON(q("/api/plan"));
    if (pid === app.pid) paint(plan);
  } catch {
    if (pid !== app.pid) return;
    if (last) setOffline(true);
    else $("branches").textContent = "Sin conexión con tu ordenador o cargando el plan. Reintento en un momento…";
    setTimeout(() => { if (pid === app.pid) loadPlan(); }, 4000);
  }
}

function closeEvents() {
  if (events) events.close();
  events = null;
}

function showBoard(p) {
  clearInterval(homeTimer);
  if (app.pid !== p.id) { resetBoard(); resetBox(); last = null; $("branches").replaceChildren(); $("inbox").hidden = true; }
  app.pid = p.id;
  $("home").hidden = true;
  $("board").hidden = false;
  fillSelect(p.id);
  $("project-name").textContent = p.name || "Mi proyecto";
  document.title = `${p.name || "Proyecto"} · Unificador`;
  closeEvents();
  events = new EventSource(q("/api/events"));
  events.addEventListener("plan", loadPlan);
  loadPlan();
}

// Selector de proyecto de la cabecera; la última opción lleva a la portada con todos.
function fillSelect(id) {
  const sel = $("project-select");
  const usable = app.projects.filter((p) => p.exists && !p.error);
  const opts = usable.map((p) => {
    const o = document.createElement("option");
    o.value = p.id;
    o.textContent = p.waiting ? `${p.name} (${p.waiting} te esperan)` : p.name;
    return o;
  });
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "Todos los proyectos";
  sel.replaceChildren(...opts, all);
  sel.value = usable.some((p) => p.id === id) ? id : "";
  sel.disabled = !app.projects.length;
}
$("project-select").addEventListener("change", (e) => {
  location.hash = e.target.value ? `#p=${e.target.value}` : "#todos";
});

async function route() {
  await loadProjects();
  if (location.hash === "#todos") return showHome();
  const m = location.hash.match(/^#p=([0-9a-f]+)$/);
  const found = m && app.projects.find((p) => p.id === m[1]);
  if (found) return showBoard(found);
  if (!app.projects.length) return showBoard({ id: null, name: "Mi proyecto" });
  // Sin proyecto en la ruta: el último trabajado (active), el de aquí, o el primero que se pueda abrir.
  const usable = app.projects.filter((p) => p.exists && !p.error);
  const first = usable.find((p) => p.active) || usable.find((p) => p.current) || usable[0];
  if (first) return showBoard(first);
  showHome();
}

for (const id of ["logout-home", "logout-board"]) {
  const btn = $(id);
  if (btn) {
    btn.prepend(icon("logout"));
    btn.addEventListener("click", logout);
  }
}
$("offline-retry")?.addEventListener("click", route);
window.addEventListener("online", route);
window.addEventListener("hashchange", route);
setupViewer();
initBoard();
initBox();
route();
