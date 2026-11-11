"""
Sesiones nativas de Claude Code: Unificador no guarda conversaciones propias.

Lo que la persona escribe en la terminal, en la app de escritorio o en la web acaba en el mismo
sitio: ``~/.claude/projects/<ruta-codificada>/<sesión>.jsonl``. Aquí solo se leen esos ficheros.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
SESSION_ID = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{7,63}$")
TITLE_MAX = 70

TOOL_LABELS = {"Bash": "Ejecuta", "PowerShell": "Ejecuta", "Edit": "Edita", "Write": "Escribe",
               "Read": "Lee", "Grep": "Busca", "Glob": "Busca", "WebFetch": "Abre",
               "WebSearch": "Busca en la web", "TodoWrite": "Actualiza su lista",
               "Task": "Lanza un ayudante", "Agent": "Lanza un ayudante", "Skill": "Usa la habilidad"}

ORIGINS = {"claude-desktop": "app", "cli": "terminal", "sdk-cli": "web", "sdk-py": "web", "sdk-ts": "web"}


class SessionError(Exception):
    pass


def short(text: Any, n: int = 90) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def describe_tool(name: str, inp: Any) -> str:
    """Resumen corto de una llamada a herramienta para mostrar en el chat."""
    if not isinstance(inp, dict):
        inp = {}
    target = (inp.get("description") or inp.get("command") or inp.get("file_path") or inp.get("path")
              or inp.get("pattern") or inp.get("url") or inp.get("query") or inp.get("skill") or "")
    if name.startswith("mcp__"):
        name = name.split("__")[-1].replace("_", " ")
    return f"{TOOL_LABELS.get(name, name)} {short(target, 80)}".strip()


def project_dir(project_path: str | Path, base: Optional[Path] = None) -> Path:
    """Carpeta de sesiones de un proyecto: cada carácter no alfanumérico de la ruta pasa a '-'."""
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(Path(project_path).resolve()))
    return (base or CLAUDE_PROJECTS_DIR) / encoded


def session_path(project_path: str | Path, session_id: str, base: Optional[Path] = None) -> Path:
    if not SESSION_ID.match(session_id or ""):
        raise SessionError("identificador de sesión no válido")
    return project_dir(project_path, base) / f"{session_id}.jsonl"


def _entries(path: Path, wanted: Tuple[str, ...]) -> Iterator[Dict[str, Any]]:
    """Entradas del transcript cuyo ``type`` está en ``wanted`` (sin decodificar el resto: hay líneas enormes)."""
    marks = tuple(f'"type":"{t}"' for t in wanted)
    try:
        f = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return
    with f:
        for line in f:
            if not any(m in line for m in marks):
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue  # línea a medio escribir
            if isinstance(e, dict) and e.get("type") in wanted:
                yield e


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _human_text(e: Dict[str, Any]) -> str:
    """Lo que escribió la persona en una entrada ``user``; '' si es ruido (herramientas, avisos, resúmenes)."""
    if e.get("isMeta") or e.get("isSidechain") or e.get("isCompactSummary"):
        return ""
    content = (e.get("message") or {}).get("content")
    if isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return ""
    text = _text_of(content).strip()
    return "" if text.startswith("<") else text


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")


_summary_cache: Dict[str, Tuple[Tuple[float, int], Dict[str, Any]]] = {}


def summarize(path: Path) -> Optional[Dict[str, Any]]:
    """Título, fecha y origen de una sesión. None si no tiene ningún mensaje de la persona."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (st.st_mtime, st.st_size)
    hit = _summary_cache.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    title = first = origin = ""
    count = 0
    for e in _entries(path, ("user", "custom-title", "summary")):
        t = e["type"]
        if t == "custom-title":
            title = str(e.get("customTitle") or "") or title
        elif t == "summary":
            title = title or str(e.get("summary") or "")
        else:
            text = _human_text(e)
            if text:
                count += 1
                first = first or text
                origin = origin or ORIGINS.get(str(e.get("entrypoint") or ""), "")
    info = None
    if first:
        info = {"id": path.stem, "agent": "claude", "title": short(title or first, TITLE_MAX),
                "updated": _mtime_iso(path), "messages": count, "origin": origin or "terminal"}
    _summary_cache[str(path)] = (key, info)
    return info


def list_sessions(project_path: str | Path, base: Optional[Path] = None,
                  limit: int = 50) -> List[Dict[str, Any]]:
    """Sesiones del proyecto, la más reciente primero."""
    folder = project_dir(project_path, base)
    try:
        files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []
    out = []
    for p in files:
        info = summarize(p)
        if info:
            out.append(info)
            if len(out) >= limit:
                break
    return out


def read_turns(path: Path) -> List[Dict[str, Any]]:
    """Conversación limpia: ``{role, text, tools, at}``; los trozos seguidos del agente se juntan."""
    turns: List[Dict[str, Any]] = []
    for e in _entries(path, ("user", "assistant")):
        if e.get("isSidechain") or e.get("isMeta"):
            continue
        at = str(e.get("timestamp") or "")
        if e["type"] == "user":
            text = _human_text(e)
            if text:
                turns.append({"role": "user", "text": text, "tools": [], "at": at})
            continue
        content = (e.get("message") or {}).get("content")
        text = _text_of(content).strip()
        tools = [describe_tool(str(b.get("name") or ""), b.get("input"))
                 for b in content or [] if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not text and not tools:
            continue
        if not turns or turns[-1]["role"] != "assistant":
            turns.append({"role": "assistant", "text": "", "tools": [], "at": at, "model": ""})
        last = turns[-1]
        model = str((e.get("message") or {}).get("model") or "")
        if model and not model.startswith("<"):
            last["model"] = model
        if text:
            last["text"] += ("\n\n" if last["text"] else "") + text
        last["tools"] += tools
    return turns


def read_session(project_path: str | Path, session_id: str,
                 base: Optional[Path] = None) -> Dict[str, Any]:
    path = session_path(project_path, session_id, base)
    if not path.is_file():
        raise SessionError(f"no existe la sesión {session_id}")
    info = summarize(path) or {"id": session_id, "agent": "claude", "title": "Conversación nueva",
                               "updated": _mtime_iso(path), "messages": 0, "origin": "web"}
    return {**info, "turns": read_turns(path)}


def latest_mtime(project_path: str | Path, base: Optional[Path] = None) -> float:
    """Marca de cambio de las sesiones del proyecto (para avisar a la web en vivo)."""
    try:
        return max((p.stat().st_mtime for p in project_dir(project_path, base).glob("*.jsonl")),
                   default=0.0)
    except OSError:
        return 0.0
