"""
Adaptador para Claude Code (CLI oficial de Anthropic).
Permite ejecución en streaming, modo no interactivo o lanzamiento de ventana interactiva.
"""

from __future__ import annotations
import shutil
import subprocess
import os
import sys
from typing import Generator, Tuple
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter


class ClaudeCodeAdapter(BaseAgentAdapter):
    def __init__(self, cli_command: str = "claude"):
        super().__init__(AgentType.CLAUDE_CODE, "Claude Code")
        self.cli_command = cli_command

    def is_installed(self) -> bool:
        return shutil.which(self.cli_command) is not None

    def execute_sync(self, context: ExecutionContext) -> Tuple[int, str]:
        if not self.is_installed():
            return 1, f"Error: La CLI '{self.cli_command}' no está instalada o no está en el PATH."

        try:
            # claude -p ejecuta el prompt y sale
            proc = subprocess.run(
                [self.cli_command, "-p", context.final_injected_prompt],
                cwd=str(context.project.path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False
            )
            output = (proc.stdout + "\n" + proc.stderr).strip()
            return proc.returncode, output
        except Exception as e:
            return 1, f"Fallo al ejecutar Claude Code: {e}"

    def stream_execute(self, context: ExecutionContext) -> Generator[str, None, None]:
        if not self.is_installed():
            yield f"Error: La CLI '{self.cli_command}' no está instalada o no se encuentra en el PATH."
            return

        try:
            proc = subprocess.Popen(
                [self.cli_command, "-p", context.final_injected_prompt],
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
            yield f"Excepción durante streaming con Claude Code: {e}"

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        """Abre Windows Terminal o PowerShell interactivo con Claude Code en el proyecto."""
        project_path = str(context.project.path)
        prompt_text = context.final_injected_prompt.replace('"', '\\"')

        # Si estamos en Windows, usar Windows Terminal (wt) o PowerShell
        if sys.platform == "win32":
            # Guarda el prompt temporalmente para no superar el límite de longitud de línea de comandos
            temp_prompt_file = os.path.join(project_path, ".unificador_prompt.tmp")
            try:
                with open(temp_prompt_file, "w", encoding="utf-8") as f:
                    f.write(context.final_injected_prompt)
            except Exception as e:
                return False, f"No se pudo guardar archivo temporal de prompt: {e}"

            # Comando para lanzar en Windows Terminal si existe, sino PowerShell estándar
            if shutil.which("wt"):
                cmd = f'wt -d "{project_path}" powershell -NoExit -Command "Get-Content .unificador_prompt.tmp | claude; Remove-Item .unificador_prompt.tmp -ErrorAction SilentlyContinue"'
            else:
                cmd = f'start powershell -NoExit -Command "Set-Location \'{project_path}\'; Get-Content .unificador_prompt.tmp | claude; Remove-Item .unificador_prompt.tmp -ErrorAction SilentlyContinue"'

            try:
                subprocess.Popen(cmd, shell=True)
                return True, "Ventana nativa de Claude Code iniciada con éxito."
            except Exception as e:
                return False, f"Error al abrir la ventana de Claude Code: {e}"
        else:
            # En macOS / Linux
            return False, "Lanzador de ventana nativa aún no configurado para este sistema operativo."
