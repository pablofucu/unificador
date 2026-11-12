// Avisos de cumplimiento que manda el servidor en plan.audit:
// [{level: "error"|"aviso", ref: "IN2-3" | "P-4" | "IN2/Fase", text}].
import { el } from "./util.js";
import { icon } from "./icons.js";

// Los avisos de un paso ("IN2-3"), una pregunta ("P-4") o una fase ("IN2/Fase").
export function auditFor(plan, ref) {
  return (plan && plan.audit ? plan.audit : []).filter((a) => a.ref === ref);
}

// Chip discreto con el número de avisos; el texto completo va en title y en un detalle desplegable.
// Devuelve null si no hay avisos, para poder hacer node.append(...[chip].filter(Boolean)).
export function auditChip(items) {
  if (!items || !items.length) return null;
  const bad = items.some((a) => a.level === "error");
  const chip = el("details", "audit-chip" + (bad ? " is-error" : ""));
  const sum = el("summary");
  sum.append(icon("warn"), el("span", null, String(items.length)));
  sum.setAttribute("aria-label", (bad ? "Errores" : "Avisos") + " de cumplimiento: " + items.length);
  chip.title = items.map((a) => a.text).join("\n");
  const list = el("ul", "audit-list");
  for (const a of items) list.append(el("li", a.level === "error" ? "is-error" : null, a.text));
  chip.append(sum, list);
  return chip;
}
