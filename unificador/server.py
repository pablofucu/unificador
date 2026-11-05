"""
Servidor API REST backend para Unificador.
Provee endpoints JSON para proyectos, fases de Kanvas, inyección de prompts,
lanzamiento de agentes nativos y control de Git.
"""

from __future__ import annotations
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Dict, Any, Optional

from unificador.config import config
from unificador.models import Project, AgentType
from unificador.kanvas_bridge import KanvasBridge
from unificador.context_injector import ContextInjector
from unificador.adapters import get_adapter, list_adapters_status
from unificador.git_service import GitService


injector = ContextInjector()


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


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

        # GET /api/git/status?project_id=...
        if path == "/api/git/status":
            pid = query.get("project_id", [""])[0]
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": "Parámetro project_id requerido"})
            git = GitService(project.path)
            return self._send_json(200, git.get_status())

        self._send_json(404, {"error": "Ruta no encontrada"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        data = self._read_json()
        if data is None:
            return self._send_json(400, {"error": "JSON no válido"})

        # POST /api/projects (Registrar nuevo proyecto)
        if path == "/api/projects":
            name = data.get("name")
            proj_path = data.get("path")
            if not name or not proj_path:
                return self._send_json(400, {"error": "Se requieren 'name' y 'path'"})

            new_project = Project(
                id=data.get("id") or name.lower().replace(" ", "_"),
                name=name,
                path=proj_path,
                color_theme=data.get("color_theme", "#3b82f6"),
                default_agent=AgentType(data.get("default_agent", AgentType.CLAUDE_CODE.value))
            )
            config.add_project(new_project)
            return self._send_json(201, {"message": "Proyecto registrado", "project": new_project.to_dict()})

        # POST /api/chat/prepare (Construir e inyectar prompt sin ejecutar)
        if path == "/api/chat/prepare":
            pid = data.get("project_id")
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": "Proyecto no encontrado"})

            agent_type = AgentType(data.get("agent", project.default_agent.value))
            user_prompt = data.get("prompt", "")
            task_id = data.get("task_id")

            bridge = KanvasBridge(project.path)
            task = bridge.get_task(task_id) if task_id else None
            phases, _ = bridge.get_phases_and_tasks()
            active_phase = next((ph for ph in phases if task and task.group == ph.name), None)

            context = injector.build_context(
                project=project,
                user_prompt=user_prompt,
                target_agent=agent_type,
                phase=active_phase,
                active_task=task
            )

            return self._send_json(200, {
                "injected_prompt": context.final_injected_prompt,
                "project": project.name,
                "agent": agent_type.value,
                "task_id": task_id
            })

        # POST /api/chat/send (Ejecutar prompt con el agente)
        if path == "/api/chat/send":
            pid = data.get("project_id")
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": "Proyecto no encontrado"})

            agent_type = AgentType(data.get("agent", project.default_agent.value))
            user_prompt = data.get("prompt", "")
            task_id = data.get("task_id")

            bridge = KanvasBridge(project.path)
            task = bridge.get_task(task_id) if task_id else None
            phases, _ = bridge.get_phases_and_tasks()
            active_phase = next((ph for ph in phases if task and task.group == ph.name), None)

            context = injector.build_context(
                project=project,
                user_prompt=user_prompt,
                target_agent=agent_type,
                phase=active_phase,
                active_task=task
            )

            adapter = get_adapter(agent_type)
            code, response_text = adapter.execute_sync(context)

            return self._send_json(200 if code == 0 else 500, {
                "exit_code": code,
                "response": response_text,
                "agent": agent_type.value,
                "task_id": task_id
            })

        # POST /api/chat/launch-native (Lanzar ventana oficial en el PC)
        if path == "/api/chat/launch-native":
            pid = data.get("project_id")
            project = config.get_project(pid)
            if not project:
                return self._send_json(404, {"error": "Proyecto no encontrado"})

            agent_type = AgentType(data.get("agent", project.default_agent.value))
            user_prompt = data.get("prompt", "")
            task_id = data.get("task_id")

            bridge = KanvasBridge(project.path)
            task = bridge.get_task(task_id) if task_id else None
            phases, _ = bridge.get_phases_and_tasks()
            active_phase = next((ph for ph in phases if task and task.group == ph.name), None)

            context = injector.build_context(
                project=project,
                user_prompt=user_prompt,
                target_agent=agent_type,
                phase=active_phase,
                active_task=task
            )

            adapter = get_adapter(agent_type)
            success, msg = adapter.launch_native_window(context)

            return self._send_json(200 if success else 500, {
                "success": success,
                "message": msg,
                "agent": agent_type.value
            })

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


def start_server(host: str = "127.0.0.1", port: int = 8766):
    server = ThreadedHTTPServer((host, port), UnificadorAPIHandler)
    print(f"[Unificador] Servidor API activo en http://{host}:{port}/api/status")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Unificador] Deteniendo servidor...")
        server.server_close()
