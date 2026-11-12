"""
Servidor local de Unificador: una web con todos tus proyectos, solo para esta máquina.

- Sirve el proyecto con el que arrancó y los del registro (``projects.py``), elegidos con ``?project=<id>``;
  nunca una carpeta que no salga de ahí.
- Escucha únicamente en 127.0.0.1 y no envía cabeceras CORS: ninguna otra web puede leerlo.
- Rechaza peticiones que no vengan de la propia página (Host, Origin y Sec-Fetch-Site). Los mockups de
  ``/propuestas/`` se sirven con una CSP ``sandbox``: sin origen propio, sin red y sin acceso a la página.
- Los GET no cambian nada; los cambios van por POST con JSON.
- Las rutas están en una tabla (``ROUTES``): método, patrón y función.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from unificador import plan as P
from unificador import projects as R

WEB_DIR = Path(__file__).parent / "web"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
DEFAULT_PORT = 8766
WATCH_EVERY = 1.0
MAX_BODY = 1_000_000
PERSON = "persona"
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; "
       "frame-ancestors 'none'")
# Los mockups los escribe el agente: van aislados (sin origen propio, sin red, sin tocar la aplicación).
PROPOSAL_CSP = ("sandbox allow-scripts; default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "img-src data:; font-src data:; media-src data:; frame-ancestors 'self'")
PROPOSAL_PATH = re.compile(r"^/propuestas/(P-\d{1,6})/(\d{1,3})\.html$")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Stream:
    """Respuesta que se va enviando a trozos (los avisos en vivo)."""

    def __init__(self, chunks: Iterator[str], content_type: str = "text/event-stream"):
        self.chunks = chunks
        self.content_type = content_type


class Project:
    """El proyecto que se está viendo: su carpeta y su plan."""

    def __init__(self, path: str | Path, pid: Optional[str] = None):
        self.path = Path(path).resolve()
        self.plan_path = self.path / P.PLAN_FILE
        self.id = pid or project_id(self.path)

    @property
    def name(self) -> str:
        return self.path.name


def project_id(path: str | Path) -> str:
    """El id con el que el registro conoce la carpeta (o el que tendría si se apuntara)."""
    wanted = os.path.normcase(os.path.abspath(str(path)))
    for item in R.listing():
        if os.path.normcase(os.path.abspath(item["path"])) == wanted:
            return item["id"]
    return hashlib.sha1(wanted.encode("utf-8")).hexdigest()[:10]  # misma cuenta que projects.py


def resolve(start: "Project", query: Dict[str, str]) -> "Project":
    """El proyecto de ``?project=``: el de arranque o uno del registro. Nunca una ruta libre."""
    pid = (query.get("project") or "").strip()
    if not pid or pid == start.id:
        return start
    if not re.fullmatch(r"[0-9a-f]{4,40}", pid):
        raise ApiError("Ese proyecto no existe.", 404)
    found = R.find(pid)
    if found is None or not Path(found).is_dir():
        raise ApiError("Ese proyecto no existe o su carpeta ya no está.", 404)
    return Project(found, pid)


# ----------------------------------------------------------------------------- seguridad

def _host_name(value: str) -> str:
    value = (value or "").strip().lower()
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if ":" in value else value


def refusal(method: str, headers: Any, port: int) -> Optional[str]:
    """Por qué se rechaza la petición, o None si viene de la propia página."""
    host = headers.get("Host", "")
    if _host_name(host) not in LOCAL_HOSTS:
        return "Unificador solo atiende a esta máquina."
    if (headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
        return "Petición de otra web: rechazada."
    origin = headers.get("Origin")
    if origin is not None:
        o = urlsplit(origin)
        if o.scheme != "http" or _host_name(o.netloc) not in LOCAL_HOSTS or (o.port or 80) != port:
            return "Petición de otra web: rechazada."
    if method == "POST" and "application/json" not in (headers.get("Content-Type") or "").lower():
        return "Los cambios se envían como JSON."
    return None


# ----------------------------------------------------------------------------- rutas

Route = Callable[["Project", Tuple[str, ...], Dict[str, str], Dict[str, Any]], Any]
ROUTES: List[Tuple[str, "re.Pattern[str]", Route]] = []


def route(method: str, pattern: str):
    def add(fn: Route) -> Route:
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn))
        return fn
    return add


def _text(body: Dict[str, Any], key: str, limit: int = 20000) -> str:
    value = body.get(key, "")
    if not isinstance(value, str):
        raise ApiError(f"«{key}» tiene que ser texto.")
    return value.strip()[:limit]


def waiting_count(plan: Dict[str, Any]) -> int:
    """Cosas que esperan a la persona: fases por revisar y preguntas sin responder."""
    phases = sum(1 for b in plan.get("branches", []) if not b.get("archived")
                 for p in b.get("phases", []) if P.review_state(p) == P.WAITING)
    return phases + sum(1 for a in plan.get("asks", []) if not a.get("answer"))


def summary(project: "Project") -> Dict[str, Any]:
    out: Dict[str, Any] = {"done": 0, "total": 0, "waiting": 0}
    if not project.path.is_dir():
        return out
    try:
        plan = P.load(project.plan_path)
    except P.PlanError as e:
        return {**out, "error": str(e)}
    for b in plan.get("branches", []):
        if not b.get("archived"):
            done, total = P.branch_progress(b)
            out["done"] += done
            out["total"] += total
    out["waiting"] = waiting_count(plan)
    out["title"] = plan.get("title") or ""
    return out


@route("GET", "/api/projects")
def get_projects(project, args, query, body):
    """El de arranque (``current``) y los del registro, con su progreso resumido."""
    start = project
    items = [{"id": start.id, "name": start.name, "path": str(start.path), "exists": start.path.is_dir()}]
    items += [i for i in R.listing() if i["id"] != start.id]
    out = []
    for item in items:
        p = start if item["id"] == start.id else Project(item["path"], item["id"])
        out.append({**item, "current": item["id"] == start.id, **summary(p)})
    return {"projects": out}


@route("GET", "/api/project")
def get_project(project, args, query, body):
    return {"id": project.id, "name": project.name, "path": str(project.path)}


@route("GET", "/api/plan")
def get_plan(project, args, query, body):
    return P.load(project.plan_path)


@route("POST", "/api/plan/steps/([^/]+)/state")
def post_step_state(project, args, query, body):
    state, text = _text(body, "state", 20), _text(body, "text")
    P.mutate(project.plan_path, lambda plan: P.set_state(plan, args[0], state, PERSON, text))
    return P.load(project.plan_path)


@route("POST", "/api/plan/steps/([^/]+)/change")
def post_step_change(project, args, query, body):
    text = _text(body, "text")
    P.mutate(project.plan_path, lambda plan: P.request_change(plan, args[0], text, PERSON))
    return P.load(project.plan_path)


@route("POST", "/api/plan/phases/review")
def post_phase_review(project, args, query, body):
    """Aprobar una fase o pedir cambios. Queda sin ver para que el agente lo reciba solo."""
    branch, phase, verdict = _text(body, "branch", 200), _text(body, "phase", 200), _text(body, "verdict", 20)
    if not branch or not phase:
        raise ApiError("Falta la rama o la fase.")
    if verdict not in (P.APPROVED, P.CHANGES):
        raise ApiError("La revisión es «approved» o «changes».")
    text = _text(body, "text")
    P.mutate(project.plan_path, lambda plan: P.review_phase(plan, branch, phase, verdict, text, by=PERSON, seen=False))
    return P.load(project.plan_path)


@route("POST", "/api/plan/asks/([^/]+)/answer")
def post_ask_answer(project, args, query, body):
    option = body.get("option")
    if option is not None and (isinstance(option, bool) or not isinstance(option, int)):
        raise ApiError("«option» tiene que ser un número (1, 2…) o null.")
    text = _text(body, "text")
    P.mutate(project.plan_path, lambda plan: P.answer_ask(plan, args[0], option, text, by=PERSON, seen=False))
    return P.load(project.plan_path)


@route("POST", "/api/plan/branches/([^/]+)/nonstop")
def post_branch_nonstop(project, args, query, body):
    on = body.get("on")
    if not isinstance(on, bool):
        raise ApiError("«on» tiene que ser true o false.")
    P.mutate(project.plan_path, lambda plan: P.set_nonstop(plan, args[0], on))
    return P.load(project.plan_path)


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def watch(project: "Project", every: float = 1.0, ping: float = 15.0) -> Iterator[str]:
    """Avisos en vivo (SSE): ``plan`` cuando cambia el fichero del plan."""
    seen, quiet = _mtime(project.plan_path), 0.0
    yield "retry: 2000\n\n"
    while True:
        time.sleep(every)
        now, quiet = _mtime(project.plan_path), quiet + every
        if now != seen:
            quiet, seen = 0.0, now
            yield "event: plan\ndata: {}\n\n"
        if quiet >= ping:
            quiet = 0.0
            yield ": sigo aquí\n\n"  # también sirve para notar que la página se ha cerrado


@route("GET", "/api/events")
def get_events(project, args, query, body):
    return Stream(watch(project, WATCH_EVERY), "text/event-stream")


# ----------------------------------------------------------------------------- servidor

class Handler(BaseHTTPRequestHandler):
    server_version = "Unificador"
    protocol_version = "HTTP/1.1"
    project: Project

    def log_message(self, *args):  # silencio: la terminal es para la persona
        pass

    def _send(self, status: int, body: bytes, content_type: str, csp: str = CSP) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", csp)
        if self.command == "POST" and not getattr(self, "_read_body", False):
            self.send_header("Connection", "close")  # no se ha leído el cuerpo: no reutilizar
            self.close_connection = True
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (ConnectionError, OSError):
            self.close_connection = True  # la página se ha ido

    def _json(self, data: Any, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _stream(self, stream: Stream) -> None:
        self.send_response(200)
        self.send_header("Content-Type", f"{stream.content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for chunk in stream.chunks:
                self.wfile.write(chunk.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionError, OSError):
            pass  # la página se ha cerrado
        finally:
            close = getattr(stream.chunks, "close", None)
            if close:
                close()

    def _static(self, path: str) -> None:
        rel = unquote(path).lstrip("/") or "index.html"
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in target.parents or not target.is_file():
            return self._json({"error": "No existe."}, 404)
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind in ("application/javascript", "application/json"):
            kind += "; charset=utf-8"
        self._send(200, target.read_bytes(), kind)

    def _proposal(self, path: str, query: Dict[str, str]) -> None:
        """Un mockup de ``.unificador/propuestas/<P-n>/<n>.html``; nada más se sirve por aquí."""
        m = PROPOSAL_PATH.match(path)
        if not m:
            return self._json({"error": "No existe."}, 404)
        try:
            project = resolve(self.project, query)
        except ApiError as e:
            return self._json({"error": str(e)}, e.status)
        folder = (project.path / P.PROPOSALS_DIR).resolve()
        target = (folder / m.group(1) / f"{int(m.group(2))}.html").resolve()
        if folder not in target.parents or not target.is_file() or target.stat().st_size > P.MAX_PROPOSAL:
            return self._json({"error": "No existe."}, 404)
        self._send(200, target.read_bytes(), "text/html; charset=utf-8", PROPOSAL_CSP)

    def _body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            raise ApiError("Petición demasiado grande.", 413)
        raw = self.rfile.read(length)
        self._read_body = True
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            raise ApiError("El cuerpo no es JSON válido.")
        if not isinstance(data, dict):
            raise ApiError("El cuerpo tiene que ser un objeto JSON.")
        return data

    def _handle(self) -> None:
        self._read_body = False
        method = "GET" if self.command == "HEAD" else self.command
        why = refusal(method, self.headers, self.server.server_address[1])
        if why:
            return self._json({"error": why}, 403)
        url = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        if not url.path.startswith("/api/"):
            if method != "GET":
                return self._json({"error": "Método no permitido."}, 405)
            if url.path.startswith("/propuestas/"):
                return self._proposal(url.path, query)
            return self._static(url.path)
        known = False
        for verb, pattern, fn in ROUTES:
            m = pattern.match(url.path)
            if not m:
                continue
            known = True
            if verb != method:
                continue
            try:
                args = tuple(unquote(a) for a in m.groups())
                project = self.project if fn is get_projects else resolve(self.project, query)
                result = fn(project, args, query, self._body() if method == "POST" else {})
            except ApiError as e:
                return self._json({"error": str(e)}, e.status)
            except P.PlanError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:  # un fallo nuestro no debe tirar el servidor
                return self._json({"error": f"Error interno: {e}"}, 500)
            return self._stream(result) if isinstance(result, Stream) else self._json(result)
        self._json({"error": "Método no permitido." if known else "No existe."}, 405 if known else 404)

    do_GET = do_HEAD = do_POST = _handle

    def do_OPTIONS(self):  # sin CORS: no se contesta a los preflight de otras webs
        self._json({"error": "No permitido."}, 403)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request, client_address):
        import sys
        if not isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            super().handle_error(request, client_address)  # que una pestaña se cierre no es un error


def make_server(project_path: str | Path, port: int = DEFAULT_PORT, tries: int = 20) -> Server:
    """Abre el servidor en 127.0.0.1, en ``port`` o en el siguiente que esté libre."""
    project = Project(project_path)
    handler = type("ProjectHandler", (Handler,), {"project": project})
    last: Optional[OSError] = None
    for candidate in ([0] if port == 0 else range(port, port + tries)):
        try:
            server = Server(("127.0.0.1", candidate), handler)
            server.project = project  # type: ignore[attr-defined]
            return server
        except OSError as e:
            last = e
    raise OSError(f"No hay ningún puerto libre entre {port} y {port + tries - 1}: {last}")
