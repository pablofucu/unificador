"""
Adaptador para Google Antigravity.
Permite interactuar mediante la CLI 'agy' o disparar subagentes en el entorno local.
"""

from __future__ import annotations
import shutil
import subprocess
import sys
from typing import Generator, Tuple
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter


class AntigravityAdapter(BaseAgentAdapter):
    def __init__(self, cli_command: str = "agy"):
        super().__init__(AgentType.ANTIGRAVITY, "Google Antigravity")
        self.cli_command = cli_command

    def is_installed(self) -> bool:
        return shutil.which(self.cli_command) is not None or "ANTIGRAVITY" in sys.modules

    def execute_sync(self, context: ExecutionContext) -> Tuple[int, str]:
        if not self.is_installed():
            # Si se ejecuta dentro del propio IDE o CLI
            return 0, f"[Antigravity] Prompt inyectado listo para procesar en sesión actual:\n{context.final_injected_prompt}"

        try:
            proc = subprocess.run(
                [self.cli_command, "run", context.final_injected_prompt],
                cwd=str(context.project.path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False
            )
            return proc.returncode, (proc.stdout + "\n" + proc.stderr).strip()
        except Exception as e:
            return 1, f"Error al ejecutar Antigravity CLI: {e}"

    def stream_execute(self, context: ExecutionContext) -> Generator[str, None, None]:
        if not self.is_installed():
            yield "[Antigravity Adapter]: El entorno está activo. Enrutando instrucciones..."
            yield context.final_injected_prompt
            return

        try:
            proc = subprocess.Popen(
                [self.cli_command, "run", context.final_injected_prompt],
                cwd=str(context.project.path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                bufsize=1
            )
            if proc.stdout:
                for line in proc.stdout:
                    yield line
            proc.wait()
        except Exception as e:
            yield f"Fallo en stream de Antigravity: {e}"

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        # Si se abre en Windows
        if sys.platform == "win32":
            cmd = f'start agy "{context.project.path}"'
            try:
                subprocess.Popen(cmd, shell=True)
                return True, "Entorno de Antigravity activado para el proyecto."
            except Exception as e:
                return False, f"Error al lanzar Antigravity: {e}"
        return False, "Plataforma no soportada para lanzamiento nativo."
