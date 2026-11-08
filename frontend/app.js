// Rama → Fase → Paso. Estados: pend, run, toca, hecho.
let RAMAS = [];
let JOIN = { name: 'Juntarlo todo', steps: [['Unir las ramas', 'pend', null]] };
// Agentes conocidos por la interfaz; cuáles se pueden usar lo dice /api/status.
const AGENTS = {
  claude_code: { label: 'Claude', icon: '✳', color: '#b84a33' },
  antigravity: { label: 'Antigravity', icon: '▲', color: '#3b6fe0' },
  codex: { label: 'Codex', icon: '◉', color: '#0a7d5f' },
  deepseek: { label: 'DeepSeek', icon: '◆', color: '#3f5ae0' },
};
let agent = 'claude_code', ai = 'Claude', sel = null, open = null;

const $ = (id) => document.getElementById(id);
const ST_NAME = { pend: 'Pendiente', run: 'Trabajando', toca: 'Te toca', hecho: 'Hecho' };
const st = (s) => `<span class="st st-${s}" role="img" aria-label="${ST_NAME[s] || ''}"></span>`;
const faseState = (f) => f.steps.every((s) => s[1] === 'hecho') ? 'done'
  : f.steps.some((s) => s[1] === 'toca') ? 'toca'
  : f.steps.some((s) => s[1] !== 'pend') ? 'now' : 'wait';
const label = { hecho: '', run: 'trabajando', pend: '' };

function faseHTML(f, key, color) {
  const state = faseState(f), done = f.steps.filter((s) => s[1] === 'hecho').length;
  const steps = f.steps.map((s, i) => {
    const isSel = sel && `${sel.r}-${sel.f}` === key && sel.s === i;
    const prop = s[3] && s[3].board_state === 'proposed';
    const extra = s[1] === 'toca' ? '<span class="go">Revisar</span>' : s[1] === 'run' ? `<span class="who">${ai}</span>` : prop ? '<span class="prop-tag">propuesto</span>' : '';
    return `<button class="step${isSel ? ' sel' : ''}${prop ? ' prop' : ''}" aria-pressed="${!!isSel}" data-k="${key}" data-s="${i}">${st(s[1])}<span>${esc(s[0])}</span>${extra}</button>`;
  }).join('');
  return `<div class="fase ${state}${open === key ? ' open' : ''}" style="--r:${color}" data-key="${key}">
    <button class="f-head" aria-expanded="${open === key}" data-open="${key}"><b>${esc(f.name)}</b><span class="n">${done}/${f.steps.length}</span></button>
    <div class="f-dots">${f.steps.map((s) => st(s[1])).join('')}</div>
    <div class="f-steps">${steps}</div></div>`;
}

function render() {
  const grid = $('grid');
  let html = '<svg class="wires" id="wires"></svg>';
  RAMAS.forEach((r, ri) => {
    const done = r.fases.flatMap((f) => f.steps).filter((s) => s[1] === 'hecho').length;
    const total = r.fases.flatMap((f) => f.steps).length;
    html += `<div class="r-name" style="--r:${r.color};grid-row:${ri + 1}"><i></i><span>${esc(r.name)}<br><small>${done} de ${total} pasos</small></span></div>`;
    html += `<div class="track" style="--r:${r.color};grid-row:${ri + 1}" data-row="${ri}">`;
    r.fases.forEach((f, fi) => {
      if (fi) {
        const prev = faseState(r.fases[fi - 1]), cur = faseState(f);
        const cls = prev === 'done' && cur !== 'wait' ? (cur === 'done' ? '' : 'live') : 'next';
        html += `<span class="link ${cls}"></span>`;
      }
      html += faseHTML(f, `${ri}-${fi}`, r.color);
    });
    const allDone = r.fases.every((f) => faseState(f) === 'done');
    html += `<span class="tail${allDone ? ' done' : ''}"></span></div>`;
  });
  html += RAMAS.length
    ? `<div class="join">${faseHTML(JOIN, 'j-0', '#5b5fd6')}</div>`
    : `<p class="empty">${project ? 'Este proyecto aún no tiene pasos. Cuéntale a la IA qué quieres hacer.' : 'Elige un proyecto en «Mis proyectos».'}</p>`;
  grid.innerHTML = html;
  wire(); chatHead(); counts(); planCard();
}

