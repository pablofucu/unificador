const CATS = {
  codigo: { n: "Código", i: "⌨️", c: "#4f6bed" }, interfaz: { n: "Interfaz", i: "🎨", c: "#e0559a" },
  pruebas: { n: "Pruebas", i: "🧪", c: "#1fa971" }, investigar: { n: "Investigar", i: "🔎", c: "#e8930c" },
  decidir: { n: "Decidir", i: "🤔", c: "#8b5cf6" },
};
const S = (id, t, cat, st = "p") => ({ id, t, cat, st });
// steps: un array dentro del array = pasos que se hacen a la vez. needs: "RAMA/índice de fase" que tiene que acabar antes.
const DATA = [
  { id: "uni", n: "Unificador", i: "🧩", c: "#6c5ce7", br: [
    { id: "PM", n: "Prompts maestros", i: "📜", c: "#0ea5b7", ph: [
      { n: "Biblioteca de prompts", steps: [[S("PM-1", "Carpeta de prompts con unos de serie", "codigo", "w"), S("PM-2", "Verlos y copiarlos desde la web", "interfaz", "w")]] },
      { n: "Cola para los agentes", steps: [S("PM-3", "Encolar un prompt para un agente", "codigo"), S("PM-4", "Probar la cola con dos agentes a la vez", "pruebas")] }] },
    { id: "CAT", n: "Categorías de pasos", i: "🏷️", c: "#f2711c", ph: [
      { n: "Qué categorías hacen falta", steps: [S("CAT-1", "Comparar cómo etiquetan otros tableros", "investigar", "d"), S("CAT-2", "Elegir la lista final de categorías", "decidir", "a")] },
      { n: "Guardarlas en el plan", steps: [[S("CAT-3", "Categoría obligatoria en cada paso", "codigo"), S("CAT-4", "Rechazar nombres de fase vagos", "codigo")], S("CAT-5", "Probar planes antiguos sin categoría", "pruebas")] },
      { n: "Enseñarlas en la web", steps: [[S("CAT-6", "Chip de color en cada paso", "interfaz"), S("CAT-7", "Mezcla de categorías por fase", "interfaz")]] }] },
    { id: "IN", n: "Interfaz nueva", i: "🎨", c: "#d6409f", ph: [
      { n: "Propuestas de distribución", steps: [S("IN-1", "Seis diseños distintos para comparar", "interfaz", "w"), S("IN-2", "Elegir distribución y animaciones", "decidir")] },
      { n: "Lienzo que se arrastra", needs: "CAT/1", steps: [S("IN-3", "Arrastrar y hacer zoom", "codigo"), [S("IN-4", "Pasos en paralelo sin lío", "interfaz"), S("IN-5", "Flechas de dependencia", "interfaz")]] },
      { n: "Pulido y tablet", steps: [S("IN-6", "Animaciones de entrada y cambio", "interfaz"), S("IN-7", "Probar en ordenador y tablet", "pruebas")] }] },
    { id: "TA", n: "Tablero", i: "🗂️", c: "#3b82f6", ph: [
      { n: "Varios proyectos", steps: [S("TA-1", "Registro de proyectos", "codigo", "d"), S("TA-2", "Abrir un proyecto por su ruta", "codigo", "d"), S("TA-3", "Probar con tres proyectos", "pruebas", "d")] },
      { n: "Portada", steps: [S("TA-4", "Tarjeta por proyecto", "interfaz", "d"), S("TA-5", "Avance en vivo", "codigo", "d")] }] }] },
  { id: "lola", n: "Tienda Lola", i: "🛍️", c: "#e0445e", br: [
    { id: "CA", n: "Carrito de compra", i: "🛒", c: "#e0445e", ph: [
      { n: "Cimientos del carrito", steps: [S("CA-1", "Modelo del carrito", "codigo", "d"), S("CA-2", "Guardar y recuperar", "codigo", "d")] },
      { n: "Pagos", steps: [S("CA-3", "Comparar pasarelas de pago", "investigar", "d"), [S("CA-4", "Conectar la pasarela", "codigo", "w"), S("CA-5", "Pantalla de pago", "interfaz", "w")], S("CA-6", "Pago fallido y reintentos", "pruebas")] },
      { n: "Recibos", steps: [S("CA-7", "Recibo por correo", "codigo")] }] },
    { id: "CT", n: "Catálogo", i: "📦", c: "#16a34a", ph: [
      { n: "Fichas de producto", steps: [S("CT-1", "Plantilla de ficha", "interfaz", "d"), S("CT-2", "Elegir fotos cuadradas o verticales", "decidir", "a")] },
      { n: "Buscador", needs: "CA/0", steps: [S("CT-3", "Buscar por nombre y talla", "codigo"), S("CT-4", "Probar búsquedas con erratas", "pruebas")] }] }] },
  { id: "kan", n: "Kanvas", i: "📋", c: "#0d9488", br: [
    { id: "EX", n: "Exportar tablero", i: "📤", c: "#0d9488", ph: [
      { n: "Formato de salida", steps: [S("EX-1", "Mirar qué exportan Trello y Linear", "investigar", "d"), S("EX-2", "Exportar a Markdown", "codigo", "w")] },
      { n: "Comprobación", steps: [S("EX-3", "Probar con un tablero de 200 tareas", "pruebas")] }] }] },
];
const STT = { d: ["✔", "Hecho"], w: ["●", "En marcha"], p: ["", "Pendiente"], a: ["?", "Espera tu decisión"] };
for (const p of DATA) for (const b of p.br) b.ph.forEach((ph, k) => { ph.key = b.id + "/" + k; ph.b = b; for (const s of ph.steps.flat()) Object.assign(s, { _p: p, _b: b, _ph: ph }); });

