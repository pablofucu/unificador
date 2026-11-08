"""
Clase base para adaptadores de agentes de Inteligencia Artificial.

``stream_execute`` emite eventos:

- ``str`` o ``{"type": "text", "text": ...}``: texto de la respuesta, conforme llega.
- ``{"type": "tool", "text": ...}``: aviso corto de lo que hace el agente (editar, ejecutar…).
- ``{"type": "session", "id": ...}``: id de la sesión nativa, para continuar la conversación.
- ``{"type": "error", "text": ...}``: fallo; es el último evento.
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple, Union
from unificador.models import AgentType, ExecutionContext

Event = Union[str, Dict[str, Any]]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def as_event(ev: Event) -> Dict[str, Any]:
    return {"type": "text", "text": ev} if isinstance(ev, str) else ev


def short(text: Any, n: int = 90) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[: n - 1] + "…"


class BaseAgentAdapter(ABC):
    def __init__(self, agent_type: AgentType, name: str):
        self.agent_type = agent_type
        self.name = name

    @abstractmethod
    def is_installed(self) -> bool:
        """Verifica si la herramienta o CLI está disponible en el sistema."""

    @abstractmethod
    def stream_execute(self, context: ExecutionContext) -> Iterator[Event]:
        """Ejecuta la orden emitiendo eventos (ver docstring del módulo)."""

    @abstractmethod
    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        """Abre la aplicación nativa con la sesión de la conversación."""

    def execute_sync(self, context: ExecutionContext) -> Tuple[int, str]:
        """Ejecuta y devuelve (código, texto). No lanza excepciones."""
        text, code = [], 0
        try:
            for ev in map(as_event, self.stream_execute(context)):
                if ev["type"] == "text":
                    text.append(ev["text"])
                elif ev["type"] == "error":
                    code = 1
                    text.append(("\n" if text else "") + ev["text"])
        except Exception as e:  # pragma: no cover - defensivo
            return 1, f"Fallo al ejecutar {self.name}: {e}"
        return code, "".join(text).strip()


def run_json_lines(cmd: List[str], cwd: str, parse: Callable[[Dict[str, Any]], Iterable[Event]],
                   stdin_text: Optional[str] = None, env_extra: Optional[Dict[str, str]] = None,
                   name: str = "agente") -> Iterator[Event]:
    """Lanza ``cmd`` y traduce cada línea JSON de su salida con ``parse``.

    Las líneas que no son JSON se emiten como texto. Si el proceso acaba mal sin haber
    dado un error propio, se emite un error con lo último que escribió.
    """
    env = {**os.environ, **(env_extra or {})}
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=NO_WINDOW,
        )
    except OSError as e:
        yield {"type": "error", "text": f"No se pudo ejecutar {name}: {e}"}
        return
    errored, tail = False, []
    try:
        if stdin_text is not None and proc.stdin:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        for line in proc.stdout or []:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                tail = (tail + [line])[-5:]
                continue
            if not isinstance(data, dict):
                continue
            for ev in parse(data):
                ev = as_event(ev)
                errored = errored or ev["type"] == "error"
                yield ev
        proc.wait()
        if proc.returncode and not errored:
            msg = "\n".join(tail) or f"terminó con código {proc.returncode}"
            yield {"type": "error", "text": f"{name}: {msg}"}
        elif tail and not errored and proc.returncode == 0:
            pass  # avisos sueltos de la CLI: no son parte de la respuesta
    finally:
        if proc.poll() is None:  # la persona paró el chat: no dejar el agente huérfano
            proc.kill()
