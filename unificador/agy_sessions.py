"""Conversaciones de Antigravity, leídas de donde las guarda su CLI (``agy``).

Solo lectura: ``conversation_summaries.db`` da la lista y ``conversations/<id>.db`` los pasos.
Cada paso es un mensaje protobuf sin esquema publicado; aquí se lee lo justo:

* paso 14 → mensaje de la persona (texto en ``19.2``)
* paso 15 → respuesta del agente (texto en ``20.1``, herramientas en ``20.7``: nombre ``.2``, JSON ``.3``)

Si Antigravity cambia el formato, las conversaciones salen vacías pero nada se rompe.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import unquote

from unificador import sessions as S

CONVERSATION_ID = re.compile(r"^[0-9a-fA-F][0-9a-fA-F\-]{7,63}$")
USER_STEP, AGENT_STEP = 14, 15
# Las versiones viejas de Unificador metían contexto delante del mensaje; se enseña solo lo escrito.
OLD_MARKER = "[INSTRUCCIÓN DEL USUARIO]:"
TOOL_LABELS = {"read_file": "Lee", "view_file": "Lee", "write_to_file": "Escribe", "write_file": "Escribe",
               "replace_file_content": "Edita", "multi_replace_file_content": "Edita", "edit_file": "Edita",
               "run_command": "Ejecuta", "list_dir": "Mira la carpeta", "list_directory": "Mira la carpeta",
               "grep_search": "Busca", "find_by_name": "Busca", "search_web": "Busca en la web",
               "read_url_content": "Abre"}


def home(base: Optional[Path] = None) -> Path:
    return Path(base) if base else Path.home() / ".gemini" / "antigravity-cli"


def _open(path: Path) -> sqlite3.Connection:
    uri = "file:" + path.as_posix().replace("?", "%3f").replace("#", "%23") + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=2)


# ----------------------------------------------------------------------------- protobuf mínimo

def _varint(b: bytes, i: int) -> Tuple[int, int]:
    n = shift = 0
    while True:
        c = b[i]
        i += 1
        n |= (c & 0x7F) << shift
        if not c & 0x80:
            return n, i
        shift += 7
        if shift > 70:
            raise IndexError


def fields(b: bytes) -> List[Tuple[int, Any]]:
    """Campos de un mensaje: ``(número, valor)``; los valores con longitud llegan como ``bytes``."""
    i, out = 0, []
    try:
        while i < len(b):
            key, i = _varint(b, i)
            num, wire = key >> 3, key & 7
            if wire == 0:
                v, i = _varint(b, i)
            elif wire in (1, 5):
                size = 8 if wire == 1 else 4
                v, i = b[i:i + size], i + size
            elif wire == 2:
                n, i = _varint(b, i)
                v, i = b[i:i + n], i + n
                if len(v) != n:
                    return []
            else:
                return []
            out.append((num, v))
    except IndexError:
        return []
    return out


def get_all(b: Any, *path: int) -> List[Any]:
    """Todos los valores que hay siguiendo ``path`` (p. ej. ``20, 7`` → cada llamada a herramienta)."""
    found = [b]
    for num in path:
        found = [v for item in found if isinstance(item, bytes) for n, v in fields(item) if n == num]
    return found


def get_text(b: Any, *path: int) -> str:
    for v in get_all(b, *path):
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8")
            except UnicodeDecodeError:
                continue
    return ""


# ----------------------------------------------------------------------------- lista

def _uri_path(uri: str) -> str:
    if not uri.lower().startswith("file:"):
        return ""
    p = unquote(uri[5:]).lstrip("/") if re.match(r"^file:/+[A-Za-z](:|%3[aA])", uri) else unquote(uri[5:])
    p = re.sub(r"^//+", "/", p)
    return os.path.normcase(os.path.normpath(p))


def _is_project(workspace_uris: Any, project_path: str | Path) -> bool:
    try:
        uris = json.loads(workspace_uris or "[]")
    except (TypeError, ValueError):
        return False
    here = os.path.normcase(os.path.normpath(str(Path(project_path).resolve())))
    return any(_uri_path(str(u)) == here for u in uris if isinstance(u, str))


def _iso(stamp: Any) -> str:
    """``2026-11-08 18:43:22.8889869+00:00`` → ISO en UTC con segundos."""
    m = re.match(r"^(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)(?:\.\d+)?\s*(Z|[+-]\d\d:?\d\d)?", str(stamp or ""))
    if not m:
        return ""
    zone = (m.group(3) or "+00:00").replace("Z", "+00:00")
    if ":" not in zone:
        zone = zone[:3] + ":" + zone[3:]
    try:
        when = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}{zone}")
    except ValueError:
        return ""
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


def clean_user_text(text: str) -> str:
    if OLD_MARKER in text:
        text = text.split(OLD_MARKER, 1)[1]
    return text.strip()


def _rows(base: Optional[Path]) -> List[Tuple[Any, ...]]:
    path = home(base) / "conversation_summaries.db"
    if not path.is_file():
        return []
    try:
        db = _open(path)
        try:
            return db.execute(
                "select conversation_id, title, preview, step_count, last_modified_time, workspace_uris "
                "from conversation_summaries").fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return []


def _summary(row: Tuple[Any, ...], base: Optional[Path]) -> Dict[str, Any]:
    cid, title, preview, steps, modified, _ = row
    title = str(title or "").strip() or clean_user_text(str(preview or ""))
    if not title or title.startswith("["):
        first = next((t["text"] for t in _turns(cid, base) if t["role"] == "user"), "")
        title = first or title
    return {"id": str(cid), "agent": "antigravity", "title": S.short(title or "Conversación", 70),
            "updated": _iso(modified), "messages": int(steps or 0), "origin": "antigravity"}


def list_sessions(project_path: str | Path, base: Optional[Path] = None) -> List[Dict[str, Any]]:
    out = [_summary(r, base) for r in _rows(base)
           if CONVERSATION_ID.match(str(r[0] or "")) and _is_project(r[5], project_path)]
    return sorted(out, key=lambda s: s["updated"], reverse=True)


# ----------------------------------------------------------------------------- conversación

def describe_tool(name: str, raw_args: str) -> str:
    try:
        args = json.loads(raw_args) if raw_args else {}
    except ValueError:
        args = {}
    if not isinstance(args, dict):
        args = {}
    target = ""
    for key in ("toolSummary", "CommandLine", "Path", "AbsolutePath", "TargetFile", "DirectoryPath",
                "SearchPath", "Query", "Pattern", "Url"):
        if args.get(key):
            target = str(args[key])
            break
    label = TOOL_LABELS.get(name, name.replace("_", " "))
    return f"{label} {S.short(target, 80)}".strip()


def _step_time(metadata: Any) -> str:
    seconds = next((v for v in get_all(metadata, 1, 1) if isinstance(v, int)), 0) if metadata else 0
    if not 0 < seconds < 4102444800:
        return ""
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds")


def _steps(session_id: str, base: Optional[Path]) -> Iterator[Tuple[int, Any, bytes]]:
    path = home(base) / "conversations" / f"{session_id}.db"
    if not path.is_file():
        return
    try:
        db = _open(path)
        try:
            yield from db.execute(
                "select step_type, metadata, step_payload from steps where step_type in (?, ?) order by idx",
                (USER_STEP, AGENT_STEP))
        finally:
            db.close()
    except sqlite3.Error:
        return


def _turns(session_id: str, base: Optional[Path] = None) -> List[Dict[str, Any]]:
    turns: List[Dict[str, Any]] = []
    for kind, metadata, payload in _steps(session_id, base):
        payload, at = bytes(payload or b""), _step_time(bytes(metadata or b""))
        if kind == USER_STEP:
            text = clean_user_text(get_text(payload, 19, 2) or get_text(payload, 19, 3, 1))
            if text:
                turns.append({"role": "user", "text": text, "tools": [], "at": at})
            continue
        text = (get_text(payload, 20, 1) or get_text(payload, 20, 8)).strip()
        tools = [describe_tool(get_text(call, 2), get_text(call, 3))
                 for call in get_all(payload, 20, 7) if get_text(call, 2)]
        if not text and not tools:
            continue
        if not turns or turns[-1]["role"] != "assistant":
            turns.append({"role": "assistant", "text": "", "tools": [], "at": at, "model": ""})
        last = turns[-1]
        if text:
            last["text"] += ("\n\n" if last["text"] else "") + text
        last["tools"] += tools
    return turns


def read_session(project_path: str | Path, session_id: str, base: Optional[Path] = None) -> Dict[str, Any]:
    if not CONVERSATION_ID.match(str(session_id or "")):
        raise S.SessionError("identificador de sesión no válido")
    row = next((r for r in _rows(base) if str(r[0]) == session_id), None)
    if row is not None and not _is_project(row[5], project_path):
        raise S.SessionError(f"no existe la conversación {session_id}")
    exists = (home(base) / "conversations" / f"{session_id}.db").is_file()
    if row is None and not exists:
        raise S.SessionError(f"no existe la conversación {session_id}")
    info = _summary(row, base) if row is not None else {
        "id": session_id, "agent": "antigravity", "title": "Conversación nueva", "updated": "",
        "messages": 0, "origin": "antigravity"}
    return {**info, "turns": _turns(session_id, base)}


def latest_mtime(project_path: str | Path, base: Optional[Path] = None) -> float:
    """Última escritura en el índice de conversaciones (cambia cada vez que alguna avanza)."""
    newest = 0.0
    for name in ("conversation_summaries.db", "conversation_summaries.db-wal"):
        try:
            newest = max(newest, (home(base) / name).stat().st_mtime)
        except OSError:
            pass
    return newest
