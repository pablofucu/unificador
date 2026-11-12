const CATS = {
  codigo: { n: "Código", i: "⌨️", c: "#4f6bed" }, interfaz: { n: "Interfaz", i: "🎨", c: "#e0559a" },
  pruebas: { n: "Pruebas", i: "🧪", c: "#1fa971" }, investigar: { n: "Investigar", i: "🔎", c: "#e8930c" },
  decidir: { n: "Decidir", i: "🤔", c: "#8b5cf6" },
};
const S = (id, t, cat, st = "p") => ({ id, t, cat, st });
// hue: el color del proyecto (ángulo oklch). Las ramas sacan de ahí sus tonos.
// steps: un array dentro del array = pasos que se hacen a la vez. needs: "RAMA/índice de fase" que tiene que acabar antes.
const DATA = [
  { id: "uni", n: "Unificador", i: "🧩", hue: 295, br: [
    { id: "PM", n: "Prompts maestros", i: "📜", ph: [
      { n: "Biblioteca de prompts", steps: [[S("PM-1", "Carpeta de prompts con unos de serie", "codigo", "w"), S("PM-2", "Verlos y copiarlos desde la web", "interfaz", "w")]] },
      { n: "Cola para los agentes", steps: [S("PM-3", "Encolar un prompt para un agente", "codigo"), S("PM-4", "Probar la cola con dos agentes a la vez", "pruebas")] }] },
    { id: "CAT", n: "Categorías de pasos", i: "🏷️", ph: [
      { n: "Qué categorías hacen falta", steps: [S("CAT-1", "Comparar cómo etiquetan otros tableros", "investigar", "d"), S("CAT-2", "Elegir la lista final de categorías", "decidir", "a")] },
      { n: "Guardarlas en el plan", steps: [[S("CAT-3", "Categoría obligatoria en cada paso", "codigo"), S("CAT-4", "Rechazar nombres de fase vagos", "codigo")], S("CAT-5", "Probar planes antiguos sin categoría", "pruebas")] },
      { n: "Enseñarlas en la web", steps: [[S("CAT-6", "Chip de color en cada paso", "interfaz"), S("CAT-7", "Mezcla de categorías por fase", "interfaz")]] }] },
    { id: "IN", n: "Interfaz nueva", i: "🎨", ph: [
      { n: "Propuestas de distribución", steps: [S("IN-1", "Seis diseños distintos para comparar", "interfaz", "d"), S("IN-2", "Elegir distribución y animaciones", "decidir", "w")] },
      { n: "Lienzo que se arrastra", needs: "CAT/1", steps: [S("IN-3", "Arrastrar y hacer zoom", "codigo"), [S("IN-4", "Pasos en paralelo sin lío", "interfaz"), S("IN-5", "Flechas de dependencia", "interfaz")]] },
      { n: "Pulido y tablet", steps: [S("IN-6", "Animaciones de entrada y cambio", "interfaz"), S("IN-7", "Probar en ordenador y tablet", "pruebas")] }] },
    { id: "TA", n: "Tablero", i: "🗂️", ph: [
      { n: "Varios proyectos", steps: [S("TA-1", "Registro de proyectos", "codigo", "d"), S("TA-2", "Abrir un proyecto por su ruta", "codigo", "d"), S("TA-3", "Probar con tres proyectos", "pruebas", "d")] },
      { n: "Portada", steps: [S("TA-4", "Tarjeta por proyecto", "interfaz", "d"), S("TA-5", "Avance en vivo", "codigo", "d")] }] }] },
  { id: "lola", n: "Tienda Lola", i: "🛍️", hue: 22, br: [
    { id: "CA", n: "Carrito de compra", i: "🛒", ph: [
      { n: "Cimientos del carrito", steps: [S("CA-1", "Modelo del carrito", "codigo", "d"), S("CA-2", "Guardar y recuperar", "codigo", "d")] },
      { n: "Pagos", steps: [S("CA-3", "Comparar pasarelas de pago", "investigar", "d"), [S("CA-4", "Conectar la pasarela", "codigo", "w"), S("CA-5", "Pantalla de pago", "interfaz", "w")], S("CA-6", "Pago fallido y reintentos", "pruebas")] },
      { n: "Recibos", steps: [S("CA-7", "Recibo por correo", "codigo")] }] },
    { id: "CT", n: "Catálogo", i: "📦", ph: [
      { n: "Fichas de producto", steps: [S("CT-1", "Plantilla de ficha", "interfaz", "d"), S("CT-2", "Elegir fotos cuadradas o verticales", "decidir", "a")] },
      { n: "Buscador", needs: "CA/0", steps: [S("CT-3", "Buscar por nombre y talla", "codigo"), S("CT-4", "Probar búsquedas con erratas", "pruebas")] }] }] },
  { id: "visor", n: "Visor de capturas", i: "🖼️", hue: 240, br: [
    { id: "EN", n: "Emparejamiento nuevo", i: "🔄", ph: [
      { n: "Estudio previo", steps: [S("EN-1", "Estudiar cómo empareja Apollo", "investigar", "d"), S("EN-2", "Maquetas del emparejamiento", "interfaz", "d")] },
      { n: "Protocolo", steps: [S("EN-3", "Solicitudes, billetes y tokens", "codigo", "w"), S("EN-4", "Pruebas del emparejamiento", "pruebas")] },
      { n: "PC principal", steps: [S("EN-5", "Pantalla de dispositivos", "interfaz"), S("EN-6", "Aviso y notificación arcoíris", "interfaz")] }] },
    { id: "MYT", n: "Magpie y tablet", i: "📱", ph: [
      { n: "Perfil y destino", steps: [S("MYT-1", "Escalado por juego y pantalla", "codigo"), S("MYT-2", "Recalcular al reconectar", "codigo")] },
      { n: "Pruebas en la tablet", needs: "EN/1", steps: [[S("MYT-3", "Probar con tres juegos", "pruebas"), S("MYT-4", "Elegir el modo por defecto", "decidir")]] }] },
    { id: "IYE", n: "Interfaz y estadísticas", i: "📊", ph: [
      { n: "Semana y Terminados", steps: [S("IYE-1", "Pestaña Semana", "interfaz"), S("IYE-2", "Pestaña Terminados", "interfaz")] },
      { n: "Colecciones", steps: [S("IYE-3", "Elegir estilo de Colecciones", "decidir", "a"), S("IYE-4", "Montar la vista elegida", "codigo")] }] }] },
  { id: "kan", n: "Kanvas", i: "📋", hue: 155, br: [
    { id: "EX", n: "Exportar tablero", i: "📤", ph: [
      { n: "Formato de salida", steps: [S("EX-1", "Mirar qué exportan Trello y Linear", "investigar", "d"), S("EX-2", "Exportar a Markdown", "codigo", "w")] },
      { n: "Comprobación", steps: [S("EX-3", "Probar con un tablero de 200 tareas", "pruebas")] }] },
    { id: "AT", n: "Atajos de teclado", i: "⌨️", ph: [
      { n: "Qué atajos", steps: [S("AT-1", "Lista de atajos que usan otros", "investigar", "d"), S("AT-2", "Elegir los diez primeros", "decidir", "d")] },
      { n: "Ponerlos", steps: [S("AT-3", "Atajos en el tablero", "codigo", "d"), S("AT-4", "Chuleta de atajos", "interfaz", "w")] }] }] },
  { id: "rec", n: "Recetario", i: "🍳", hue: 68, br: [
    { id: "LC", n: "Lista de la compra", i: "🧺", ph: [
      { n: "Ingredientes", steps: [S("LC-1", "Juntar ingredientes repetidos", "codigo", "d"), S("LC-2", "Probar con diez recetas", "pruebas", "d")] },
      { n: "Compartir la lista", steps: [S("LC-3", "Enviar la lista por enlace", "codigo"), S("LC-4", "Vista para el móvil", "interfaz")] }] }] },
  { id: "blog", n: "Blog de viajes", i: "🧭", hue: 348, br: [
    { id: "MP", n: "Mapa de rutas", i: "🗺️", ph: [
      { n: "Elegir el mapa", steps: [S("MP-1", "Comparar tres mapas gratuitos", "investigar", "d"), S("MP-2", "Elegir uno", "decidir", "d")] },
      { n: "Pintar las rutas", steps: [S("MP-3", "Ruta de cada viaje", "codigo", "w"), S("MP-4", "Fotos en cada parada", "interfaz")] }] }] },
];
// Plan arcoíris: los proyectos van ordenados por color y cada rama es un tono del color de su proyecto.
DATA.sort((a, b) => a.hue - b.hue);
const tone = (hue, t) => `oklch(${(0.5 + 0.2 * t).toFixed(3)} ${(0.19 - 0.05 * t).toFixed(3)} ${(hue + (t - 0.5) * 20).toFixed(1)})`;
for (const p of DATA) { p.c = tone(p.hue, 0.3); p.br.forEach((b, i) => { b.c = tone(p.hue, p.br.length === 1 ? 0.3 : i / (p.br.length - 1)); }); }