function h(t, a, ...k) {
  const e = document.createElement(t);
  for (const x in a || {}) {
    if (x === "on") for (const ev in a.on) e.addEventListener(ev, a.on[ev]);
    else if (x === "style") Object.assign(e.style, a[x]);
    else if (x === "css") for (const v in a.css) e.style.setProperty(v, a.css[v]);
    else if (x === "html") e.innerHTML = a[x];
    else if (a[x] != null && a[x] !== false) e.setAttribute(x, a[x]);
  }
  for (const c of k.flat(9)) if (c != null && c !== false) e.append(c.nodeType ? c : String(c));
  return e;
}
const flat = (ph) => ph.steps.flat();
const bsteps = (b) => b.ph.flatMap(flat);
const psteps = (p) => p.br.flatMap(bsteps);
const pct = (l) => Math.round(100 * l.filter((s) => s.st === "d").length / l.length);
const phSt = (ph) => { const l = flat(ph); return l.every((s) => s.st === "d") ? "d" : l.some((s) => s.st !== "p") ? "w" : "p"; };
const findPh = (p, key) => p.br.flatMap((b) => b.ph).find((x) => x.key === key);
const need = (p, ph) => { if (!ph.needs) return null; const t = findPh(p, ph.needs); return { t, ok: phSt(t) === "d" }; };
const active = (l) => l.filter((s) => s.st === "w" || s.st === "a");
const proj = (id) => DATA.find((p) => p.id === id);

const chip = (cat, txt) => h("span", { class: "chip", css: { "--k": CATS[cat].c } }, CATS[cat].i, " ", txt ?? CATS[cat].n);
const ring = (p, c, z = 44, label) => h("div", { class: "ring", css: { "--p": p, "--c": c, "--z": z + "px" } }, label ?? p + "%");
function mix(l) {
  const m = h("div", { class: "mix", title: "Mezcla de categorías" });
  for (const c in CATS) { const n = l.filter((s) => s.cat === c).length; if (n) m.append(h("i", { css: { "--k": CATS[c].c }, style: { flex: n } })); }
  return m;
}
const seg = (b) => h("div", { class: "seg" }, b.ph.map((ph) => h("i", { title: ph.n, css: { "--w": flat(ph).length, "--p": pct(flat(ph)), "--c": b.c } })));
function lock(p, ph) {
  const n = need(p, ph); if (!n) return null;
  return h("span", { class: "lock" + (n.ok ? " ok" : "") }, n.ok ? "✔" : "🔒", ` ${n.ok ? "Ya puede:" : "Espera a"} «${n.t.n}» de ${n.t.b.i}`);
}
function stepCard(s, short) {
  return h("button", { class: "s st-" + s.st, "data-cat": s.cat, css: { "--k": CATS[s.cat].c }, title: CATS[s.cat].n, on: { click: () => sheet(s) } },
    h("span", { class: "si" }, CATS[s.cat].i), h("span", { class: "stt" }, s.t, !short && h("span", { class: "sid" }, s.id + " · " + CATS[s.cat].n)),
    h("span", { class: "sst" }, STT[s.st][0]));
}
// Un hueco de fase: paso suelto o grupo «a la vez».
const slot = (x, short) => Array.isArray(x) ? h("div", { class: "par" }, x.map((s) => stepCard(s, short))) : stepCard(x, short);

