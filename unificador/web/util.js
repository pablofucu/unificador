// Piezas comunes: crear nodos, hablar con el servidor y recordar borradores entre repintados.
// Todo se pinta con createElement/textContent (nunca innerHTML con datos del plan).

export const app = {
  pid: null,          // proyecto que se está viendo
  projects: [],       // lista de /api/projects
  onPlan: () => {},   // lo pone app.js: repinta con un plan recién recibido
  rerender: () => {}, // lo pone app.js: repinta con el último plan
};

export function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

export function button(text, cls, fn, label) {
  const b = el("button", cls || "pill", text);
  b.type = "button";
  if (label) b.setAttribute("aria-label", label);
  if (fn) b.addEventListener("click", fn);
  return b;
}

// La ruta con el proyecto que se está viendo.
export const q = (path) => (app.pid ? `${path}${path.includes("?") ? "&" : "?"}project=${encodeURIComponent(app.pid)}` : path);

export async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`Error ${r.status}`);
  return r.json();
}

// POST con JSON; devuelve el plan actualizado y lo repinta.
export async function send(path, body) {
  const r = await fetch(q(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  app.onPlan(data);
  return data;
}

// Ejecuta una acción con el botón desactivado; los errores se cuentan en `say`.
export async function run(btn, say, fn) {
  btn.disabled = true;
  say("");
  try { await fn(); } catch (e) { say(`No se pudo: ${e.message}`); }
  btn.disabled = false;
}

export const drafts = new Map();   // clave -> texto escrito (existe = formulario abierto)
export const msgs = new Map();     // clave -> último aviso

export function status(key) {
  const m = el("span", "act-msg", msgs.get(key) || "");
  m.setAttribute("role", "status");
  const say = (t) => { msgs.set(key, t); m.textContent = t; };
  return [m, say];
}

export function textarea(key, placeholder, label, rows = 2) {
  const ta = el("textarea");
  ta.rows = rows;
  ta.placeholder = placeholder;
  ta.setAttribute("aria-label", label);
  ta.value = drafts.get(key) || "";
  ta.addEventListener("input", () => drafts.set(key, ta.value));
  return ta;
}

export function toast(text) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 4500);
}

export function when(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  return d.toLocaleString("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export const reduce = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const allSteps = (b) => b.phases.flatMap((p) => p.steps);
export const count = (list) => [list.filter((s) => s.state === "done").length, list.length];
export const pctOf = (done, total) => (total ? Math.round((done / total) * 100) : 0);

// Color de la rama: índice 0-7 de la paleta, o un color CSS si viene como texto.
export function paint(node, b, i) {
  const raw = b.color;
  if (typeof raw === "string" && /^#[0-9a-f]{3,8}$/i.test(raw)) { node.style.setProperty("--accent", raw); return; }
  const n = raw === "" || raw == null || isNaN(Number(raw)) ? i : Number(raw);
  node.dataset.color = String(((n % 8) + 8) % 8);
}
