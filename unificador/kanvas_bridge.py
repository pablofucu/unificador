"""
Puente de integración con Kanvas (kanvas.json y CLI).
Lee tareas, organiza fases por grupos/profundidad y ejecuta comandos de actualización.
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from unificador.models import Task, Phase, TaskState, AgentType


# Paleta armónica de fases (matices de color para cada etapa)
PHASE_TONES = [
    "#3b82f6",  # Fase 1: Azul primario
    "#06b6d4",  # Fase 2: Cian / Turquesa
    "#10b981",  # Fase 3: Esmeralda
    "#f59e0b",  # Fase 4: Ámbar cálido
    "#8b5cf6",  # Fase 5: Púrpura
    "#ec4899",  # Fase 6: Rosa vibrante
]


class KanvasBridge:
    def __init__(self, project_path: str | Path):
        self.project_path = Path(project_path).resolve()
        self.board_file = self.project_path / "kanvas.json"

    def board_exists(self) -> bool:
        return self.board_file.is_file()

    def load_raw_board(self) -> Dict[str, Any]:
        if not self.board_exists():
            return {"title": self.project_path.name, "groups": [], "tasks": []}
        try:
            with open(self.board_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[KanvasBridge] Error al leer {self.board_file}: {e}")
            return {"title": self.project_path.name, "groups": [], "tasks": []}

    def compute_chain_depths(self, tasks: List[Dict[str, Any]]) -> Dict[str, int]:
        """Calcula la profundidad topológica de cada tarea en el DAG."""
        deps_map: Dict[str, List[str]] = {t.get("id", ""): t.get("deps", []) for t in tasks}
        depths: Dict[str, int] = {}

        def get_depth(task_id: str, visited: set) -> int:
            if task_id in depths:
                return depths[task_id]
            if task_id in visited:
                return 0  # Prevenir ciclos
            visited.add(task_id)
            deps = deps_map.get(task_id, [])
            if not deps:
                depths[task_id] = 0
                return 0
            max_d = 0
            for d in deps:
                max_d = max(max_d, get_depth(d, visited) + 1)
            depths[task_id] = max_d
            return max_d

        for t in tasks:
            tid = t.get("id", "")
            if tid:
                get_depth(tid, set())

        return depths

    def get_phases_and_tasks(self) -> Tuple[List[Phase], List[Task]]:
        """Extrae las fases del proyecto agrupadas y coloreadas."""
        raw = self.load_raw_board()
        raw_tasks = raw.get("tasks", [])
        raw_groups = raw.get("groups", [])
        depths = self.compute_chain_depths(raw_tasks)

        all_tasks: List[Task] = []
        # Construir mapa de grupos por ID y Nombre
        group_map: Dict[str, str] = {}
        for g in raw_groups:
            if isinstance(g, dict):
                gid = g.get("id") or g.get("name")
                gname = g.get("name") or g.get("id")
                if gid and gname:
                    group_map[gid] = gname

        for rt in raw_tasks:
            tid = rt.get("id", "")
            state_str = rt.get("state", "proposed")
            try:
                state = TaskState(state_str)
            except ValueError:
                state = TaskState.PROPOSED

            raw_grp = rt.get("group", "")
            grp_name = group_map.get(raw_grp, raw_grp)

            task = Task(
                id=tid,
                title=rt.get("title", ""),
                description=rt.get("desc") or rt.get("description", ""),
                state=state,
                group=grp_name,
                deps=rt.get("deps", []) or [],
                notes=rt.get("notes", []) or [],
                depth=depths.get(tid, 0)
            )
            all_tasks.append(task)

        # Construir fases basadas en los grupos definidos
        phases: List[Phase] = []
        if raw_groups:
            for idx, g in enumerate(raw_groups):
                tone = PHASE_TONES[idx % len(PHASE_TONES)]
                gid = g.get("id") if isinstance(g, dict) else str(g)
                gname = g.get("name") if isinstance(g, dict) else str(g)
                prefix = g.get("id") or g.get("prefix", "") if isinstance(g, dict) else ""

                phase_tasks = [t for t in all_tasks if t.group == gname or t.group == gid]
                phase = Phase(
                    id=f"phase_{gid.lower() if gid else idx + 1}",
                    name=gname,
                    order=idx + 1,
                    color_tone=tone,
                    tasks=phase_tasks,
                    prefix=prefix
                )
                phases.append(phase)
        else:
            # Si no hay grupos, agrupar automáticamente por profundidad DAG (Nivel 0 = Fase 1, etc.)
            max_depth = max([t.depth for t in all_tasks], default=0)
            for d in range(max_depth + 1):
                tone = PHASE_TONES[d % len(PHASE_TONES)]
                phase_tasks = [t for t in all_tasks if t.depth == d]
                phase = Phase(
                    id=f"depth_{d}",
                    name=f"Fase {d + 1}",
                    order=d + 1,
                    color_tone=tone,
                    tasks=phase_tasks
                )
                phases.append(phase)

        return phases, all_tasks

    def get_task(self, task_id: str) -> Optional[Task]:
        _, tasks = self.get_phases_and_tasks()
        for t in tasks:
            if t.id == task_id:
                return t
        return None

    def execute_cli(self, args: List[str], stdin_text: Optional[str] = None) -> Tuple[int, str]:
        """Ejecuta un comando de la CLI oficial de Kanvas en el directorio del proyecto."""
        # Intenta usar 'kanvas' o el script local del proyecto
        local_script = self.project_path / ".agents" / "skills" / "kanvas" / "kanvas.py"
        cmd = ["kanvas"] + args
        if local_script.is_file():
            cmd = ["python", str(local_script)] + args

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                input=stdin_text,
                check=False
            )
            output = (res.stdout + "\n" + res.stderr).strip()
            return res.returncode, output
        except Exception as e:
            return 1, str(e)

    def add_note(self, task_id: str, note_text: str, author: str = "agent") -> Tuple[int, str]:
        return self.execute_cli(["--as", author, "note", task_id, "--stdin"], stdin_text=note_text)

    def start_task(self, task_id: str, author: str = "agent") -> Tuple[int, str]:
        return self.execute_cli(["--as", author, "start", task_id])

    def finish_task(self, task_id: str, summary: str, author: str = "agent") -> Tuple[int, str]:
        return self.execute_cli(["--as", author, "finish", task_id, "--stdin"], stdin_text=summary)

    # ── Decisiones de la persona (la CLI de Kanvas no las ofrece a los agentes) ──
    def _board_module(self):
        """Carga el kanvas.py del proyecto para escribir con su mismo bloqueo y formato."""
        import importlib.util
        script = self.project_path / ".agents" / "skills" / "kanvas" / "kanvas.py"
        if not script.is_file() or not self.board_exists():
            raise FileNotFoundError("Este proyecto no tiene tablero que se pueda modificar")
        spec = importlib.util.spec_from_file_location(f"_kanvas_{abs(hash(str(script)))}", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def review_task(self, task_id: str, accept: bool, comment: str = "", author: str = "usuario") -> str:
        """Acepta (review -> done) o devuelve (review -> doing) un paso. Devuelve el estado nuevo.

        Lanza KeyError si no existe el paso, ValueError si no está pendiente de revisión.
        """
        mod = self._board_module()

        def apply(board):
            task = next((t for t in board["tasks"] if t["id"].upper() == task_id.upper()), None)
            if task is None:
                raise KeyError(task_id)
            if task.get("state") != "review":
                raise ValueError("Este paso no está esperando tu revisión")
            task["state"] = "done" if accept else "doing"
            text = comment.strip() or ("Aceptado." if accept else "Hay que cambiar algo.")
            task.setdefault("notes", []).append({"at": mod.now_iso(), "by": author, "text": text})
            return task["state"]

        return mod.mutate(str(self.board_file), apply)


    def approve_tasks(self, task_ids: Optional[List[str]] = None, author: str = "usuario") -> List[str]:
        """Aprueba propuestas (proposed -> todo): las indicadas o, sin lista, todas. Devuelve sus ids.

        Es la decisión de la persona sobre el plan; la toma desde Unificador con «Aprobar plan».
        """
        mod = self._board_module()
        wanted = {t.upper() for t in task_ids} if task_ids else None

        def apply(board):
            approved = []
            for task in board["tasks"]:
                if task.get("state") != "proposed":
                    continue
                if wanted is not None and task["id"].upper() not in wanted:
                    continue
                task["state"] = "todo"
                task.setdefault("notes", []).append({"at": mod.now_iso(), "by": author, "text": "Plan aprobado."})
                approved.append(task["id"])
            return approved

        return mod.mutate(str(self.board_file), apply)

    @staticmethod
    def init_project(project_path: str | Path) -> Tuple[int, str]:
        """Instala Kanvas en un proyecto (skill, kanvas.json, AGENTS.md) con el kanvas.py de Unificador."""
        script = Path(__file__).resolve().parent.parent / ".agents" / "skills" / "kanvas" / "kanvas.py"
        if not script.is_file():
            return 1, f"No se encuentra {script}"
        try:
            proc = subprocess.run([sys.executable, str(script), "init", str(project_path)],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=60, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, str(e)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
