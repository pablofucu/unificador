# Arquitectura del Sistema - Unificador

Especificación técnica de Unificador. Describe lo que **ya existe** en `unificador/` y marca con **[Pendiente]** lo que se decide aquí pero aún no está implementado. La sección 10 recoge las discrepancias detectadas entre código y diseño.

## 1. Propósito

Unificador es un orquestador **local** para desarrollo asistido por varios agentes de IA (Claude Code, Google Antigravity, OpenAI Codex / Cursor y DeepSeek API). Hace tres cosas:

1. Muestra el trabajo de cada proyecto en fases, a partir de su tablero Kanvas.
2. Ofrece un chat desde el que se elige agente y tarea; el mensaje llega al agente con el contexto del proyecto ya inyectado.
3. Automatiza el commit y el push a Git al terminar una tarea.

Principios: todo corre en la máquina del usuario (solo se escucha en `127.0.0.1`), el estado del trabajo vive en `kanvas.json` de cada proyecto (Unificador no tiene base de datos propia) y solo se usa la librería estándar de Python.

## 2. Vista general

```
 Frontend (HTML/JS)  ──HTTP/JSON──▶  server.py ──▶ ContextInjector ──▶ Adaptador ──▶ Agente
                                        │                                   (CLI / API)
                                        ├──▶ KanvasBridge ──▶ kanvas.json  (vía CLI kanvas)
                                        ├──▶ GitService   ──▶ git
                                        └──▶ ConfigManager ─▶ ~/.unificador/config.json
```

### Módulos

```
unificador/
├── models.py              # Dataclasses y enums
├── config.py              # ConfigManager: proyectos, claves API, rutas CLI, ajustes
├── kanvas_bridge.py       # Lee kanvas.json, calcula fases/profundidades, ejecuta la CLI kanvas
├── context_injector.py    # Ensambla el prompt enriquecido
├── git_service.py         # status, commit estructurado, push
├── server.py              # API HTTP (http.server, ThreadedHTTPServer)
└── adapters/
    ├── base.py            # BaseAgentAdapter
    ├── claude_code.py     # CLI `claude -p`
    ├── antigravity.py     # CLI `agy run`
    ├── codex.py           # Abre Cursor/VS Code (sin ejecución real todavía)
    └── deepseek.py        # API REST chat/completions con streaming
main.py                    # Punto de entrada: arranca el servidor
```

Dependencias permitidas entre módulos: `server` → todo; `adapters` → `models`, `config`; `context_injector`, `kanvas_bridge`, `git_service`, `config` → solo `models`. Ningún módulo importa `server`.

## 3. Modelos de datos (`models.py`)

| Tipo | Campos principales | Notas |
|---|---|---|
| `AgentType` (enum) | `antigravity`, `claude_code`, `codex`, `deepseek` | Valor textual usado en la API y en `config.json` |
| `TaskState` (enum) | `proposed`, `todo`, `doing`, `review`, `done` | Idéntico al flujo de Kanvas |
| `Task` | `id`, `title`, `description`, `state`, `group`, `deps[]`, `notes[]`, `depth`, `assigned_agent?` | Se rellena desde `kanvas.json`; `depth` es la profundidad en el grafo de dependencias |
| `Phase` | `id`, `name`, `order`, `color_tone`, `tasks[]`, `prefix` | Propiedades calculadas: `total_tasks`, `completed_tasks`, `progress_percent` (solo cuenta `done`) |
| `Project` | `id`, `name`, `path`, `color_theme`, `active_phase_id?`, `default_agent`, `git_repo?`, `git_branch`, `created_at` | `to_dict()` serializa `default_agent` como texto |
| `ChatMessage` | `role` (`user`/`assistant`/`system`), `content`, `agent_type`, `timestamp`, `task_id?`, `injected_context?` | **[Pendiente]** no se persiste el historial todavía |
| `ExecutionContext` | `project`, `phase?`, `active_task?`, `user_prompt`, `target_agent`, `history[]`, `board_rules`, `final_injected_prompt` | Lo único que recibe un adaptador |

## 4. Configuración y multi-proyecto (`config.py`)