function sheet(s) {
  const el = document.getElementById("sheet");
  el.style.setProperty("--k", CATS[s.cat].c);
  el.replaceChildren(h("button", { class: "x", on: { click: () => el.classList.remove("on") } }, "✕"),
    chip(s.cat), " ", h("span", { class: "tag" }, STT[s.st][1]), h("h3", {}, s.t),
    h("p", {}, `${s._p.i} ${s._p.n} › ${s._b.i} ${s._b.n} › fase «${s._ph.n}»`), h("p", {}, `Paso ${s.id}`));
  el.classList.add("on");
}
// Arrastrar con el ratón para moverse (con el dedo ya se desliza solo).
function pan(el) {
  if (el._pan) return; el._pan = 1;
  let d = null, moved = false; el.classList.add("grab");
  el.addEventListener("pointerdown", (e) => { if (e.pointerType === "mouse") { d = { x: e.clientX, y: e.clientY, l: el.scrollLeft, t: el.scrollTop }; moved = false; } });
  window.addEventListener("pointermove", (e) => {
    if (!d) return; const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (!moved && Math.hypot(dx, dy) < 5) return; moved = true; el.classList.add("drag"); el.scrollLeft = d.l - dx; el.scrollTop = d.t - dy;
  });
  window.addEventListener("pointerup", () => { d = null; el.classList.remove("drag"); });
  el.addEventListener("click", (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
}
// Flechas de dependencia entre [data-ph] y [data-needs] dentro de wrap (position:relative). dir: "h" o "v".
function drawDeps(wrap, p, dir = "h") {
  wrap.querySelector("svg.deps")?.remove();
  const w = wrap.getBoundingClientRect(), box = (e) => { const r = e.getBoundingClientRect(); return { l: r.left - w.left + wrap.scrollLeft, t: r.top - w.top + wrap.scrollTop, w: r.width, h: r.height }; };
  let d = "";
  for (const to of wrap.querySelectorAll("[data-needs]")) {
    const from = wrap.querySelector(`[data-ph="${to.dataset.needs}"]`); if (!from) continue;
    const a = box(from), b = box(to), ok = phSt(findPh(p, to.dataset.needs)) === "d", col = ok ? "#1fa971" : "#f59e0b";
    let x1, y1, x2, y2, c;
    if (dir === "h") { x1 = a.l + a.w; y1 = a.t + a.h / 2; x2 = b.l; y2 = b.t + b.h / 2; if (x2 < x1 + 20) { x1 = a.l + a.w / 2; y1 = y2 > y1 ? a.t + a.h : a.t; x2 = b.l + 30; y2 = y2 > y1 ? b.t : b.t + b.h; c = `C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2}`; } else c = `C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2}`; }
    else { x1 = a.l + a.w / 2; y1 = a.t + a.h; x2 = b.l + b.w / 2; y2 = b.t; if (y2 < y1 + 10) { x1 = x2 > x1 ? a.l + a.w : a.l; y1 = a.t + a.h / 2; x2 = x2 > x1 ? b.l : b.l + b.w; y2 = b.t + 24; c = `C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2}`; } else c = `C${x1},${(y1 + y2) / 2} ${x2},${(y1 + y2) / 2}`; }
    d += `<path d="M${x1},${y1} ${c} ${x2},${y2}" stroke="${col}"/><circle cx="${x1}" cy="${y1}" r="5" fill="${col}"/><circle cx="${x2}" cy="${y2}" r="6" fill="#fff" stroke="${col}" stroke-width="3"/>`;
  }
  if (d) wrap.insertAdjacentHTML("beforeend", `<svg class="deps" width="${wrap.scrollWidth}" height="${wrap.scrollHeight}">${d}</svg>`);
}

const depsSoon = (w, p, dir) => { const f = () => w.isConnected && drawDeps(w, p, dir); requestAnimationFrame(f); setTimeout(f, 800); };
const cut = (t, n) => t.length > n ? t.slice(0, n - 1).trimEnd() + "…" : t;
let FILTER = null;
function applyFilter() {
  document.querySelectorAll("[data-cat]").forEach((e) => e.classList.toggle("dim", !!FILTER && e.dataset.cat !== FILTER));
  document.querySelectorAll("#legend .chip").forEach((e) => e.classList.toggle("on", e.dataset.c === FILTER));
}
function render() {
  const id = location.hash.slice(2), p = proj(id), root = document.getElementById("root");
  document.getElementById("sheet").classList.remove("on");
  root.replaceChildren(); root.scrollTo(0, 0); root.className = p ? "v-project" : "v-all";
  document.getElementById("nav").replaceChildren(
    h("button", { class: p ? "" : "on", on: { click: () => go("") } }, "Todos los proyectos"),
    ...DATA.map((x) => h("button", { class: x === p ? "on" : "", on: { click: () => go(x.id) } }, x.i + " " + x.n)));
  p ? DESIGN.project(root, p) : DESIGN.all(root);
  applyFilter();
}
function go(id) { location.hash = "/" + id; }
window.addEventListener("hashchange", () => document.startViewTransition ? document.startViewTransition(render) : render());
window.addEventListener("DOMContentLoaded", () => {
  document.querySelector(".tag").textContent = DESIGN.name;
  document.getElementById("legend").replaceChildren(...Object.keys(CATS).map((c) => {
    const e = chip(c); e.dataset.c = c; e.addEventListener("click", () => { FILTER = FILTER === c ? null : c; applyFilter(); }); return e;
  }));
  document.querySelector(".help").addEventListener("click", () => document.getElementById("gloss").classList.toggle("on"));
  render();
});
