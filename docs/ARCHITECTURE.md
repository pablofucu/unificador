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
```

- El estado de fases y ramas se calcula a partir de sus pasos; no se guarda.
- `change` es una corrección pedida por la persona: reabre el paso hasta que la IA lo termina otra vez.
- `notes` es la historia del paso: quién (`ia` o `persona`), cuándo y qué.
- La IA crea una rama con `uni.py branch "Nombre" --phase "Fase" "Paso"…`: una sola línea que vale en cualquier
  terminal (los modelos flojos fallaban con JSON por la entrada estándar). Cada orden imprime cuál es la siguiente.

## Módulos (`unificador/`)

| Módulo | Qué hace |
| --- | --- |
| `cli.py` | Orden `unificador`: abrir la web, `install`, `doctor`, `import-kanvas`. |
| `app.py` | Servidor HTTP: ficheros de `web/`, API JSON y eventos en vivo. |
| `plan.py` | Formato del plan, operaciones y la orden `uni` (se copia al proyecto como `.unificador/uni.py`). |
| `rules.py` | Prepara un proyecto: `uni.py`, bloque de reglas en `AGENTS.md`/`CLAUDE.md` y aviso de inicio de sesión. Se puede repetir sin duplicar nada. |
| `agents.py` | Localiza el ejecutable de `claude`, `agy` y `codex` (PATH y carpetas habituales); lo usa `doctor`. |
| `kanvas_import.py` | Convierte un `kanvas.json` antiguo en plan. |
| `projects.py` | Registro de proyectos de la máquina (`~/.unificador/proyectos.json`, o `UNIFICADOR_HOME`). |
| `web/` | La página, JavaScript sin librerías en módulos ES: `index.html`, `app.css`, `app.js` (portada con todos los proyectos o tablero de uno, `#p=<id>`, y eventos en vivo), `util.js` (nodos, peticiones, borradores), `plan.js` (carriles por rama con fases en tarjetas y sus pasos), `decide.js` (bandeja «Te toca», revisar fases, preguntas, propuestas en miniatura y visor a pantalla completa). |

## API

Todas las rutas del plan aceptan `?project=<id>` (un proyecto del registro); sin él, el proyecto con el que
arrancó el servidor. Un id que no esté en el registro da 404: nunca se sirve una carpeta libre.

| Ruta | Para qué |
| --- | --- |
| `GET /api/projects` | El de arranque (`current`) y los registrados: `id, name, path, exists, done, total, waiting`. |
| `GET /api/project` | Id, nombre y ruta del proyecto. |
| `GET /api/plan` | El plan tal cual (ramas, fases con `review`, `asks`). |
| `POST /api/plan/steps/<id>/state` | Marcar un paso a mano: `{state, text?}`. |
| `POST /api/plan/steps/<id>/change` | Pedir un cambio: `{text}`; reabre el paso. |
| `POST /api/plan/phases/review` | Revisar una fase: `{branch, phase, verdict: approved\|changes, text}`. |
| `POST /api/plan/asks/<id>/answer` | Responder: `{option: 1..n \| null, text}`. |
| `POST /api/plan/branches/<key>/nonstop` | Rama sin paradas: `{on: true\|false}`. |
| `GET /propuestas/<P-n>/<n>.html` | Un mockup de `.unificador/propuestas/` (solo esa forma de ruta), con CSP `sandbox`. |
| `GET /api/events` | Eventos en vivo (SSE) del proyecto que se ve: `plan` cuando cambia su fichero. |

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
se informa; que falten las reglas o el plan no responda sí es un error.

## Seguridad

- Escucha solo en `127.0.0.1` y no envía cabeceras CORS.
- Rechaza peticiones que no vengan de la propia página (`Host`, `Origin`, `Sec-Fetch-Site`).
- Política de contenido estricta: sin scripts en línea ni recursos de fuera; solo marcos del propio servidor.
- Los mockups del agente van en `<iframe sandbox="allow-scripts">` y se sirven con `sandbox allow-scripts;
  default-src 'none'…`: sin origen propio, sin red y sin poder llamar a la API ni tocar la página.
- No se lanza ningún proceso de agente ni se leen conversaciones.

## Pruebas

`python -m unittest discover -s tests`. Usan carpetas temporales; no gastan nada.
