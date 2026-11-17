# Cómo está hecho Unificador

Un servidor local en Python (solo biblioteca estándar) que sirve una página estática con el plan de todos tus proyectos. No hay
base de datos ni dependencias. Las conversaciones no pasan por aquí: cada agente (Claude Code, Antigravity,
Codex) las lleva en su propio cliente y apunta el plan con `uni.py`.

```text
navegador  ⇄  unificador/app.py (127.0.0.1)
                    │
                    └─ unificador.json  ←  plan  ←──  .unificador/uni.py (lo usan los agentes)
```

## Dos ideas que lo sostienen

1. **El plan es un fichero** (`unificador.json`) dentro del proyecto. La web lo lee; el agente lo cambia con
   `uni.py`; la persona, desde la web. Todos escriben a través de `unificador/plan.py`, que valida y
   guarda de forma atómica.
2. **La web es un tablero complementario.** Enseña el plan de cada proyecto y recoge lo que decide la persona
   (aprobar fases, responder preguntas, elegir propuestas). No envía mensajes ni lee conversaciones; nada bloquea.

## El plan

```text
branches[]   rama: key, name, goal, icon, color, archived?
  phases[]   fase: name, icon
    steps[]  paso: id, title, desc, state (pending | doing | done), change?, result?, notes[], updated
ideas[]      idea: id (I-n), text, by, at, state (open | planned | dropped), branch?, note?, seen
queue[]      encargo: id (C-n), title, text, prompt?, branch?, phase?, state (pending | done), result?, seen
tweaks[]     retoque: id (R-n), title, cat?, commits[], at
news[]       novedad sin publicar: text, kind (nuevo | arreglo | cambio | fase), ref?, by, at
versions[]   versión publicada: version (SemVer, sin «v»), at, by, news[], sha?, tag? (vX.Y.Z)
```

- **Ideas** (`uni.py idea`, `ideas plan|drop|reopen`, `branch … --ideas I-1,I-2`): la caja de cosas que no tocan
  ahora. Las que deja la persona en la web llegan al agente por `inbox` (`seen: false`).
- **Prompts maestros**: los de serie viven en `plan.py` (`BUILTIN_PROMPTS`, viajan con `uni.py`); los del proyecto,
  en `.unificador/prompts/*.md` (primera línea `# Título`) y tapan al de serie con el mismo nombre.
- **Cola de encargos** (`uni.py queue add|done|drop`): un prompt maestro o texto libre sobre el proyecto, una rama
  o una fase. El agente los recoge por `inbox` y los cierra con `queue done C-1 -m`.
- **Retoques** (`uni.py tweak "…" --commit HEAD`): cambios rápidos sin rama. `commits` lista los commits que no
  están enlazados a ningún paso ni retoque (`--from-now` marca el punto de partida).
- **Versiones** (`uni.py news "…" --kind`, `news`, `versions`): SemVer. Al terminar una fase se apunta sola como
  novedad (`kind: fase`, `ref: RAMA/Fase`, sin repetirse). La próxima versión sube MENOR si hay algo nuevo o una
  fase, PARCHE si solo son arreglos o cambios, y MAYOR solo si se pide; la primera es 0.1.0.
  `news` enseña también lo comiteado desde la última versión (desde su `sha` o su tag; sin los commits que solo
  tocan el plan). `release [X.Y.Z] [--bump …] [--no-tag]` valida, crea el tag anotado `vX.Y.Z` en HEAD con las
  novedades como mensaje y después pasa las novedades al historial.
  En la web, la Caja tiene una sección «Versiones» que lee `GET /api/versions` (próxima, novedades, sin publicar, historial).

- El estado de fases y ramas se calcula a partir de sus pasos; no se guarda.
- `change` es una corrección pedida por la persona: reabre el paso hasta que la IA lo termina otra vez.
- `notes` es la historia del paso: quién (`ia` o `persona`), cuándo y qué.
- La IA crea una rama con `uni.py branch "Nombre" --phase "Fase" "Paso"…`: una sola línea que vale en cualquier
  terminal (los modelos flojos fallaban con JSON por la entrada estándar). Cada orden imprime cuál es la siguiente.

## Módulos (`unificador/`)