const STT = { d: ["✓", "Hecho"], w: ["●", "En marcha"], p: ["", "Pendiente"], a: ["?", "Espera tu decisión"] };
for (const p of DATA) for (const b of p.br) b.ph.forEach((ph, k) => { ph.key = b.id + "/" + k; ph.b = b; ph.k = k; for (const s of ph.steps.flat()) Object.assign(s, { _p: p, _b: b, _ph: ph }); });

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
const findPh = (key) => DATA.flatMap((p) => p.br).flatMap((b) => b.ph).find((x) => x.key === key);
const need = (ph) => { if (!ph.needs) return null; const t = findPh(ph.needs); return { t, ok: phSt(t) === "d" }; };
const proj = (id) => DATA.find((p) => p.id === id);
const done = (l) => l.filter((s) => s.st === "d").length;

const chip = (cat, txt) => h("span", { class: "chip", css: { "--k": CATS[cat].c } }, CATS[cat].i, " ", txt ?? CATS[cat].n);
const ring = (p, c, z = 44, label) => h("div", { class: "ring", css: { "--p": p, "--c": c, "--z": z + "px" } }, label ?? p + "%");
function mix(l) {
  const m = h("div", { class: "mix", title: "Mezcla de categorías" });
  for (const c in CATS) { const n = l.filter((s) => s.cat === c).length; if (n) m.append(h("i", { css: { "--k": CATS[c].c }, style: { flex: n } })); }
  return m;
}
function lock(ph) {
  const n = need(ph); if (!n) return null;
  return h("span", { class: "lock" + (n.ok ? " ok" : "") }, n.ok ? "✓" : "🔒", ` ${n.ok ? "Ya puede empezar: acabó" : "Espera a"} «${n.t.n}» de ${n.t.b.i} ${n.t.b.n}`);
}
// La tira arcoíris: todos los proyectos por orden de color, con los tonos de sus ramas debajo.
function rainbow(cur) {
  return h("div", { class: "rb" }, DATA.map((p) => h("button", { class: "rbp" + (p === cur ? " on" : ""), css: { "--c": p.c }, on: { click: () => go(p.id) } },
    h("span", { class: "rbn" }, p.i, " ", p.n), h("span", { class: "rbs" }, pct(psteps(p)) + "% · " + p.br.length + (p.br.length === 1 ? " rama" : " ramas")),
    h("span", { class: "rbt" }, p.br.map((b) => h("i", { title: b.n, css: { "--c": b.c } }))))));
}
const pjHead = (p, single) => h(single ? "div" : "button", { class: "pjh", on: single ? {} : { click: () => go(p.id) } },
  h("span", { class: "pji" }, p.i), h("span", { class: "pjn" }, p.n, h("small", {}, `${done(psteps(p))} de ${psteps(p).length} pasos · ${p.br.length} ${p.br.length === 1 ? "rama" : "ramas"}`)),
  ring(pct(psteps(p)), p.c, 46), !single && h("span", { class: "pjgo" }, "abrir ›"));