function wire() {
  const svg = $('wires'), g = $('grid').getBoundingClientRect();
  const joinEl = document.querySelector('.join .fase');
  if (!joinEl) { svg.innerHTML = ''; return; }
  const join = joinEl.getBoundingClientRect();
  const jx = join.left - g.left, jy = join.top - g.top + 32;
  svg.setAttribute('width', g.width); svg.setAttribute('height', g.height);
  svg.innerHTML = [...document.querySelectorAll('.track')].map((t) => {
    const r = RAMAS[+t.dataset.row], tail = t.querySelector('.tail').getBoundingClientRect();
    const x = tail.right - g.left, y = tail.top - g.top + 2, mx = (x + jx) / 2;
    const done = r.fases.every((f) => faseState(f) === 'done');
    return `<path d="M${x} ${y} C${mx} ${y} ${mx} ${jy} ${jx} ${jy}" fill="none" stroke="${r.color}" stroke-width="4" stroke-linecap="round" ${done ? '' : 'stroke-dasharray="7 6" stroke-opacity=".5"'}/>`;
  }).join('');
}

function stepAt(k, s) {
  if (k === 'j-0') return { r: { name: 'Final', color: '#5b5fd6' }, f: JOIN, step: JOIN.steps[s] };
  const [ri, fi] = k.split('-').map(Number);
  return { r: RAMAS[ri], f: RAMAS[ri].fases[fi], step: RAMAS[ri].fases[fi].steps[s] };
}

function chatHead() {
  const k = sel ? (sel.r === 'j' ? 'j-0' : `${sel.r}-${sel.f}`) : null;
  const x = k ? stepAt(k, sel.s) : null;
  $('where').style.setProperty('--wr', x ? x.r.color : '#7a5af8');
  $('where').innerHTML = x ? `<i></i>${esc(x.r.name)} › ${esc(x.f.name)} › <b>${esc(x.step[0])}</b>` : '<i></i><b>Todo el proyecto</b>';
  $('ctx').innerHTML = x ? `Sobre: ${esc(x.step[0])} <button id="clr" title="Quitar">✕</button>` : 'Sobre: todo el proyecto';
  const c = $('clr'); if (c) c.onclick = () => { sel = null; render(); };
  reportCard(x);
}