| Módulo | Qué hace |
| --- | --- |
| `cli.py` | Orden `unificador`: abrir la web, `install`, `doctor`, `import-kanvas`, `funnel`. |
| `app.py` | Servidor HTTP: ficheros de `web/`, puerta remota (`LOGIN_HTML` y `/auth/*`), API JSON y eventos en vivo. |
| `funnel.py` | Clave cifrada (`PBKDF2-HMAC-SHA256`), cookies firmadas (`HMAC-SHA256`), límite de intentos, CLI de Tailscale Funnel y arranque en segundo plano. |
| `plan.py` | Formato del plan, operaciones y la orden `uni` (se copia al proyecto como `.unificador/uni.py`, incluida la activación automática del proyecto y del servidor). |
| `rules.py` | Prepara un proyecto: `uni.py`, bloque de reglas en `AGENTS.md`/`CLAUDE.md` y aviso de inicio de sesión. Se puede repetir sin duplicar nada. |
| `agents.py` | Localiza el ejecutable de `claude`, `agy` y `codex` (PATH y carpetas habituales); lo usa `doctor`. |
| `kanvas_import.py` | Convierte un `kanvas.json` antiguo en plan. |
| `projects.py` | Registro de proyectos (`~/.unificador/proyectos.json`) y proyecto activo (`active.json`, o `UNIFICADOR_HOME`). |
| `web/` | La página, JavaScript sin librerías en módulos ES: `index.html`, `app.css`, `app.js` (portada con todos los proyectos o tablero de uno, `#p=<id>`, y eventos en vivo), `util.js` (nodos, peticiones, borradores, modo sin conexión y cierre de sesión), `plan.js` (carriles por rama con fases en tarjetas y sus pasos), `box.js` (cajón «Caja»: ideas, prompts maestros, cola de encargos y retoques), `decide.js` (bandeja «Te toca», revisar fases, preguntas, propuestas en miniatura y visor a pantalla completa), `sw.js` (en móvil, cabecera y `nav.tabs` como barra inferior: Plan, Filtrar, Caja y Decisiones), `manifest.webmanifest` e `icon.svg` (PWA y caché de solo lectura en remoto). |

## API

Todas las rutas del plan aceptan `?project=<id>` (un proyecto del registro); sin él, el proyecto con el que
arrancó el servidor. Un id que no esté en el registro da 404: nunca se sirve una carpeta libre.

| Ruta | Para qué |
| --- | --- |
| `GET /api/projects` | El de arranque (`current`), el último trabajado (`active`), indicador `remote` y los registrados: `id, name, path, exists, done, total, waiting`. |
| `GET /api/project` | Id, nombre y ruta del proyecto. |
| `GET /api/plan` | El plan tal cual (ramas, fases con `review`, `asks`). |
| `POST /api/plan/steps/<id>/state` | Marcar un paso a mano: `{state, text?}`. |
| `POST /api/plan/steps/<id>/change` | Pedir un cambio: `{text}`; reabre el paso. |
| `POST /api/plan/phases/review` | Revisar una fase: `{branch, phase, verdict: approved\|changes, text}`. |
| `POST /api/plan/asks/<id>/answer` | Responder: `{option: 1..n \| null, text}`. |
| `POST /api/plan/branches/<key>/nonstop` | Rama sin paradas: `{on: true\|false}`. |
| `POST /api/plan/ideas` | Idea nueva de la persona: `{text}`. |
| `POST /api/plan/ideas/<id>/drop` · `/reopen` | Descartar (`{text}` opcional) o recuperar una idea. |
| `GET /api/prompts` | Prompts maestros (de serie y del proyecto): `name, title, text, source`. |
| `POST /api/plan/queue` | Encargar: `{prompt?, text?, branch?, phase?}`. |
| `POST /api/plan/queue/<id>/drop` | Quitar un encargo pendiente. |
| `GET /propuestas/<P-n>/<n>.html` | Un mockup de `.unificador/propuestas/` (solo esa forma de ruta), con CSP `sandbox`. |
| `GET /api/events` | Eventos en vivo (SSE) del proyecto que se ve: `plan` cuando cambia su fichero. |
| `POST /auth/login` | Inicia sesión remota por Funnel con `{key}` y emite la cookie firmada `uni_session`. |
| `POST /auth/logout` | Cierra la sesión remota borrando la cookie (`Max-Age=0`). |

Lo que la persona decide en la web se guarda con `seen: false`: el agente lo recibe solo con `inbox`/`wait`.

