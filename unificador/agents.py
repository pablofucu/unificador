"""
Los agentes con los que se puede hablar desde la web: Claude Code y Antigravity.

El mensaje de la persona se envía **tal cual** a la CLI del agente, en su sesión nativa: lo que se
escribe aquí aparece en la app o la terminal, y al revés. No se inyecta contexto: las reglas del
proyecto ya están en AGENTS.md y las lee el propio agente.

``stream`` va dando eventos (dict con ``type``):
``run`` (id para poder parar), ``session`` (id de la sesión nativa), ``text``, ``tool``,
``error`` y, siempre el último, ``done``.
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
MODEL_ID = re.compile(r"^[\w.\-\[\]]{1,80}$")
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
HIDDEN_STEPS = {"user_input", "system_message", "ephemeral_message", "checkpoint", "conversation_history",
                "planner_response", "error_message"}


class AgentError(Exception):
    pass


def _exe(agent: str) -> str:
    return shutil.which(AGENTS[agent]["command"]) or ""


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
        out.append({"id": key, "name": a["name"], "icon": a["icon"], "installed": bool(_exe(key)),
                    "models": models, "efforts": a["efforts"], "modes": MODES})
    return out


def clean_settings(data: Any) -> Dict[str, Any]:
    """Ajustes de la persona, ya comprobados: agente elegido y modelo/esfuerzo/modo de cada uno."""
    data = data if isinstance(data, dict) else {}
    agent = data.get("agent") if data.get("agent") in AGENTS else "claude"
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


def read_session(project_path: str | Path, agent: str, session_id: str) -> Dict[str, Any]:
    if _need(agent) == "antigravity":
        from unificador import agy_sessions
        return agy_sessions.read_session(project_path, session_id)
    return S.read_session(project_path, session_id)


# ----------------------------------------------------------------------------- enviar

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
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    yield {"type": "tool", "text": S.describe_tool(str(b.get("name") or ""), b.get("input"))}
        elif kind == "result":
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
                detail = inner.get("command") or inner.get("file_path") or inner.get("summary") or ""
                yield {"type": "tool", "text": S.short(f"{STEP_LABELS.get(step, step.replace('_', ' '))} {detail}".strip())}
        elif ev == "result":
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
    cmd = [exe, "--output-format", "stream-json", "--mode", AGY_MODES[mode]]
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
    state: Dict[str, Any] = {"session": session_id}
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