Fichero: `~/.unificador/config.json` (se crea al primer arranque). Singleton `config`.

```json
{
  "projects": [
    {
      "id": "unificador",
      "name": "Unificador",
      "path": "C:\\Users\\pablo\\Documents\\Proyectos\\Unificador",
      "color_theme": "#3b82f6",
      "active_phase_id": null,
      "default_agent": "claude_code",
      "git_repo": null,
      "git_branch": "main",
      "created_at": 1730000000.0
    }
  ],
  "agents": {
    "claude_code": { "agent_type": "claude_code", "command": "claude", "model": "", "enabled": true, "extra_args": [] },
    "antigravity": { "agent_type": "antigravity", "command": "agy", "model": "", "enabled": true, "extra_args": [] }
  },
  "settings": { "auto_commit_on_finish": false, "port": 8766, "host": "127.0.0.1" }
}
```

Reglas:

- `id` único; registrar un proyecto con un `id` existente lo **reemplaza**.
- Las claves API viven en `~/.unificador/credentials.json` (aparte, permisos 0600), no en `config.json`. Las variables de entorno `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` tienen prioridad y nunca se escriben a disco. No se devuelven nunca por la API. Un `config.json` antiguo (`api_keys`, `cli_paths`) se migra solo.
- Un proyecto con datos corruptos se omite con un aviso por consola; no rompe el listado.
- Cada proyecto es independiente: su tablero es su propio `kanvas.json`, y Unificador lo trata como fuente de verdad.
- `cli_paths`, `auto_commit_on_finish`, `host` y `port` están en la configuración pero **[Pendiente]** todavía no los usa el código (los adaptadores fijan el nombre del comando y `main.py` arranca con valores por defecto).

## 5. Fases (`kanvas_bridge.py`)

Una **fase** es un grupo de Kanvas.

1. Si `kanvas.json` define grupos, cada grupo es una fase, en el orden en que aparece (`order` empieza en 1). Una tarea pertenece a la fase cuyo nombre o id coincide con su `group`.
2. Si no hay grupos, las fases se derivan de la profundidad en el grafo de dependencias: profundidad 0 → «Fase 1», 1 → «Fase 2», etc.
3. El color de cada fase sale de la paleta `PHASE_TONES` por posición.
4. `depth` de una tarea = longitud de su cadena más larga de dependencias; se calcula con recorrido recursivo y control de ciclos.

La fase **activa** de un chat se deduce de la tarea elegida (la fase que contiene la tarea). `Project.active_phase_id` queda reservado para recordar la última fase abierta en el frontend **[Pendiente]**.

## 6. Puente con Kanvas

Lectura: se parsea directamente `kanvas.json` (solo lectura).
Escritura: **siempre** mediante la CLI de Kanvas, nunca editando el JSON, para respetar las transiciones de estado.

`execute_cli(args)` usa `python <proyecto>/.agents/skills/kanvas/kanvas.py` si existe; si no, el comando `kanvas`. Se ejecuta con `cwd` = ruta del proyecto.

Operaciones expuestas: `add_note`, `start_task`, `finish_task`. La sintaxis real de la CLI es:

```
kanvas note   ID "texto"   [--as NOMBRE]
kanvas start  ID -m "plan" [--as NOMBRE]
kanvas finish ID -m "resumen" [--as NOMBRE]
kanvas ask    ID "pregunta"
```

`--as` se acepta antes o después del subcomando. Los agentes lanzados por Unificador deben firmar con su nombre (`claude-code`, `gemini`, `codex`, `deepseek`).

Reglas de propiedad (las impone la CLI, Unificador no las puentea): los agentes proponen, inician, finalizan y anotan; solo la persona aprueba propuestas y marca como hecho.

## 7. Inyección de contexto (`context_injector.py`)

`ContextInjector.build_context(project, user_prompt, target_agent, phase?, active_task?)` devuelve un `ExecutionContext` con `final_injected_prompt`.

Formato del prompt, en este orden:

```
[SISTEMA: CONTEXTO DEL PROYECTO INYECTADO AUTOMÁTICAMENTE POR UNIFICADOR]
Estás colaborando como agente de IA (<nombre del agente>) en este proyecto.
- Proyecto / Ruta local / Rama Git
- Fase Actual: <nombre> (Progreso: N%)                 ← solo si hay fase

### TAREA EN CURSO: [<ID>] <título>                      ← solo si hay tarea
- Estado, Descripción, Dependencias
- Últimas 3 notas

### REGLAS DE SEGUIMIENTO EN EL TABLERO (Kanvas)         ← protocolo de retroalimentación
### DIRECTRICES DE EJECUCIÓN
================================================================================
[INSTRUCCIÓN DEL USUARIO]:
<prompt del usuario>
```

- Sin tarea elegida, el `task_id` de las reglas es `GENERAL`.
- `format_for_cli` devuelve el texto completo; `format_for_api` lo separa en *system* (todo lo anterior a `[INSTRUCCIÓN DEL USUARIO]:`) y *user*.
- El protocolo de retroalimentación obliga al agente a: anotar avances (`note`), cerrar con resumen (`finish`), preguntar con `ask` cuando necesite una decisión y no editar nunca `kanvas.json` a mano.
- Las plantillas están en español y en constantes del módulo. **[Pendiente]** el historial del chat (`history`) no se incluye aún en el prompt.

## 8. Contrato de los adaptadores (`adapters/`)

```python
class BaseAgentAdapter(ABC):
    agent_type: AgentType
    name: str
    def is_installed(self) -> bool
    def stream_execute(self, context) -> Iterator[Event]        # eventos (ver abajo)
    def execute_sync(self, context) -> tuple[int, str]          # se construye sobre el stream
    def launch_native_window(self, context) -> tuple[bool, str] # (éxito, mensaje)
```

Eventos de `stream_execute` (`as_event` normaliza un `str` a `{"type": "text"}`):

| Evento | Significado |
|---|---|
| `{"type": "text", "text"}` | Trozo de la respuesta, en cuanto llega |
| `{"type": "tool", "text"}` | Acción del agente en una línea («Ejecuta ls», «Edita app.js») |
| `{"type": "session", "id"}` | Id de la sesión nativa (Claude Code / Antigravity) para continuarla |
| `{"type": "error", "text"}` | Fallo accionable; `execute_sync` devuelve código 1 si hubo alguno |

Reglas comunes:

- Ningún adaptador lanza excepciones por fallos del agente: los emite como evento `error`.
- `run_json_lines` (en `base.py`) lanza la CLI sin ventana, lee su salida JSON línea a línea, la pasa al parser del adaptador y, si el proceso acaba mal sin haber emitido error, emite uno con las últimas líneas. Mata el proceso si el cliente corta.
- El directorio de trabajo es siempre `context.project.path`; la variable `KANVAS_AGENT` firma las notas del tablero.
- `permission_mode` (config del agente, por defecto `auto`) se traduce al modo de permisos de cada CLI.
- El registro `ADAPTERS` (en `adapters/__init__.py`) asocia cada `AgentType` con una instancia; `get_adapter` lanza `ValueError` si falta.

| Agente | Ejecución | Sesión nativa | «Abrir en…» |
|---|---|---|---|
| **Claude Code** | `claude -p --output-format stream-json --include-partial-messages --permission-mode X`; prompt por `stdin` | Turno 1: `--session-id <uuid> -n <título>`; después `--resume <id>`. Queda en `~/.claude/projects/<ruta>/<id>.jsonl` | `wt -d <ruta> claude --resume <id>` (o `cmd start`) |
| **Antigravity** | `agy --output-format stream-json [--mode …] -p <prompt>` (por encima de 24 000 caracteres el prompt va en `.unificador_prompt.md`) | `--conversation <id>` (id del evento `init`) | `wt -d <ruta> agy --conversation <id>`; sin conversación, `antigravity-ide <ruta>` |
| **Codex / Cursor** | No chatea: emite un error que remite a «Abrir» | – | `cursor` o `code` |
| **DeepSeek** | API `chat/completions` (modelo de la config, `deepseek-chat` por defecto) con *system* + últimos 20 mensajes del historial | – (el historial lo guarda Unificador) | No aplica |