// ── Git: guardar versión y subir (/api/git/*) ──
const GIT_LABEL = { M: 'cambiado', A: 'nuevo', D: 'borrado', R: 'renombrado', '?': 'nuevo', '??': 'nuevo' };
let git = null, gitMsg = null, gitErr = null;
async function loadGit() {
  if (!project) return;
  const id = project.id;
  try {
    const g = await api(`/api/git/status?project_id=${encodeURIComponent(id)}`);
    if (!project || project.id !== id) return;
    const same = JSON.stringify(g) === JSON.stringify(git);
    git = g; gitErr = null; gitPill();
    if (!same && !$('gitPanel').hidden) drawGit();
  } catch (e) { git = null; gitErr = e.message; gitPill(); if (!$('gitPanel').hidden) drawGit(); }
}
function gitPill() {
  const b = $('gitBtn');
  if (gitErr) { $('gitLbl').textContent = 'Sin conexión'; b.classList.remove('dirty'); return; }
  if (!git || !git.is_repo) { $('gitLbl').textContent = 'Sin versiones'; b.classList.remove('dirty'); return; }
  const n = git.changed_count;
  $('gitLbl').textContent = n ? `${n} sin guardar` : git.ahead ? `${git.ahead} sin subir` : 'Al día';
  b.classList.toggle('dirty', n > 0 || git.ahead > 0);
}
function gitDefaultMsg() {
  const k = sel ? (sel.r === 'j' ? 'j-0' : `${sel.r}-${sel.f}`) : null;
  const x = k ? stepAt(k, sel.s) : null;
  return x && x.step[2] ? { id: x.step[2], title: x.step[0], phase: x.r.name } : { id: 'GENERAL', title: '', phase: '' };
}
function drawGit() {
  const P = $('gitPanel');
  if (gitErr) { P.innerHTML = `<p class="gmsg err">${esc(gitErr)}</p>`; return; }
  if (!git || !git.is_repo) {
    P.innerHTML = '<p class="muted">Esta carpeta todavía no usa Git, así que no se pueden guardar versiones desde aquí.</p>';
    return;
  }
  const keep = { t: P.querySelector('#gitTitle')?.value };
  const d = gitDefaultMsg();
  const files = git.files.slice(0, 8).map((f) => `<li><span class="gs">${esc(GIT_LABEL[f.status] || f.status)}</span> ${esc(f.file)}</li>`).join('');
  const more = git.files.length > 8 ? `<li class="muted">… y ${git.files.length - 8} más</li>` : '';
  P.innerHTML = `<div class="gh"><b>Versiones</b><span class="muted">rama ${esc(git.branch)}</span></div>
    ${git.clean ? '<p class="muted">Todo está guardado.</p>' : `<ul class="gfiles">${files}${more}</ul>
    <label class="gl">¿Qué has cambiado?<input id="gitTitle" maxlength="120" placeholder="${esc(d.title || 'Actualización')}"></label>
    <p class="muted gprev" id="gitPrev"></p>
    <button class="b1" id="gitCommit">Guardar versión</button>`}
    ${git.has_remote ? `<button class="b2" id="gitPush" ${git.ahead ? '' : 'disabled'}>Subir a GitHub${git.ahead ? ` (${git.ahead})` : ''}</button>` : '<p class="muted">Sin GitHub conectado: las versiones quedan solo en tu ordenador.</p>'}
    <p class="gmsg" role="status" ${gitMsg ? '' : 'hidden'}>${gitMsg ? esc(gitMsg.text) : ''}</p>`;
  const m = P.querySelector('.gmsg'); if (gitMsg) m.classList.toggle('err', !!gitMsg.err);
  const ti = P.querySelector('#gitTitle');
  if (ti) {
    if (keep.t) ti.value = keep.t;
    const prev = () => {
      const t = ti.value.trim() || d.title || 'Actualización';
      $('gitPrev').textContent = `Se guardará como: ${d.phase ? `[${d.phase}] ` : ''}${d.id}: ${t}`;
    };
    ti.oninput = prev; prev();
    ti.onkeydown = (e) => { if (e.key === 'Enter') $('gitCommit').click(); };
    $('gitCommit').onclick = (e) => gitAct(e.target, '/api/git/commit', { task_id: d.id, title: ti.value.trim() || d.title || 'Actualización', phase: d.phase || undefined, author: 'usuario' }, 'Versión guardada.');
  }
  const push = P.querySelector('#gitPush');
  if (push) push.onclick = (e) => gitAct(e.target, '/api/git/push', {}, 'Subido a GitHub.');
}
async function gitAct(btn, url, extra, ok) {
  btn.disabled = true; gitMsg = { text: 'Un momento…' }; drawGit();
  try {
    const r = await api(url, { project_id: project.id, ...extra });
    gitMsg = { text: /^No hab/.test(r.message || '') ? r.message : ok };
  } catch (e) { gitMsg = { text: e.message, err: true }; }
  git = null; await loadGit(); drawGit();
}
$('gitBtn').onclick = () => {
  const P = $('gitPanel'), show = P.hidden;
  P.hidden = !show; $('gitBtn').setAttribute('aria-expanded', show);
  if (show) { gitMsg = null; drawGit(); loadGit(); }
};
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('gitPanel').hidden) { $('gitPanel').hidden = true; $('gitBtn').setAttribute('aria-expanded', false); $('gitBtn').focus(); } });
document.addEventListener('click', (e) => { if (!$('gitPanel').hidden && !e.target.closest('#gitPanel, #gitBtn')) { $('gitPanel').hidden = true; $('gitBtn').setAttribute('aria-expanded', false); } });

