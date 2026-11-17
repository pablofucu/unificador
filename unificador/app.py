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
import hmac
import json
import mimetypes
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlsplit

from unificador import funnel
from unificador import plan as P
from unificador import projects as R

WEB_DIR = Path(__file__).parent / "web"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
LOOPBACK_IPS = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
PROXY_HEADERS = ("Tailscale-Funnel-Request", "Tailscale-User-Login", "X-Forwarded-For",
                 "X-Forwarded-Host", "X-Forwarded-Proto", "Forwarded")
DEFAULT_PORT = 8766
WATCH_EVERY = 1.0
MAX_BODY = 1_000_000
PERSON = "persona"
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; "
       "worker-src 'self'; manifest-src 'self'; frame-ancestors 'none'")
LOGIN_CSP = ("default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
             "connect-src 'self'; img-src data:; frame-ancestors 'none'")
# Los mockups los escribe el agente: van aislados (sin origen propio, sin red, sin tocar la aplicación).
# Script que se inyecta en cada propuesta: avisa del scroll al visor (que no puede leerlo: iframe sin
# allow-same-origin) y obedece sus órdenes, para que el modo comparar mueva las dos a la vez.
SYNC_SCRIPT = b"""<script>(function(){var q=false,mute=false,de=document.documentElement;
function pr(a,b){return a/(b||1)}
function mx(){return[Math.max(0,de.scrollWidth-innerWidth),Math.max(0,de.scrollHeight-innerHeight)]}
addEventListener("scroll",function(){if(mute||q)return;q=true;setTimeout(function(){q=false;var m=mx();
parent.postMessage({uni:"scroll",x:pr(scrollX,m[0]),y:pr(scrollY,m[1])},"*")},30)});
addEventListener("message",function(e){var d=e.data;if(!d||e.source!==parent)return;
if(d.uni==="scrollTo"){var m=mx();mute=true;scrollTo(d.x*m[0],d.y*m[1]);setTimeout(function(){mute=false},60)}
else if(d.uni==="scrollBy"){scrollBy(0,+d.dy||0)}})})();</script>"""


def _inject_sync(raw: bytes) -> bytes:
    i = raw.lower().rfind(b"</body>")
    return raw + SYNC_SCRIPT if i < 0 else raw[:i] + SYNC_SCRIPT + raw[i:]