DeepSeek es solo un modelo de chat: no ejecuta la CLI `kanvas`, así que su prompt no la menciona.

## 9. Git (`git_service.py`) y API (`server.py`)

### Git

| Operación | Comportamiento |
|---|---|
| `is_git_repo()` | `git rev-parse --is-inside-work-tree` |
| `get_status()` | `{is_repo, branch, clean, files:[{status,file}], changed_count}` |
| `commit_task(task_id, title, phase?, author?)` | `git add .` + commit con mensaje `[<Fase>] <ID>: <título>` y, si hay autor, `Realizado por: <autor>` |
| `push(remote="origin", branch?)` | `git push -u <remote> <rama actual>` (fija la rama remota). Ruta: `POST /api/git/push` |

Un commit sin cambios se considera éxito («No había cambios pendientes»). La automatización con `auto_commit_on_finish` **[Pendiente]**. El commit actual añade todo el árbol con `git add .`; **[Pendiente]** limitarlo a los ficheros del agente o pedir confirmación.

### Itinerario (`itinerary.py`)

Traduce el tablero a **Rama > Fase > Paso**: cada grupo del tablero es una rama, cada tarea un paso, y las fases son tramos dentro de la rama (un paso va un tramo después de las tareas del mismo grupo de las que depende; sin dependencias, tramo 1). Las ramas sin tareas no aparecen. Estados del paso: `proposed`/`todo` → `pend`, `doing` → `run`, `review` → `toca`, `done` → `hecho`; `blocked` marca un `todo` con dependencias sin terminar. El estado de la fase sale de sus pasos (todo hecho → `hecho`; alguno `toca` → `toca`; alguno `run` → `run`; si no, `pend`). `join` («Juntarlo todo») es `hecho` solo cuando todos los pasos lo están. Las fases se llaman «Fase N»: el tablero no guarda nombres de fase.

### API HTTP

Servidor `ThreadedHTTPServer` en `127.0.0.1:8766`, JSON, CORS abierto para el frontend local. Errores: `{ "error": "..." }` con 400 / 404 / 500.

| Método y ruta | Entrada | Salida |
|---|---|---|
| `GET /api/status` | – | `{status, version, adapters:{agente:{name,installed}}}` |
| `GET /api/projects` | – | Proyectos con `total_tasks`, `phases_count`, `progress`, `run` (en curso) y `toca` (en revisión) |
| `POST /api/projects` | `name`, `path?`, `id?`, `color_theme?`, `default_agent?`, `git?` (por defecto `true`) | 201 con `{project, setup}`. `id` sale del nombre (minúsculas ASCII y `_`); sin `path` se crea `~/Unificador/<id>`. Deja el proyecto listo para planificar: `kanvas init` (tablero, skill y `AGENTS.md`) si no hay `kanvas.json`, y `git init -b main` con un primer commit. `setup` lista lo que falló. 400 si falta el nombre o la carpeta no se puede crear; 409 si el id ya existe |
| `GET /api/projects/<id>/chats` | – | `{chats:[{id,title,agent,count,updated,...}]}`, la más reciente primero |
| `GET /api/projects/<id>/chats/<chat>` | – | La conversación con `messages`; antes trae los turnos escritos en la terminal de Claude Code (`sync_from_claude`) |
| `POST /api/projects/<id>/chats` | `agent?`, `task_id?`, `title?` | 201 con la conversación vacía |
| `DELETE /api/projects/<id>/chats/<chat>` | – | `{deleted}`; borra solo la copia de Unificador |
| `POST /api/projects/<id>/plan/approve` | `ids?` (sin `ids`, todas las propuestas) | `{approved:[...]}`: `proposed → todo` con la nota «Plan aprobado.» |
| `GET /api/projects/<id>/board` | – | `{project, phases:[{id,name,order,color,progress,tasks[]}]}` |
| `GET /api/projects/<id>/itinerary` | – | `{project, ramas:[{id,name,color,fases:[{name,state,steps:[{id,title,description,state,board_state,blocked,last_note}]}]}], counts:{total,hecho,run,toca}, join:{name,state}}` (`itinerary.py`) |
| `GET /` y ficheros de `frontend/` | – | El frontend estático (`index.html`, `styles.css`, `app.js`); las rutas `/api/...` nunca se sirven como fichero |
| `POST /api/chat/prepare` | `project_id`, `prompt`, `agent?`, `task_id?` | `{injected_prompt, project, agent, task_id}` (no ejecuta nada) |
| `POST /api/chat/send` | igual | `{exit_code, response, agent, task_id}` (síncrono; 500 si el código ≠ 0) |
| `POST /api/chat/launch-native` | igual, más `chat_id?` | `{success, message, agent}`; con `chat_id` reabre su sesión nativa |
| `GET /api/git/status?project_id=` | – | `{is_repo, branch, clean, files:[{status,file}], changed_count, has_remote, ahead}`; `ahead` = commits sin subir |
| `POST /api/git/push` | `project_id`, `remote?`, `branch?` | `{success, message}` |
| `POST /api/chat/stream` | igual que `send`, más `chat_id?` y `save?` (por defecto `true`) | SSE: `event: chat` {id,title}; `data: {"chunk"}` por fragmento; `event: tool` {text}; `event: error` {error}; `event: done`. Sin `chat_id` crea una conversación. 404 si `chat_id` no existe; 400 si el mensaje está vacío |
| `POST /api/projects/<id>/tasks/<paso>/accept` | – | Revisión humana: `review → done`, con nota de `usuario`. 404 si no existe, 409 si el paso no está en revisión. Escribe con el `kanvas.py` del proyecto (mismo bloqueo y formato) |
| `POST /api/projects/<id>/tasks/<paso>/send-back` | `comment` (obligatorio, 400 si vacío) | `review → doing` con el comentario como nota |
| `POST /api/git/commit` | `project_id`, `task_id?`, `title?`, `phase?`, `author?` | `{success, message}` |

El streaming del chat usa SSE (`/api/chat/stream`, sobre `stream_execute`); no hay WebSocket. Un `agent` no válido devuelve 400.

### Conversaciones (`chats.py`)

Cada conversación es un JSON en `~/.unificador/chats/<proyecto>/<id>.json` con `agent`, `native_session_id`, `title` (de la primera pregunta) y `messages` (`role`, `content`, `agent`, `task_id`, `tools?`, `error?`, `source?`). El stream guarda el mensaje de la persona antes de lanzar el agente y la respuesta al terminar, aunque se corte.

- **Mismo agente** → se continúa su sesión nativa y el contexto inyectado es corto (`followup`): el agente ya tiene las reglas en su sesión. **Otro agente** → la sesión se descarta y se envía el contexto completo.
- **Clientes nativos**: la conversación de Claude Code vive también en su historial (`claude --resume`) y lo que se escriba allí aparece en Unificador al abrirla (`source: "claude_code"`). La de Antigravity queda en el historial de la CLI `agy` (`agy --conversation`); el IDE de Antigravity guarda sus conversaciones aparte.

### Planificación por fases

Con el tablero vacío, el prompt pide a la IA un plan antes de programar: una rama (grupo) por línea de trabajo y pasos con `deps`, de modo que cada tramo de dependencias sea una fase; todo con `kanvas batch` y en estado `proposed`. La persona lo ve en la tarjeta «Plan propuesto» y lo aprueba (`plan/approve`) o pide cambios en el chat.

## 10. Discrepancias pendientes

1. **`cli_paths`, `host`, `port` y `auto_commit_on_finish` no se aplican del todo** (ver sección 4).
2. **El IDE de Antigravity no muestra las conversaciones de la CLI `agy`**: «Abrir en Antigravity» las reabre en la terminal.
3. **El commit de un paso añade todo el árbol** (`git add .`).

## 11. Fuera de alcance (por ahora)

Autenticación (la API solo escucha en localhost), ejecución remota, varios usuarios, edición del tablero desde Unificador (la hacen los agentes y la persona mediante Kanvas) y resolución de conflictos Git.
