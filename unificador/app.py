"""
Servidor local de Unificador: un proyecto, una web, solo para esta máquina.

- Escucha únicamente en 127.0.0.1 y no envía cabeceras CORS: ninguna otra web puede leerlo.
- Rechaza peticiones que no vengan de la propia página (Host, Origin y Sec-Fetch-Site).
- Los GET no cambian nada; los cambios van por POST con JSON.
- Las rutas están en una tabla (``ROUTES``): método, patrón y función.
"""

from __future__ import annotations

import json
import mimetypes
import queue
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from unificador import agents as G
from unificador import plan as P
from unificador import rules as R
from unificador import sessions as S

WEB_DIR = Path(__file__).parent / "web"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
DEFAULT_PORT = 8766
MAX_BODY = 1_000_000
PERSON = "persona"
CSP = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Stream:
    """Respuesta que se va enviando a trozos (chat y avisos en vivo)."""

    def __init__(self, chunks: Iterator[str], content_type: str = "application/x-ndjson"):
        self.chunks = chunks
        self.content_type = content_type


class Project:
    """El proyecto que se está viendo: su carpeta, su plan y los ajustes de esta máquina."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.plan_path = self.path / P.PLAN_FILE
        self.settings_path = self.path / R.LOCAL_DIR / R.LOCAL_SETTINGS
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.path.name

    def settings(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.settings_path.with_name(self.settings_path.name + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(self.settings_path)
        return data


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


@route("GET", "/api/project")
def get_project(project, args, query, body):
    return {"name": project.name, "path": str(project.path), "agents": G.available(),
            "settings": G.clean_settings(project.settings())}


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


@route("GET", "/api/sessions")
def get_sessions(project, args, query, body):
    return {"sessions": G.list_sessions(project.path, query.get("agent", ""))}


@route("GET", "/api/sessions/([a-z]+)/([^/]+)")
def get_session(project, args, query, body):
    return G.read_session(project.path, args[0], args[1])


@route("POST", "/api/settings")
def post_settings(project, args, query, body):
    return project.save_settings(G.clean_settings({**project.settings(), **body}))


def _detached(events: Iterator[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
    """Recorre ``events`` en un hilo aparte: si la página se cierra, el agente termina su trabajo."""
    box: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()

    def work() -> None:
        try:
            for ev in events:
                box.put(ev)
        finally:
            box.put(None)

    threading.Thread(target=work, daemon=True).start()
    while True:
        ev = box.get()
        if ev is None:
            return
        yield ev


@route("POST", "/api/chat")
def post_chat(project, args, query, body):
    """Envía el mensaje tal cual al agente y va devolviendo su respuesta, un evento JSON por línea."""
    saved = G.clean_settings(project.settings())
    agent = _text(body, "agent", 40) or saved["agent"]
    if agent not in G.AGENTS:
        raise ApiError(f"No conozco el agente «{agent}».")
    text = _text(body, "text", 200000)
    if not text:
        raise ApiError("Escribe algo para enviar.")
    chosen = {k: (_text(body, k, 80) if k in body else saved["agents"][agent][k])
              for k in ("model", "effort", "mode")}
    events = _detached(G.stream(project.path, agent, text, _text(body, "session", 80), **chosen))
    return Stream(json.dumps(ev, ensure_ascii=False) + "\n" for ev in events)


@route("POST", "/api/chat/stop")
def post_chat_stop(project, args, query, body):
    return {"stopped": G.stop(_text(body, "run", 80))}


@route("POST", "/api/open-native")
def post_open_native(project, args, query, body):
    return {"message": G.open_native(project.path, _text(body, "agent", 40), _text(body, "session", 80))}


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def watch(project: "Project", every: float = 1.0, ping: float = 15.0) -> Iterator[str]:
    """Avisos en vivo (SSE): ``plan`` cuando cambia el plan y ``sessions`` cuando alguien escribe
    en una conversación, sea desde la web, la terminal o la app."""
    def look() -> Dict[str, Any]:
        return {"plan": _mtime(project.plan_path),
                "sessions": (G.latest_mtime(project.path), sorted(G.busy_sessions()))}

    seen, quiet = look(), 0.0
    yield "retry: 2000\n\n"
    while True:
        time.sleep(every)
        now, quiet = look(), quiet + every
        for name in now:
            if now[name] != seen[name]:
                quiet = 0.0
                yield f"event: {name}\ndata: {{}}\n\n"
        seen = now
        if quiet >= ping:
            quiet = 0.0
            yield ": sigo aquí\n\n"  # también sirve para notar que la página se ha cerrado


@route("GET", "/api/events")
def get_events(project, args, query, body):
    return Stream(watch(project, G.WATCH_EVERY), "text/event-stream")


# ----------------------------------------------------------------------------- servidor

class Handler(BaseHTTPRequestHandler):
    server_version = "Unificador"
    protocol_version = "HTTP/1.1"
    project: Project

    def log_message(self, *args):  # silencio: la terminal es para la persona
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
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
        if not url.path.startswith("/api/"):
            if method != "GET":
                return self._json({"error": "Método no permitido."}, 405)
            return self._static(url.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
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
                result = fn(self.project, args, query, self._body() if method == "POST" else {})
            except ApiError as e:
                return self._json({"error": str(e)}, e.status)
            except (P.PlanError, S.SessionError, G.AgentError) as e:
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
