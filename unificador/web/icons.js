// Iconos SVG de la interfaz (nada de emojis). Se crean con createElementNS, sin innerHTML.
// icon("codigo") devuelve un <svg class="i"> de 24x24 que hereda el color con currentColor.

const NS = "http://www.w3.org/2000/svg";

// Cada icono: lista de [etiqueta, atributos].
const P = (d) => ["path", { d }];
const SHAPES = {
  codigo: [P("M8 7l-5 5 5 5M16 7l5 5-5 5")],
  interfaz: [["rect", { x: 3, y: 4, width: 18, height: 16, rx: 3 }], P("M3 9h18M9 9v11")],
  pruebas: [P("M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"), P("M7.5 15h9")],
  investigar: [["circle", { cx: 11, cy: 11, r: 6.5 }], P("M20 20l-4.2-4.2")],
  decidir: [P("M12 21v-8M12 13L6 7M12 13l6-6M3 7h6M15 7h6M3 7l3-3M21 7l-3-3")],
  check: [P("M5 12.5l4.5 4.5L19 7.5")],
  lock: [["rect", { x: 5, y: 11, width: 14, height: 10, rx: 2.5 }], P("M8 11V8a4 4 0 0 1 8 0v3")],
  flag: [P("M5 21V4M5 4h11l-2 4 2 4H5")],
  x: [P("M6 6l12 12M18 6L6 18")],
  down: [P("M6 9l6 6 6-6")],
  left: [P("M15 6l-6 6 6 6")],
  right: [P("M9 6l6 6-6 6")],
  ask: [["circle", { cx: 12, cy: 12, r: 9 }], P("M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17.3v.2")],
  eye: [P("M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"), ["circle", { cx: 12, cy: 12, r: 3 }]],
  pause: [P("M9 5v14M15 5v14")],
  inbox: [P("M3 13l3-8h12l3 8v6H3z"), P("M3 13h5l1 3h6l1-3h5")],
  edit: [P("M4 20h4L19 9l-4-4L4 16v4z"), P("M13.5 6.5l4 4")],
  star: [P("M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z")],
  warn: [P("M12 4L2.5 20h19z"), P("M12 10v4.5M12 17.3v.2")],
  phone: [["rect", { x: 7, y: 2.5, width: 10, height: 19, rx: 2.5 }], P("M11 18.5h2")],
  tablet: [["rect", { x: 4, y: 3, width: 16, height: 18, rx: 2.5 }], P("M11 18h2")],
  desktop: [["rect", { x: 2.5, y: 4, width: 19, height: 12.5, rx: 2 }], P("M8.5 20.5h7M12 16.5v4")],
  zoomin: [["circle", { cx: 11, cy: 11, r: 6.5 }], P("M20 20l-4.2-4.2M8 11h6M11 8v6")],
  zoomout: [["circle", { cx: 11, cy: 11, r: 6.5 }], P("M20 20l-4.2-4.2M8 11h6")],
  fit: [P("M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5")],
  sprout: [P("M12 21v-9"), P("M12 12c0-4 3-7 8-7 0 5-3 7-8 7z"), P("M12 14c0-3-2.5-5.5-7-5.5 0 4 2.5 5.5 7 5.5z")],
  grid: [["rect", { x: 3.5, y: 3.5, width: 7, height: 7, rx: 1.5 }], ["rect", { x: 13.5, y: 3.5, width: 7, height: 7, rx: 1.5 }],
    ["rect", { x: 3.5, y: 13.5, width: 7, height: 7, rx: 1.5 }], ["rect", { x: 13.5, y: 13.5, width: 7, height: 7, rx: 1.5 }]],
  logout: [P("M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9")],
};

export const ICONS = Object.keys(SHAPES);

export function icon(name, cls) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", cls ? "i " + cls : "i");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  for (const [tag, attrs] of SHAPES[name] || SHAPES.ask) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    svg.append(n);
  }
  return svg;
}

// Las cinco categorías de los pasos, con su nombre y su color (iguales que en la maqueta).
export const CATS = {
  codigo: { name: "Código", color: "#4f6bed" },
  interfaz: { name: "Interfaz", color: "#e0559a" },
  pruebas: { name: "Pruebas", color: "#1fa971" },
  investigar: { name: "Investigar", color: "#e8930c" },
  decidir: { name: "Decidir", color: "#8b5cf6" },
};