function sheet(s) {
  const el = document.getElementById("sheet");
  el.style.setProperty("--k", s._b.c);
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

/* ---- El mapa: tarjetas en el DOM y las vías pintadas detrás, midiendo dónde ha caído cada tarjeta ---- */
let Z = 1, BOX = null;
const R = (e) => { const w = BOX.getBoundingClientRect(), r = e.getBoundingClientRect(), l = r.left - w.left, t = r.top - w.top;
  return { l, t, r: l + r.width, b: t + r.height, cx: l + r.width / 2, cy: t + r.height / 2 }; };
const hlink = (a, b) => { const m = (a.r + b.l) / 2; return `M${a.r - 3},${a.cy}C${m},${a.cy} ${m},${b.cy} ${b.l + 3},${b.cy}`; };
const vlink = (a, b) => { const m = (a.b + b.t) / 2; return `M${a.cx},${a.b - 3}C${a.cx},${m} ${b.cx},${m} ${b.cx},${b.t + 3}`; };
const colorOf = (e) => e.closest("[data-br]").style.getPropertyValue("--c");
// Una fase que espera a otra se empuja hasta quedar después de ella, para que el enlace se lea en orden.
function alignDeps(dir) {
  const all = [...BOX.querySelectorAll("[data-needs]")]; all.forEach((e) => { e.style.marginLeft = e.style.marginTop = ""; });
  for (const to of all) {
    const from = BOX.querySelector(`[data-ph="${to.dataset.needs}"]`); if (!from) continue;
    const a = R(from), b = R(to), gap = dir === "h" ? a.r + 54 - b.l : a.b + 10 - b.t;
    if (gap > 0) to.style[dir === "h" ? "marginLeft" : "marginTop"] = gap + "px";
  }
}
// Vías de una rama: cabecera -> huecos (.slot con uno o dos [data-node]) -> final. Encendida hasta donde se ha llegado.
function rails(dir) {
  const link = dir === "h" ? hlink : vlink; let out = "", n = 0;
  for (const row of BOX.querySelectorAll("[data-br]")) {
    const c = colorOf(row); let prev = [row.querySelector(".head")];
    const seg = (a, b, on) => { out += `<path class="rail${on ? " on" : ""}" pathLength="1" style="animation-delay:${(n++ * 35)}ms" stroke="${c}" d="${link(R(a), R(b))}"/>`; };
    for (const sl of row.querySelectorAll(".slot")) {
      const cur = [...sl.querySelectorAll("[data-node]")];
      if (prev.length === cur.length) cur.forEach((e, i) => seg(prev[i], e, e.dataset.node !== "p"));
      else for (const a of prev) for (const e of cur) seg(a, e, (cur.length > 1 ? e : a).dataset.node !== "p" && e.dataset.node !== "p");
      prev = cur;
    }
    const end = row.querySelector(".end"); if (end) for (const a of prev) seg(a, end, end.classList.contains("ok"));
  }
  return out;
}
// Enlaces entre líneas: de la fase que hay que acabar a la fase que la espera.
function depLines(dir) {
  let out = "";
  for (const to of BOX.querySelectorAll("[data-needs]")) {
    const from = BOX.querySelector(`[data-ph="${to.dataset.needs}"]`); if (!from) continue;
    const a = R(from), b = R(to), c = colorOf(from); let x1, y1, x2, y2, d;
    if (dir === "h") { const dn = b.t > a.t; x1 = a.r - 36; y1 = dn ? a.b : a.t; x2 = b.l + 36; y2 = dn ? b.t : b.b; const m = (y1 + y2) / 2; d = `M${x1},${y1}C${x1},${m} ${x2},${m} ${x2},${y2}`; }
    else { const rt = b.l > a.l; x1 = rt ? a.r : a.l; y1 = a.b - 26; x2 = rt ? b.l : b.r; y2 = b.t + 26; const m = (x1 + x2) / 2; d = `M${x1},${y1}C${m},${y1} ${m},${y2} ${x2},${y2}`; }
    const sq = (x, y) => `<rect x="${x - 8}" y="${y - 8}" width="16" height="16" rx="5" fill="#fff" stroke="${c}" stroke-width="4"/>`;
    out += `<path class="dep0" d="${d}"/><path class="dep" stroke="${c}" d="${d}"/>${sq(x1, y1)}${sq(x2, y2)}`;
  }
  return out;
}
function stage(root, box, dir, fit) {
  BOX = box; box.classList.add("m-box");
  const zl = h("span", {}), setZ = () => { box.style.zoom = Z; zl.textContent = Math.round(Z * 100) + "%"; };
  const paint = () => {
    if (!box.isConnected) return; box.style.zoom = 1; box.querySelector("svg.rails")?.remove(); alignDeps(dir);
    box.insertAdjacentHTML("afterbegin", `<svg class="rails" width="${box.scrollWidth}" height="${box.scrollHeight}">${depLines(dir)}${rails(dir)}</svg>`); setZ();
  };
  const zoom = (f) => { Z = Math.min(1.6, Math.max(0.3, Z * f)); setZ(); };
  root.append(box, h("div", { class: "m-zoom" }, h("button", { on: { click: () => zoom(1 / 1.2) } }, "−"), zl, h("button", { on: { click: () => zoom(1.2) } }, "+")));
  box.addEventListener("click", (e) => { const g = e.target.closest("[data-id]"); if (g) sheet(IDX[g.dataset.id]); });
  root.onwheel = (e) => { if (e.ctrlKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1); } };
  Z = 1; paint(); if (fit) { Z = Math.min(1, Math.max(fit, (root.clientWidth - 8) / box.scrollWidth)); setZ(); }
  document.fonts?.ready.then(paint); window.onresize = paint; pan(root);
}
const IDX = {}; for (const p of DATA) for (const s of psteps(p)) IDX[s.id] = s;

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
    ...DATA.map((x) => h("button", { class: x === p ? "on" : "", css: { "--c": x.c }, on: { click: () => go(x.id) } }, h("i", { class: "dot" }), x.i + " " + x.n)));
  p ? DESIGN.project(root, p) : DESIGN.all(root);
  applyFilter();
}
function go(id) { location.hash = "/" + id; }
window.addEventListener("hashchange", render);
window.addEventListener("DOMContentLoaded", () => {
  document.querySelector(".tag").textContent = DESIGN.name;
  document.getElementById("legend").replaceChildren(...Object.keys(CATS).map((c) => {
    const e = chip(c); e.dataset.c = c; e.addEventListener("click", () => { FILTER = FILTER === c ? null : c; applyFilter(); }); return e;
  }));
  document.querySelector(".help").addEventListener("click", () => document.getElementById("gloss").classList.toggle("on"));
  render();
});
