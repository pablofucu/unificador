"""
Actualizaciones: saber si hay una versión nueva, instalarla y dejar al día todos los proyectos.

Dos formas de instalación:

- **git**: la carpeta del paquete es un clon (``pip install -e .``). Hay novedades si ``origin`` tiene commits
  que aquí no están; se actualiza con ``git pull --ff-only`` (git se niega solo si choca con cambios sin comitear).
- **pip**: instalado desde GitHub. Hay novedades si el último tag ``vX.Y.Z`` es mayor que ``__version__``;
  se actualiza con ``pip install -U git+https://github.com/<REPO>``.

Lo que se recuerda (última comprobación, resultado y el ajuste «actualizar solo») vive en
``~/.unificador/update.json``. ``UNIFICADOR_NO_UPDATE_CHECK=1`` apaga la comprobación por red (pruebas).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from unificador import __version__, projects

REPO = os.environ.get("UNIFICADOR_REPO", "pablofucu/unificador")
STATE_FILE = "update.json"
CHECK_EVERY = 24 * 3600
_lock = threading.Lock()


# ----------------------------------------------------------------------------- estado

def _state_file() -> Path:
    return projects._home() / STATE_FILE


def load_state() -> Dict[str, Any]:
    try:
        data = json.loads(_state_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(changes: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        state = {**load_state(), **changes}
        projects._write_json(_state_file(), state)
        return state


def set_auto(on: bool) -> Dict[str, Any]:
    _save_state({"auto": bool(on)})
    return status()


# ----------------------------------------------------------------------------- comprobar

def package_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _git(*args: str, timeout: int = 60) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", str(package_dir()), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def kind() -> str:
    """``git`` si el paquete es un clon con ``origin``; si no, ``pip``."""
    if (package_dir() / ".git").exists() and _git("remote", "get-url", "origin"):
        return "git"
    return "pip"


def _parse(v: str) -> Optional[tuple]:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", v.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _best(names: List[str]) -> str:
    versions = [(_parse(n), n) for n in names]
    versions = [v for v in versions if v[0]]
    return max(versions)[1].lstrip("v") if versions else ""


def latest_tag(timeout: float = 20.0) -> str:
    """El tag ``vX.Y.Z`` más alto del repositorio en GitHub ("" si no tiene ninguno).

    Primero con ``git ls-remote`` (usa las credenciales de git, así vale también para repos privados);
    si no hay git, con la API pública de GitHub.
    """
    try:
        r = subprocess.run(["git", "ls-remote", "--tags", "--refs", f"https://github.com/{REPO}"],
                           capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0:
            return _best([line.rsplit("refs/tags/", 1)[-1] for line in r.stdout.splitlines() if "refs/tags/" in line])
    except (OSError, subprocess.SubprocessError):
        pass
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/tags?per_page=100",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "unificador"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return _best([t.get("name", "") for t in data if isinstance(t, dict)])


def check(force: bool = False) -> Dict[str, Any]:
    """Mira si hay versión nueva (como mucho una vez al día salvo ``force``) y lo guarda."""
    state = load_state()
    if not force and time.time() - float(state.get("checked") or 0) < CHECK_EVERY:
        return status()
    if os.environ.get("UNIFICADOR_NO_UPDATE_CHECK"):
        return status()
    how = kind()
    result: Dict[str, Any] = {"checked": int(time.time()), "kind": how, "error": ""}
    try:
        if how == "git":
            if _git("fetch", "--quiet", "origin") is None:
                raise OSError("git no pudo traer las novedades de origin.")
            behind = _git("rev-list", "--count", "HEAD..@{u}")
            if behind is None:
                raise OSError("La rama de aquí no sigue a ninguna de origin.")
            result.update(behind=int(behind or 0), latest="")
        else:
            result.update(latest=latest_tag(), behind=0)
    except Exception as e:  # red caída, GitHub con límite, git ausente…
        result["error"] = str(e) or e.__class__.__name__
    _save_state(result)
    return status()


def status() -> Dict[str, Any]:
    """Lo que la web enseña: versión instalada, si hay nueva y el ajuste «actualizar solo»."""
    state = load_state()
    how = state.get("kind") or kind()
    latest = state.get("latest") or ""
    behind = int(state.get("behind") or 0)
    if how == "git":
        available = behind > 0
    else:
        cur, new = _parse(__version__), _parse(latest) if latest else None
        available = bool(cur and new and new > cur)
    return {"current": __version__, "kind": how, "latest": latest, "behind": behind,
            "available": available, "auto": bool(state.get("auto")), "checked": int(state.get("checked") or 0),
            "error": state.get("error") or "", "applied": state.get("applied") or ""}


# ----------------------------------------------------------------------------- aplicar

class UpdateError(Exception):
    pass


def apply() -> str:
    """Instala la versión nueva. Devuelve qué se ha hecho; lanza ``UpdateError`` si no se pudo."""
    how = kind()
    if how == "git":
        # git pull se niega solo (sin tocar nada) si choca con cambios sin comitear: no hace falta exigir limpieza.
        before = _git("rev-parse", "--short", "HEAD")
        if _git("pull", "--ff-only", "--quiet", timeout=180) is None:
            raise UpdateError("git pull no pudo avanzar: hay commits aquí que no están en origin o cambios sin comitear que chocan.")
        after = _git("rev-parse", "--short", "HEAD")
        msg = "Ya estaba al día." if before == after else f"Actualizado de {before} a {after}."
    else:
        cmd = [sys.executable, "-m", "pip", "install", "-U", "--quiet", f"git+https://github.com/{REPO}"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as e:
            raise UpdateError(f"pip no se pudo lanzar: {e}")
        if r.returncode != 0:
            tail = (r.stderr or r.stdout).strip().splitlines()[-3:]
            raise UpdateError("pip falló: " + " ".join(tail))
        msg = "Instalada la última versión desde GitHub."
    _save_state({"applied": msg, "behind": 0, "checked": 0, "error": ""})
    return msg


# ----------------------------------------------------------------------------- proyectos

def refresh_all() -> Dict[str, List[str]]:
    """Pone al día ``uni.py``, reglas y hooks en todos los proyectos de la lista que usan Unificador."""
    from unificador import rules
    out: Dict[str, List[str]] = {}
    for item in projects.listing():
        root = Path(item["path"])
        if not (root / ".unificador").is_dir():
            continue
        try:
            changed = rules.install(root)
        except OSError as e:
            changed = [f"error: {e}"]
        if changed:
            out[str(root)] = changed
    return out


# ----------------------------------------------------------------------------- reiniciar

def spawn_restart(project_root: Path, delay: float = 0.8, pid: Optional[int] = None,
                  port: Optional[int] = None) -> None:
    """Lanza aparte ``unificador restart``: para este servidor y arranca el nuevo (que ya trae el código nuevo)."""
    env = dict(os.environ)
    pkg = str(package_dir())
    if (Path(pkg) / "unificador" / "__main__.py").is_file():
        env["PYTHONPATH"] = os.pathsep.join([p for p in [pkg, env.get("PYTHONPATH", "")] if p])
    kwargs: Dict[str, Any] = {"cwd": str(project_root), "env": env, "stdin": subprocess.DEVNULL,
                              "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                                   | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kwargs["start_new_session"] = True
    cmd = [sys.executable, "-m", "unificador", "restart", str(project_root), "--delay", str(delay)]
    if pid:
        cmd += ["--pid", str(pid)]
    if port:
        cmd += ["--port", str(port)]
    subprocess.Popen(cmd, **kwargs)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                               timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return str(pid) in r.stdout
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def restart(project_root: Path, delay: float = 0.0, pid: Optional[int] = None, port: Optional[int] = None) -> bool:
    """Para el servidor (el de ``server.json`` o el indicado) y lo vuelve a arrancar. ``True`` si responde al final."""
    from unificador import funnel
    if delay:
        time.sleep(delay)
    srv = funnel.load_server()
    port = int(port or srv.get("port") or 0)
    pid = pid or srv.get("pid")
    if isinstance(pid, int) and pid != os.getpid() and _pid_alive(pid):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
        except (OSError, subprocess.SubprocessError):
            pass
        deadline = time.time() + 10
        while time.time() < deadline and port and funnel.is_server_alive(port, timeout=0.2):
            time.sleep(0.2)
    if not port:
        return False
    return funnel.start_daemon(Path(project_root), port=port, python_exe=sys.executable, wait_seconds=8.0)


# ----------------------------------------------------------------------------- al arrancar

def on_start(project_root: Path, port: Optional[int] = None) -> None:
    """Hilo de fondo del servidor: pone al día los proyectos y, una vez al día, mira si hay versión nueva.

    Con «actualizar solo» encendido, la instala y se reinicia. Un fallo se apunta y no se reintenta hasta el día siguiente.
    """
    def run() -> None:
        try:
            refresh_all()
        except Exception:
            pass
        while True:
            try:
                st = check()
                if st["auto"] and st["available"] and not st["error"]:
                    try:
                        apply()
                        refresh_all()
                        spawn_restart(project_root, delay=0.5, pid=os.getpid(), port=port)
                        return
                    except UpdateError as e:
                        _save_state({"error": str(e), "checked": int(time.time())})
            except Exception:
                pass
            time.sleep(3600)

    threading.Thread(target=run, name="unificador-update", daemon=True).start()
