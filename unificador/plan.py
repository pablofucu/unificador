#!/usr/bin/env python3
"""
uni: el plan de un proyecto en ramas → fases → pasos.

Un solo fichero, ``unificador.json``, en la raíz del proyecto:

- **Rama**: un cambio con sentido propio («Carrito de compra», «Arreglar el login»).
- **Fase**: una etapa de esa rama, con un nombre que se reconozca («Cimientos», «Pagos»).
- **Paso**: una tarea pequeña y comprobable. Tres estados: pendiente, en curso, hecho.

Este módulo no depende de nada más que de la biblioteca estándar: Unificador lo copia en cada
proyecto como ``.unificador/uni.py`` para que cualquier agente lo use desde la terminal.

    python .unificador/uni.py status
    python .unificador/uni.py plan < plan.json
    python .unificador/uni.py start CA-2
    python .unificador/uni.py done CA-2 -m "Qué ha cambiado y cómo se comprueba"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

VERSION = 1
PLAN_FILE = "unificador.json"
PENDING, DOING, DONE = "pending", "doing", "done"
STATES = (PENDING, DOING, DONE)
STATE_NAMES = {PENDING: "pendiente", DOING: "en curso", DONE: "hecho"}
MARKS = {PENDING: "·", DOING: "▶", DONE: "✔"}
COLORS = 8  # la interfaz tiene una paleta de 8 colores; cada rama guarda su índice
GENERIC_PHASE = re.compile(r"^\s*(fase|etapa|paso|parte|phase|step|stage|sprint)?\s*[\d\W]*\s*$", re.I)
MAX_NAME = 60


class PlanError(Exception):
    """Algo que la persona o el agente puede corregir; el mensaje se muestra tal cual."""


# ── Fichero ──────────────────────────────────────────────────────────────────

def find_plan(start: Optional[Path] = None) -> Path:
    """El ``unificador.json`` más cercano hacia arriba; si no hay, el de la carpeta actual."""
    here = Path(start or os.getcwd()).resolve()
    for folder in (here, *here.parents):
        if (folder / PLAN_FILE).is_file():
            return folder / PLAN_FILE
    return here / PLAN_FILE


def empty_plan(title: str = "") -> Dict[str, Any]:
    return {"version": VERSION, "title": title, "branches": []}


def load(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return empty_plan(path.parent.name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise PlanError(f"{path.name} no es JSON válido ({e}). Corrígelo o bórralo para empezar de cero.")
    if not isinstance(data, dict) or not isinstance(data.get("branches", []), list):
        raise PlanError(f"{path.name} no tiene el formato de un plan de Unificador.")
    data.setdefault("version", VERSION)
    data.setdefault("title", path.parent.name)
    data.setdefault("branches", [])
    return data


def save(path: Path, plan: Dict[str, Any]) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def mutate(path: Path, change: Callable[[Dict[str, Any]], Any]) -> Any:
    """Lee, aplica ``change`` y guarda, sin pisarse con otro proceso que haga lo mismo."""
    path = Path(path)
    lock = path.with_name(path.name + ".lock")
    deadline = time.time() + 5
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime > 10
            except OSError:
                stale = False
            if stale or time.time() > deadline:
                try:
                    os.unlink(lock)
                except OSError:
                    pass
            time.sleep(0.05)
    try:
        plan = load(path)
        result = change(plan)
        save(path, plan)
        return result
    finally:
        try:
            os.unlink(lock)
        except OSError:
            pass


# ── Consultas ────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def iter_steps(plan: Dict[str, Any], archived: bool = False) -> Iterator[Tuple[dict, dict, dict]]:
    for branch in plan.get("branches", []):
        if branch.get("archived") and not archived:
            continue
        for phase in branch.get("phases", []):
            for step in phase.get("steps", []):
                yield branch, phase, step


def find_step(plan: Dict[str, Any], step_id: str) -> Tuple[dict, dict, dict]:
    wanted = step_id.strip().upper()
    for branch, phase, step in iter_steps(plan, archived=True):
        if step["id"].upper() == wanted:
            return branch, phase, step
    known = ", ".join(s["id"] for _, _, s in iter_steps(plan)) or "ninguno todavía"
    raise PlanError(f"No existe el paso {step_id}. Pasos del plan: {known}.")


def find_branch(plan: Dict[str, Any], ref: str) -> dict:
    wanted = ref.strip().lower()
    for branch in plan.get("branches", []):
        if wanted in (branch["key"].lower(), branch["name"].lower()):
            return branch
    known = ", ".join(f"{b['key']} ({b['name']})" for b in plan.get("branches", [])) or "ninguna todavía"
    raise PlanError(f"No existe la rama «{ref}». Ramas del plan: {known}.")


def phase_state(phase: dict) -> str:
    states = [s["state"] for s in phase.get("steps", [])]
    if states and all(s == DONE for s in states):
        return DONE
    return DOING if any(s != PENDING for s in states) else PENDING


def branch_progress(branch: dict) -> Tuple[int, int]:
    steps = [s for p in branch.get("phases", []) for s in p.get("steps", [])]
    return sum(1 for s in steps if s["state"] == DONE), len(steps)


def next_step(branch: dict) -> Optional[dict]:
    """El primer paso sin hacer de la primera fase incompleta: las fases van en orden."""
    for phase in branch.get("phases", []):
        for step in phase.get("steps", []):
            if step["state"] != DONE:
                return step
    return None


# ── Cambios ──────────────────────────────────────────────────────────────────

def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _new_key(name: str, used: set) -> str:
    words = re.findall(r"[^\W\d_]+", name, re.UNICODE)
    base = "".join(w[0] for w in words[:3]) if len(words) > 1 else (words[0][:2] if words else "R")
    base = (base.upper() or "R")[:3]
    key, n = base, 2
    while key in used:
        key, n = f"{base}{n}", n + 1
    return key


def _note(step: dict, by: str, text: str, kind: str = "note") -> None:
    step.setdefault("notes", []).append({"at": now(), "by": by, "kind": kind, "text": text.strip()})


def check_branches(plan: Dict[str, Any], data: Any) -> List[dict]:
    """Valida lo que propone el agente y lo devuelve normalizado. Todo o nada."""
    if isinstance(data, dict) and "branches" not in data and "phases" in data:
        data = {"branches": [data]}
    if not isinstance(data, dict) or not isinstance(data.get("branches"), list) or not data["branches"]:
        raise PlanError('El plan debe ser {"branches": [{"name": …, "phases": [{"name": …, "steps": [{"title": …}]}]}]}.')
    errors: List[str] = []
    names = {b["name"].lower() for b in plan.get("branches", []) if not b.get("archived")}
    out: List[dict] = []
    for bi, b in enumerate(data["branches"], 1):
        where = f"Rama {bi}"
        if not isinstance(b, dict):
            errors.append(f"{where}: debe ser un objeto.")
            continue
        name = _clean(b.get("name"))
        if not name:
            errors.append(f"{where}: falta «name».")
        elif len(name) > MAX_NAME:
            errors.append(f"{where}: el nombre pasa de {MAX_NAME} caracteres; ponle uno corto.")
        elif name.lower() in names:
            errors.append(f"{where}: ya hay una rama «{name}». Añade pasos con `add` o usa otro nombre.")
        names.add(name.lower())
        where = f"Rama «{name}»" if name else where
        phases = b.get("phases")
        if not isinstance(phases, list) or not phases:
            errors.append(f"{where}: necesita al menos una fase en «phases».")
            continue
        seen, clean_phases = set(), []
        for pi, p in enumerate(phases, 1):
            pname = _clean(p.get("name")) if isinstance(p, dict) else ""
            pwhere = f"{where}, fase {pi}"
            if not pname:
                errors.append(f"{pwhere}: falta «name».")
            elif GENERIC_PHASE.match(pname):
                errors.append(f"{pwhere}: «{pname}» no dice nada. Ponle un nombre que se reconozca "
                              "(p. ej. «Cimientos», «Pagos», «Pulido»).")
            elif len(pname) > MAX_NAME:
                errors.append(f"{pwhere}: el nombre pasa de {MAX_NAME} caracteres.")
            elif pname.lower() in seen:
                errors.append(f"{pwhere}: el nombre «{pname}» está repetido en la rama.")
            seen.add(pname.lower())
            steps = p.get("steps") if isinstance(p, dict) else None
            if not isinstance(steps, list) or not steps:
                errors.append(f"{pwhere}: necesita al menos un paso en «steps».")
                continue
            clean_steps = []
            for si, s in enumerate(steps, 1):
                if isinstance(s, str):
                    s = {"title": s}
                title = _clean(s.get("title")) if isinstance(s, dict) else ""
                if not title:
                    errors.append(f"{pwhere}, paso {si}: falta «title».")
                    continue
                clean_steps.append({"title": title, "desc": str(s.get("desc") or "").strip()})
            clean_phases.append({"name": pname, "icon": _clean(p.get("icon"))[:4] if isinstance(p, dict) else "",
                                 "steps": clean_steps})
        out.append({"name": name, "goal": str(b.get("goal") or "").strip(),
                    "icon": _clean(b.get("icon"))[:4], "phases": clean_phases})
    if errors:
        raise PlanError("El plan no se ha guardado:\n- " + "\n- ".join(errors))
    return out


def add_branches(plan: Dict[str, Any], data: Any, by: str = "ia") -> List[dict]:
    """Añade ramas nuevas al plan. Devuelve las ramas creadas."""
    new = check_branches(plan, data)
    used = {b["key"] for b in plan["branches"]}
    created = []
    for b in new:
        key = _new_key(b["name"], used)
        used.add(key)
        colors = [x.get("color", 0) for x in plan["branches"] if not x.get("archived")]
        color = next((c for c in range(COLORS) if c not in colors), len(plan["branches"]) % COLORS)
        branch = {"key": key, "name": b["name"], "goal": b["goal"], "icon": b["icon"], "color": color,
                  "created": now(), "by": by, "next_id": 1, "phases": []}
        for p in b["phases"]:
            phase = {"name": p["name"], "icon": p["icon"], "steps": []}
            for s in p["steps"]:
                phase["steps"].append(_new_step(branch, s["title"], s["desc"]))
            branch["phases"].append(phase)
        plan["branches"].append(branch)
        created.append(branch)
    return created


def _new_step(branch: dict, title: str, desc: str = "") -> dict:
    n = branch.get("next_id", 1)
    branch["next_id"] = n + 1
    return {"id": f"{branch['key']}-{n}", "title": title, "desc": desc, "state": PENDING, "notes": []}


def add_step(plan: Dict[str, Any], branch_ref: str, phase_name: str, title: str, desc: str = "",
             by: str = "ia") -> dict:
    """Añade un paso a una fase de una rama; si la fase no existe, la crea al final."""
    branch = find_branch(plan, branch_ref)
    phase_name, title = _clean(phase_name), _clean(title)
    if not title:
        raise PlanError("El paso necesita un título.")
    phase = next((p for p in branch["phases"] if p["name"].lower() == phase_name.lower()), None)
    if phase is None:
        if GENERIC_PHASE.match(phase_name):
            raise PlanError(f"«{phase_name}» no dice nada como nombre de fase. Usa uno que se reconozca.")
        phase = {"name": phase_name, "icon": "", "steps": []}
        branch["phases"].append(phase)
    step = _new_step(branch, title, desc.strip())
    step["by"] = by
    phase["steps"].append(step)
    branch.pop("archived", None)
    return step


def set_state(plan: Dict[str, Any], step_id: str, state: str, by: str = "ia", text: str = "") -> dict:
    if state not in STATES:
        raise PlanError(f"Estado desconocido: {state}. Usa pending, doing o done.")
    branch, _, step = find_step(plan, step_id)
    text = (text or "").strip()
    if state == DONE:
        step["result"] = text or step.get("result", "")
        step.pop("change", None)
        _note(step, by, text or "Hecho.", "done")
    elif state == DOING:
        _note(step, by, text or "Empezado.", "start")
        branch.pop("archived", None)
    else:
        _note(step, by, text or "Vuelve a pendiente.", "reopen")
        branch.pop("archived", None)
    step["state"] = state
    step["updated"] = now()
    return step


def add_note(plan: Dict[str, Any], step_id: str, text: str, by: str = "ia") -> dict:
    if not (text or "").strip():
        raise PlanError("La nota está vacía.")
    _, _, step = find_step(plan, step_id)
    _note(step, by, text)
    step["updated"] = now()
    return step


def request_change(plan: Dict[str, Any], step_id: str, text: str, by: str = "persona") -> dict:
    """La persona pide un cambio en un paso: vuelve a pendiente y queda marcado hasta que se rehaga."""
    if not (text or "").strip():
        raise PlanError("Escribe qué hay que cambiar.")
    branch, _, step = find_step(plan, step_id)
    step["state"] = PENDING
    step["change"] = text.strip()
    step["updated"] = now()
    branch.pop("archived", None)
    _note(step, by, text, "change")
    return step


def archive_branch(plan: Dict[str, Any], ref: str, force: bool = False) -> dict:
    branch = find_branch(plan, ref)
    done, total = branch_progress(branch)
    if done < total and not force:
        raise PlanError(f"A la rama «{branch['name']}» le quedan {total - done} pasos. Usa --force para archivarla igual.")
    branch["archived"] = True
    return branch


def drop_branch(plan: Dict[str, Any], ref: str) -> dict:
    branch = find_branch(plan, ref)
    plan["branches"].remove(branch)
    return branch


# ── Texto para la terminal ───────────────────────────────────────────────────

def render_status(plan: Dict[str, Any]) -> str:
    branches = [b for b in plan.get("branches", []) if not b.get("archived")]
    if not branches:
        return (f"{plan.get('title') or 'Proyecto'}: el plan está vacío.\n"
                "Cuando haya trabajo que hacer, crea una rama con `plan` (mira las reglas en AGENTS.md).")
    done = sum(branch_progress(b)[0] for b in branches)
    total = sum(branch_progress(b)[1] for b in branches)
    lines = [f"{plan.get('title') or 'Proyecto'}: {done}/{total} pasos hechos en {len(branches)} "
             f"rama{'s' if len(branches) != 1 else ''}"]
    changes = [(b, s) for b, _, s in iter_steps(plan) if s.get("change")]
    if changes:
        lines.append("\n⚠ LA PERSONA PIDE CAMBIOS (hazlos antes que nada):")
        lines += [f"  {s['id']}  {s['title']}: {s['change']}" for _, s in changes]
    for b in branches:
        d, t = branch_progress(b)
        lines.append(f"\n{b.get('icon') or '●'} {b['name']} [{b['key']}]  {d}/{t}")
        current = next((p for p in b["phases"] if phase_state(p) != DONE), None)
        for p in b["phases"]:
            st = phase_state(p)
            if p is current or st == DOING:
                lines.append(f"  {MARKS[DOING]} {p['name']}")
                lines += [f"      {MARKS[s['state']]} {s['id']}  {s['title']}"
                          + ("  (en curso)" if s["state"] == DOING else "") for s in p["steps"]]
            else:
                n = len(p["steps"])
                lines.append(f"  {MARKS[st]} {p['name']}  ({n} paso{'s' if n != 1 else ''})")
    doing = [s for _, _, s in iter_steps(plan) if s["state"] == DOING]
    nxt = [n for n in (next_step(b) for b in branches) if n and n["state"] == PENDING]
    if doing:
        lines.append("\nEn curso: " + "; ".join(f"{s['id']} {s['title']}" for s in doing))
    if nxt:
        lines.append("Siguiente: " + "; ".join(f"{s['id']} {s['title']}" for s in nxt))
    if not doing and not nxt:
        lines.append("\nTodo lo planificado está hecho.")
    return "\n".join(lines)


def render_step(plan: Dict[str, Any], step_id: str) -> str:
    branch, phase, step = find_step(plan, step_id)
    lines = [f"{step['id']}  {step['title']}  [{STATE_NAMES[step['state']]}]",
             f"Rama: {branch['name']} · Fase: {phase['name']}"]
    if step.get("desc"):
        lines.append(f"\n{step['desc']}")
    if step.get("change"):
        lines.append(f"\n⚠ Cambio pedido por la persona: {step['change']}")
    if step.get("notes"):
        lines.append("\nNotas:")
        lines += [f"  [{n.get('at', '')[:16].replace('T', ' ')} {n.get('by', '')}] {n.get('text', '')}"
                  for n in step["notes"][-8:]]
    return "\n".join(lines)


# ── Línea de órdenes ─────────────────────────────────────────────────────────

EXAMPLE = """ejemplo de plan (por la entrada estándar o con --file):

  python .unificador/uni.py plan <<'EOF'
  {"branches": [{
     "name": "Carrito de compra", "icon": "🛒", "goal": "Que se pueda comprar desde la web",
     "phases": [
       {"name": "Cimientos", "steps": [{"title": "Modelo del carrito", "desc": "Hecho cuando…"}]},
       {"name": "Pagos",     "steps": [{"title": "Pasarela de pago"}, {"title": "Recibo por correo"}]}
     ]}]}
  EOF
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uni", description="El plan del proyecto en ramas → fases → pasos.",
                                epilog=EXAMPLE, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-f", "--plan-file", metavar="RUTA", help=f"fichero del plan (por defecto, el {PLAN_FILE} más cercano)")
    p.add_argument("--as", dest="by", metavar="NOMBRE", help="quién firma (por defecto $UNI_AGENT o «ia»)")
    sub = p.add_subparsers(dest="cmd", metavar="<orden>")
    sub.add_parser("status", help="cómo va el plan (orden por defecto)")
    s = sub.add_parser("show", help="un paso con su descripción y sus notas")
    s.add_argument("id")
    s = sub.add_parser("plan", help="crea ramas nuevas desde JSON (entrada estándar o --file)")
    s.add_argument("--file", help="fichero JSON con el plan")
    s = sub.add_parser("add", help="añade un paso a una fase de una rama (crea la fase si no existe)")
    s.add_argument("branch", help="clave o nombre de la rama")
    s.add_argument("phase", help="nombre de la fase")
    s.add_argument("title")
    s.add_argument("-d", "--desc", default="")
    s = sub.add_parser("start", help="empieza un paso")
    s.add_argument("id")
    s.add_argument("-m", "--message", default="")
    s = sub.add_parser("done", help="da un paso por hecho; -m cuenta qué ha cambiado y cómo se comprueba")
    s.add_argument("id")
    s.add_argument("-m", "--message", required=True)
    s = sub.add_parser("note", help="apunta un avance o un hallazgo en un paso")
    s.add_argument("id")
    s.add_argument("text")
    s = sub.add_parser("reopen", help="devuelve un paso a pendiente")
    s.add_argument("id")
    s.add_argument("-m", "--message", default="")
    s = sub.add_parser("archive", help="guarda una rama terminada para que no ocupe sitio")
    s.add_argument("branch")
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("drop", help="borra una rama entera (para planes equivocados)")
    s.add_argument("branch")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    path = Path(args.plan_file) if args.plan_file else find_plan()
    by = args.by or os.environ.get("UNI_AGENT") or "ia"
    try:
        cmd = args.cmd or "status"
        if cmd == "status":
            print(render_status(load(path)))
        elif cmd == "show":
            print(render_step(load(path), args.id))
        elif cmd == "plan":
            raw = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
            try:
                data = json.loads(raw)
            except ValueError as e:
                raise PlanError(f"El plan no es JSON válido: {e}")
            for b in mutate(path, lambda plan: add_branches(plan, data, by)):
                print(f"+ rama {b.get('icon') or '●'} {b['name']} [{b['key']}]")
                for ph in b["phases"]:
                    print(f"    {ph['name']}: " + ", ".join(s["id"] for s in ph["steps"]))
            print("Plan guardado. Empieza por el primer paso con `start`.")
        elif cmd == "add":
            s = mutate(path, lambda plan: add_step(plan, args.branch, args.phase, args.title, args.desc, by))
            print(f"+ {s['id']}  {s['title']}")
        elif cmd in ("start", "done", "reopen"):
            state = {"start": DOING, "done": DONE, "reopen": PENDING}[cmd]
            s = mutate(path, lambda plan: set_state(plan, args.id, state, by, args.message))
            print(f"{MARKS[state]} {s['id']}  {s['title']}  [{STATE_NAMES[state]}]")
        elif cmd == "note":
            s = mutate(path, lambda plan: add_note(plan, args.id, args.text, by))
            print(f"Nota guardada en {s['id']}.")
        elif cmd == "archive":
            b = mutate(path, lambda plan: archive_branch(plan, args.branch, args.force))
            print(f"Rama «{b['name']}» archivada.")
        elif cmd == "drop":
            b = mutate(path, lambda plan: drop_branch(plan, args.branch))
            print(f"Rama «{b['name']}» borrada.")
    except PlanError as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print(f"No se pudo leer o escribir el plan: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
