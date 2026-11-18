"""
Seguridad y configuración del acceso remoto (Tailscale Funnel) para Unificador.

Guarda la clave de acceso cifrada (PBKDF2-HMAC-SHA256) y el secreto para firmar
cookies de sesión en ``~/.unificador/funnel.json`` (o ``UNIFICADOR_HOME``).
Solo usa la biblioteca estándar de Python.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from unificador import projects

CONFIG_FILE = "funnel.json"
SERVER_FILE = "server.json"
DEFAULT_FUNNEL_PORT = 443
ALLOWED_FUNNEL_PORTS = (443, 8443, 10000)
SESSION_COOKIE = "uni_session"
SESSION_TTL = 30 * 24 * 3600  # 30 días
PBKDF2_ITERATIONS = 200_000
MIN_KEY_LENGTH = 6
TS_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.ts\.net$", re.I)


class FunnelError(Exception):
    """Error comprensible al configurar o consultar Tailscale Funnel."""


def config_path() -> Path:
    return projects._home() / CONFIG_FILE


def default_config() -> Dict[str, Any]:
    return {
        "enabled": False,
        "funnel_port": DEFAULT_FUNNEL_PORT,
        "server_port": 8766,
        "public_url": "",
        "hide_paths": True,
        "salt": "",
        "key_hash": "",
        "cookie_secret": "",
    }


def load_config() -> Dict[str, Any]:
    """Lee la configuración de Funnel; si falta o está rota, devuelve valores seguros por defecto."""
    base = default_config()
    try:
        raw = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return base
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    out["enabled"] = bool(raw.get("enabled", False))
    port = raw.get("funnel_port", DEFAULT_FUNNEL_PORT)
    if isinstance(port, int) and not isinstance(port, bool) and port in ALLOWED_FUNNEL_PORTS:
        out["funnel_port"] = port
    srv = raw.get("server_port", 8766)
    if isinstance(srv, int) and not isinstance(srv, bool) and 1 <= srv <= 65535:
        out["server_port"] = srv
    if isinstance(raw.get("public_url"), str):
        out["public_url"] = raw["public_url"].strip()
    out["hide_paths"] = bool(raw.get("hide_paths", True))
    for k in ("salt", "key_hash", "cookie_secret"):
        if isinstance(raw.get(k), str):
            out[k] = raw[k].strip()
    return out


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Guarda ``funnel.json`` de forma atómica y con permisos restringidos (0600 en POSIX)."""
    target = config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    merged = {**default_config(), **cfg}
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return merged


