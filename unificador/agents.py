"""
Los clientes de IA con los que se trabaja: Claude Code, Antigravity y Codex.

Unificador no habla con ellos: cada uno lleva sus conversaciones en su propio cliente y apunta el plan
con ``uni.py``. Este módulo solo sabe si cada cliente está instalado, para que ``unificador doctor``
pueda decirlo.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

CLIENTS: Dict[str, Dict[str, str]] = {
    "claude": {"name": "Claude Code", "command": "claude", "rules": "CLAUDE.md"},
    "antigravity": {"name": "Antigravity", "command": "agy", "rules": "AGENTS.md"},
    "codex": {"name": "Codex", "command": "codex", "rules": "AGENTS.md"},
}


def _usual_places(client: str) -> List[Path]:
    """Dónde suelen instalarse, por si la terminal que abrió Unificador no los tiene en el PATH."""
    home, env = Path.home(), os.environ
    local = Path(env.get("LOCALAPPDATA") or home / "AppData/Local")
    roaming = Path(env.get("APPDATA") or home / "AppData/Roaming")
    shared = [home / ".local/bin", Path("/usr/local/bin"), Path("/opt/homebrew/bin"), home / ".npm-global/bin",
              home / ".bun/bin", roaming / "npm"]
    own = {"claude": [home / ".claude/local", home / ".claude/bin", local / "Programs/claude"],
           "antigravity": [local / "agy/bin", home / ".gemini/antigravity-cli/bin", local / "Programs/agy/bin"],
           "codex": [home / ".codex/bin", local / "Programs/codex"]}[client]
    command = CLIENTS[client]["command"]
    names = [command + ext for ext in ((".exe", ".cmd", "") if sys.platform == "win32" else ("",))]
    return [folder / name for folder in own + shared for name in names]


def find(client: str) -> str:
    """Ruta del ejecutable del cliente (PATH y carpetas habituales), o "" si no se encuentra."""
    found = shutil.which(CLIENTS[client]["command"])
    if found:
        return found
    return next((str(p) for p in _usual_places(client) if p.is_file()), "")


def available() -> List[Dict[str, Any]]:
    out = []
    for key, c in CLIENTS.items():
        exe = find(key)
        out.append({"id": key, "name": c["name"], "command": c["command"], "installed": bool(exe), "path": exe})
    return out