## Cómo le llega al agente lo que decides

Unificador no puede despertar a un agente; le llega así, sin que la persona tenga que decir nada:

- `uni.py inbox` imprime lo decidido en la web que el agente aún no ha visto (y nada si no hay nada).
- **Claude Code**: `.claude/settings.json` ejecuta `inbox` en cada mensaje (`UserPromptSubmit`) y `status` al
  abrir sesión (`SessionStart`).
- **Codex**: `.codex/hooks.json` hace lo mismo (hay que aceptarlo una vez con `/hooks`).
- **Antigravity**: no tiene aviso fiable; la regla de `AGENTS.md` le pide ejecutar `inbox` al empezar el turno.
- `uni.py wait P-n` espera un rato corto por si la persona contesta en la web mientras el agente sigue ahí.
- Si la persona contesta en el chat, el agente lo apunta con `answer`, `approve` o `revise`.

## Clientes y `doctor`

`unificador doctor` repasa por igual Claude Code (`claude`), Antigravity (`agy`) y Codex (`codex`): si se
encuentra el ejecutable y si el proyecto tiene sus reglas (`AGENTS.md` lo leen Antigravity y Codex;
`CLAUDE.md` y el aviso de inicio de `.claude/settings.json` son de Claude Code). Que falte un cliente solo
se informa; que falten las reglas o el plan no responda sí es un error. También muestra el estado del Funnel.

## Seguridad

- Escucha solo en `127.0.0.1` y no envía cabeceras CORS.
- Rechaza peticiones que no vengan de la propia página (`Host`, `Origin`, `Sec-Fetch-Site`). En acceso por Funnel
  solo admite tráfico procedente del loopback hacia el host `.ts.net` configurado y el puerto HTTPS exacto.
- Política de contenido estricta: sin scripts en línea ni recursos de fuera; solo marcos del propio servidor.
- Los mockups del agente van en `<iframe sandbox="allow-scripts">` y se sirven con `sandbox allow-scripts;
  default-src 'none'…`: sin origen propio, sin red y sin poder llamar a la API ni tocar la página.
- No se lanza ningún proceso de agente ni se leen conversaciones.

## Acceso remoto (Tailscale Funnel) y caché sin conexión

- **Puerta cerrada (opción A)**: si la petición entra por proxy/Tailscale y no trae una cookie `uni_session` válida
  (o si Funnel está desactivado / sin clave), `/` sirve solo `LOGIN_HTML` (con `X-Unificador-Auth: login` y sin
  ningún dato de proyectos ni referencia a `app.js` o `sw.js`), y cualquier ruta de `/api/*`, `/propuestas/*` o
  estáticos devuelve `401` (o `403` si Funnel no está activo). El navegador local en `127.0.0.1` sigue abierto sin clave.
- **Clave y límite de intentos**: `funnel.json` (permisos `0600`) guarda solo el hash `PBKDF2-HMAC-SHA256` (200.000
  iteraciones) y `cookie_secret`. Tras 5 fallos desde la misma IP (`RateLimiter`) bloquea temporalmente con `429`.
- **Sin rutas del disco**: las respuestas remotas de `/api/projects` y `/api/project` vacían `path` (`""`).
- **Autoarranque y proyecto activo**: `unificador funnel enable` configura Tailscale Funnel en `443` (con respaldo en
  `8443` o `10000`) y guarda en `server.json` el puerto local y `autostart: true`. Cada vez que un agente ejecuta
  `.unificador/uni.py`, registra la carpeta, la marca en `active.json` y levanta un único servidor compartido si no
  estaba vivo (`UNI_NO_AUTOSTART=1` lo desactiva).
- **PWA y caché de solo lectura**: cuando `app.remote` es `true` (nunca en `127.0.0.1`), `app.js` registra `sw.js`.
  Usa estrategia *network-first* sobre GET del mismo origen (excluyendo `/auth/` y `/api/events`) y si el ordenador
  se desconecta sirve la última copia con `X-Unificador-Offline: 1`, bloqueando escrituras en la interfaz. Al pulsar
  **Salir** o recibir `401`/`403`/`X-Unificador-Auth: login`, `sw.js` y `LOGIN_HTML` borran todas las caches y
  desregistran el Service Worker.

## Pruebas

`python -m unittest discover -s tests`. Usan carpetas temporales; no gastan nada.
