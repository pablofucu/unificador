// Arranque: portada con todos los proyectos o tablero de uno (#p=<id>). Se repinta en vivo.
import { app, el, getJSON, q, pctOf } from "./util.js";
import { renderPlan, resetBoard } from "./plan.js";
import { setupViewer } from "./decide.js";

const $ = (id) => document.getElementById(id);
let events = null, homeTimer = null, pending = null, last = null;

async function loadProjects() {
  try { app.projects = (await getJSON("/api/projects")).projects || []; } catch { /* se queda la lista anterior */ }
  return app.projects;
}

// ── Portada ──────────────────────────────────────────────────────────

function projectCard(p) {
  const ok = p.exists && !p.error;
  const c = el(ok ? "a" : "div", `proj${p.waiting ? " waiting" : ""}${ok ? "" : " missing"}`);
  if (ok) c.href = `#p=${p.id}`;
  const head = el("div", "proj-head");
  head.append(el("h2", null, p.name));
  if (p.current) head.append(el("span", "chip", "Abierto aquí"));
  c.append(head, el("p", "proj-path", p.path));
  if (!p.exists) { c.append(el("p", "muted", "No encuentro la carpeta.")); return c; }
  if (p.error) { c.append(el("p", "muted", p.error)); return c; }
  const pct = pctOf(p.done, p.total);
  const bar = el("div", "bar"), fill = el("i");
  fill.style.width = `${pct}%`;
  bar.append(fill);
  c.append(el("p", "proj-count", p.total ? `${p.done} de ${p.total} pasos · ${pct}%` : "Todavía sin plan"), bar);
  c.append(p.waiting
    ? el("p", "proj-wait", `🔔 ${p.waiting} ${p.waiting === 1 ? "cosa espera" : "cosas esperan"} tu respuesta`)
    : el("p", "proj-calm", "Nada pendiente de ti"));
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
    $("branches").textContent = "No consigo leer el plan. Reintento en un momento…";
    setTimeout(() => { if (pid === app.pid) loadPlan(); }, 3000);
  }
}

function closeEvents() {
  if (events) events.close();
  events = null;
}

function showBoard(p) {
  clearInterval(homeTimer);
  if (app.pid !== p.id) { resetBoard(); last = null; $("branches").replaceChildren(); $("inbox").hidden = true; }
  app.pid = p.id;
  $("home").hidden = true;
  $("board").hidden = false;
  $("crumbs").hidden = app.projects.length < 2;
  $("project-name").textContent = p.name || "Mi proyecto";
  document.title = `${p.name || "Proyecto"} · Unificador`;
  closeEvents();
  events = new EventSource(q("/api/events"));
  events.addEventListener("plan", loadPlan);
  loadPlan();
}

async function route() {
  await loadProjects();
  const m = location.hash.match(/^#p=([0-9a-f]+)$/);
  const found = m && app.projects.find((p) => p.id === m[1]);
  if (found) return showBoard(found);
  const usable = app.projects.filter((p) => p.exists);
  if (usable.length === 1) return showBoard(usable[0]);
  if (!app.projects.length) return showBoard({ id: null, name: "Mi proyecto" });
  showHome();
}

$("back").addEventListener("click", (e) => { e.preventDefault(); history.pushState(null, "", location.pathname); route(); });
window.addEventListener("hashchange", route);
setupViewer();
route();
