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
            # rstrip y no strip: la primera columna de `status --porcelain` puede ser un espacio.
            parts = [x.rstrip() for x in (res.stdout, res.stderr) if x.strip()]
            return res.returncode, "\n".join(parts)
        except Exception as e:
            return 1, str(e)

    def is_git_repo(self) -> bool:
        code, out = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return code == 0 and "true" in out.lower()

    def init_repo(self) -> Tuple[bool, str]:
        """Crea el repositorio si no existe, con un primer commit para tener rama desde el principio."""
        if self.is_git_repo():
            return True, "Ya era un repositorio Git."
        code, out = self._run_git(["init", "-b", "main"])
        if code != 0:
            return False, out
        self._run_git(["add", "-A"])
        commit = ["commit", "-m", "Proyecto creado con Unificador", "--allow-empty"]
        code, out = self._run_git(commit)
        if code != 0:  # sin identidad de Git configurada: firma Unificador
            code, out = self._run_git(["-c", "user.name=Unificador", "-c", "user.email=unificador@localhost", *commit])
        return code == 0, out

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
            if len(line) < 4:  # el estado ocupa 2 columnas: no se puede usar strip()
                continue
            files.append({"status": line[:2].strip() or "?", "file": line[3:].strip().strip('"')})

        remote_code, remotes = self._run_git(["remote"])
        has_remote = remote_code == 0 and bool(remotes.strip())
        ahead = 0
        if has_remote:
            c, o = self._run_git(["rev-list", "--count", "@{u}..HEAD"])
            if c == 0 and o.strip().isdigit():
                ahead = int(o.strip())
            else:  # sin rama remota asociada: todo lo que haya está pendiente de subir
                c, o = self._run_git(["rev-list", "--count", "HEAD"])
                ahead = int(o.strip()) if c == 0 and o.strip().isdigit() else 0

        return {
            "is_repo": True,
            "branch": self.get_current_branch(),
            "clean": len(files) == 0,
            "files": files,
            "changed_count": len(files),
            "has_remote": has_remote,
            "ahead": ahead,
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
        code, out = self._run_git(["push", "-u", remote, target_branch])
        if code != 0:
            return False, f"Fallo en git push: {out}"
        return True, f"Cambios sincronizados con {remote}/{target_branch}."
