"""
Traduce el tablero (fases y tareas) al itinerario que pinta el frontend:
Rama > Fase > Paso.

- Rama: cada grupo del tablero.
- Paso: cada tarea del grupo.
- Fase: tramo de pasos de una rama; un paso va en el tramo siguiente al de las
  tareas del mismo grupo de las que depende (tramo 1 si no depende de ninguna).
"""

from __future__ import annotations
from typing import Any, Dict, List

from unificador.models import Phase, Task, TaskState

# Estados del tablero -> estados del itinerario.
STEP_STATE = {
    TaskState.PROPOSED: "pend",
    TaskState.TODO: "pend",
    TaskState.DOING: "run",
    TaskState.REVIEW: "toca",
    TaskState.DONE: "hecho",
}


def _fase_state(steps: List[Dict[str, Any]]) -> str:
    states = {s["state"] for s in steps}
    if states == {"hecho"}:
        return "hecho"
    if "toca" in states:
        return "toca"
    if "run" in states:
        return "run"
    return "pend"


def _tramos(tasks: List[Task]) -> Dict[str, int]:
    """Número de tramo (desde 1) de cada tarea según sus dependencias dentro del grupo."""
    ids = {t.id for t in tasks}
    by_id = {t.id: t for t in tasks}
    memo: Dict[str, int] = {}

    def level(tid: str, seen: frozenset) -> int:
        if tid in memo:
            return memo[tid]
        if tid in seen:  # ciclo: se corta
            return 1
        deps = [d for d in by_id[tid].deps if d in ids]
        lv = 1 + max((level(d, seen | {tid}) for d in deps), default=0)
        memo[tid] = lv
        return lv

    return {t.id: level(t.id, frozenset()) for t in tasks}


def _step(task: Task, done_ids: set) -> Dict[str, Any]:
    last_note = ""
    if task.notes:
        n = task.notes[-1]
        last_note = n.get("text", "") if isinstance(n, dict) else str(n)
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "state": STEP_STATE[task.state],
        "board_state": task.state.value,
        "blocked": task.state == TaskState.TODO and any(d not in done_ids for d in task.deps),
        "last_note": last_note,
    }


def build_itinerary(phases: List[Phase], all_tasks: List[Task]) -> Dict[str, Any]:
    """Itinerario completo: ramas con fases y pasos, recuento y bloque final «Juntarlo todo»."""
    done_ids = {t.id for t in all_tasks if t.state == TaskState.DONE}
    ramas: List[Dict[str, Any]] = []

    for ph in phases:
        if not ph.tasks:
            continue
        tramo_of = _tramos(ph.tasks)
        fases: List[Dict[str, Any]] = []
        for n in sorted(set(tramo_of.values())):
            steps = [_step(t, done_ids) for t in ph.tasks if tramo_of[t.id] == n]
            fases.append({"name": f"Fase {n}", "state": _fase_state(steps), "steps": steps})
        ramas.append({"id": ph.id, "name": ph.name, "color": ph.color_tone, "fases": fases})

    steps = [s for r in ramas for f in r["fases"] for s in f["steps"]]
    counts = {
        "total": len(steps),
        "hecho": sum(s["state"] == "hecho" for s in steps),
        "run": sum(s["state"] == "run" for s in steps),
        "toca": sum(s["state"] == "toca" for s in steps),
    }
    join_state = "hecho" if steps and counts["hecho"] == counts["total"] else "pend"
    return {"ramas": ramas, "counts": counts, "join": {"name": "Juntarlo todo", "state": join_state}}
