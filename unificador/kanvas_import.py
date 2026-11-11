"""
Convierte un tablero Kanvas (``kanvas.json``) al plan de Unificador (``unificador.json``).

- Cada grupo pasa a ser una rama (se quita el prefijo «Fase N:» del nombre).
- Las fases salen de las dependencias dentro del grupo; su nombre se toma del primer paso.
- done y review → hecho; doing → en curso; el resto → pendiente. Las tareas retiradas no se copian.
- Los pasos conservan su identificador (PS-02 sigue siendo PS-02) y sus notas.
- Las ramas que ya estaban terminadas entran archivadas, para que no ocupen sitio.

No borra ni toca ``kanvas.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from unificador import plan as P

KANVAS_FILE = "kanvas.json"
STATE_MAP = {"done": P.DONE, "review": P.DONE, "doing": P.DOING}
SKIP = {"withdrawn", "rejected", "cancelled", "canceled"}
ORDER_PREFIX = re.compile(r"^\s*(fase|etapa|phase|sprint)\s*\d+\s*[:.\-–—]\s*", re.I)
ICONS = ("🧩", "🚀", "🎨", "🔧", "📦", "🧪", "💬", "🧹")


def _phase_name(steps: List[dict], used: set) -> str:
    first = " ".join(str(steps[0]["title"]).split()).rstrip(".")
    room = P.MAX_NAME - (9 if len(steps) > 1 else 0)
    name = first if len(first) <= room else first[: room - 1].rstrip() + "…"
    if len(steps) > 1:
        name += f" y {len(steps) - 1} más"
    if P.GENERIC_PHASE.match(name):
        name = f"Trabajo: {name}"
    base, n = name, 2
    while name.lower() in used:
        name, n = f"{base} ({n})", n + 1
    used.add(name.lower())
    return name


def _depth(task_id: str, deps: Dict[str, List[str]], seen: tuple = ()) -> int:
    if task_id in seen:  # ciclo: no debería haberlo, pero no nos colgamos por él
        return 0
    return 1 + max((_depth(d, deps, seen + (task_id,)) for d in deps.get(task_id, [])), default=-1)


def convert(board: Dict[str, Any], by: str = "importado de Kanvas") -> Dict[str, Any]:
    if not isinstance(board, dict) or not isinstance(board.get("tasks"), list):
        raise P.PlanError("Eso no parece un tablero Kanvas (falta la lista «tasks»).")
    plan = P.empty_plan(str(board.get("title") or ""))
    tasks = [t for t in board["tasks"] if isinstance(t, dict) and t.get("id")
             and str(t.get("state")) not in SKIP]
    groups = [g for g in board.get("groups") or [] if isinstance(g, dict) and g.get("id")]
    known = {g["id"] for g in groups}
    groups += [{"id": gid, "name": gid} for gid in dict.fromkeys(
        str(t.get("group") or "OTROS") for t in tasks) if gid not in known]
    names: set = set()
    live = 0
    for g in groups:
        mine = [t for t in tasks if str(t.get("group") or "OTROS") == g["id"]]
        if not mine:
            continue
        ids = {t["id"] for t in mine}
        deps = {t["id"]: [d for d in t.get("deps") or [] if d in ids] for t in mine}
        levels: Dict[int, List[dict]] = {}
        for t in mine:
            levels.setdefault(_depth(t["id"], deps), []).append(t)
        name = ORDER_PREFIX.sub("", str(g.get("name") or g["id"])).strip()[: P.MAX_NAME] or g["id"]
        base, n = name, 2
        while name.lower() in names:
            name, n = f"{base} ({n})", n + 1
        names.add(name.lower())
        numbers = [int(m.group(1)) for t in mine if (m := re.search(r"(\d+)$", t["id"]))]
        branch = {"key": str(g["id"]).upper(), "name": name, "goal": "", "icon": "", "color": 0,
                  "created": min((str(t.get("at") or "") for t in mine), default="") or P.now(),
                  "by": by, "next_id": max(numbers, default=len(mine)) + 1, "phases": []}
        used: set = set()
        for level in sorted(levels):
            steps = []
            for t in levels[level]:
                state = STATE_MAP.get(str(t.get("state")), P.PENDING)
                notes = [{"at": str(x.get("at") or ""), "by": str(x.get("by") or "?"), "kind": "note",
                          "text": str(x.get("text") or "")}
                         for x in t.get("notes") or [] if isinstance(x, dict) and x.get("text")]
                step = {"id": str(t["id"]), "title": str(t.get("title") or t["id"]),
                        "desc": str(t.get("desc") or ""), "state": state, "notes": notes}
                if str(t.get("state")) == "proposed":
                    step["notes"].append({"at": P.now(), "by": by, "kind": "note",
                                          "text": "En Kanvas era una propuesta sin aprobar."})
                if state == P.DONE and notes:
                    step["result"] = next((x["text"] for x in reversed(notes)
                                           if "delegado" not in x["by"] and x["text"] != "Plan aprobado."),
                                          notes[-1]["text"])
                steps.append(step)
            branch["phases"].append({"name": _phase_name(steps, used), "icon": "", "steps": steps})
        done, total = P.branch_progress(branch)
        if done == total:
            branch["archived"] = True
        else:
            branch["color"] = live % P.COLORS
            live += 1
        branch["icon"] = ICONS[len(plan["branches"]) % len(ICONS)]
        plan["branches"].append(branch)
    return plan


def import_board(project: str | Path, force: bool = False) -> Dict[str, Any]:
    """Lee ``kanvas.json`` del proyecto y escribe ``unificador.json``. Devuelve el plan creado."""
    root = Path(project)
    source, target = root / KANVAS_FILE, root / P.PLAN_FILE
    if not source.is_file():
        raise P.PlanError(f"No hay {KANVAS_FILE} en {root}.")
    if target.is_file() and P.load(target).get("branches") and not force:
        raise P.PlanError(f"Ya hay un plan en {target}. Usa --force para sustituirlo.")
    try:
        board = json.loads(source.read_text(encoding="utf-8"))
    except ValueError as e:
        raise P.PlanError(f"{source} no es JSON válido: {e}")
    plan = convert(board)
    P.save(target, plan)
    return plan
