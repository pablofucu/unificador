"""
Conversaciones guardadas de Unificador.

Cada conversación es un fichero JSON en ``~/.unificador/chats/<proyecto>/<id>.json``:

    {id, project_id, agent, task_id, title, native_session_id, created_at, updated_at,
     messages: [{role, content, agent, at, task_id?, tools?, source?}]}

``native_session_id`` es el id de la sesión del propio agente (Claude Code o Antigravity).
Con él la conversación sigue el hilo en el siguiente mensaje (``--resume`` / ``--conversation``)
y se puede continuar desde la terminal o el cliente de escritorio. Lo que se escriba allí en una
sesión de Claude Code se vuelve a traer al abrir la conversación (``sync_from_claude``).
"""

from __future__ import annotations
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from unificador.config import CONFIG_DIR, _write_json_atomic

CHATS_DIR = CONFIG_DIR / "chats"
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe(name: str) -> str:
    return _SAFE.sub("_", str(name)) or "_"


def claude_transcript_path(project_path: str, session_id: str,
                           base: Optional[Path] = None) -> Path:
    """Ruta del transcript de Claude Code: cada carácter no alfanumérico de la ruta pasa a '-'."""
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(Path(project_path).resolve()))
    return (base or CLAUDE_PROJECTS_DIR) / encoded / f"{session_id}.jsonl"


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content
                       if isinstance(b, dict) and b.get("type") == "text")
    return ""


def read_claude_turns(path: Path) -> List[Dict[str, str]]:
    """Turnos user/assistant de un transcript de Claude Code (sin resultados de herramientas)."""
    turns: List[Dict[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return turns
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("isMeta") or e.get("isSidechain") or e.get("type") not in ("user", "assistant"):
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if e["type"] == "user":
            # Un resultado de herramienta también llega como "user": no es un turno de la persona
            if isinstance(content, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            text = _text_of(content).strip()
            if text and not text.startswith("<"):
                turns.append({"role": "user", "content": text})
        else:
            text = _text_of(content)
            if not text:
                continue
            if turns and turns[-1]["role"] == "assistant":
                turns[-1]["content"] += ("\n\n" if turns[-1]["content"] else "") + text
            else:
                turns.append({"role": "assistant", "content": text})
    return turns


def strip_injected(text: str) -> str:
    """Del mensaje que vio el agente, deja solo lo que escribió la persona."""
    from unificador.context_injector import USER_MARKER
    _, sep, rest = text.partition(USER_MARKER)
    return rest.strip() if sep else text.strip()


class ChatStore:
    def __init__(self, base_dir: Optional[Path] = None, claude_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir or CHATS_DIR)
        self.claude_dir = claude_dir
        self._lock = threading.RLock()

    def _file(self, project_id: str, chat_id: str) -> Path:
        return self.base_dir / _safe(project_id) / f"{_safe(chat_id)}.json"

    def _save(self, chat: Dict[str, Any]) -> None:
        _write_json_atomic(self._file(chat["project_id"], chat["id"]), chat)

    # ---------- Lectura ----------
    def get(self, project_id: str, chat_id: str) -> Optional[Dict[str, Any]]:
        try:
            with open(self._file(project_id, chat_id), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def list(self, project_id: str) -> List[Dict[str, Any]]:
        """Resúmenes, la más reciente primero."""
        folder = self.base_dir / _safe(project_id)
        out = []
        for p in folder.glob("*.json") if folder.is_dir() else []:
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            last = c["messages"][-1]["content"] if c.get("messages") else ""
            out.append({k: c.get(k) for k in ("id", "agent", "task_id", "title",
                                                 "native_session_id", "created_at", "updated_at")}
                       | {"count": len(c.get("messages", [])), "preview": last[:140]})
        return sorted(out, key=lambda c: c.get("updated_at") or 0, reverse=True)

    # ---------- Escritura ----------
    def create(self, project_id: str, agent: str, task_id: Optional[str] = None,
               title: str = "") -> Dict[str, Any]:
        now = time.time()
        chat = {"id": uuid.uuid4().hex[:12], "project_id": project_id, "agent": agent,
                "task_id": task_id, "title": title or "Conversación nueva",
                "native_session_id": None, "created_at": now, "updated_at": now, "messages": []}
        with self._lock:
            self._save(chat)
        return chat

    def update(self, project_id: str, chat_id: str, **fields) -> Optional[Dict[str, Any]]:
        with self._lock:
            chat = self.get(project_id, chat_id)
            if chat is None:
                return None
            chat.update(fields)
            chat["updated_at"] = time.time()
            self._save(chat)
            return chat

    def append(self, project_id: str, chat_id: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._lock:
            chat = self.get(project_id, chat_id)
            if chat is None:
                return None
            message = {"at": time.time(), **message}
            chat["messages"].append(message)
            if message["role"] == "user" and chat.get("title") in (None, "", "Conversación nueva"):
                first = " ".join(message["content"].split())
                chat["title"] = first[:60] + ("…" if len(first) > 60 else "")
            chat["updated_at"] = time.time()
            self._save(chat)
            return chat

    def delete(self, project_id: str, chat_id: str) -> bool:
        with self._lock:
            try:
                os.remove(self._file(project_id, chat_id))
                return True
            except OSError:
                return False

    # ---------- Sincronización con el cliente nativo ----------
    def sync_from_claude(self, project_id: str, chat_id: str, project_path: str) -> Optional[Dict[str, Any]]:
        """Añade los turnos escritos fuera de Unificador (terminal o app de escritorio).

        Compara cuántos turnos de la persona hay en el transcript de Claude Code con los
        guardados aquí y trae los que faltan, en orden.
        """
        with self._lock:
            chat = self.get(project_id, chat_id)
            if not chat or chat.get("agent") != "claude_code" or not chat.get("native_session_id"):
                return chat
            path = claude_transcript_path(project_path, chat["native_session_id"], self.claude_dir)
            if not path.is_file():
                return chat
            turns = read_claude_turns(path)
            known_users = sum(1 for m in chat["messages"] if m["role"] == "user")
            seen = 0
            new: List[Dict[str, Any]] = []
            for i, t in enumerate(turns):
                if t["role"] == "user":
                    seen += 1
                if seen > known_users:
                    new = turns[i:]
                    break
            if not new:
                return chat
            mtime = path.stat().st_mtime
            for t in new:
                content = strip_injected(t["content"]) if t["role"] == "user" else t["content"]
                chat["messages"].append({"role": t["role"], "content": content, "agent": "claude_code",
                                         "at": mtime, "source": "claude_code"})
            chat["updated_at"] = max(chat.get("updated_at") or 0, mtime)
            self._save(chat)
            return chat


chat_store = ChatStore()
