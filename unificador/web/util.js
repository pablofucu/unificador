// Piezas comunes: crear nodos, hablar con el servidor y recordar borradores entre repintados.
// Todo se pinta con createElement/textContent (nunca innerHTML con datos del plan).

export const app = {
  pid: null,          // proyecto que se está viendo
  projects: [],       // lista de /api/projects
  remote: false,      // sesión remota vía Tailscale Funnel
  offline: false,     // mostrando copia guardada (solo lectura)
  cachedAt: "",       // marca temporal de la copia guardada
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

export async function clearOfflineCache() {
  try {
    if ("serviceWorker" in navigator) {
      const regs = await navigator.serviceWorker.getRegistrations();
      await Promise.all(regs.map((r) => r.unregister()));
    }
    if ("caches" in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch { /* sin soporte SW/caches */ }
}

export function setOffline(on, cachedAt = "") {
  app.offline = !!on;
  if (cachedAt) app.cachedAt = cachedAt;
  else if (!app.offline) app.cachedAt = "";
  document.body?.classList.toggle("is-offline", app.offline);
  const bar = document.getElementById("offline-banner");
  const txt = document.getElementById("offline-text");
  if (bar) bar.hidden = !app.offline;
  if (txt && app.offline) {
    const stamp = app.cachedAt ? when(app.cachedAt) : "";
    txt.textContent = stamp
      ? `Sin conexión con tu ordenador · Última copia guardada (${stamp}) · Solo lectura`
      : "Sin conexión con tu ordenador · Mostrando la última copia guardada (solo lectura).";
  }
}

export async function logout() {
  for (const id of ["logout-home", "logout-board"]) {
    const btn = document.getElementById(id);
    if (btn) btn.disabled = true;
  }
  await clearOfflineCache();
  try {
    await fetch("/auth/logout", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  } catch { /* aunque falle la red, recarga tras limpiar caché */ }
  location.reload();
}

export async function getJSON(path) {
  const r = await fetch(path);
  if (r.status === 401) {
    await clearOfflineCache();
    location.reload();
    throw new Error("Sesión cerrada");
  }
  if (!r.ok) throw new Error(`Error ${r.status}`);
  if (r.headers.get("X-Unificador-Offline") === "1") {
    setOffline(true, r.headers.get("X-Unificador-Cached-At") || r.headers.get("Date") || "");
  } else {
    setOffline(false);
  }
  return r.json();
}

// POST con JSON; devuelve el plan actualizado y lo repinta.
export async function send(path, body) {
  if (app.offline) throw new Error("Sin conexión con tu ordenador: solo lectura hasta que vuelva.");
  const r = await fetch(q(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.status === 401) {
    await clearOfflineCache();
    location.reload();
    throw new Error("Sesión cerrada");
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Error ${r.status}`);
  setOffline(false);
  app.onPlan(data);
  return data;
}

// Ejecuta una acción con el botón desactivado; los errores se cuentan en `say`.
export async function run(btn, say, fn) {
  if (app.offline) {
    say("Sin conexión con tu ordenador: solo lectura hasta que vuelva.");
    return;
  }
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
