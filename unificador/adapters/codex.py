"""
Adaptador para OpenAI Codex / Cursor.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from typing import Generator, Tuple
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter


class CodexAdapter(BaseAgentAdapter):
    def __init__(self, cli_command: str = "cursor"):
        super().__init__(AgentType.CODEX, "Codex / Cursor")
        self.cli_command = cli_command

    def is_installed(self) -> bool:
        return shutil.which(self.cli_command) is not None or shutil.which("code") is not None

    def execute_sync(self, context: ExecutionContext) -> Tuple[int, str]:
        return 0, f"[Codex] Contexto inyectado preparado para el workspace:\n{context.final_injected_prompt[:300]}..."

    def stream_execute(self, context: ExecutionContext) -> Generator[str, None, None]:
        yield f"[Codex Adapter]: Sesión iniciada para proyecto {context.project.name}.\n"
        yield context.final_injected_prompt

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        editor = "cursor" if shutil.which("cursor") else "code"
        if not shutil.which(editor):
            return False, "Ni Cursor ni VS Code se encuentran instalados en el sistema."

        try:
            subprocess.Popen([editor, str(context.project.path)], shell=(sys.platform == "win32"))
            return True, f"Abierto workspace en {editor} con éxito."
        except Exception as e:
            return False, f"Error al abrir {editor}: {e}"
