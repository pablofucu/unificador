"""
Servicio de integración simple con Git y GitHub.
Permite rastrear cambios, realizar commits estandarizados por fase y sincronizar ramas.
"""

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


class GitService:
    def __init__(self, project_path: str | Path):
        self.project_path = Path(project_path).resolve()

    def _run_git(self, args: List[str]) -> Tuple[int, str]:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False
            )
            return res.returncode, (res.stdout + "\n" + res.stderr).strip()
        except Exception as e:
            return 1, str(e)

    def is_git_repo(self) -> bool:
        code, out = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return code == 0 and "true" in out.lower()

    def get_current_branch(self) -> str:
        code, out = self._run_git(["branch", "--show-current"])
        return out.splitlines()[0].strip() if code == 0 and out else "main"

    def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado de Git en formato estructurado."""
        if not self.is_git_repo():
            return {"is_repo": False, "clean": True, "files": [], "branch": "none"}

        code, out = self._run_git(["status", "--porcelain"])
        files: List[Dict[str, str]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            status_code = line[:2]
            filename = line[3:].strip()
            files.append({"status": status_code, "file": filename})

        return {
            "is_repo": True,
            "branch": self.get_current_branch(),
            "clean": len(files) == 0,
            "files": files,
            "changed_count": len(files)
        }

    def commit_task(
        self,
        task_id: str,
        task_title: str,
        phase_name: Optional[str] = None,
        author: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Realiza un git add . y commit formateado con la fase y tarea."""
        if not self.is_git_repo():
            return False, "El directorio no es un repositorio Git válido."

        # Añadir archivos al stage
        add_code, add_out = self._run_git(["add", "."])
        if add_code != 0:
            return False, f"Error en git add: {add_out}"

        prefix = f"[{phase_name}] " if phase_name else ""
        commit_msg = f"{prefix}{task_id}: {task_title}"
        if author:
            commit_msg += f"\n\nRealizado por: {author}"

        commit_code, commit_out = self._run_git(["commit", "-m", commit_msg])
        if commit_code != 0:
            if "nothing to commit" in commit_out:
                return True, "No había cambios pendientes para realizar commit."
            return False, f"Error en git commit: {commit_out}"

        return True, f"Commit realizado con éxito: '{commit_msg.splitlines()[0]}'"

    def push(self, remote: str = "origin", branch: Optional[str] = None) -> Tuple[bool, str]:
        """Envía los commits al repositorio remoto (GitHub)."""
        if not self.is_git_repo():
            return False, "No es un repositorio Git."

        target_branch = branch or self.get_current_branch()
        code, out = self._run_git(["push", remote, target_branch])
        if code != 0:
            return False, f"Fallo en git push: {out}"
        return True, f"Cambios sincronizados con {remote}/{target_branch}."
