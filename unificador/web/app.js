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

function projectCard(p) {
  const ok = p.exists && !p.error;
  const c = el(ok ? "a" : "div", `proj${p.waiting ? " waiting" : ""}${ok ? "" : " missing"}`);
  if (ok) c.href = `#p=${p.id}`;
  const head = el("div", "proj-head");
  head.append(el("h2", null, p.name));
  if (p.active) head.append(el("span", "chip ok", "Activo"));
  else if (p.current) head.append(el("span", "chip", "Abierto aquí"));
  c.append(head);
  if (p.path) c.append(el("p", "proj-path", p.path));
  if (!p.exists) { c.append(el("p", "muted", "No encuentro la carpeta.")); return c; }
  if (p.error) { c.append(el("p", "muted", p.error)); return c; }
  const pct = pctOf(p.done, p.total);
  const bar = el("div", "bar"), fill = el("i");
  fill.style.width = `${pct}%`;
  bar.append(fill);
  c.append(el("p", "proj-count", p.total ? `${p.done} de ${p.total} pasos · ${pct}%` : "Todavía sin plan"), bar);
  if (p.waiting) {
    const w = el("p", "proj-wait");
    w.append(icon("inbox"), `${p.waiting} ${p.waiting === 1 ? "cosa espera" : "cosas esperan"} tu respuesta`);
    c.append(w);
  } else c.append(el("p", "proj-calm", "Nada pendiente de ti"));
  return c;
}

function renderHome() {
  $("projects").replaceChildren(...app.projects.map(projectCard));
}

async function showHome() {
  closeEvents();
  app.pid = null;
  $("board").hidden = true;
  $("home").hidden = false;
  document.title = "Tus proyectos · Unificador";
  renderHome();
  clearInterval(homeTimer);
  homeTimer = setInterval(async () => { await loadProjects(); if (!$("home").hidden) renderHome(); }, 5000);
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
