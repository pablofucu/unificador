"""
Los agentes con los que se puede hablar desde la web: Claude Code y Antigravity.

El mensaje de la persona se envía **tal cual** a la CLI del agente, en su sesión nativa: lo que se
escribe aquí aparece en la app o la terminal, y al revés. No se inyecta contexto: las reglas del
proyecto ya están en AGENTS.md y las lee el propio agente.

``stream`` va dando eventos (dict con ``type``):
``run`` (id para poder parar), ``session`` (id de la sesión nativa), ``model`` (el que contesta
de verdad), ``text``, ``tool``,
``denied`` (el agente necesitaba un permiso que no tenía), ``error`` y, siempre el último, ``done``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from unificador import sessions as S

Event = Dict[str, Any]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
MODEL_ID = re.compile(r"^\w[\w.\-\[\]]{0,79}$")
WATCH_EVERY = 1.0  # cada cuánto se mira si algo ha cambiado (segundos)
MAX_ARG_PROMPT = 24000  # agy recibe el mensaje como argumento

MODES = [{"id": "auto", "name": "Autónomo"}, {"id": "acceptEdits", "name": "Edita sin preguntar"},
         {"id": "plan", "name": "Solo planifica"}]
AGY_MODES = {"auto": "auto", "acceptEdits": "accept-edits", "plan": "plan"}

AGENTS: Dict[str, Dict[str, Any]] = {
    "claude": {
        "name": "Claude Code", "command": "claude", "icon": "🟠",
        "models": [{"id": "", "name": "El de siempre"}, {"id": "fable", "name": "Fable"},
                   {"id": "opus", "name": "Opus"}, {"id": "sonnet", "name": "Sonnet"},
                   {"id": "haiku", "name": "Haiku"}],
        "efforts": [{"id": "", "name": "Normal"}, {"id": "low", "name": "Rápido"},
                    {"id": "medium", "name": "Medio"}, {"id": "high", "name": "Alto"},
                    {"id": "xhigh", "name": "Muy alto"}, {"id": "max", "name": "Máximo"}],
    },
    "antigravity": {
        "name": "Antigravity", "command": "agy", "icon": "🔵",
        "models": [{"id": "", "name": "El de siempre"}], "efforts": [],
    },
}

STEP_LABELS = {"run_command": "Ejecuta", "write_to_file": "Escribe", "replace_file_content": "Edita",
               "multi_replace_file_content": "Edita", "view_file": "Lee", "list_dir": "Mira la carpeta",
               "grep_search": "Busca", "find_by_name": "Busca", "search_web": "Busca en la web",
               "read_url_content": "Abre"}
TOOL_DETAIL = ("CommandLine", "command", "TargetFile", "AbsolutePath", "file_path", "DirectoryPath",
               "SearchPath", "Query", "query", "Url", "url")
DENIED_LABELS = {"command": "ejecutar órdenes", "write_file": "escribir ficheros", "read_url": "abrir páginas web",
                 "Bash": "ejecutar órdenes", "Write": "escribir ficheros", "Edit": "editar ficheros",
                 "WebFetch": "abrir páginas web", "WebSearch": "buscar en la web"}
HIDDEN_STEPS = {"user_input", "system_message", "ephemeral_message", "checkpoint", "conversation_history",
                "planner_response", "error_message"}


class AgentError(Exception):
    pass


PATHS_FILE = Path.home() / ".unificador" / "agentes.json"  # rutas puestas a mano; son de este ordenador
_paths: Optional[Dict[str, str]] = None


def _usual_places(agent: str) -> List[Path]:
    """Dónde suelen instalarse, por si la terminal que abrió Unificador no los tiene en el PATH."""
    home, env = Path.home(), os.environ
    local, roaming = Path(env.get("LOCALAPPDATA") or home / "AppData/Local"), Path(env.get("APPDATA") or home / "AppData/Roaming")
    shared = [home / ".local/bin", Path("/usr/local/bin"), Path("/opt/homebrew/bin"), home / ".npm-global/bin",
              home / ".bun/bin", roaming / "npm"]
    own = {"claude": [home / ".claude/local", home / ".claude/bin", local / "Programs/claude"],
           "antigravity": [local / "agy/bin", home / ".gemini/antigravity-cli/bin", local / "Programs/agy/bin"]}[agent]
    command = AGENTS[agent]["command"]
    names = [command + ext for ext in ((".exe", ".cmd", "") if sys.platform == "win32" else ("",))]
    return [folder / name for folder in own + shared for name in names]


def _saved_paths() -> Dict[str, str]:
    global _paths
    if _paths is None:
        try:
            data = json.loads(PATHS_FILE.read_text(encoding="utf-8"))
            _paths = {k: v for k, v in data.items() if k in AGENTS and isinstance(v, str)} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            _paths = {}
    return _paths


def set_path(agent: str, path: str) -> str:
    """Guarda dónde está el programa de un agente (vacío = volver a buscarlo solo). Devuelve la ruta usada."""
    global _agy_models
    if agent not in AGENTS:
        raise AgentError(f"No conozco el agente «{agent}».")
    command, name = AGENTS[agent]["command"], AGENTS[agent]["name"]
    path = path.strip().strip('"')
    if path:
        p = Path(path).expanduser()
        if p.is_dir():
            p = next((p / (command + ext) for ext in (".exe", ".cmd", "") if (p / (command + ext)).is_file()), p)
        if not p.is_file():
            raise AgentError(f"Ahí no hay ningún programa: {p}")
        if p.stem.lower() != command:
            raise AgentError(f"Ese fichero no es {name}: tiene que llamarse «{command}».")
        path = str(p)
    paths = dict(_saved_paths())
    paths.pop(agent, None)
    if path:
        paths[agent] = path
    try:
        PATHS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PATHS_FILE.write_text(json.dumps(paths, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        raise AgentError(f"No he podido guardar la ruta: {e}")
    _saved_paths().clear()
    _saved_paths().update(paths)
    if agent == "antigravity":
        _agy_models = None
    return _exe(agent)


def _exe(agent: str) -> str:
    saved = _saved_paths().get(agent, "")
    if saved and Path(saved).is_file():
        return saved
    found = shutil.which(AGENTS[agent]["command"])
    if found:
        return found
    return next((str(p) for p in _usual_places(agent) if p.is_file()), "")


# ----------------------------------------------------------------------------- qué hay

_agy_models: Optional[List[Dict[str, str]]] = None
_agy_lock = threading.Lock()


def parse_agy_models(output: str) -> List[Dict[str, str]]:
    models = []
    for line in output.splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 2 and MODEL_ID.match(parts[0]):
            models.append({"id": parts[0], "name": parts[1].strip()})
    return models


def _load_agy_models() -> None:
    global _agy_models
    with _agy_lock:
        if _agy_models is not None:
            return
        try:
            out = subprocess.run([_exe("antigravity"), "models"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30,
                                 creationflags=NO_WINDOW).stdout
            _agy_models = parse_agy_models(out)
        except (OSError, subprocess.SubprocessError):
            _agy_models = []


def warm_up() -> None:
    """Pregunta a Antigravity qué modelos tiene, sin hacer esperar a nadie."""
    if _exe("antigravity") and _agy_models is None:
        threading.Thread(target=_load_agy_models, daemon=True).start()


def available() -> List[Dict[str, Any]]:
    warm_up()
    out = []
    for key, a in AGENTS.items():
        models = list(a["models"])
        if key == "antigravity":
            models += _agy_models or []
        exe = _exe(key)
        out.append({"id": key, "name": a["name"], "icon": a["icon"], "installed": bool(exe), "path": exe,
                    "models": models, "efforts": a["efforts"], "modes": MODES})
    return out


def clean_settings(data: Any) -> Dict[str, Any]:
    """Ajustes de la persona, ya comprobados: agente elegido y modelo/esfuerzo/modo de cada uno."""
    data = data if isinstance(data, dict) else {}
    installed = [k for k in AGENTS if _exe(k)]
    agent = data.get("agent") if data.get("agent") in AGENTS else ""
    if not agent or (installed and agent not in installed):
        agent = (installed or ["claude"])[0]  # nunca se deja elegido uno que no se puede usar
    per = data.get("agents") if isinstance(data.get("agents"), dict) else {}
    agents = {}
    for key, a in AGENTS.items():
        mine = per.get(key) if isinstance(per.get(key), dict) else {}
        model = mine.get("model") if isinstance(mine.get("model"), str) else ""
        effort, mode = mine.get("effort"), mine.get("mode")
        agents[key] = {
            "model": model if MODEL_ID.match(model) else "",
            "effort": effort if effort in {e["id"] for e in a["efforts"]} else "",
            "mode": mode if mode in AGY_MODES else "auto",
        }
    return {"agent": agent, "agents": agents}


# ----------------------------------------------------------------------------- conversaciones

def _need(agent: str) -> str:
    if agent not in AGENTS:
        raise S.SessionError(f"No conozco el agente «{agent}».")
    return agent


def list_sessions(project_path: str | Path, agent: str = "") -> List[Dict[str, Any]]:
    wanted = [_need(agent)] if agent else list(AGENTS)
    out: List[Dict[str, Any]] = []
    if "claude" in wanted:
        out += S.list_sessions(project_path)
    if "antigravity" in wanted:
        from unificador import agy_sessions
        out += agy_sessions.list_sessions(project_path)
    return sorted(out, key=lambda s: s.get("updated", ""), reverse=True)


def latest_mtime(project_path: str | Path) -> float:
    """Cuándo se escribió por última vez en alguna conversación del proyecto."""
    from unificador import agy_sessions
    return max(S.latest_mtime(project_path), agy_sessions.latest_mtime(project_path))


def read_session(project_path: str | Path, agent: str, session_id: str) -> Dict[str, Any]:
    if _need(agent) == "antigravity":
        from unificador import agy_sessions
        return agy_sessions.read_session(project_path, session_id)
    return S.read_session(project_path, session_id)


# ----------------------------------------------------------------------------- enviar

def denied_event(name: str, actions: List[str], mode: str) -> Event:
    """Aviso de que el agente no ha podido hacer algo por falta de permiso, dicho en llano."""
    what = []
    for a in actions:
        label = DENIED_LABELS.get(a, a)
        if label and label not in what:
            what.append(label)
    text = f"{name} necesitaba permiso para {' y '.join(what) or 'hacer algo'} y no lo tenía, así que no lo ha hecho."
    return {"type": "denied", "text": text, "retry": mode != "auto"}


def _agy_tool_text(inner: Dict[str, Any]) -> str:
    """«Ejecuta python …» a partir de un paso de Antigravity, en su formato nuevo o en el antiguo."""
    info = inner.get("tool_info") if isinstance(inner.get("tool_info"), dict) else {}
    name = str(inner.get("tool_name") or info.get("name") or inner.get("step_type") or "")
    params = info.get("parameters") if isinstance(info.get("parameters"), dict) else {}
    detail = next((str(params[k]) for k in TOOL_DETAIL if params.get(k)), "")
    detail = detail or inner.get("command") or inner.get("file_path") or inner.get("summary") or ""
    return S.short(f"{STEP_LABELS.get(name, name.replace('_', ' ').capitalize())} {detail}".strip())


def claude_parser(state: Dict[str, Any]) -> Callable[[Dict[str, Any]], Iterator[Event]]:
    """Convierte las líneas ``stream-json`` de Claude Code en eventos."""
    def parse(d: Dict[str, Any]) -> Iterator[Event]:
        kind = d.get("type")
        if kind == "stream_event":
            ev = d.get("event") or {}
            if d.get("parent_tool_use_id"):
                return  # lo que escribe un ayudante no es la respuesta
            if ev.get("type") == "message_start":
                state["new_message"] = state.get("wrote", False)
            elif ev.get("type") == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                text = ev["delta"].get("text") or ""
                if text:
                    if state.pop("new_message", False):
                        text = "\n\n" + text
                    state["wrote"] = True
                    yield {"type": "text", "text": text}
        elif kind == "assistant" and not d.get("parent_tool_use_id"):
            model = str((d.get("message") or {}).get("model") or "")
            if model and not model.startswith("<") and model != state.get("model"):
                state["model"] = model
                yield {"type": "model", "id": model}
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    yield {"type": "tool", "text": S.describe_tool(str(b.get("name") or ""), b.get("input"))}
        elif kind == "result":
            denials = [str(x.get("tool_name") or "") for x in d.get("permission_denials") or [] if isinstance(x, dict)]
            if denials:
                yield denied_event("Claude Code", denials, state.get("mode", "auto"))
            if d.get("is_error") or d.get("subtype") not in (None, "success"):
                state["failed"] = True
                yield {"type": "error", "text": S.short(d.get("result") or d.get("subtype") or "Claude ha fallado.", 400)}
            elif not state.get("wrote") and d.get("result"):
                yield {"type": "text", "text": str(d["result"])}
    return parse


def agy_parser(state: Dict[str, Any]) -> Callable[[Dict[str, Any]], Iterator[Event]]:
    """Convierte las líneas ``stream-json`` de Antigravity en eventos."""
    seen: set = set()

    def parse(d: Dict[str, Any]) -> Iterator[Event]:
        ev = d.get("event")
        inner = d.get(ev) if isinstance(ev, str) and isinstance(d.get(ev), dict) else {}
        cid = d.get("conversation_id") or inner.get("conversation_id")
        if cid and cid != state.get("session"):
            state["session"] = cid
            yield {"type": "session", "id": cid}
        if ev == "step_update":
            step = inner.get("step_type", "")
            if step == "agent_response":
                if inner.get("text_delta"):
                    state["wrote"] = True
                    yield {"type": "text", "text": inner["text_delta"]}
            elif step and step not in HIDDEN_STEPS and inner.get("step_index") not in seen:
                seen.add(inner.get("step_index"))
                yield {"type": "tool", "text": _agy_tool_text(inner)}
        elif ev == "result":
            denied = [str(x.get("action") or x.get("display_name") or "") for x in inner.get("denied_actions") or []
                      if isinstance(x, dict)]
            if denied:
                yield denied_event("Antigravity", denied, state.get("mode", "auto"))
            if inner.get("status") not in (None, "SUCCESS"):
                state["failed"] = True
                yield {"type": "error", "text": S.short(f"Antigravity: {inner.get('response') or inner.get('status')}", 400)}
            elif not state.get("wrote") and inner.get("response"):
                yield {"type": "text", "text": str(inner["response"])}
    return parse


def build_command(agent: str, exe: str, text: str, session_id: str, new_session: bool,
                  model: str = "", effort: str = "", mode: str = "auto") -> Tuple[List[str], Optional[str]]:
    """Orden y texto para la entrada estándar (None si el mensaje va como argumento)."""
    if agent == "claude":
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--permission-mode", mode]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        cmd += ["--session-id", session_id] if new_session else ["--resume", session_id]
        return cmd, text
    cmd = [exe, "--output-format", "stream-json"]
    if mode == "auto" and sys.platform == "win32":
        # En Windows agy no tiene su modo «auto» (le falta el aislamiento de la terminal) y, sin nadie a
        # quien preguntar, deniega cada orden. «Autónomo» significa aquí aprobarlo todo.
        cmd.append("--dangerously-skip-permissions")
    else:
        cmd += ["--mode", AGY_MODES[mode]]
    if model:
        cmd += ["--model", model]
    if session_id:
        cmd += ["--conversation", session_id]
    return cmd + ["-p", text], None


_running: Dict[str, Dict[str, Any]] = {}
_running_lock = threading.Lock()


def busy_sessions() -> List[str]:
    with _running_lock:
        return [r["session"] for r in _running.values() if r.get("session")]


def stop(run_id: str) -> bool:
    """Corta la respuesta en curso (y lo que el agente tuviera lanzado)."""
    with _running_lock:
        run = _running.get(run_id)
    if not run:
        return False
    run["stopped"] = True
    proc = run["proc"]
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                           creationflags=NO_WINDOW)
        else:
            proc.terminate()
    except OSError:
        pass
    return True


def stream(project_path: str | Path, agent: str, text: str, session_id: str = "",
           model: str = "", effort: str = "", mode: str = "auto") -> Iterator[Event]:
    try:
        yield from _stream(project_path, agent, text, session_id, model, effort, mode)
    except AgentError as e:
        yield {"type": "error", "text": str(e)}
    yield {"type": "done"}


def _stream(project_path, agent, text, session_id, model, effort, mode) -> Iterator[Event]:
    if agent not in AGENTS:
        raise AgentError(f"No conozco el agente «{agent}».")
    name = AGENTS[agent]["name"]
    exe = _exe(agent)
    if not exe:
        raise AgentError(f"{name} no está instalado en este ordenador (falta «{AGENTS[agent]['command']}»).")
    if not text.strip():
        raise AgentError("Escribe algo para enviar.")
    if session_id and not S.SESSION_ID.match(session_id):
        raise AgentError("Esa conversación no es válida.")
    chosen = clean_settings({"agents": {agent: {"model": model, "effort": effort, "mode": mode}}})["agents"][agent]
    if agent == "antigravity" and len(text) > MAX_ARG_PROMPT:
        raise AgentError(f"El mensaje es demasiado largo para Antigravity (máximo {MAX_ARG_PROMPT} letras).")
    if session_id and session_id in busy_sessions():
        raise AgentError("Esta conversación ya está respondiendo. Espera o párala.")
    new_session = not session_id
    if agent == "claude" and new_session:
        session_id = str(uuid.uuid4())
    cmd, stdin_text = build_command(agent, exe, text, session_id, new_session, **chosen)
    if stdin_text is None and exe.lower().endswith((".cmd", ".bat")):
        raise AgentError(f"{name} está instalado como script y no es seguro pasarle el mensaje. Usa su terminal.")
    state: Dict[str, Any] = {"session": session_id, "mode": chosen["mode"]}
    parse = (claude_parser if agent == "claude" else agy_parser)(state)
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(project_path), stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1, env={**os.environ, "UNI_AGENT": agent}, creationflags=NO_WINDOW)
    except OSError as e:
        raise AgentError(f"No se ha podido arrancar {name}: {e}")
    run_id = uuid.uuid4().hex
    run = {"proc": proc, "session": session_id, "stopped": False}
    with _running_lock:
        _running[run_id] = run
    tail: List[str] = []
    try:
        yield {"type": "run", "id": run_id}
        if session_id:
            yield {"type": "session", "id": session_id}
        if stdin_text is not None:
            try:
                proc.stdin.write(stdin_text)
                proc.stdin.close()
            except OSError:
                pass
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                tail = (tail + [line])[-5:]
                continue
            if isinstance(data, dict):
                for ev in parse(data):
                    if ev["type"] == "session":
                        run["session"] = ev["id"]
                    yield ev
        code = proc.wait()
        if run["stopped"]:
            yield {"type": "stopped"}
        elif code != 0 and not state.get("failed"):
            detail = S.short(" · ".join(tail), 400) if tail else f"código {code}"
            yield {"type": "error", "text": f"{name} ha terminado con un error: {detail}"}
    finally:
        with _running_lock:
            _running.pop(run_id, None)
        if proc.poll() is None:
            proc.kill()


# ----------------------------------------------------------------------------- abrir en la app nativa

def open_native(project_path: str | Path, agent: str, session_id: str = "") -> str:
    """Abre la conversación en una terminal con la CLI del agente. Devuelve qué ha hecho."""
    if agent not in AGENTS:
        raise AgentError(f"No conozco el agente «{agent}».")
    exe, name = _exe(agent), AGENTS[agent]["name"]
    if not exe:
        raise AgentError(f"{name} no está instalado en este ordenador.")
    if session_id and not S.SESSION_ID.match(session_id):
        raise AgentError("Esa conversación no es válida.")
    args = [exe] + (["--resume" if agent == "claude" else "--conversation", session_id] if session_id else [])
    path = str(project_path)
    env = {**os.environ, "UNI_AGENT": agent}
    try:
        if sys.platform == "win32":
            if shutil.which("wt"):
                subprocess.Popen(["wt", "-d", path, *args], env=env)
            else:
                subprocess.Popen(["cmd", "/c", "start", name, "/D", path, "cmd", "/k", *args], env=env)
        elif sys.platform == "darwin":
            raise AgentError(f"Abre una terminal en el proyecto y escribe: {' '.join(args[1:] and [AGENTS[agent]['command'], *args[1:]] or [AGENTS[agent]['command']])}")
        else:
            term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
            if not term:
                raise AgentError("No encuentro una terminal que abrir.")
            subprocess.Popen([term, "-e", *args] if "x-terminal" in term else [term, "--", *args], cwd=path, env=env)
    except OSError as e:
        raise AgentError(f"No se ha podido abrir {name}: {e}")
    return f"Conversación abierta en {name}."