// ── Informe y «¿Te vale?» ──
function reportCard(x) {
  const step = x && x.step[1] === 'toca' ? x.step : null;
  const old = $('report');
  if (!step) { if (old) old.remove(); return; }
  const info = step[3] || {}, key = `${project && project.id}|${step[2]}|${info.last_note}`;
  if (old && old.dataset.key === key) return;  // sin cambios: se conserva lo que la persona esté escribiendo
  if (old) old.remove();
  const c = document.createElement('div');
  c.className = 'card toca'; c.id = 'report'; c.dataset.key = key;
  const body = info.last_note || info.description || 'La IA ha terminado este paso y espera tu visto bueno.';
  c.innerHTML = `<div class="tag"><span class="st st-toca"></span> Te toca · ${esc(x.r.name)} › ${esc(x.f.name)}</div>
    <h3></h3><p class="muted rep-body"></p><p class="ask">¿Te vale?</p>
    <div class="btns"><button class="b1" id="okBtn">Sí, sigue</button><button class="b2" id="chgBtn">Cambia esto…</button></div>
    <div class="chg" hidden><textarea id="chgTxt" rows="3" placeholder="¿Qué quieres que cambie?"></textarea>
    <div class="btns"><button class="b1" id="chgSend">Devolver</button><button class="b2" id="chgCancel">Cancelar</button></div></div>
    <p class="rep-err" role="alert" hidden></p>`;
  c.querySelector('h3').textContent = step[0];
  c.querySelector('.rep-body').textContent = body;
  const err = c.querySelector('.rep-err'), chg = c.querySelector('.chg');
  const act = async (what, payload, btns) => {
    err.hidden = true; btns.forEach((b) => b.disabled = true);
    try {
      await api(`/api/projects/${encodeURIComponent(project.id)}/tasks/${encodeURIComponent(step[2])}/${what}`, payload);
      lastKey = ''; await loadItinerary();
    } catch (e) { err.textContent = e.message; err.hidden = false; btns.forEach((b) => b.disabled = false); }
  };
  c.querySelector('#okBtn').onclick = (e) => act('accept', {}, [e.target, c.querySelector('#chgBtn')]);
  c.querySelector('#chgBtn').onclick = () => { chg.hidden = false; c.querySelector('#chgTxt').focus(); };
  c.querySelector('#chgCancel').onclick = () => { chg.hidden = true; };
  c.querySelector('#chgSend').onclick = (e) => {
    const t = c.querySelector('#chgTxt').value.trim();
    if (!t) { err.textContent = 'Cuéntale a la IA qué quieres cambiar.'; err.hidden = false; return; }
    act('send-back', { comment: t }, [e.target]);
  };
  $('msgs').prepend(c);
}

// ── Plan propuesto por la IA: la persona lo aprueba (proposed → todo) ──
function proposedSteps() {
  const out = [];
  RAMAS.forEach((r) => r.fases.forEach((f) => f.steps.forEach((x) => {
    if (x[3] && x[3].board_state === 'proposed') out.push({ rama: r.name, fase: f.name, title: x[0], id: x[2] });
  })));
  return out;
}
function planCard() {
  const steps = project ? proposedSteps() : [], old = $('planCard');
  const key = steps.map((x) => x.id).join(',');
  if (!steps.length) { if (old) old.remove(); return; }
  if (old && old.dataset.key === key) return;
  if (old) old.remove();
  const ramas = [...new Set(steps.map((x) => x.rama))];
  const c = document.createElement('div');
  c.className = 'card plan'; c.id = 'planCard'; c.dataset.key = key;
  c.innerHTML = `<div class="tag">Plan propuesto por la IA</div>
    <h3>${steps.length} paso${steps.length > 1 ? 's' : ''} en ${ramas.length} rama${ramas.length > 1 ? 's' : ''}</h3>
    <ol>${steps.slice(0, 8).map((x) => `<li>${esc(x.title)} <small>· ${esc(x.rama)} › ${esc(x.fase)}</small></li>`).join('')}${steps.length > 8 ? `<li><small>y ${steps.length - 8} más en el tablero</small></li>` : ''}</ol>
    <p class="ask">¿Empezamos con este plan?</p>
    <div class="btns"><button class="b1" id="planOk">Aprobar plan</button><button class="b2" id="planChg">Pedir cambios…</button></div>
    <p class="rep-err" role="alert" hidden></p>`;
  const err = c.querySelector('.rep-err');
  c.querySelector('#planOk').onclick = async (e) => {
    e.target.disabled = true; err.hidden = true;
    try {
      const r = await api(`/api/projects/${encodeURIComponent(project.id)}/plan/approve`, { ids: steps.map((x) => x.id) });
      sysMsg(`Plan aprobado (${r.approved.length} pasos). Dile a la IA que empiece por la fase 1.`);
      if (!$('ta').value) $('ta').value = 'Plan aprobado. Empieza por la fase 1.';
      lastKey = ''; await loadItinerary(); $('ta').focus();
    } catch (x) { err.textContent = x.message; err.hidden = false; e.target.disabled = false; }
  };
  c.querySelector('#planChg').onclick = () => { $('ta').value = 'Antes de aprobar el plan, cambia esto: '; $('ta').focus(); };
  $('msgs').prepend(c);
}