def _hash_key(raw_key: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", raw_key.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex()


def generate_key() -> str:
    """Genera una clave aleatoria robusta."""
    return secrets.token_urlsafe(18)


def has_key(cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Indica si hay una clave válida y un secreto de sesión configurados."""
    data = load_config() if cfg is None else cfg
    return bool(data.get("salt") and data.get("key_hash") and data.get("cookie_secret"))


def set_key(raw_key: Optional[str] = None, *, rotate_sessions: bool = True) -> str:
    """Configura o sustituye la clave de acceso remoto y la guarda cifrada.

    Si ``raw_key`` es ``None``, genera una clave aleatoria.
    Devuelve la clave en claro (solo en este momento; en disco nunca se guarda en claro).
    """
    if raw_key is None:
        key = generate_key()
    else:
        if not isinstance(raw_key, str):
            raise ValueError("La clave tiene que ser texto.")
        key = raw_key.strip()
        if len(key) < MIN_KEY_LENGTH:
            raise ValueError(f"La clave debe tener al menos {MIN_KEY_LENGTH} caracteres.")
    cfg = load_config()
    salt = secrets.token_hex(16)
    cfg["salt"] = salt
    cfg["key_hash"] = _hash_key(key, salt)
    if rotate_sessions or not cfg.get("cookie_secret"):
        cfg["cookie_secret"] = secrets.token_hex(32)
    save_config(cfg)
    return key


def verify_key(raw_key: str, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Comprueba en tiempo constante si ``raw_key`` coincide con la clave guardada."""
    if not isinstance(raw_key, str):
        return False
    candidate = raw_key.strip()
    if not candidate:
        return False
    data = load_config() if cfg is None else cfg
    if not has_key(data):
        return False
    try:
        computed = _hash_key(candidate, data["salt"])
    except ValueError:
        return False
    return hmac.compare_digest(computed, data["key_hash"])


def reset_sessions() -> Dict[str, Any]:
    """Rota el secreto de firma de cookies; invalida al instante todas las sesiones activas."""
    cfg = load_config()
    cfg["cookie_secret"] = secrets.token_hex(32)
    return save_config(cfg)


def sign_session(cookie_secret: str, ttl: int = SESSION_TTL, now_ts: Optional[int] = None) -> str:
    """Emite un token de sesión firmado con HMAC-SHA256."""
    if not cookie_secret:
        raise ValueError("Falta el secreto de sesión.")
    now_i = int(time.time() if now_ts is None else now_ts)
    exp = now_i + max(1, int(ttl))
    nonce = secrets.token_hex(12)
    payload = f"{exp}.{nonce}"
    secret_bytes = bytes.fromhex(cookie_secret)
    sig = hmac.new(secret_bytes, payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_session(token: str, cookie_secret: str, now_ts: Optional[int] = None) -> bool:
    """Verifica firma y caducidad de un token de sesión en tiempo constante."""
    if not token or not cookie_secret or not isinstance(token, str):
        return False
    parts = token.strip().split(".")
    if len(parts) != 3:
        return False
    exp_s, nonce, sig = parts
    if not exp_s.isdigit() or not nonce or not sig:
        return False
    now_i = int(time.time() if now_ts is None else now_ts)
    if int(exp_s) <= now_i:
        return False
    try:
        secret_bytes = bytes.fromhex(cookie_secret)
    except ValueError:
        return False
    payload = f"{exp_s}.{nonce}"
    expected = hmac.new(secret_bytes, payload.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def parse_cookie(cookie_header: Optional[str], name: str = SESSION_COOKIE) -> str:
    """Extrae el valor de la cookie ``name`` de la cabecera HTTP ``Cookie``."""
    if not cookie_header:
        return ""
    for chunk in cookie_header.split(";"):
        k, sep, v = chunk.strip().partition("=")
        if sep and k.strip() == name:
            return v.strip().strip('"')
    return ""


def is_ts_host(host: str) -> bool:
    """Comprueba si ``host`` (sin puerto) corresponde a un dominio MagicDNS ``*.ts.net``."""
    return bool(host and TS_HOST_RE.match(host.strip().lower()))


class RateLimiter:
    """Limita intentos fallidos de acceso remoto por IP (protección frente a fuerza bruta)."""

    def __init__(self, max_failures: int = 5, window: int = 300, lock_seconds: int = 60, max_lock: int = 900):
        self.max_failures = max_failures
        self.window = window
        self.lock_seconds = lock_seconds
        self.max_lock = max_lock
        self._lock = threading.Lock()
        self._state: Dict[str, Dict[str, Any]] = {}

    def _prune(self, now_f: float) -> None:
        if len(self._state) <= 1000:
            return
        stale = [ip for ip, st in self._state.items()
                 if st.get("locked_until", 0.0) <= now_f
                 and all(now_f - t > self.window for t in st.get("fails", []))]
        for ip in stale:
            self._state.pop(ip, None)
        while len(self._state) > 1000:
            self._state.pop(next(iter(self._state)))

    def retry_after(self, ip: str, now_ts: Optional[float] = None) -> int:
        now_f = float(time.time() if now_ts is None else now_ts)
        key = (ip or "unknown").strip() or "unknown"
        with self._lock:
            st = self._state.get(key)
            if not st:
                return 0
            until = float(st.get("locked_until", 0.0))
            if until > now_f:
                return max(1, int(until - now_f + 0.999))
            return 0

    def record_failure(self, ip: str, now_ts: Optional[float] = None) -> int:
        now_f = float(time.time() if now_ts is None else now_ts)
        key = (ip or "unknown").strip() or "unknown"
        with self._lock:
            self._prune(now_f)
            st = self._state.setdefault(key, {"fails": [], "locked_until": 0.0, "strikes": 0})
            fails = [t for t in st["fails"] if now_f - t <= self.window]
            fails.append(now_f)
            st["fails"] = fails
            if len(fails) >= self.max_failures:
                st["strikes"] = int(st.get("strikes", 0)) + 1
                duration = min(self.max_lock, self.lock_seconds * (2 ** (st["strikes"] - 1)))
                st["locked_until"] = now_f + duration
                st["fails"] = []
                return int(duration)
            return 0

    def record_success(self, ip: str) -> None:
        key = (ip or "unknown").strip() or "unknown"
        with self._lock:
            self._state.pop(key, None)


# ----------------------------------------------------------------------------- Tailscale CLI

def tailscale_exe() -> str:
    """Ruta del ejecutable ``tailscale`` (PATH o carpetas habituales), o ``""`` si no está."""
    found = shutil.which("tailscale")
    if found:
        return found
    env = os.environ
    candidates: List[Path] = []
    if sys.platform == "win32":
        pf = Path(env.get("ProgramFiles") or "C:/Program Files")
        pfx = Path(env.get("ProgramFiles(x86)") or "C:/Program Files (x86)")
        local = Path(env.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        candidates = [pf / "Tailscale/tailscale.exe", pfx / "Tailscale/tailscale.exe",
                      local / "Tailscale/tailscale.exe"]
    elif sys.platform == "darwin":
        candidates = [Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale"),
                      Path("/usr/local/bin/tailscale"), Path("/opt/homebrew/bin/tailscale")]
    else:
        candidates = [Path("/usr/bin/tailscale"), Path("/usr/local/bin/tailscale")]
    return next((str(p) for p in candidates if p.is_file()), "")


def _run_ts(args: List[str], exe: Optional[str] = None, timeout: int = 15) -> subprocess.CompletedProcess:
    ts = exe or tailscale_exe()
    if not ts:
        raise FunnelError("No encuentro «tailscale». Instálalo e inicia sesión antes de activar Funnel.")
    try:
        return subprocess.run([ts, *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        raise FunnelError(f"No se pudo ejecutar tailscale: {e}")


def tailscale_dns_name(exe: Optional[str] = None) -> str:
    """Nombre MagicDNS de este equipo (p. ej. ``mi-pc.tail1234.ts.net``)."""
    run = _run_ts(["status", "--json"], exe=exe, timeout=10)
    if run.returncode != 0:
        msg = (run.stderr or run.stdout or "").strip()
        raise FunnelError(f"Tailscale no responde ({msg or 'sin conexión'}).")
    try:
        data = json.loads(run.stdout or "{}")
    except ValueError:
        raise FunnelError("Tailscale devolvió un estado ilegible.")
    state = data.get("BackendState") or ""
    if state and state != "Running":
        raise FunnelError(f"Tailscale no está conectado (estado: {state}). Inicia sesión en Tailscale primero.")
    dns = ((data.get("Self") or {}).get("DNSName") or "").strip().rstrip(".")
    if not dns:
        raise FunnelError("Este equipo no tiene MagicDNS activo en Tailscale (actívalo en el panel de Tailscale).")
    return dns


def tailscale_serve_status(exe: Optional[str] = None) -> Dict[str, Any]:
    """Configuración actual de ``tailscale serve/funnel status --json``."""
    run = _run_ts(["serve", "status", "--json"], exe=exe, timeout=10)
    if run.returncode != 0:
        return {}
    try:
        data = json.loads(run.stdout or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _port_busy(status_data: Dict[str, Any], port: int, local_port: int) -> bool:
    ours = {f"http://127.0.0.1:{local_port}", f"http://localhost:{local_port}"}
    suffix = f":{port}"
    web = status_data.get("Web") or {}
    if isinstance(web, dict):
        for host_port, cfg in web.items():
            if not str(host_port).endswith(suffix) or not isinstance(cfg, dict):
                continue
            handlers = cfg.get("Handlers") or {}
            if not isinstance(handlers, dict):
                return True
            for route_path, target in handlers.items():
                proxy = target.get("Proxy") if isinstance(target, dict) else ""
                if route_path != "/" or str(proxy).rstrip("/") not in ours:
                    return True
    tcp = status_data.get("TCP") or {}
    if isinstance(tcp, dict) and str(port) in tcp:
        entry = tcp[str(port)]
        if not isinstance(entry, dict) or not entry.get("HTTPS"):
            return True
    return False


def choose_funnel_port(requested: Optional[int], local_port: int, status_data: Dict[str, Any]) -> int:
    """Usa el puerto pedido o el primero libre entre 443, 8443 y 10000."""
    if requested is not None:
        if requested not in ALLOWED_FUNNEL_PORTS:
            raise FunnelError(f"Funnel solo admite los puertos {', '.join(map(str, ALLOWED_FUNNEL_PORTS))}.")
        return requested
    for port in ALLOWED_FUNNEL_PORTS:
        if not _port_busy(status_data, port, local_port):
            return port
    return DEFAULT_FUNNEL_PORT


def build_public_url(dns_name: str, funnel_port: int = DEFAULT_FUNNEL_PORT) -> str:
    dns = dns_name.strip().rstrip(".")
    return f"https://{dns}/" if funnel_port == 443 else f"https://{dns}:{funnel_port}/"


def configure_tailscale_funnel(local_port: int, funnel_port: Optional[int] = None,
                               exe: Optional[str] = None) -> Tuple[str, int]:
    """Activa ``tailscale funnel --bg`` apuntando a ``127.0.0.1:<local_port>``."""
    ts = exe or tailscale_exe()
    dns = tailscale_dns_name(ts)
    status = tailscale_serve_status(ts)
    port = choose_funnel_port(funnel_port, local_port, status)
    run = _run_ts(["funnel", "--bg", f"--https={port}", f"http://127.0.0.1:{local_port}"], exe=ts, timeout=20)
    if run.returncode != 0:
        msg = (run.stderr or run.stdout or "").strip()
        raise FunnelError(f"Tailscale no pudo activar Funnel en el puerto {port}: {msg}")
    return build_public_url(dns, port), port


def disable_tailscale_funnel(funnel_port: int, exe: Optional[str] = None) -> bool:
    """Desactiva ``tailscale funnel --https=<port> off``. Devuelve False si no está tailscale."""
    ts = exe or tailscale_exe()
    if not ts:
        return False
    run = _run_ts(["funnel", f"--https={funnel_port}", "off"], exe=ts, timeout=15)
    if run.returncode != 0:
        msg = (run.stderr or run.stdout or "").strip()
        if "no serve config" in msg.lower() or "does not exist" in msg.lower():
            return True
        raise FunnelError(f"No se pudo apagar Tailscale Funnel: {msg}")
    return True


# ----------------------------------------------------------------------------- servidor y autoarranque

def server_path() -> Path:
    return projects._home() / SERVER_FILE


def load_server() -> Dict[str, Any]:
    try:
        data = json.loads(server_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def home_port() -> int:
    """El puerto oficial del servidor de fondo: el de Funnel si está activado; si no, 8766.

    Es el único que se apunta en ``server.json``: un servidor de pruebas en otro puerto no lo pisa,
    y así el autoarranque, ``server.json`` y Funnel van siempre al mismo sitio.
    """
    cfg = load_config()
    if cfg.get("enabled"):
        try:
            return int(cfg.get("server_port") or 8766)
        except (TypeError, ValueError):
            return 8766
    return 8766


def save_server(info: Dict[str, Any]) -> Dict[str, Any]:
    target = server_path()
    projects._write_json(target, info)
    return info


def register_runtime(port: int, autostart: Optional[bool] = None, pid: Optional[int] = None) -> Dict[str, Any]:
    """Guarda qué Python y puerto usa Unificador en esta máquina para el autoarranque."""
    cur = load_server()
    pkg_dir = str(Path(__file__).resolve().parent.parent)
    info = {
        "python": sys.executable,
        "port": int(port),
        "autostart": bool(cur.get("autostart", False) if autostart is None else autostart),
        "pid": pid if pid is not None else cur.get("pid"),
        "updated": int(time.time()),
    }
    if (Path(pkg_dir) / "unificador" / "__main__.py").is_file():
        info["package_dir"] = pkg_dir
    elif cur.get("package_dir"):
        info["package_dir"] = cur["package_dir"]
    return save_server(info)


def clear_runtime_pid(pid: int) -> None:
    cur = load_server()
    if cur and cur.get("pid") == pid:
        cur["pid"] = None
        save_server(cur)


def is_server_alive(port: int, timeout: float = 0.25) -> bool:
    """Comprueba si Unificador responde localmente en ``127.0.0.1:<port>/api/health``."""
    conn: Optional[http.client.HTTPConnection] = None
    try:
        conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=timeout)
        conn.request("GET", "/api/health", headers={"Host": f"127.0.0.1:{int(port)}"})
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status == 200 and b'"ok"' in raw
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def _daemon_env(pkg_dir: Optional[str] = None) -> Dict[str, str]:
    env = dict(os.environ)
    candidate = pkg_dir or str(Path(__file__).resolve().parent.parent)
    if candidate and (Path(candidate) / "unificador" / "__main__.py").is_file():
        cur = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
        if candidate not in cur:
            cur.append(candidate)
            env["PYTHONPATH"] = os.pathsep.join(cur)
    return env


def start_daemon(project_root: Path, port: Optional[int] = None, python_exe: Optional[str] = None,
                 wait_seconds: float = 3.0) -> bool:
    """Arranca el servidor de Unificador en segundo plano si no estaba vivo."""
    srv = load_server()
    target_port = int(port or home_port())
    if is_server_alive(target_port):
        return True
    exe = python_exe or srv.get("python") or sys.executable
    if not exe:
        return False
    home = projects._home()
    home.mkdir(parents=True, exist_ok=True)
    lock = home / "server.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        try:
            if time.time() - lock.stat().st_mtime > 15:
                os.unlink(lock)
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
            else:
                deadline = time.time() + min(wait_seconds, 2.0)
                while time.time() < deadline:
                    if is_server_alive(target_port, timeout=0.15):
                        return True
                    time.sleep(0.08)
                return is_server_alive(target_port, timeout=0.15)
        except OSError:
            return is_server_alive(target_port, timeout=0.15)
    try:
        if is_server_alive(target_port):
            return True
        cmd = [str(exe), "-m", "unificador", str(Path(project_root).resolve()),
               "--port", str(target_port), "--no-open", "--daemon"]
        kwargs: Dict[str, Any] = {"cwd": str(Path(project_root).resolve()),
                                  "env": _daemon_env(srv.get("package_dir")),
                                  "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0)
                                       | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                                       | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            kwargs["start_new_session"] = True
        log_f = open(home / "server.log", "ab")
        try:
            kwargs["stderr"] = log_f
            proc = subprocess.Popen(cmd, **kwargs)
        finally:
            log_f.close()
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if is_server_alive(target_port, timeout=0.15):
                return True
            if proc.poll() is not None:
                return False
            time.sleep(0.08)
        return is_server_alive(target_port, timeout=0.15)
    except OSError:
        return False
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass

