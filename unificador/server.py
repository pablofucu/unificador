"""
Servidor API REST backend para Unificador.
Provee endpoints JSON para proyectos, fases de Kanvas, inyección de prompts,
lanzamiento de agentes nativos y control de Git.
"""

from __future__ import annotations
import json
import mimetypes
import re
import unicodedata
import urllib.parse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Dict, Any, Optional

from unificador.config import config
from unificador.models import Project, AgentType
from unificador.kanvas_bridge import KanvasBridge
from unificador.context_injector import ContextInjector
from unificador.adapters import get_adapter, list_adapters_status
from unificador.git_service import GitService
from unificador.itinerary import build_itinerary
from unificador.chats import chat_store
from unificador.adapters.base import as_event


injector = ContextInjector()
DEFAULT_PROJECTS_DIR = Path.home() / "Unificador"
FRONTEND_DIR = (Path(__file__).resolve().parent.parent / "frontend").resolve()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def slugify(name: str) -> str:
    """Identificador estable a partir del nombre: minúsculas ASCII y guiones bajos."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_") or "proyecto"


def sse(event: Optional[str], payload: Dict[str, Any]) -> str:
    """Formatea un mensaje Server-Sent Event."""
    head = f"event: {event}\n" if event else ""
    return head + "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _build_chat_context(data: Dict[str, Any], chat: Optional[Dict[str, Any]] = None):
    """Devuelve (contexto, agent_type, task_id, error). error = (status, mensaje) o None.

    Con ``chat`` (conversación guardada) se continúa su sesión nativa si es del mismo agente
    y se le pasa el historial.
    """
    project = config.get_project(data.get("project_id"))
    if not project:
        return None, None, None, (404, "Proyecto no encontrado")
    try:
        agent_type = AgentType(data.get("agent", project.default_agent.value))
    except ValueError:
        return None, None, None, (400, f"Agente no válido: {data.get('agent')!r}")
    task_id = data.get("task_id")
    bridge = KanvasBridge(project.path)
    task = bridge.get_task(task_id) if task_id else None
    phases, tasks = bridge.get_phases_and_tasks()
    active_phase = next((ph for ph in phases if task and task.group == ph.name), None)
    same_agent = bool(chat) and chat.get("agent") == agent_type.value
    session = chat.get("native_session_id") if same_agent else None
    context = injector.build_context(
        project=project,
        user_prompt=data.get("prompt", ""),
        target_agent=agent_type,
        phase=active_phase,
        active_task=task,
        tasks=tasks if bridge.board_exists() else None,
        followup=bool(session),
    )
    if chat:
        context.native_session_id = session
        context.chat_title = chat.get("title", "")
        context.history = [{"role": m["role"], "content": m["content"]} for m in chat.get("messages", [])]
    return context, agent_type, task_id, None


class UnificadorAPIHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: Any):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Optional[Dict[str, Any]]:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        try:
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except Exception:
            return None

    def _stream_sse(self, adapter, context, chat: Optional[Dict[str, Any]] = None):
        """Respuesta en streaming (Server-Sent Events).

        Eventos: `chat` {id, title} al empezar; `data: {"chunk"}` con el texto; `tool` {text};
        `error` {error}; `done` {}. Con ``chat`` se guardan el mensaje de la persona antes de
        lanzar el agente y su respuesta (aunque se corte) al terminar.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def emit(payload: str):
            self.wfile.write(payload.encode("utf-8"))
            self.wfile.flush()

        pid = context.project.id
        agent = context.target_agent.value
        task_id = context.active_task.id if context.active_task else None
        text, tools, errors = [], [], []
        if chat:
            if chat.get("agent") != agent:  # cambió de agente: la sesión anterior no le sirve
                chat_store.update(pid, chat["id"], agent=agent, native_session_id=None)
            chat = chat_store.append(pid, chat["id"], {"role": "user", "content": context.user_prompt,
                                                         "agent": agent, "task_id": task_id}) or chat
        try:
            if chat:
                emit(sse("chat", {"id": chat["id"], "title": chat.get("title", "")}))
            for raw in adapter.stream_execute(context):
                ev = as_event(raw)
                kind = ev.get("type")
                if kind == "text":
                    text.append(ev["text"])
                    emit(sse(None, {"chunk": ev["text"]}))
                elif kind == "tool":
                    tools.append(ev["text"])
                    emit(sse("tool", {"text": ev["text"]}))
                elif kind == "session" and chat:
                    chat_store.update(pid, chat["id"], native_session_id=ev["id"])
                elif kind == "error":
                    errors.append(ev["text"])
                    emit(sse("error", {"error": ev["text"]}))
            emit(sse("done", {}))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            errors.append(str(e))
            try:
                emit(sse("error", {"error": str(e)}))
            except OSError:
                pass
        finally:
            if chat and (text or tools or errors):
                msg = {"role": "assistant", "content": "".join(text).strip(), "agent": agent, "task_id": task_id}
                if tools:
                    msg["tools"] = tools
                if errors:
                    msg["error"] = errors[-1]
                chat_store.append(pid, chat["id"], msg)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, PUT, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = urllib.parse.parse_qs(parsed.query)

        # GET /api/status
        if path == "/api/status":
            return self._send_json(200, {
                "status": "online",
                "version": "0.1.0",
                "adapters": list_adapters_status()
            })

        # GET /api/projects
        if path == "/api/projects":
            projects = config.get_projects()
            out = []
            for p in projects:
                p_dict = p.to_dict()
                bridge = KanvasBridge(p.path)
                phases, tasks = bridge.get_phases_and_tasks()
                p_dict["total_tasks"] = len(tasks)
                p_dict["phases_count"] = len(phases)
                completed = sum(1 for t in tasks if t.state.value == "done")
                p_dict["progress"] = round((completed / len(tasks) * 100), 1) if tasks else 0.0
                p_dict["run"] = sum(1 for t in tasks if t.state.value == "doing")
                p_dict["toca"] = sum(1 for t in tasks if t.state.value == "review")
                out.append(p_dict)
            return self._send_json(200, {"projects": out})

        # GET /api/projects/<id>/board
        if path.startswith("/api/projects/") and path.endswith("/board"):
            project_id = path.split("/")[3]
            project = config.get_project(project_id)
            if not project:
                return self._send_json(404, {"error": f"Proyecto '{project_id}' no encontrado"})

            bridge = KanvasBridge(project.path)
            phases, tasks = bridge.get_phases_and_tasks()

            return self._send_json(200, {
                "project": project.to_dict(),
                "phases": [
                    {
                        "id": ph.id,
                        "name": ph.name,
                        "order": ph.order,
                        "color": ph.color_tone,
                        "progress": ph.progress_percent,
                        "tasks": [
                            {
                                "id": t.id,
                                "title": t.title,
                                "description": t.description,
                                "state": t.state.value,
                                "group": t.group,
                                "deps": t.deps,
                                "notes": t.notes
                            }
                            for t in ph.tasks
                        ]
                    }
                    for ph in phases
                ]
            })

        # GET /api/projects/<id>/itinerary
        # GET /api/projects/<id>/chats  |  /api/projects/<id>/chats/<chat>
        m = re.fullmatch(r"/api/projects/([^/]+)/chats(?:/([^/]+))?", path)
        if m:
            pid, cid = (urllib.parse.unquote(x) if x else None for x in m.groups())
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": f"Proyecto '{pid}' no encontrado"})
            if not cid:
                return self._send_json(200, {"chats": chat_store.list(pid)})
            chat = chat_store.sync_from_claude(pid, cid, project.path)
            if not chat:
                return self._send_json(404, {"error": "Conversación no encontrada"})
            return self._send_json(200, chat)

        if path.startswith("/api/projects/") and path.endswith("/itinerary"):
            project_id = path[len("/api/projects/"):-len("/itinerary")]
            project = config.get_project(project_id)
            if not project:
                return self._send_json(404, {"error": f"Proyecto '{project_id}' no encontrado"})
            phases, tasks = KanvasBridge(project.path).get_phases_and_tasks()
            return self._send_json(200, {
                "project": project.to_dict(),
                **build_itinerary(phases, tasks),
            })

        # GET /api/git/status?project_id=...
        if path == "/api/git/status":
            pid = query.get("project_id", [""])[0]
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": "Proyecto no encontrado"})
            git = GitService(project.path)
            return self._send_json(200, git.get_status())

        if not path.startswith("/api/") and self._serve_static(path):
            return

        self._send_json(404, {"error": "Ruta no encontrada"})

    def _serve_static(self, path: str) -> bool:
        """Sirve ficheros de frontend/. Devuelve False si no existe."""
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        target = (FRONTEND_DIR / rel).resolve()
        if FRONTEND_DIR not in target.parents or not target.is_file():
            return False
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)
        return True

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"error": "JSON no válido"})

        # POST /api/projects (Registrar nuevo proyecto)
        if path == "/api/projects":
            name = (data.get("name") or "").strip()
            if not name:
                return self._send_json(400, {"error": "Se requiere 'name'"})
            proj_id = data.get("id") or slugify(name)
            if config.get_project(proj_id):
                return self._send_json(409, {"error": "Ya tienes un proyecto con ese nombre"})
            proj_dir = Path(data.get("path") or DEFAULT_PROJECTS_DIR / proj_id).expanduser()
            try:
                proj_dir.mkdir(parents=True, exist_ok=True)
                agent = AgentType(data.get("default_agent", AgentType.CLAUDE_CODE.value))
            except (OSError, ValueError) as e:
                return self._send_json(400, {"error": f"No se pudo crear el proyecto: {e}"})

            new_project = Project(
                id=proj_id,
                name=name,
                path=str(proj_dir),
                color_theme=data.get("color_theme", "#3b82f6"),
                default_agent=agent,
            )
            # Listo para planificar: tablero Kanvas (con instrucciones para los agentes) y Git
            setup = []
            if not (proj_dir / "kanvas.json").is_file():
                code, out = KanvasBridge.init_project(proj_dir)
                setup.append("Tablero Kanvas creado." if code == 0 else f"No se pudo crear el tablero: {out[-300:]}")
            if data.get("git", True):
                git = GitService(proj_dir)
                ok, out = git.init_repo()
                if ok:
                    new_project.git_branch = git.get_current_branch() or new_project.git_branch
                else:
                    setup.append(f"No se pudo iniciar Git: {out[-300:]}")
            config.add_project(new_project)
            return self._send_json(201, {"message": "Proyecto creado", "project": new_project.to_dict(),
                                         "setup": setup})

        # POST /api/projects/<id>/chats  (nueva conversación)
        m = re.fullmatch(r"/api/projects/([^/]+)/chats", path)
        if m:
            pid = urllib.parse.unquote(m.group(1))
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": f"Proyecto '{pid}' no encontrado"})
            chat = chat_store.create(pid, data.get("agent") or project.default_agent.value,
                                     data.get("task_id"), data.get("title", ""))
            return self._send_json(201, chat)

        # POST /api/projects/<id>/plan/approve  {ids?: [...]}  (proposed -> todo)
        m = re.fullmatch(r"/api/projects/([^/]+)/plan/approve", path)
        if m:
            pid = urllib.parse.unquote(m.group(1))
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": f"Proyecto '{pid}' no encontrado"})
            ids = data.get("ids")
            if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
                return self._send_json(400, {"error": "'ids' debe ser una lista de ids"})
            try:
                approved = KanvasBridge(project.path).approve_tasks(ids)
            except FileNotFoundError as e:
                return self._send_json(409, {"error": str(e)})
            except Exception as e:
                return self._send_json(500, {"error": f"No se pudo actualizar el tablero: {e}"})
            return self._send_json(200, {"approved": approved})

        # POST /api/projects/<id>/tasks/<task>/accept | send-back
        m = re.fullmatch(r"/api/projects/([^/]+)/tasks/([^/]+)/(accept|send-back)", path)
        if m:
            pid, tid, action = (urllib.parse.unquote(x) for x in m.groups())
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": f"Proyecto '{pid}' no encontrado"})
            comment = str(data.get("comment") or "").strip()
            if action == "send-back" and not comment:
                return self._send_json(400, {"error": "Cuéntale a la IA qué quieres cambiar"})
            try:
                state = KanvasBridge(project.path).review_task(tid, action == "accept", comment)
            except KeyError:
                return self._send_json(404, {"error": f"Paso '{tid}' no encontrado"})
            except ValueError as e:
                return self._send_json(409, {"error": str(e)})
            except Exception as e:
                return self._send_json(500, {"error": f"No se pudo actualizar el tablero: {e}"})
            return self._send_json(200, {"id": tid, "board_state": state})

        # POST /api/chat/prepare | send | stream | launch-native
        if path in ("/api/chat/prepare", "/api/chat/send", "/api/chat/stream", "/api/chat/launch-native"):
            chat = None
            project = config.get_project(data.get("project_id"))
            if project and data.get("chat_id") and path in ("/api/chat/stream", "/api/chat/launch-native"):
                chat = chat_store.get(project.id, str(data["chat_id"]))
                if not chat:
                    return self._send_json(404, {"error": "Conversación no encontrada"})
            elif project and path == "/api/chat/stream" and data.get("save", True) and str(data.get("prompt", "")).strip():
                chat = chat_store.create(project.id, data.get("agent") or project.default_agent.value,
                                         data.get("task_id"))
            context, agent_type, task_id, err = _build_chat_context(data, chat)
            if err:
                return self._send_json(err[0], {"error": err[1]})

            if path == "/api/chat/prepare":
                return self._send_json(200, {
                    "injected_prompt": context.final_injected_prompt,
                    "project": context.project.name,
                    "agent": agent_type.value,
                    "task_id": task_id
                })

            adapter = get_adapter(agent_type)

            if path == "/api/chat/send":
                code, response_text = adapter.execute_sync(context)
                return self._send_json(200 if code == 0 else 500, {
                    "exit_code": code,
                    "response": response_text,
                    "agent": agent_type.value,
                    "task_id": task_id
                })

            if path == "/api/chat/stream":
                if not context.user_prompt.strip():
                    return self._send_json(400, {"error": "Escribe un mensaje"})
                return self._stream_sse(adapter, context, chat)

            success, msg = adapter.launch_native_window(context)
            return self._send_json(200 if success else 500, {
                "success": success,
                "message": msg,
                "agent": agent_type.value
            })

        # POST /api/git/push
        if path == "/api/git/push":
            project = config.get_project(data.get("project_id"))
            if not project:
                return self._send_json(404, {"error": "Proyecto no encontrado"})
            git = GitService(project.path)
            success, msg = git.push(data.get("remote", "origin"), data.get("branch"))
            return self._send_json(200 if success else 500, {"success": success, "message": msg})

        # POST /api/git/commit
        if path == "/api/git/commit":
            pid = data.get("project_id")
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": "Proyecto no encontrado"})

            task_id = data.get("task_id", "GENERAL")
            task_title = data.get("title", "Actualización")
            phase_name = data.get("phase")
            author = data.get("author", "Unificador")

            git = GitService(project.path)
            success, msg = git.commit_task(task_id, task_title, phase_name, author)
            return self._send_json(200 if success else 500, {"success": success, "message": msg})

        self._send_json(404, {"error": "Ruta no encontrada"})


def _do_delete(self):
    path = urllib.parse.urlparse(self.path).path.rstrip("/")
    m = re.fullmatch(r"/api/projects/([^/]+)/chats/([^/]+)", path)
    if not m:
        return self._send_json(404, {"error": "Ruta no encontrada"})
    pid, cid = (urllib.parse.unquote(x) for x in m.groups())
    if not chat_store.delete(pid, cid):
        return self._send_json(404, {"error": "Conversación no encontrada"})
    return self._send_json(200, {"deleted": cid})


UnificadorAPIHandler.do_DELETE = _do_delete


def start_server(host: str = "127.0.0.1", port: int = 8766):
    server = ThreadedHTTPServer((host, port), UnificadorAPIHandler)
    print(f"[Unificador] Servidor API activo en http://{host}:{port}/api/status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Unificador] Deteniendo servidor...")
        server.server_close()