function counts() {
  const all = RAMAS.flatMap((r) => r.fases).flatMap((f) => f.steps);
  $('nToca').textContent = all.filter((s) => s[1] === 'toca').length;
  $('nRun').textContent = all.filter((s) => s[1] === 'run').length;
  const done = all.filter((s) => s[1] === 'hecho').length;
  $('psub').textContent = `${done} de ${all.length} pasos hechos`;
}

function setAI(id) {
  agent = id; ai = AGENTS[id].label;
  document.querySelectorAll('.prov').forEach((b) => { b.classList.toggle('on', b.dataset.ai === id); b.setAttribute('aria-pressed', b.dataset.ai === id); });
  document.documentElement.style.setProperty('--ai', AGENTS[id].color);
  $('ta').placeholder = `Escribe a ${ai}…`;
  $('sig').textContent = `${AGENTS[id].icon} ${ai}`;
  drawConvs();
  render();
}
async function loadAgents() {
  let adapters = {};
  try { adapters = (await api('/api/status')).adapters || {}; } catch (e) { /* sin conexión: se avisa al enviar */ }
  const ids = Object.keys(AGENTS).filter((id) => id in adapters);
  $('chat').querySelector('.rail').innerHTML = ids.map((id) => {
    const a = AGENTS[id], ok = adapters[id].installed;
    return `<button class="prov" data-ai="${id}" style="--f:${a.color}" ${ok ? '' : 'disabled'} title="${ok ? esc(adapters[id].name) : 'No está instalado'}"><i>${a.icon}</i>${a.label}</button>`;
  }).join('');
  installed = ids.filter((id) => adapters[id].installed);
  const pref = project && installed.includes(project.default_agent) ? project.default_agent : installed[0];
  if (pref) setAI(pref); else setAI(agent);
}

document.addEventListener('click', (e) => {
  const o = e.target.closest('[data-open]');
  if (o) { open = open === o.dataset.open ? null : o.dataset.open; render(); return; }
  const s = e.target.closest('.step');
  if (s) { const [a, b] = s.dataset.k.split('-'); sel = { r: a === 'j' ? 'j' : +a, f: +b, s: +s.dataset.s }; sel.id = stepAt(s.dataset.k, sel.s).step[2]; render(); return; }
  const p = e.target.closest('.prov');
  if (p && !p.disabled) setAI(p.dataset.ai);
});
$('tocaBtn').onclick = () => {
  for (const [ri, r] of RAMAS.entries()) for (const [fi, f] of r.fases.entries()) {
    const si = f.steps.findIndex((x) => x[1] === 'toca');
    if (si >= 0) { open = `${ri}-${fi}`; sel = { r: ri, f: fi, s: si, id: f.steps[si][2] }; return render(); }
  }
};
// ── Mis proyectos (datos reales de /api/projects) ──
const COLORS = ['#7a5af8', '#0e9f9a', '#e0457b', '#e0902c', '#3b6fe0'];
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let projects = [], project = null, creating = false, installed = [];

async function api(url, body) {
  const r = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined)
    .catch(() => { throw new Error('No hay conexión con el servidor. Comprueba que Unificador sigue abierto.'); });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || data.message || 'Algo ha fallado. Inténtalo de nuevo.');
  return data;
}

function newCard() {
  if (!creating) return '<button class="pcard new" data-new>＋ Nuevo proyecto</button>';
  return `<form class="pcard new-form" id="newForm">
    <h3>Nuevo proyecto</h3>
    <label>Nombre<input id="newName" required maxlength="60" autocomplete="off" placeholder="Mi proyecto"></label>
    <details><summary>Carpeta (opcional)</summary>
      <input id="newPath" autocomplete="off" placeholder="Si lo dejas vacío, se crea una"></details>
    <p class="err" id="newErr" role="alert"></p>
    <div class="row"><button type="submit" class="ok">Crear</button><button type="button" data-cancel>Cancelar</button></div>
  </form>`;
}

function renderCards(msg) {
  const list = projects.length
    ? projects.map((p, i) => {
        const v = Math.round(p.progress || 0);
        return `<button class="pcard" style="--p:${esc(p.color_theme)}" data-p="${i}"><h3><i></i>${esc(p.name)}</h3>
          <div class="prog"><span style="width:${v}%"></span></div>
          <div class="meta"><span>${v}% hecho</span>${p.run ? `<span>${st('run')} ${p.run} trabajando</span>` : ''}${p.toca ? `<span>${st('toca')} ${p.toca} te toca</span>` : ''}</div></button>`;
      }).join('')
    : '';
  $('cards').innerHTML = (msg ? `<p class="muted cards-msg">${esc(msg)}</p>` : '') + list + newCard();
  if (creating) $('newName').focus();
}

async function loadProjects() {
  try {
    projects = (await api('/api/projects')).projects;
    renderCards(projects.length ? '' : 'Todavía no tienes proyectos. Crea el primero.');
  } catch (e) {
    projects = [];
    renderCards('No se pudo cargar tus proyectos: ' + e.message);
  }
}

async function loadItinerary() {
  if (!project) return;
  const id = project.id;
  try {
    const d = await api(`/api/projects/${encodeURIComponent(id)}/itinerary`);
    if (!project || project.id !== id) return;  // se cambió de proyecto mientras cargaba
    const key = JSON.stringify(d);
    if (key === lastKey) return;
    lastKey = key;
    RAMAS = d.ramas.map((r) => ({ name: r.name, color: r.color, fases: r.fases.map((f) => ({
      name: f.name, steps: f.steps.map((x) => [x.title, x.state, x.id, x]) })) }));
    JOIN = { name: d.join.name, steps: [['Unir las ramas', d.join.state, null]] };
    restoreSelection();
    offline(false);
    render();
  } catch (e) {
    offline(true);
  }
}
function restoreSelection() {
  if (open && !document.querySelector(`[data-key="${open}"]`) && !RAMAS.some((r, ri) => r.fases.some((f, fi) => `${ri}-${fi}` === open))) open = null;
  if (!sel || sel.id == null) return;
  for (const [ri, r] of RAMAS.entries()) for (const [fi, f] of r.fases.entries()) {
    const si = f.steps.findIndex((x) => x[2] === sel.id);
    if (si >= 0) { sel = { r: ri, f: fi, s: si, id: sel.id }; return; }
  }
  sel = null;
}
function offline(on) {
  $('psub').classList.toggle('warn', on);
  if (on) $('psub').textContent = 'Sin conexión con el servidor. Reintentando…';
}
let lastKey = '', pollTimer = null, tick = 0;
function startPolling() {
  clearInterval(pollTimer);
  pollTimer = setInterval(() => { if (!document.hidden && !$('home').classList.contains('show')) { loadItinerary(); if (++tick % 3 === 0) loadGit(); } }, 3000);
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) loadItinerary(); });

function enterProject(p) {
  if (abortChat) abortChat.abort();
  project = p; sel = null; open = null; lastKey = ''; RAMAS = [];
  clearMsgs(); chatId = null; chats = []; drawConvs();
  if (installed.length) setAI(installed.includes(p.default_agent) ? p.default_agent : installed.includes(agent) ? agent : installed[0]);
  git = null; gitMsg = null; $('gitPanel').hidden = true; gitPill();
  render(); loadItinerary(); loadGit(); startPolling(); loadChats(true);
  $('pname').textContent = $('ptitle').textContent = p.name;
  $('pdot').style.background = p.color_theme;
  $('home').classList.remove('show');
}

function openHome() { creating = false; $('home').classList.add('show'); loadProjects(); }

$('homeBtn').onclick = openHome;
$('cards').onclick = (e) => {
  if (e.target.closest('[data-new]')) { creating = true; return renderCards(); }
  if (e.target.closest('[data-cancel]')) { creating = false; return renderCards(); }
  const c = e.target.closest('[data-p]');
  if (c) enterProject(projects[+c.dataset.p]);
};
$('cards').onsubmit = async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('.ok'); btn.disabled = true;
  try {
    const body = { name: $('newName').value.trim(), color_theme: COLORS[projects.length % COLORS.length] };
    if ($('newPath').value.trim()) body.path = $('newPath').value.trim();
    const { project: p, setup } = await api('/api/projects', body);
    creating = false;
    enterProject(p);
    (setup || []).filter((x) => x.startsWith('No ')).forEach((x) => sysMsg(x, true));
    if (!$('ta').value) $('ta').value = 'Quiero hacer… (cuéntale a la IA tu idea y te propondrá un plan por fases)';
    $('ta').select();
  } catch (err) {
    $('newErr').textContent = err.message; btn.disabled = false;
  }
};
openHome();
// ── Conversaciones guardadas (/api/projects/<id>/chats) ──
let chatId = null, chats = [];
const NATIVE = { claude_code: 'Claude Code', antigravity: 'Antigravity', codex: 'el editor' };
function clearMsgs() { document.querySelectorAll('#msgs .me, #msgs .bot, #msgs .sysmsg').forEach((m) => m.remove()); }
function sysMsg(text, bad) {
  const d = document.createElement('div'); d.className = 'sysmsg' + (bad ? ' err' : ''); d.textContent = text;
  $('msgs').append(d); $('msgs').scrollTop = $('msgs').scrollHeight;
}
function drawConvs() {
  const selEl = $('convSel');
  if (!selEl) return;
  const opts = chats.map((c) => `<option value="${esc(c.id)}"${c.id === chatId ? ' selected' : ''}>${esc((AGENTS[c.agent] || {}).icon || '')} ${esc(c.title || 'Conversación')}</option>`);
  if (!chatId) opts.unshift('<option value="" selected>Conversación nueva</option>');
  selEl.innerHTML = opts.join('');
  selEl.disabled = !project;
  const nb = $('nativeBtn'), where = NATIVE[agent];
  nb.hidden = !where; nb.disabled = !project || !installed.includes(agent);
  if (where) nb.textContent = `Abrir en ${where} ↗`;
}
async function loadChats(openLatest) {
  if (!project) return;
  const pid = project.id;
  try {
    const r = await api(`/api/projects/${encodeURIComponent(pid)}/chats`);
    if (!project || project.id !== pid) return;
    chats = r.chats || [];
    if (openLatest && chats.length) return openChat(chats[0].id);
  } catch (e) { chats = []; }
  drawConvs();
}
async function openChat(id) {
  if (abortChat) abortChat.abort();
  const pid = project.id;
  clearMsgs(); chatId = id || null; drawConvs();
  if (!id) return;
  try {
    const c = await api(`/api/projects/${encodeURIComponent(pid)}/chats/${encodeURIComponent(id)}`);
    if (!project || project.id !== pid || chatId !== id) return;
    if (installed.includes(c.agent) && c.agent !== agent) setAI(c.agent);
    c.messages.forEach(showMsg);
    const known = chats.find((x) => x.id === id);
    if (known && known.count !== c.messages.length) loadChats();  // trajo turnos escritos en el cliente nativo
  } catch (e) { sysMsg('No se pudo abrir la conversación: ' + e.message, true); }
}
function showMsg(m) {
  if (m.role === 'user') {
    const t = addMsg('me', m.content);
    if (m.source) { const s = document.createElement('small'); s.className = 'src'; s.textContent = `escrito en ${NATIVE[m.agent] || m.agent}`; t.parentElement.append(s); }
    return;
  }
  const who = (AGENTS[m.agent] || {}).label || m.agent;
  const t = addMsg('bot' + (m.error && !m.content ? ' err' : ''), m.content || m.error || '(sin respuesta)', who);
  if (m.tools && m.tools.length) t.before(toolsList(m.tools));
  if (m.error && m.content) { t.parentElement.classList.add('err'); t.textContent += '\n' + m.error; }
}
function toolsList(items) {
  const ul = document.createElement('ul'); ul.className = 'tools';
  items.slice(-6).forEach((x) => { const li = document.createElement('li'); li.textContent = x; ul.append(li); });
  if (items.length > 6) ul.title = `${items.length} acciones en total`;
  return ul;
}
$('convSel').onchange = (e) => openChat(e.target.value);
$('newConv').onclick = () => { openChat(null); $('ta').focus(); };
$('nativeBtn').onclick = async (e) => {
  if (!project) return;
  e.target.disabled = true;
  try {
    const body = { project_id: project.id, agent, prompt: '' };
    if (chatId) body.chat_id = chatId;
    if (sel && sel.id) body.task_id = sel.id;
    const r = await api('/api/chat/launch-native', body);
    sysMsg(r.message);
  } catch (x) { sysMsg(x.message, true); }
  e.target.disabled = false;
};
addEventListener('focus', () => { if (chatId && !abortChat) openChat(chatId); });  // al volver del cliente nativo

