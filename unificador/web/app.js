// Vista del plan: rama → fases → pasos. Solo lectura; se repinta en vivo.
import { renderPlan } from "./plan.js";

const $ = (id) => document.getElementById(id);
const getJSON = (url) => fetch(url).then((r) => { if (!r.ok) throw new Error(url); return r.json(); });

async function loadProject() {
  try {
    const p = await getJSON("/api/project");
    $("project-name").textContent = p.name || "Mi proyecto";
    document.title = `${p.name || "Proyecto"} · Unificador`;
  } catch { /* sin nombre, se queda el título por defecto */ }
}

async function loadPlan() {
  try { renderPlan(await getJSON("/api/plan")); }
  catch { $("branches").textContent = "No consigo leer el plan. Reintento en un momento…"; setTimeout(loadPlan, 3000); }
}

// Pestañas inferiores (pantalla estrecha)
for (const b of document.querySelectorAll(".tabs button")) {
  b.addEventListener("click", () => {
    document.body.dataset.tab = b.dataset.tab;
    for (const o of document.querySelectorAll(".tabs button")) o.setAttribute("aria-pressed", String(o === b));
  });
}

// En vivo
const events = new EventSource("/api/events");
events.addEventListener("plan", loadPlan);
events.addEventListener("sessions", () => { /* gancho: el chat refrescará aquí sus conversaciones */ });

loadProject();
loadPlan();