PROPOSAL_CSP = ("sandbox allow-scripts; default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "img-src data:; font-src data:; media-src data:; frame-ancestors 'self'")
PROPOSAL_PATH = re.compile(r"^/propuestas/(P-\d{1,6})/(\d{1,3})\.html$")
RATE_LIMITER = funnel.RateLimiter()

LOGIN_HTML = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acceso · Unificador</title>
  <link rel="icon" href="data:,">
  <style>
    :root { color-scheme: light; --bg: #f6f7fb; --card: #fff; --ink: #1f2338; --muted: #6a7088;
      --line: #e4e7f1; --soft: #eff1f8; --ai: #6c5ce7; --bad: #e0445e; font-family: system-ui, "Segoe UI", Roboto, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 20px; color: var(--ink);
      background: var(--bg) radial-gradient(circle, #d3d7e8 1.2px, transparent 1.4px) 0 0 / 22px 22px; }
    .gate { width: min(100%, 390px); background: var(--card); border-radius: 22px; padding: 26px 24px 22px;
      border: 1.5px solid var(--line); box-shadow: 0 10px 30px rgba(40, 50, 110, .12); display: grid; gap: 14px; }
    .brand { display: flex; align-items: center; gap: 10px; }
    .badge { width: 38px; height: 38px; border-radius: 12px; background: #f1eeff; color: var(--ai);
      display: grid; place-items: center; flex: none; }
    .badge svg { width: 20px; height: 20px; }
    h1 { margin: 0; font-size: 1.38rem; letter-spacing: -.01em; }
    p { margin: 0; color: var(--muted); font-size: .92rem; line-height: 1.45; }
    form { display: grid; gap: 12px; }
    input { width: 100%; min-height: 44px; padding: 10px 14px; border-radius: 12px; border: 1.5px solid var(--line);
      font: inherit; color: inherit; background: #fff; transition: border-color .15s; }
    input:focus { outline: none; border-color: var(--ai); box-shadow: 0 0 0 3px rgba(108, 92, 231, .16); }
    button { min-height: 44px; border: 0; border-radius: 99px; background: var(--ai); color: #fff; font: inherit;
      font-weight: 700; cursor: pointer; transition: background .15s; }
    button:hover:not(:disabled) { background: #5b4bd6; }
    button:disabled { opacity: .65; cursor: not-allowed; }
    .err { color: var(--bad); font-size: .86rem; min-height: 1.2em; font-weight: 600; }
    .hint { font-size: .78rem; color: var(--muted); border-top: 1px solid var(--line); padding-top: 10px; }
  </style>
</head>
<body>
  <main class="gate">
    <div class="brand">
      <span class="badge" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="5" y="11" width="14" height="10" rx="2.5"></rect>
          <path d="M8 11V8a4 4 0 0 1 8 0v3"></path>
        </svg>
      </span>
      <h1>Unificador</h1>
    </div>
    <p>Acceso remoto privado. Introduce tu clave para ver tus proyectos.</p>
    <form id="f">
      <input id="k" type="password" autocomplete="current-password" placeholder="Clave de acceso" aria-label="Clave de acceso" required autofocus>
      <button id="b" type="submit">Entrar</button>
      <p id="e" class="err" role="status" aria-live="polite"></p>
    </form>
    <p class="hint">Si cambiaste la clave desde tu equipo con <code>reset-key</code>, usa la nueva.</p>
  </main>
  <script>
    try {
      navigator.serviceWorker?.getRegistrations().then((rs) => rs.forEach((r) => r.unregister()));
      caches?.keys().then((ks) => ks.forEach((n) => caches.delete(n)));
    } catch {}
    const f = document.getElementById("f"), k = document.getElementById("k"), b = document.getElementById("b"), e = document.getElementById("e");
    f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      e.textContent = "";
      b.disabled = true;
      b.textContent = "Comprobando…";
      try {
        const r = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key: k.value }) });
        const d = await r.json().catch(() => ({}));
        if (r.ok) { location.reload(); return; }
        e.textContent = d.error || "No se pudo entrar.";
      } catch { e.textContent = "Sin conexión con el servidor."; }
      b.disabled = false;
      b.textContent = "Entrar";
      k.select();
      k.focus();
    });
  </script>
</body>
</html>
"""


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


def _host_port(value: str) -> Optional[int]:
    value = (value or "").strip()
    if value.startswith("["):
        _, _, rest = value.partition("]")
        raw = rest[1:] if rest.startswith(":") else ""
    elif ":" in value:
        raw = value.rsplit(":", 1)[1]
    else:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _public_host(cfg: Dict[str, Any]) -> str:
    url = (cfg.get("public_url") or "").strip()
    return _host_name(urlsplit(url).netloc) if url else ""


def _is_tailscale_host(host_name: str, cfg: Dict[str, Any]) -> bool:
    pub = _public_host(cfg)
    return funnel.is_ts_host(host_name) or bool(pub and host_name == pub)


def _is_proxied(headers: Any) -> bool:
    return any(headers.get(h) for h in PROXY_HEADERS)


def _is_funnel_traffic(headers: Any, client_ip: str, cfg: Dict[str, Any]) -> bool:
    """Distingue el acceso remoto por Tailscale/Funnel del navegador local en 127.0.0.1."""
    h_name = _host_name(headers.get("Host", ""))
    if headers.get("Tailscale-Funnel-Request"):
        return True
    if _is_tailscale_host(h_name, cfg):
        return True
    if cfg.get("enabled") and (_is_proxied(headers) or client_ip not in LOOPBACK_IPS or h_name not in LOCAL_HOSTS):
        return True
    return False


def _peer_ip(headers: Any, client_ip: str) -> str:
    if client_ip in LOOPBACK_IPS:
        xff = (headers.get("X-Forwarded-For") or "").strip()
        if xff:
            last = xff.split(",")[-1].strip()
            if last:
                return last
        return "funnel"
    return client_ip or "unknown"


def refusal(method: str, headers: Any, port: int, host: str = "127.0.0.1",
            allow_tailscale: bool = False, client_ip: str = "127.0.0.1",
            funnel_cfg: Optional[Dict[str, Any]] = None, path: str = "/") -> Optional[str]:
    """Por qué se rechaza la petición, o None si viene de la propia página."""
    cfg = funnel_cfg or {}
    h_host = headers.get("Host", "")
    h_name = _host_name(h_host)
    xfh = (headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    xfh_name = _host_name(xfh)
    is_lan = host not in ("127.0.0.1", "localhost", "::1")
    ts_host_match = _is_tailscale_host(h_name, cfg)
    ts_proxy_match = bool(
        h_name in LOCAL_HOSTS
        and (
            _is_tailscale_host(xfh_name, cfg)
            or (cfg.get("enabled") and headers.get("Tailscale-Funnel-Request") and _public_host(cfg))
        )
    )
    ts_allowed = bool(allow_tailscale and client_ip in LOOPBACK_IPS and (ts_host_match or ts_proxy_match))
    if not is_lan and h_name not in LOCAL_HOSTS and not ts_allowed:
        return "Unificador solo atiende a esta máquina."
    is_doc_nav = (
        method == "GET"
        and path in ("/", "/index.html")
        and (headers.get("Sec-Fetch-Mode") or "").lower() == "navigate"
        and (headers.get("Sec-Fetch-Dest") or "").lower() == "document"
    )
    if (headers.get("Sec-Fetch-Site") or "").lower() == "cross-site" and not is_doc_nav:
        return "Petición de otra web: rechazada."
    origin = headers.get("Origin")
    if origin is not None:
        o = urlsplit(origin)
        if o.scheme == "http":
            if (o.port or 80) != port:
                return "Petición de otra web: rechazada."
            if not is_lan and _host_name(o.netloc) not in LOCAL_HOSTS:
                return "Petición de otra web: rechazada."
            if is_lan and _host_name(o.netloc) != h_name:
                return "Petición de otra web: rechazada."
        elif o.scheme == "https" and ts_allowed:
            expected_host = h_name if ts_host_match else (xfh_name if _is_tailscale_host(xfh_name, cfg) else _public_host(cfg))
            if _host_name(o.netloc) != expected_host:
                return "Petición de otra web: rechazada."
            o_port = o.port or 443
            h_port = _host_port(h_host) if ts_host_match else _host_port(xfh)
            expected_ports = {h_port} if h_port else {443, int(cfg.get("funnel_port") or 443)}
            if o_port not in expected_ports or o_port not in funnel.ALLOWED_FUNNEL_PORTS:
                return "Petición de otra web: rechazada."
        else:
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


@route("GET", "/api/health")
def get_health(project, args, query, body):
    return {"ok": True}


@route("GET", "/api/projects")
def get_projects(project, args, query, body):
    """El de arranque (``current``), el último trabajado (``active``) y los del registro."""
    start = project
    active = R.active_id()
    items = [{"id": start.id, "name": start.name, "path": str(start.path), "exists": start.path.is_dir()}]
    items += [i for i in R.listing() if i["id"] != start.id]
    out = []
    for item in items:
        p = start if item["id"] == start.id else Project(item["path"], item["id"])
        out.append({**item, "current": item["id"] == start.id, "active": item["id"] == active, **summary(p)})
    return {"projects": out}


@route("GET", "/api/project")
def get_project(project, args, query, body):
    return {"id": project.id, "name": project.name, "path": str(project.path)}


@route("GET", "/api/plan")
def get_plan(project, args, query, body):
    plan = P.load(project.plan_path)
    plan["audit"] = P.audit(plan, project.plan_path.resolve().parent)  # solo en la respuesta, no se guarda
    return plan


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


@route("POST", "/api/plan/ideas")
def post_idea(project, args, query, body):
    """Una idea suelta de la persona: queda sin ver para que el agente la reciba por inbox."""
    text = _text(body, "text", P.MAX_IDEA)
    P.mutate(project.plan_path, lambda plan: P.add_idea(plan, text, PERSON, seen=False))
    return P.load(project.plan_path)


@route("POST", "/api/plan/ideas/([^/]+)/drop")
def post_idea_drop(project, args, query, body):
    text = _text(body, "text", 500)
    P.mutate(project.plan_path, lambda plan: P.drop_idea(plan, args[0], text))
    return P.load(project.plan_path)


@route("POST", "/api/plan/ideas/([^/]+)/reopen")
def post_idea_reopen(project, args, query, body):
    P.mutate(project.plan_path, lambda plan: P.reopen_idea(plan, args[0]))
    return P.load(project.plan_path)


@route("GET", "/api/prompts")
def get_prompts(project, args, query, body):
    return {"prompts": P.list_prompts(project.plan_path.resolve().parent)}


@route("GET", "/api/versions")
def get_versions(project, args, query, body):
    """Próxima versión (SemVer), sus novedades, lo comiteado sin publicar y el historial."""
    plan = P.load(project.plan_path)
    commits = P.unreleased_commits(plan, project.plan_path.resolve().parent) or []
    return {"next": P.next_version(plan), "last": P.last_version(plan), "news": plan.get("news") or [],
            "versions": list(reversed(plan.get("versions") or [])),
            "unreleased": [{"sha": c["sha"][:7], "subject": c["subject"], "date": c["date"],
                            "refs": P.commit_refs(plan, c)} for c in commits]}


@route("POST", "/api/plan/queue")
def post_job(project, args, query, body):
    """Encargar un prompt maestro (o un texto) al agente, sobre una rama o fase si se dice."""
    name, extra = _text(body, "prompt", 120), _text(body, "text", P.MAX_JOB)
    branch, phase = _text(body, "branch", 200) or None, _text(body, "phase", 200) or None
    pr = P.find_prompt(project.plan_path.resolve().parent, name) if name else {}
    text = "\n\n".join(x for x in (pr.get("text", ""), extra) if x)
    P.mutate(project.plan_path, lambda plan: P.add_job(plan, text, pr.get("title", ""), branch, phase,
                                                        pr.get("name", ""), PERSON, seen=False))
    return P.load(project.plan_path)


@route("POST", "/api/plan/queue/([^/]+)/drop")
def post_job_drop(project, args, query, body):
    P.mutate(project.plan_path, lambda plan: P.drop_job(plan, args[0]))
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


def _sanitize_remote(path: str, result: Any, via_funnel: bool, cfg: Dict[str, Any]) -> Any:
    """En tráfico público de Funnel oculta las rutas del disco y señala sesión remota."""
    if not via_funnel or not isinstance(result, dict):
        return result
    hide = bool(cfg.get("hide_paths", True))
    if path == "/api/projects":
        if hide:
            result = {**result, "projects": [{**item, "path": ""} for item in result.get("projects", [])]}
        result["remote"] = True
    elif path == "/api/project" and hide:
        result = {**result, "path": ""}
    return result


# ----------------------------------------------------------------------------- servidor

class Handler(BaseHTTPRequestHandler):
    server_version = "Unificador"
    protocol_version = "HTTP/1.1"
    project: Project

    def log_message(self, *args):  # silencio: la terminal es para la persona
        pass

    def _send(self, status: int, body: bytes, content_type: str, csp: str = CSP,
              extra_headers: Optional[List[Tuple[str, str]]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", csp)
        for k, v in (extra_headers or ()):
            self.send_header(k, v)
        if self.command == "POST" and not getattr(self, "_read_body", False):
            self.send_header("Connection", "close")  # no se ha leído el cuerpo: no reutilizar
            self.close_connection = True
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (ConnectionError, OSError):
            self.close_connection = True  # la página se ha ido

    def _json(self, data: Any, status: int = 200,
              extra_headers: Optional[List[Tuple[str, str]]] = None) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", extra_headers=extra_headers)

    def _stream(self, stream: Stream) -> None:
        self.send_response(200)
        self.send_header("Content-Type", f"{stream.content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Accel-Buffering", "no")
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
        if target.suffix == ".webmanifest":
            kind = "application/manifest+json"
        elif target.suffix == ".js" and kind == "application/octet-stream":
            kind = "text/javascript"
        if kind.startswith("text/") or kind in ("application/javascript", "application/json", "application/manifest+json"):
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
        self._send(200, _inject_sync(target.read_bytes()), "text/html; charset=utf-8", PROPOSAL_CSP)

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

    def _is_https(self, cfg: Dict[str, Any]) -> bool:
        h_name = _host_name(self.headers.get("Host", ""))
        return bool(self.headers.get("Tailscale-Funnel-Request")
                    or (self.headers.get("X-Forwarded-Proto") or "").lower() == "https"
                    or _is_tailscale_host(h_name, cfg))

    def _cookie_header(self, value: str, max_age: int, cfg: Dict[str, Any]) -> str:
        parts = [f"{funnel.SESSION_COOKIE}={value}", "HttpOnly", "SameSite=Strict", "Path=/", f"Max-Age={max_age}"]
        if self._is_https(cfg):
            parts.append("Secure")
        return "; ".join(parts)

    def _auth_login(self, cfg: Dict[str, Any], client_ip: str) -> None:
        if not cfg.get("enabled") or not funnel.has_key(cfg):
            return self._json({"error": "El acceso remoto no está activado."}, 403)
        peer = _peer_ip(self.headers, client_ip)
        wait = RATE_LIMITER.retry_after(peer)
        if wait > 0:
            return self._json({"error": f"Demasiados intentos. Espera {wait} s."}, 429,
                              [("Retry-After", str(wait))])
        try:
            data = self._body()
        except ApiError as e:
            return self._json({"error": str(e)}, e.status)
        raw_key = data.get("key", "")
        if not isinstance(raw_key, str) or not funnel.verify_key(raw_key, cfg):
            lock_sec = RATE_LIMITER.record_failure(peer)
            if lock_sec > 0:
                return self._json({"error": f"Demasiados intentos. Espera {lock_sec} s."}, 429,
                                  [("Retry-After", str(lock_sec))])
            return self._json({"error": "Clave incorrecta."}, 401)
        RATE_LIMITER.record_success(peer)
        token = funnel.sign_session(cfg["cookie_secret"])
        self._json({"ok": True}, 200, [("Set-Cookie", self._cookie_header(token, funnel.SESSION_TTL, cfg))])

    def _auth_logout(self, cfg: Dict[str, Any]) -> None:
        self._json({"ok": True}, 200, [("Set-Cookie", self._cookie_header("", 0, cfg))])

    def _handle(self) -> None:
        self._read_body = False
        method = "GET" if self.command == "HEAD" else self.command
        client_ip = self.client_address[0] if self.client_address else ""
        cfg = funnel.load_config()
        allow_ts = bool(getattr(self.server, "tailscale", False) or cfg.get("enabled"))
        url = urlsplit(self.path)
        why = refusal(method, self.headers, self.server.server_address[1],
                      getattr(self.server, "host", "127.0.0.1"),
                      allow_tailscale=allow_ts, client_ip=client_ip, funnel_cfg=cfg, path=url.path)
        if why:
            return self._json({"error": why}, 403)
        via_funnel = _is_funnel_traffic(self.headers, client_ip, cfg)
        if url.path == "/auth/login":
            if method != "POST":
                return self._json({"error": "Método no permitido."}, 405)
            return self._auth_login(cfg, client_ip)
        if url.path == "/auth/logout":
            if method != "POST":
                return self._json({"error": "Método no permitido."}, 405)
            return self._auth_logout(cfg)
        if via_funnel:
            if not cfg.get("enabled") or not funnel.has_key(cfg):
                return self._json({"error": "El acceso remoto por Funnel no está activado."}, 403)
            token = funnel.parse_cookie(self.headers.get("Cookie"))
            if not funnel.verify_session(token, cfg["cookie_secret"]):
                if method == "GET" and url.path in ("/", "/index.html"):
                    return self._send(200, LOGIN_HTML.encode("utf-8"), "text/html; charset=utf-8", LOGIN_CSP,
                                      [("X-Unificador-Auth", "login")])
                if method == "GET" and url.path == "/favicon.ico":
                    return self._send(204, b"", "image/x-icon", LOGIN_CSP)
                return self._json({"error": "Necesitas iniciar sesión."}, 401)
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
                result = _sanitize_remote(url.path, result, via_funnel, cfg)
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


def make_server(project_path: str | Path, port: int = DEFAULT_PORT, host: str = "127.0.0.1",
                tries: int = 20, tailscale: bool = False) -> Server:
    """Abre el servidor en ``host``, en ``port`` o en el siguiente que esté libre."""
    project = Project(project_path)
    handler = type("ProjectHandler", (Handler,), {"project": project})
    last: Optional[OSError] = None
    for candidate in ([0] if port == 0 else range(port, port + tries)):
        try:
            server = Server((host, candidate), handler)
            server.project = project  # type: ignore[attr-defined]
            server.host = host  # type: ignore[attr-defined]
            server.tailscale = tailscale  # type: ignore[attr-defined]
            return server
        except OSError as e:
            last = e
    raise OSError(f"No hay ningún puerto libre entre {port} y {port + tries - 1}: {last}")
