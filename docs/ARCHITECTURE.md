# Cómo está hecho Unificador

Un servidor local en Python (solo biblioteca estándar) que sirve una página estática y habla con los
agentes a través de sus propias órdenes de terminal. No hay base de datos ni dependencias.

```text
navegador  ⇄  unificador/app.py (127.0.0.1)  ⇄  claude / agy  (procesos)
                    │                                │
                    ├─ unificador.json  ← plan  ←── .unificador/uni.py (lo usa la IA)
                    └─ lee las sesiones nativas: ~/.claude/projects/… y ~/.gemini/antigravity-cli/…
```

## Dos ideas que lo sostienen

1. **El plan es un fichero** (`unificador.json`) dentro del proyecto. La web lo lee; la IA lo cambia con
   `uni.py`; la persona, desde la web. Todos escriben a través de `unificador/plan.py`, que valida y
   guarda de forma atómica.
2. **Las conversaciones son las del agente**, no copias. Unificador lanza `claude -p --resume <id>` o
   `agy --conversation <id>` y lee el historial de donde cada agente lo guarda. Por eso lo escrito en
   la web aparece en la aplicación nativa y al revés.

## El plan

```text
branches[]   rama: key, name, goal, icon, color, archived?
  phases[]   fase: name, icon
    steps[]  paso: id, title, desc, state (pending | doing | done), change?, result?, notes[], updated
```

- El estado de fases y ramas se calcula a partir de sus pasos; no se guarda.
- `change` es una corrección pedida por la persona: reabre el paso hasta que la IA lo termina otra vez.
- `notes` es la historia del paso: quién (`ia` o `persona`), cuándo y qué.

## Módulos (`unificador/`)

| Módulo | Qué hace |
| --- | --- |
| `cli.py` | Orden `unificador`: abrir la web, `install`, `import-kanvas`. |
| `app.py` | Servidor HTTP: ficheros de `web/`, API JSON, chat en streaming y eventos en vivo. |
| `plan.py` | Formato del plan, operaciones y la orden `uni` (se copia al proyecto como `.unificador/uni.py`). |
| `rules.py` | Prepara un proyecto: `uni.py`, bloque de reglas en `AGENTS.md`/`CLAUDE.md` y aviso de inicio de sesión. Se puede repetir sin duplicar nada. |
| `agents.py` | Qué agentes hay instalados, sus modelos, y cómo lanzarlos y traducir su salida a eventos. |
| `sessions.py` | Lee las sesiones de Claude Code del proyecto (`~/.claude/projects/<carpeta>/*.jsonl`). |
| `agy_sessions.py` | Lee las conversaciones de Antigravity (SQLite en solo lectura y un lector mínimo de protobuf). |
| `kanvas_import.py` | Convierte un `kanvas.json` antiguo en plan. |
| `web/` | La página: `index.html`, `app.css`, `app.js` (arranque y eventos), `plan.js`, `chat.js`. JavaScript sin librerías. |

Aparcados, sin uso en la aplicación: `adapters/` (DeepSeek), `config.py`, `models.py` y `git_service.py`,
restos de la versión anterior.

## API

| Ruta | Para qué |
| --- | --- |
| `GET /api/project` | Nombre del proyecto, agentes disponibles y preferencias guardadas. |
| `GET /api/plan` | El plan con el progreso calculado. |
| `POST /api/plan/steps/<id>/state` | Marcar un paso a mano: `{state, text?}`. |
| `POST /api/plan/steps/<id>/change` | Pedir un cambio: `{text}`; reabre el paso. |
| `GET /api/sessions` | Conversaciones del proyecto de todos los agentes. |
| `GET /api/sessions/<agente>/<id>` | Una conversación, en turnos limpios. |
| `POST /api/settings` | Guardar agente, modelo, esfuerzo y modo elegidos (`.unificador/local.json`). |
| `POST /api/chat` | Enviar un mensaje. Responde línea a línea (NDJSON): `run`, `session`, `model`, `text`, `tool`, `error`, `stopped`, `done`. |
| `POST /api/chat/stop` | Parar una respuesta: `{run}`. |
| `POST /api/open-native` | Abrir la conversación en la terminal del agente. |
| `GET /api/events` | Eventos en vivo (SSE): `plan` y `sessions` cuando algo cambia en disco. |

## Chat

- **Claude Code**: `claude -p --output-format stream-json --permission-mode <modo> [--model] [--effort]`
  con `--session-id` (conversación nueva) o `--resume`. El mensaje va por la entrada estándar.
- **Antigravity**: `agy --output-format stream-json --mode <modo> [--model] [--conversation <id>] -p <mensaje>`.
- Una conversación solo puede tener una respuesta en curso; parar mata el proceso del agente.
- El modelo que se enseña junto a cada respuesta es el que dice el propio agente, no el elegido.

## Seguridad

- Escucha solo en `127.0.0.1` y no envía cabeceras CORS.
- Rechaza peticiones que no vengan de la propia página (`Host`, `Origin`, `Sec-Fetch-Site`).
- Política de contenido estricta: sin scripts en línea ni recursos de fuera.
- Los identificadores de sesión y de modelo se validan antes de llegar a una orden; nunca se usa un intérprete de órdenes.
- Solo se leen conversaciones del proyecto abierto.

## Pruebas

`python -m unittest discover -s tests`. Usan carpetas temporales y agentes de mentira; no gastan nada.
