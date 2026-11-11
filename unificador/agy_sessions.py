"""Conversaciones de Antigravity (se rellena en CN-04)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from unificador import sessions as S


def list_sessions(project_path: str | Path) -> List[Dict[str, Any]]:
    return []


def read_session(project_path: str | Path, session_id: str) -> Dict[str, Any]:
    raise S.SessionError(f"no existe la conversación {session_id}")
