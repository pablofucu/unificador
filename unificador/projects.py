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
import time
from pathlib import Path
from typing import Dict, List, Optional

FILE_NAME = "proyectos.json"
ACTIVE_FILE = "active.json"
NAMES_FILE = "nombres.json"
MAX_NAME = 60


def _home() -> Path:
    env = os.environ.get("UNIFICADOR_HOME")
    return Path(env) if env else Path.home() / ".unificador"


def _file() -> Path:
    return _home() / FILE_NAME


def _names_file() -> Path:
    return _home() / NAMES_FILE


def _active_file() -> Path:
    return _home() / ACTIVE_FILE


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _id(path: str) -> str:
    return hashlib.sha1(_norm(path).encode("utf-8")).hexdigest()[:10]


def _write_json(target: Path, payload: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, target)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load() -> List[str]:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        paths = data["projects"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else []


def _save(paths: List[str]) -> None:
    _write_json(_file(), {"projects": paths})


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


def set_active(path) -> str:
    """Marca ``path`` como el proyecto en el que se está trabajando ahora."""
    absolute = os.path.abspath(str(path))
    pid = _id(absolute)
    _write_json(_active_file(), {"id": pid, "path": absolute, "updated": int(time.time())})
    return pid


def clear_active() -> None:
    try:
        _active_file().unlink()
    except OSError:
        pass


def active_id() -> str:
    """El id del último proyecto activo registrado, o ``""`` si no hay ninguno."""
    try:
        data = json.loads(_active_file().read_text(encoding="utf-8"))
        pid = data.get("id", "")
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    return pid if isinstance(pid, str) else ""


def _names() -> Dict[str, str]:
    """Nombres puestos por la persona, por id (fichero aparte: los ``uni.py`` viejos reescriben el registro)."""
    try:
        data = json.loads(_names_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and v.strip()}


def clean_name(name) -> str:
    """Un nombre en una línea, sin espacios de sobra; vacío = volver al de la carpeta."""
    if not isinstance(name, str):
        raise ValueError("El nombre tiene que ser texto.")
    text = " ".join(name.split())
    if len(text) > MAX_NAME:
        raise ValueError(f"El nombre es demasiado largo (máx. {MAX_NAME} caracteres).")
    return text


def name_of(path) -> str:
    """El nombre con el que se enseña la carpeta: el puesto por la persona o el de la carpeta."""
    return _names().get(_id(str(path))) or Path(str(path)).name or str(path)


def rename(project_id: str, name) -> str:
    """Pone (o quita, con ``""``) el nombre del proyecto. Devuelve el nombre guardado."""
    text = clean_name(name)
    names = _names()
    if text:
        names[project_id] = text
    else:
        names.pop(project_id, None)
    _write_json(_names_file(), names)
    return text


def forget_id(project_id: str) -> bool:
    """Quita de la lista el proyecto con ese id (la carpeta no se toca). ``False`` si no estaba."""
    path = find(project_id)
    if path is None:
        return False
    forget(path)
    names = _names()
    if names.pop(project_id, None) is not None:
        _write_json(_names_file(), names)
    return True


def listing() -> List[Dict]:
    """Proyectos conocidos, por nombre: ``{"id", "name", "folder", "path", "exists"}``."""
    names = _names()
    out = []
    for p in _load():
        pid, folder = _id(p), Path(p).name or p
        out.append({"id": pid, "name": names.get(pid) or folder, "folder": folder,
                    "path": p, "exists": Path(p).is_dir()})
    return sorted(out, key=lambda d: (d["name"].lower(), d["path"]))


def find(project_id: str) -> Optional[Path]:
    for item in listing():
        if item["id"] == project_id:
            return Path(item["path"])
    return None
