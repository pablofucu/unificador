// Pinta el plan con createElement/textContent (nunca innerHTML con datos del plan).
const STATE = { pending: ["·", "Pendiente"], doing: ["▶", "En curso"], done: ["✔", "Hecho"] };
const KIND = { start: "Empezó", done: "Terminó", reopen: "Reabrió", change: "Pidió un cambio", note: "Nota" };
const open = new Set(); // ids de pasos desplegados (sobrevive a los repintados)

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

const steps = (b) => b.phases.flatMap((p) => p.steps);
const count = (list) => [list.filter((s) => s.state === "done").length, list.length];
const phaseState = (p) => (p.steps.every((s) => s.state === "done") ? "done" : p.steps.some((s) => s.state !== "pending") ? "doing" : "pending");

function when(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  return d.toLocaleString("es", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function bar(done, total) {
  const b = el("div", "bar"), i = el("i");
  i.style.width = total ? `${Math.round((done / total) * 100)}%` : "0";
  b.append(i);
  return b;
}

function section(title, ...kids) {
  const d = el("div");
  d.append(el("h4", null, title), ...kids);
  return d;
}

function detail(s) {
  const d = el("div", "detail");
  d.id = `d-${s.id}`;
  d.hidden = !open.has(s.id);
  if (s.change) d.append(Object.assign(el("div", "change-box"), { textContent: `✏️ Corrección pedida: ${s.change}` }));
  if (s.desc) d.append(section("Qué hay que hacer", el("p", null, s.desc)));
  if (s.result) d.append(section("Cómo quedó", el("p", null, s.result)));
  if (s.notes && s.notes.length) {
    const ul = el("ul", "notes");
    for (const n of s.notes) {
      const li = el("li");
      const who = el("b", null, `${KIND[n.kind] || "Nota"}${n.by ? ` · ${n.by}` : ""}`);
      const txt = el("span", null, n.text ? `: ${n.text}` : "");
      const body = el("span");
      body.append(who, txt);
      li.append(el("time", null, when(n.at)), body);
      ul.append(li);
    }
    d.append(section("Historia", ul));
  }
  d.append(el("div", "actions")); // hueco para «Corregir» y «Marcar» (siguiente paso)
  return d;
}

function step(s) {
  const li = el("li", `step ${s.state}`);
  li.dataset.id = s.id;
  const btn = el("button", "s-btn");
  btn.type = "button";
  btn.setAttribute("aria-expanded", String(open.has(s.id)));
  btn.setAttribute("aria-controls", `d-${s.id}`);
  const [mark, name] = STATE[s.state] || STATE.pending;
  const m = el("span", "s-mark", mark);
  m.title = name;
  btn.append(m, el("span", "s-title", s.title));
  if (s.state === "doing") btn.append(el("span", "badge", "En curso"));
  if (s.change) btn.append(el("span", "badge", "✏️ Corrección pedida"));
  btn.append(el("span", "chev", "›"));
  const d = detail(s);
  btn.addEventListener("click", () => {
    const now = d.hidden;
    d.hidden = !now;
    now ? open.add(s.id) : open.delete(s.id);
    btn.setAttribute("aria-expanded", String(now));
  });
  li.append(btn, d);
  return li;
}

function phase(p, i) {
  const st = phaseState(p), [done, total] = count(p.steps);
  const sec = el("section", `phase ${st}`);
  const head = el("div", "p-head");
  head.append(el("span", "p-num", `Fase ${i + 1}`), el("h3", null, `${p.icon ? p.icon + " " : ""}${p.name}`),
    el("span", "p-state", st === "done" ? "✔ Hecha" : st === "doing" ? `▶ En curso · ${done}/${total}` : "Pendiente"));
  const ul = el("ul", "steps");
  ul.append(...p.steps.map(step));
  sec.append(head, ul);
  return sec;
}

function branch(b) {
  const [done, total] = count(steps(b));
  const c = el("article", "branch");
  c.dataset.color = String((Number(b.color) || 0) % 8);
  const head = el("div", "b-head"), t = el("div");
  t.append(el("h2", null, b.name));
  if (b.goal) t.append(el("p", "muted", b.goal));
  head.append(el("div", "b-icon", b.icon || "📌"), t, el("div", "b-count", `${done} de ${total}`));
  c.append(head, bar(done, total), ...b.phases.map(phase));
  return c;
}

export function renderPlan(plan) {
  const root = document.getElementById("branches");
  const y = window.scrollY;
  const all = (plan.branches || []);
  const live = all.filter((b) => !b.archived), old = all.filter((b) => b.archived);
  const [done, total] = count(all.flatMap(steps));

  const totalBox = document.getElementById("total");
  totalBox.hidden = !total;
  document.getElementById("total-text").textContent = `${done} de ${total} pasos`;
  document.getElementById("total-bar").style.width = total ? `${Math.round((done / total) * 100)}%` : "0";
  document.getElementById("project-sub").textContent = plan.title || "";

  const nodes = [];
  if (!all.length) {
    const e = el("div", "empty");
    e.append(el("div", "big", "🌱"), el("h2", null, "Todavía no hay plan"),
      el("p", "muted", "Pídele al agente que lo prepare, desde el chat o desde la terminal: por ejemplo, «propón un plan para esto». Aparecerá aquí al momento."));
    nodes.push(e);
  }
  nodes.push(...live.map(branch));
  if (old.length) {
    const d = el("details", "archived");
    d.append(el("summary", null, `🏁 Terminadas (${old.length})`), ...old.map(branch));
    d.open = root.querySelector(".archived")?.open || false;
    nodes.push(d);
  }
  root.replaceChildren(...nodes);
  window.scrollTo(0, y);
}
