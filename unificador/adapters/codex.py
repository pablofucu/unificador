"""
Adaptador para OpenAI Codex / Cursor.

No hay modo de chat por línea de órdenes: el chat lo dice claramente y «Abrir» lleva al editor.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from typing import Iterator, Tuple
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter, Event


class CodexAdapter(BaseAgentAdapter):
    def __init__(self, cli_command: str = "cursor"):
        super().__init__(AgentType.CODEX, "Codex / Cursor")
        self.cli_command = cli_command

    def _editor(self) -> str:
        return shutil.which(self.cli_command) or shutil.which("code") or ""

    def is_installed(self) -> bool:
        return bool(self._editor())

    def stream_execute(self, context: ExecutionContext) -> Iterator[Event]:
        yield {"type": "error", "text": "Codex / Cursor no puede chatear desde Unificador. Usa «Abrir» para "
                                         "trabajar en el editor, o elige Claude Code, Antigravity o DeepSeek."}

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        editor = self._editor()
        if not editor:
            return False, "Ni Cursor ni VS Code se encuentran instalados en el sistema."
        try:
            subprocess.Popen([editor, str(context.project.path)], shell=(sys.platform == "win32"))
            return True, "Proyecto abierto en el editor."
        except Exception as e:
            return False, f"Error al abrir el editor: {e}"
