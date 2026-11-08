/* Unificador · lógica común de los mockups (datos de ejemplo, chat, informe, aprobaciones).
   Cada mockup aporta su propio CSS y su propio dibujo del canvas. */
(function () {
  const AIS = {
    claude: { name: 'Claude', glyph: '✳', color: '#d97757', fill: '#b9532f',
      models: ['Opus 5.5', 'Sonnet 5.5', 'Haiku 5.5', 'Fable 5.1'] },
    gpt: { name: 'GPT', glyph: '◎', color: '#10a37f', fill: '#0b7d61',
      models: ['GPT-5', 'GPT-5 mini', 'Codex'] },
    antigravity: { name: 'Antigravity', glyph: '▲', color: '#4f8cff', fill: '#2f6fe0',
      models: ['Gemini Pro', 'Gemini Flash', 'Gemini Flash Lite'] },
  };

  const STATES = {
    proposed: { label: 'Propuesta', mark: '' },
    todo: { label: 'Por hacer', mark: '' },
    blocked: { label: 'Bloqueada', mark: '–' },
    running: { label: 'En ejecución', mark: '' },
    review: { label: 'Por aprobar', mark: '!' },
    done: { label: 'Hecha', mark: '✓' },
  };

  const PHASES = ['Planificar', 'Explorar', 'Implementar', 'Verificar', 'Informe'];

  const PROJECTS = [
    { id: 'uni', name: 'Unificador', color: '#8b5cf6', phases: ['Especificación', 'Motor', 'Adaptadores', 'API', 'Frontend'],
      threads: [
        { id: 'nucleo', name: 'Núcleo', color: '#6d6cf0', ai: 'claude', model: 'Sonnet 5.5' },
        { id: 'adapt', name: 'Adaptadores', color: '#a855f7', ai: 'antigravity', model: 'Gemini Pro' },
        { id: 'interfaz', name: 'Interfaz', color: '#d36bf0', ai: 'claude', model: 'Opus 5.5' },
      ] },
    { id: 'yum', name: 'Yumemi', color: '#e8488a', phases: ['Base', 'Contenido', 'Pulido'],
      threads: [
        { id: 'lector', name: 'Lector', color: '#e8488a', ai: 'gpt', model: 'GPT-5' },
        { id: 'biblio', name: 'Biblioteca', color: '#f2709c', ai: 'claude', model: 'Sonnet 5.5' },
      ] },
    { id: 'iris', name: 'StudioIris', color: '#12a5ba', phases: ['Diseño', 'Implementación', 'Salida'],
      threads: [
        { id: 'editor', name: 'Editor', color: '#12a5ba', ai: 'claude', model: 'Opus 5.5' },
        { id: 'export', name: 'Exportación', color: '#45c4d6', ai: 'antigravity', model: 'Gemini Flash' },
      ] },
    { id: 'cap', name: 'App capturas', color: '#84a82c', phases: ['Flujo', 'Pulido'],
      threads: [
        { id: 'nav', name: 'Navegación', color: '#84a82c', ai: 'gpt', model: 'Codex' },
        { id: 'anim', name: 'Animaciones', color: '#a9c64c', ai: 'antigravity', model: 'Gemini Flash' },
      ] },
  ];

  const t = (id, title, thread, phase, state, ai, deps, extra) =>
    Object.assign({ id, title, thread, phase, state, ai, deps: deps || [] }, extra || {});

  const TASKS = [
    t('ES-01', 'Arquitectura del sistema', 'nucleo', 0, 'done', 'claude'),
    t('MC-01', 'Modelos y configuración', 'nucleo', 1, 'done', 'claude', ['ES-01']),
    t('MC-02', 'Inyección de contexto', 'nucleo', 1, 'done', 'claude', ['MC-01']),
    t('IN-01', 'API REST y streaming', 'nucleo', 3, 'running', 'claude', ['MC-02'], { phaseIdx: 3, elapsed: 512 }),
    t('IN-02', 'Git desde la interfaz', 'nucleo', 3, 'blocked', 'claude', ['IN-01']),
    t('AD-01', 'Adaptador Claude Code', 'adapt', 2, 'done', 'claude', ['MC-01']),
    t('AD-02', 'Adaptador Antigravity', 'adapt', 2, 'review', 'antigravity', ['AD-01'], {
      report: { summary: 'Unificador ya lanza Antigravity y muestra sus pasos en el chat igual que Claude.',
        checks: ['Lanza una tarea con Gemini Flash y mira las fases', 'Pulsa Parar a mitad: el proceso debe cerrarse'],
        files: 3, added: 142, removed: 18, tests: '11 de 11', time: '12 min' } }),
    t('AD-03', 'Adaptador Codex', 'adapt', 2, 'todo', 'gpt', ['AD-01']),
    t('FE-01', 'Mockups de diseño', 'interfaz', 0, 'review', 'claude', [], {
      report: { summary: 'Tres direcciones visuales listas para comparar: carriles, grafo y metro.',
        checks: ['Prueba a cambiar de IA: el color debe seguirte por todo el chat', 'Aprueba una tarea y mira cómo cambia en el canvas', 'Elige una dirección o mezcla ideas'],
        files: 5, added: 1180, removed: 0, tests: 'Revisión visual', time: '18 min' } }),
    t('FE-02', 'Estructura chat + canvas', 'interfaz', 4, 'running', 'claude', [], { phaseIdx: 2, elapsed: 164, ends: true }),
    t('FE-03', 'Selector de modelos', 'interfaz', 4, 'blocked', 'claude', ['FE-02']),
    t('FE-04', 'Vista de todos los proyectos', 'interfaz', 4, 'proposed', 'claude', ['FE-02']),

    t('YM-01', 'Motor de lectura', 'lector', 0, 'done', 'gpt'),
    t('YM-02', 'Modo vertical', 'lector', 1, 'running', 'gpt', ['YM-01'], { phaseIdx: 2, elapsed: 305 }),
    t('YM-03', 'Gestos y zoom', 'lector', 2, 'blocked', 'gpt', ['YM-02']),
    t('YB-01', 'Índice local', 'biblio', 0, 'done', 'claude'),
    t('YB-02', 'Etiquetas y filtros', 'biblio', 1, 'proposed', 'claude', ['YB-01']),
    t('YB-03', 'Importar colecciones', 'biblio', 1, 'proposed', 'claude', ['YB-02']),

    t('SI-01', 'Lienzo por capas', 'editor', 0, 'done', 'claude'),
    t('SI-02', 'Pinceles', 'editor', 1, 'review', 'claude', ['SI-01'], {
      report: { summary: 'Cinco pinceles con presión y vista previa en tiempo real.',
        checks: ['Dibuja con el lápiz en una capa nueva', 'Comprueba que deshacer funciona con trazos largos'],
        files: 6, added: 390, removed: 41, tests: '24 de 24', time: '31 min' } }),
    t('SI-03', 'Historial', 'editor', 1, 'todo', 'claude', ['SI-01']),
    t('SE-01', 'Formatos de salida', 'export', 0, 'done', 'antigravity'),
    t('SE-02', 'Cola de exportación', 'export', 2, 'todo', 'antigravity', ['SE-01']),

    t('AC-01', 'Informe de flujo', 'nav', 0, 'done', 'gpt'),
    t('AC-02', 'Menú compartido', 'nav', 1, 'running', 'gpt', ['AC-01'], { phaseIdx: 1, elapsed: 47 }),
    t('AN-01', 'Transición de captura', 'anim', 0, 'done', 'antigravity'),
    t('AN-02', 'Aparición del logo', 'anim', 1, 'done', 'antigravity', ['AN-01']),
  ];

  const ACTIONS = {
    0: ['Leyendo la tarea y sus dependencias', 'Comparando alternativas', 'Escribiendo el plan'],
    1: ['Buscando dónde encaja', 'Leyendo unificador/server.py', 'Leyendo kanvas.html (estados)', 'Revisando la API del backend'],
    2: ['Editando frontend/app.js', 'Creando frontend/chat.js', 'Editando frontend/canvas.js', 'Conectando el streaming al chat', 'Ajustando estilos y colores'],
    3: ['Ejecutando las pruebas', 'Abriendo la app en el navegador', 'Comprobando el cambio de hilo'],
    4: ['Redactando el informe'],
  };

  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const threadOf = (id) => { for (const p of PROJECTS) for (const th of p.threads) if (th.id === id) return th; };
  const projectOfThread = (id) => PROJECTS.find((p) => p.threads.some((th) => th.id === id));
  const task = (id) => TASKS.find((x) => x.id === id);
  const tasksOf = (threadId) => TASKS.filter((x) => x.thread === threadId);

  const state = { project: 'all', thread: 'interfaz', openTask: null, draftFor: null, listeners: [] };

  /* Conversaciones: una por hilo. */
  const CHATS = {
    interfaz: [
      { type: 'user', text: 'Necesito el frontend: chat a la izquierda y canvas de proyectos a la derecha. Empieza con mockups.' },
      { type: 'ai', ai: 'claude', model: 'Opus 5.5', text: 'He terminado los mockups. Te dejo el informe para que lo apruebes.' },
      { type: 'report', task: 'FE-01' },
      { type: 'user', text: 'Mientras los miro, ve montando la estructura del chat y el canvas.' },
      { type: 'work', task: 'FE-02' },
    ],
    biblio: [
      { type: 'user', text: 'Quiero poder organizar la biblioteca mejor.' },
      { type: 'ai', ai: 'claude', model: 'Sonnet 5.5', text: 'Propongo dos tareas. No empiezo hasta que me des el visto bueno.' },
      { type: 'plan', tasks: ['YB-02', 'YB-03'] },
    ],
  };

  function chatOf(threadId) {
    if (CHATS[threadId]) return CHATS[threadId];
    const th = threadOf(threadId), msgs = [{ type: 'user', text: `Seguimos con «${th.name}».` }];
    for (const x of tasksOf(threadId)) {
      if (x.state === 'done') msgs.push({ type: 'ai', ai: x.ai, model: x.ai === th.ai ? th.model : AIS[x.ai].models[0], text: `«${x.title}» terminada y aprobada.` });
      if (x.state === 'review') msgs.push({ type: 'report', task: x.id });
      if (x.state === 'running') msgs.push({ type: 'work', task: x.id });
    }
    return (CHATS[threadId] = msgs);
  }

  const emit = (kind) => state.listeners.forEach((fn) => fn(kind));

  function pushChat(threadId, msg) { chatOf(threadId).push(msg); }

  /* Una tarea relanzada deja un solo bloque «Trabajando»: el anterior pasa a ser una nota. */
  function pushWork(threadId, id) {
    chatOf(threadId).forEach((m) => {
      if (m.type === 'work' && m.task === id) { m.type = 'note'; m.text = `Pasada anterior de «${task(id).title}»`; }
    });
    pushChat(threadId, { type: 'work', task: id });
  }

  const U = window.U = {
    AIS, STATES, PHASES, PROJECTS, TASKS, state, esc, fmt, threadOf, projectOfThread, task, tasksOf,
    on(fn) { state.listeners.push(fn); },
    /* Puntos de ajuste: cada mockup puede cambiar cómo se nombran tareas e hilos. */
    code: (x) => x.id,
    threadLabel: (th) => th.name,
    pathOf(x) { const th = threadOf(x.thread), p = projectOfThread(x.thread); return `${p.name} / ${th.name} / ${p.phases[x.phase]}`; },
    refresh() { emit('change'); },
    counts(list) {
      const c = { running: 0, review: 0, proposed: 0, done: 0, total: list.length };
      list.forEach((x) => { if (c[x.state] !== undefined) c[x.state]++; });
      c.approve = c.review + c.proposed;
      return c;
    },
    tasksOfProject(p) { return TASKS.filter((x) => p.threads.some((th) => th.id === x.thread)); },
    selectProject(id) { state.project = id; emit('project'); },
    selectThread(id) { state.thread = id; emit('thread'); },
    openTask(id) {
      state.openTask = id;
      if (id) state.thread = task(id).thread;
      emit('thread');
    },
    closeTask() { state.openTask = null; emit('drawer'); },
    nextPending() {
      const list = TASKS.filter((x) => x.state === 'review' || x.state === 'proposed');
      if (!list.length) return;
      const i = list.findIndex((x) => x.id === state.openTask);
      const next = list[(i + 1) % list.length];
      const p = projectOfThread(next.thread);
      if (state.project !== 'all') state.project = p.id;
      U.openTask(next.id);
    },
    approve(id) {
      const x = task(id);
      if (x.state === 'review') {
        x.state = 'done';
        TASKS.filter((d) => d.state === 'blocked' && d.deps.includes(id) && d.deps.every((k) => task(k).state === 'done'))
          .forEach((d) => { d.state = 'todo'; });
      } else if (x.state === 'proposed') x.state = 'todo';
      emit('change');
    },
    approvePlan(ids) { ids.forEach((id) => { if (task(id).state === 'proposed') task(id).state = 'todo'; }); emit('change'); },
    askChanges(id) {
      state.draftFor = id;
      state.thread = task(id).thread;
      emit('thread');
      const box = document.querySelector('.composer textarea');
      if (box) { box.placeholder = `Qué cambiarías en ${U.code(task(id))}…`; box.focus(); }
    },
    launch(id) {
      const x = task(id), th = threadOf(x.thread);
      Object.assign(x, { state: 'running', ai: th.ai, phaseIdx: 0, elapsed: 0 });
      pushWork(x.thread, id);
      state.thread = x.thread;
      emit('change');
    },
    stop(id) {
      const x = task(id);
      x.state = 'todo';
      pushChat(x.thread, { type: 'note', text: `Has parado «${x.title}». Queda por hacer.` });
      emit('change');
    },
    setAi(aiId) {
      const th = threadOf(state.thread);
      if (th.ai === aiId) return;
      th.ai = aiId;
      th.model = AIS[aiId].models[0];
      pushChat(th.id, { type: 'note', text: `Esta conversación sigue con ${AIS[aiId].name} · ${th.model}` });
      emit('change');
    },
    setModel(m) { threadOf(state.thread).model = m; emit('change'); },
    send(text) {
      const th = threadOf(state.thread);
      pushChat(th.id, { type: 'user', text });
      if (state.draftFor) {
        const id = state.draftFor, x = task(id);
        state.draftFor = null;
        Object.assign(x, { state: 'running', ai: th.ai, phaseIdx: 0, elapsed: 0 });
        pushWork(th.id, id);
      } else {
        pushChat(th.id, { type: 'ai', ai: th.ai, model: th.model, text: 'En la app real, aquí respondería el modelo elegido y este hilo seguiría su curso.' });
      }
      const box = document.querySelector('.composer textarea');
      if (box) box.placeholder = placeholder();
      emit('change');
    },
  };

  const placeholder = () => { const th = threadOf(state.thread); return `Escribe a ${AIS[th.ai].name} en «${th.name}»…`; };

  /* ── Marca de estado reutilizable ─────────────────────────────────── */
  U.mark = (x) => {
    const th = threadOf(x.thread);
    return `<span class="st st-${x.state}" style="--th:${th.color};--ai:${AIS[x.ai].color}" role="img" aria-label="${STATES[x.state].label}">${STATES[x.state].mark}</span>`;
  };

  /* ── Pestañas de proyectos y contadores ───────────────────────────── */
  U.mountTabs = (el) => {
    function render() {
      const all = U.counts(TASKS);
      el.innerHTML = `
        <nav class="tabs" aria-label="Proyectos">
          <button class="tab ${state.project === 'all' ? 'on' : ''}" data-p="all"><span class="tab-all">${PROJECTS.map((p) => `<i style="background:${p.color}"></i>`).join('')}</span>Todos</button>
          ${PROJECTS.map((p) => {
            const c = U.counts(U.tasksOfProject(p));
            return `<button class="tab ${state.project === p.id ? 'on' : ''}" data-p="${p.id}" style="--p:${p.color}"><i class="dot"></i>${esc(p.name)}${c.approve ? `<b class="tab-flag" title="${c.approve} por aprobar">${c.approve}</b>` : ''}</button>`;
          }).join('')}
        </nav>
        <div class="tallies">
          <span class="tally"><span class="st st-running" style="--ai:var(--ink-2)"></span>${all.running} en ejecución</span>
          <button class="tally tally-btn" data-next><span class="st st-review">!</span>${all.approve} por aprobar</button>
        </div>`;
      el.querySelectorAll('[data-p]').forEach((b) => (b.onclick = () => U.selectProject(b.dataset.p)));
      el.querySelector('[data-next]').onclick = U.nextPending;
    }
    U.on((k) => { if (k !== 'tick' && k !== 'drawer') render(); });
    render();
  };

  /* ── Leyenda ──────────────────────────────────────────────────────── */
  U.legend = () => Object.entries(STATES).map(([k, v]) =>
    `<span class="lg"><span class="st st-${k}" style="--th:var(--ink-2);--ai:var(--ink-2)">${v.mark}</span>${v.label}</span>`).join('');

  /* ── Chat ─────────────────────────────────────────────────────────── */
  function workBlock(x) {
    const done = x.state !== 'running';
    const ai = AIS[x.ai];
    if (done) {
      return `<div class="work work-done" style="--ai:${ai.color}"><span class="work-check">✓</span>Trabajo en ${U.code(x)} terminado<span class="muted">· ${fmt(x.elapsed || 0)}</span></div>`;
    }
    const act = ACTIONS[x.phaseIdx] || ['Trabajando'];
    const now = act[Math.floor((x.elapsed || 0) / 4) % act.length];
    return `<div class="work" style="--ai:${ai.color}">
      <div class="work-top">
        <span class="spin" aria-hidden="true"></span>
        <strong>Trabajando</strong><span class="muted">${U.code(x)} · <span class="js-elapsed" data-t="${x.id}">${fmt(x.elapsed || 0)}</span></span>
        <button class="ghost small" data-stop="${x.id}">Parar</button>
      </div>
      <ol class="steps">${PHASES.map((ph, i) => `<li class="${i < x.phaseIdx ? 'past' : i === x.phaseIdx ? 'now' : ''}"><i></i><span>${ph}</span></li>`).join('')}</ol>
      <p class="work-now js-action" data-t="${x.id}">${esc(now)}…</p>
    </div>`;
  }

  function reportBlock(x) {
    const r = reportOf(x);
    const pending = x.state === 'review';
    const th = threadOf(x.thread);
    return `<article class="card report ${pending ? 'pending' : 'closed'}" style="--th:${th.color}">
      <button class="card-open" data-open="${x.id}">
        <span class="card-kicker">${U.mark(x)} Informe · ${U.code(x)}</span>
        <strong>${esc(x.title)}</strong>
        <span class="card-text">${esc(r.summary)}</span>
        <span class="stats"><span>${r.files} ficheros</span><span class="plus">+${r.added}</span><span class="minus">−${r.removed}</span><span>${esc(r.tests)}</span><span>${r.time}</span></span>
      </button>
      ${pending ? `<div class="card-actions"><button class="approve" data-approve="${x.id}">Aprobar</button><button class="ghost" data-changes="${x.id}">Pedir cambios</button></div>`
        : `<p class="card-state">${x.state === 'done' ? '✓ Aprobado' : esc(STATES[x.state].label)}</p>`}
    </article>`;
  }

  function planBlock(m) {
    const pending = m.tasks.some((id) => task(id).state === 'proposed');
    return `<article class="card plan ${pending ? 'pending' : 'closed'}">
      <span class="card-kicker"><span class="st st-review">!</span> Plan propuesto</span>
      <ol class="plan-list">${m.tasks.map((id) => `<li><button class="link" data-open="${id}">${U.mark(task(id))} <b>${U.code(task(id))}</b> ${esc(task(id).title)}</button></li>`).join('')}</ol>
      ${pending ? `<div class="card-actions"><button class="approve" data-plan="${m.tasks.join(',')}">Aprobar plan</button><button class="ghost" data-changes="${m.tasks[0]}">Pedir cambios</button></div>`
        : '<p class="card-state">✓ Plan aprobado</p>'}
    </article>`;
  }

  function msgHtml(m) {
    if (m.type === 'user') return `<div class="msg user"><p>${esc(m.text)}</p></div>`;
    if (m.type === 'note') return `<div class="note">${esc(m.text)}</div>`;
    if (m.type === 'work') return workBlock(task(m.task));
    if (m.type === 'report') return reportBlock(task(m.task));
    if (m.type === 'plan') return planBlock(m);
    const ai = AIS[m.ai];
    return `<div class="msg ai" style="--ai:${ai.color}">
      <span class="who"><i>${ai.glyph}</i>${ai.name}<span class="muted">${esc(m.model)}</span></span>
      <p>${esc(m.text)}</p></div>`;
  }

  U.mountChat = (root) => {
    root.innerHTML = `
      <header class="chat-head"></header>
      <div class="ai-bar"></div>
      <div class="messages" tabindex="0" aria-label="Conversación"></div>
      <form class="composer">
        <textarea rows="2" aria-label="Mensaje"></textarea>
        <div class="composer-row">
          <span class="composer-ctx"></span>
          <button type="submit" class="send">Enviar</button>
        </div>
      </form>`;
    const head = root.querySelector('.chat-head'), bar = root.querySelector('.ai-bar');
    const list = root.querySelector('.messages'), form = root.querySelector('.composer');
    const box = form.querySelector('textarea');

    function renderHead() {
      const th = threadOf(state.thread), p = projectOfThread(th.id), ai = AIS[th.ai];
      root.style.setProperty('--ai', ai.color);
      root.style.setProperty('--ai-fill', ai.fill);
      root.dataset.ai = th.ai;
      document.documentElement.style.setProperty('--current-ai', ai.color);
      const running = tasksOf(th.id).some((x) => x.state === 'running');
      head.innerHTML = `
        <div class="crumb">
          <span class="crumb-p"><i style="background:${p.color}"></i>${esc(p.name)}</span>
          <span class="crumb-sep">/</span>
          <label class="crumb-t"><i style="background:${th.color}"></i>
            <select aria-label="Hilo">${p.threads.map((o) => `<option value="${o.id}" ${o.id === th.id ? 'selected' : ''}>${esc(U.threadLabel(o))}</option>`).join('')}</select>
          </label>
        </div>
        <span class="run-state ${running ? 'on' : ''}">${running ? 'Trabajando' : 'En espera'}</span>`;
      head.querySelector('select').onchange = (e) => U.selectThread(e.target.value);
      bar.innerHTML = `
        <div class="providers" role="radiogroup" aria-label="Inteligencia artificial">
          ${Object.entries(AIS).map(([k, v]) => `<button type="button" role="radio" aria-checked="${k === th.ai}" class="prov ${k === th.ai ? 'on' : ''}" data-ai="${k}" style="--c:${v.color};--f:${v.fill}"><i>${v.glyph}</i><span>${v.name}</span></button>`).join('')}
        </div>
        <div class="ai-subs">
          <label>Modelo<select class="sel-model">${ai.models.map((m) => `<option ${m === th.model ? 'selected' : ''}>${m}</option>`).join('')}</select></label>
          <label>Esfuerzo<select><option>Bajo</option><option selected>Medio</option><option>Alto</option></select></label>
        </div>`;
      bar.querySelectorAll('[data-ai]').forEach((b) => (b.onclick = () => U.setAi(b.dataset.ai)));
      bar.querySelector('.sel-model').onchange = (e) => U.setModel(e.target.value);
      form.querySelector('.composer-ctx').innerHTML = `<i>${ai.glyph}</i>${ai.name} · ${esc(th.model)}`;
      if (!state.draftFor) box.placeholder = placeholder();
    }

    function renderList() {
      list.innerHTML = chatOf(state.thread).map(msgHtml).join('');
      list.scrollTop = list.scrollHeight;
    }

    list.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      if (b.dataset.approve) U.approve(b.dataset.approve);
      if (b.dataset.plan) U.approvePlan(b.dataset.plan.split(','));
      if (b.dataset.changes) U.askChanges(b.dataset.changes);
      if (b.dataset.stop) U.stop(b.dataset.stop);
      if (b.dataset.open) U.openTask(b.dataset.open);
    });
    form.onsubmit = (e) => {
      e.preventDefault();
      const v = box.value.trim(); if (!v) return;
      box.value = ''; U.send(v);
    };
    box.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } };

    U.on((k) => {
      if (k === 'tick') return;
      if (k === 'finish' || k === 'change' || k === 'thread') { renderHead(); renderList(); }
    });
    renderHead(); renderList();
  };

  /* ── Informe de la tarea (panel sobre el canvas) ──────────────────── */
  function reportOf(x) {
    return x.report || { summary: x.state === 'done' ? `«${x.title}» terminada y aprobada.` : `«${x.title}» aún no tiene informe.`,
      checks: [], files: 4, added: 96, removed: 12, tests: '8 de 8', time: '9 min' };
  }

  U.mountDrawer = (el) => {
    function render() {
      const x = state.openTask && task(state.openTask);
      el.classList.toggle('open', !!x);
      if (!x) { el.innerHTML = ''; return; }
      const th = threadOf(x.thread), p = projectOfThread(x.thread), ai = AIS[x.ai], r = reportOf(x);
      const hasReport = x.state === 'review' || x.state === 'done';
      const actions = {
        review: `<button class="approve" data-approve="${x.id}">Aprobar</button><button class="ghost" data-changes="${x.id}">Pedir cambios</button>`,
        proposed: `<button class="approve" data-approve="${x.id}">Aprobar propuesta</button><button class="ghost" data-changes="${x.id}">Pedir cambios</button>`,
        todo: `<button class="launch" style="--ai-fill:${AIS[th.ai].fill}" data-launch="${x.id}">Lanzar con ${AIS[th.ai].name}</button>`,
        running: `<button class="ghost" data-stop="${x.id}">Parar</button>`,
        blocked: `<p class="muted">Espera a ${x.deps.filter((d) => task(d).state !== 'done').map((d) => U.code(task(d))).join(', ')}.</p>`,
        done: '<p class="card-state">✓ Aprobada</p>',
      }[x.state];
      el.innerHTML = `
        <div class="dr-band" style="background:linear-gradient(90deg,${p.color},${th.color})"></div>
        <header class="dr-head">
          <div>
            <p class="dr-path">${esc(U.pathOf(x))}</p>
            <h2>${esc(x.title)}</h2>
          </div>
          <button class="ghost icon" data-close aria-label="Cerrar">✕</button>
        </header>
        <div class="dr-meta">
          <span class="pill">${U.mark(x)}${STATES[x.state].label}</span>
          <span class="pill" style="--ai:${ai.color}"><i class="ai-g">${ai.glyph}</i>${ai.name}</span>
          <span class="pill mono">${U.code(x)}</span>
        </div>
        <div class="dr-body">
          ${x.state === 'running' ? workBlock(x) : ''}
          ${hasReport ? `<section><h3>Informe</h3><p>${esc(r.summary)}</p>
            <div class="stats big"><span>${r.files} ficheros</span><span class="plus">+${r.added}</span><span class="minus">−${r.removed}</span><span>${esc(r.tests)}</span><span>${r.time}</span></div></section>` : ''}
          ${hasReport && r.checks.length ? `<section><h3>Qué comprobar</h3><ul class="checks">${r.checks.map((c) => `<li>${esc(c)}</li>`).join('')}</ul></section>` : ''}
          ${x.deps.length ? `<section><h3>Depende de</h3><ul class="deps">${x.deps.map((d) => `<li><button class="link" data-open="${d}">${U.mark(task(d))} <b>${U.code(task(d))}</b> ${esc(task(d).title)}</button></li>`).join('')}</ul></section>` : ''}
        </div>
        <footer class="dr-foot">${actions}</footer>`;
    }
    el.addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      if ('close' in b.dataset) U.closeTask();
      if (b.dataset.approve) U.approve(b.dataset.approve);
      if (b.dataset.changes) U.askChanges(b.dataset.changes);
      if (b.dataset.launch) U.launch(b.dataset.launch);
      if (b.dataset.stop) U.stop(b.dataset.stop);
      if (b.dataset.open) U.openTask(b.dataset.open);
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && state.openTask) U.closeTask(); });
    U.on((k) => { if (k !== 'tick') render(); });
    render();
  };

  /* ── Simulación: las tareas en marcha avanzan solas ───────────────── */
  setInterval(() => {
    for (const x of TASKS) {
      if (x.state !== 'running') continue;
      x.elapsed = (x.elapsed || 0) + 1;
      document.querySelectorAll(`.js-elapsed[data-t="${x.id}"]`).forEach((n) => (n.textContent = fmt(x.elapsed)));
      if (x.elapsed % 4 === 0) {
        const act = ACTIONS[x.phaseIdx] || ['Trabajando'];
        document.querySelectorAll(`.js-action[data-t="${x.id}"]`).forEach((n) => (n.textContent = act[Math.floor(x.elapsed / 4) % act.length] + '…'));
      }
      if (x.ends && x.elapsed % 14 === 0) {
        if (x.phaseIdx < PHASES.length - 1) { x.phaseIdx++; emit('change'); }
        else {
          x.state = 'review';
          x.ends = false;
          x.report = { summary: 'La app ya abre con el chat a la izquierda y el canvas a la derecha, y al pulsar un hilo cambia la conversación.',
            checks: ['Pulsa hilos de distintos proyectos', 'Cambia de IA y mira el color'], files: 7, added: 412, removed: 23, tests: '16 de 16', time: fmt(x.elapsed) };
          pushChat(x.thread, { type: 'ai', ai: x.ai, model: threadOf(x.thread).model, text: 'Listo. Necesito tu aprobación para seguir con el resto del hilo.' });
          pushChat(x.thread, { type: 'report', task: x.id });
          emit('change');
        }
      }
    }
    emit('tick');
  }, 1000);
})();
