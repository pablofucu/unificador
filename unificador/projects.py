"""
Registro de proyectos: la lista de carpetas que Unificador conoce en esta máquina.

Vive en ``~/.unificador/proyectos.json`` (la carpeta se puede cambiar con la variable de entorno
``UNIFICADOR_HOME``, que usan las pruebas). Un fichero ausente o roto equivale a una lista vacía.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

FILE_NAME = "proyectos.json"


def _home() -> Path:
    env = os.environ.get("UNIFICADOR_HOME")
    return Path(env) if env else Path.home() / ".unificador"


def _file() -> Path:
    return _home() / FILE_NAME


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _id(path: str) -> str:
    return hashlib.sha1(_norm(path).encode("utf-8")).hexdigest()[:10]


def _load() -> List[str]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        paths = data["projects"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []


def _save(paths: List[str]) -> None:
    target = _file()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"projects": paths}, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, target)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def register(path) -> None:
    """Apunta el proyecto (ruta absoluta). Repetirlo no hace nada."""
    absolute = os.path.abspath(str(path))
    paths = _load()
    if any(_norm(p) == _norm(absolute) for p in paths):
        return
    _save(paths + [absolute])


def forget(path) -> None:
    """Quita el proyecto de la lista (no toca la carpeta)."""
    paths = _load()
    kept = [p for p in paths if _norm(p) != _norm(path)]
    if len(kept) != len(paths):
        _save(kept)


def listing() -> List[Dict]:
    """Proyectos conocidos, por nombre: ``{"id", "name", "path", "exists"}``."""
    out = [{"id": _id(p), "name": Path(p).name or p, "path": p, "exists": Path(p).is_dir()}
           for p in _load()]
    return sorted(out, key=lambda d: (d["name"].lower(), d["path"]))


def find(project_id: str) -> Optional[Path]:
    for item in listing():
        if item["id"] == project_id:
            return Path(item["path"])
    return None