// ── Chat (POST /api/chat/stream, respuesta en directo) ──
let abortChat = null;
function addMsg(cls, text, who) {
  const d = document.createElement('div'); d.className = cls;
  if (who) { const s = document.createElement('small'); s.textContent = who; d.append(s); }
  const t = document.createElement('span'); t.className = 'txt'; t.textContent = text; d.append(t);
  $('msgs').append(d); $('msgs').scrollTop = $('msgs').scrollHeight;
  return t;
}
function setSending(on) {
  $('sendBtn').textContent = on ? 'Parar' : 'Enviar';
  $('ta').disabled = on;
}
async function sendChat() {
  if (abortChat) { abortChat.abort(); return; }
  const prompt = $('ta').value.trim();
  if (!prompt) return;
  if (!project) { openHome(); return; }
  if (!installed.includes(agent)) { addMsg('bot err', 'Esta IA no está instalada en tu ordenador. Elige otra.', ai); return; }
  $('ta').value = '';
  addMsg('me', prompt);
  const out = addMsg('bot', '', ai); out.parentElement.classList.add('wait');
  const ctrl = abortChat = new AbortController(), pid = project.id;
  setSending(true);
  try {
    const body = { project_id: pid, prompt, agent };
    if (sel && sel.id) body.task_id = sel.id;
    if (chatId) body.chat_id = chatId;
    let tools = null;
    const r = await fetch('/api/chat/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctrl.signal })
      .catch((e) => { throw e.name === 'AbortError' ? e : new Error('No hay conexión con el servidor. Comprueba que Unificador sigue abierto.'); });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || 'No se pudo enviar el mensaje.');
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const ev = buf.slice(0, i); buf = buf.slice(i + 2);
        const name = (ev.match(/^event: (.+)$/m) || [])[1], data = (ev.match(/^data: (.*)$/m) || [])[1];
        const p = data ? JSON.parse(data) : {};
        if (name === 'chat') { if (!chatId) { chatId = p.id; loadChats(); } continue; }
        if (name === 'tool') {
          if (!tools) { tools = toolsList([]); out.before(tools); }
          const li = document.createElement('li'); li.textContent = p.text; tools.append(li);
          while (tools.children.length > 6) tools.firstChild.remove();
          $('msgs').scrollTop = $('msgs').scrollHeight; continue;
        }
        if (name === 'error') throw new Error(p.error || 'La IA ha fallado.');
        if (p.chunk) { out.textContent += p.chunk.replace(/\x1b\[[0-9;]*[A-Za-z]/g, ''); out.parentElement.classList.remove('wait'); $('msgs').scrollTop = $('msgs').scrollHeight; }
      }
    }
    if (!out.textContent) out.textContent = '(sin respuesta)';
  } catch (e) {
    if (e.name === 'AbortError') out.textContent += (out.textContent ? '\n' : '') + '(parado)';
    else {
      const empty = !out.textContent;
      out.parentElement.classList.add('err'); out.textContent += (empty ? '' : '\n') + e.message;
      if (empty && !$('ta').value) $('ta').value = prompt;  // no se pierde lo escrito
    }
  } finally {
    out.parentElement.classList.remove('wait');
    if (abortChat === ctrl) abortChat = null;
    setSending(false); $('ta').focus();
    if (project && project.id === pid) { loadItinerary(); loadGit(); loadChats(); }  // la IA pudo cambiar el tablero
  }
}
$('sendBtn').onclick = sendChat;
$('ta').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendChat(); } });

addEventListener('resize', wire);
loadAgents();
