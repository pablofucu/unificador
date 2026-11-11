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

Nada bloquea: al terminar una fase el agente para y pregunta en su chat (``approve``/``revise``),
y las preguntas y propuestas (``ask``/``propose``) se contestan en el chat o en la web
(``answer``, ``wait``, ``inbox``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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
WAITING, APPROVED, CHANGES = "waiting", "approved", "changes"  # revisión de una fase
QUESTION, PROPOSAL = "question", "proposal"
PROPOSALS_DIR = ".unificador/propuestas"
MAX_PROPOSAL = 2 * 1024 * 1024
POLL = 1.0  # segundos entre lecturas en `wait`
UNI = "python .unificador/uni.py"


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
    return {"version": VERSION, "title": title, "branches": [], "asks": []}


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
    if not isinstance(data.get("asks"), list):
        data["asks"] = []
    return data


def save(path: Path, plan: Dict[str, Any]) -> None:
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")
    for attempt in range(20):  # en Windows falla si otro proceso está leyendo justo ahora
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


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


def review_state(phase: dict) -> str:
    """«waiting», «approved», «changes» o «» si la fase no tiene revisión."""
    review = phase.get("review")
    return review.get("state", "") if isinstance(review, dict) else ""


def find_phase(branch: dict, name: Optional[str] = None) -> dict:
    """Una fase por nombre (o número); sin nombre, la que espera revisión."""
    phases = branch.get("phases", [])
    name = _clean(name)
    if not name:
        waiting = [p for p in phases if review_state(p) == WAITING]
        if waiting:
            return waiting[0]
        raise PlanError(f"Ninguna fase de «{branch['name']}» espera revisión. Di cuál, entre comillas: "
                        f'{UNI} approve {branch["key"]} "Nombre de la fase"')
    for p in phases:
        if p["name"].lower() == name.lower():
            return p
    if name.isdigit() and 1 <= int(name) <= len(phases):
        return phases[int(name) - 1]
    known = ", ".join(f"«{p['name']}»" for p in phases) or "ninguna"
    raise PlanError(f"La rama «{branch['name']}» no tiene la fase «{name}». Sus fases: {known}.")


def find_ask(plan: Dict[str, Any], ask_id: str) -> dict:
    wanted = str(ask_id).strip().upper()
    for ask in plan.get("asks", []):
        if ask["id"].upper() == wanted:
            return ask
    known = ", ".join(a["id"] for a in plan.get("asks", [])) or "ninguna todavía"
    raise PlanError(f"No existe la pregunta {ask_id}. Preguntas del plan: {known}.")


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
    _clear_review(phase)  # con un paso nuevo, la fase deja de estar terminada
    step = _new_step(branch, title, desc.strip())
    step["by"] = by
    phase["steps"].append(step)
    branch.pop("archived", None)
    return step


def set_state(plan: Dict[str, Any], step_id: str, state: str, by: str = "ia", text: str = "") -> dict:
    if state not in STATES:
        raise PlanError(f"Estado desconocido: {state}. Usa pending, doing o done.")
    branch, phase, step = find_step(plan, step_id)
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
    if state != DONE:
        _clear_review(phase)
    elif phase_state(phase) == DONE and not branch.get("nonstop") and review_state(phase) not in (WAITING, APPROVED):
        phase["review"] = {"state": WAITING, "text": "", "by": by, "at": now(), "seen": True}
    return step


def _clear_review(phase: dict) -> None:
    """Un paso reabierto: la fase ya no está terminada, ni esperando ni aprobada."""
    if review_state(phase) in (WAITING, APPROVED):
        phase.pop("review", None)


def review_phase(plan: Dict[str, Any], branch_ref: str, phase_name: Optional[str], verdict: str,
                 text: str = "", by: str = "persona", seen: bool = True) -> Tuple[dict, dict]:
    """La persona revisa una fase: «approved» (sigue) o «changes» (con qué cambiar).

    Sin ``phase_name``, la fase que está esperando. ``seen`` dice si el agente ya lo sabe
    (lo apuntó él desde el chat); la web lo deja en falso para que salga en ``inbox`` y ``wait``.
    Devuelve (rama, fase).
    """
    branch = find_branch(plan, branch_ref)
    verdict = {"approve": APPROVED, "approved": APPROVED, "revise": CHANGES, "changes": CHANGES}.get(
        str(verdict or "").strip().lower(), "")
    if not verdict:
        raise PlanError("La revisión de una fase es «approved» (aprobada) o «changes» (pide cambios).")
    text = (text or "").strip()
    if verdict == CHANGES and not text:
        raise PlanError(f'Escribe qué quiere cambiar la persona: {UNI} revise {branch["key"]} -m "qué quiere cambiar"')
    phase = find_phase(branch, phase_name)
    phase["review"] = {"state": verdict, "text": text, "by": by, "at": now(), "seen": bool(seen)}
    return branch, phase


def set_nonstop(plan: Dict[str, Any], branch_ref: str, on: bool) -> dict:
    """Rama sin paradas: al terminar sus fases no se espera la revisión de la persona."""
    branch = find_branch(plan, branch_ref)
    if on:
        branch["nonstop"] = True
    else:
        branch.pop("nonstop", None)
    return branch


# ── Preguntas y propuestas ───────────────────────────────────────────────────

def _ask_target(plan: Dict[str, Any], step: Optional[str], branch: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if step and branch:
        raise PlanError("Usa --step o --branch, no los dos.")
    if step:
        b, _, s = find_step(plan, step)
        return s["id"], b["key"]
    if branch:
        return None, find_branch(plan, branch)["key"]
    return None, None


def add_ask(plan: Dict[str, Any], title: str, kind: str = QUESTION, text: str = "", step: Optional[str] = None,
            branch: Optional[str] = None, options: Optional[List[Any]] = None, by: str = "ia") -> dict:
    """Apunta una pregunta (opciones = textos; vacío = respuesta libre) o una propuesta
    (opciones = {"label", "file"}). Devuelve la pregunta creada."""
    title = _clean(title)
    if not title:
        raise PlanError('Escribe la pregunta entre comillas: python .unificador/uni.py ask "¿Qué prefieres?"')
    if kind not in (QUESTION, PROPOSAL):
        raise PlanError("El tipo es «question» o «proposal».")
    clean_options = []
    for o in options or []:
        o = dict(o) if isinstance(o, dict) else {"label": o}
        o["label"] = _clean(o.get("label"))
        if not o["label"]:
            raise PlanError("Hay una opción vacía: escribe cada opción entre comillas.")
        clean_options.append(o)
    if len(clean_options) == 1:
        raise PlanError('Pon al menos dos opciones (--option "A" --option "B") o ninguna para una respuesta libre.')
    step_id, branch_key = _ask_target(plan, step, branch)
    n = int(plan.get("next_ask") or 1)
    used = {a["id"].upper() for a in plan.get("asks", [])}
    while f"P-{n}" in used:
        n += 1
    plan["next_ask"] = n + 1
    ask = {"id": f"P-{n}", "kind": kind, "title": title, "text": (text or "").strip(), "step": step_id,
           "branch": branch_key, "options": clean_options, "answer": None, "by": by, "created": now()}
    plan.setdefault("asks", []).append(ask)
    return ask


def check_proposal_files(options: List[Tuple[str, Any]]) -> List[Tuple[str, Path]]:
    """Valida las opciones de una propuesta: [(nombre, ruta.html)], al menos dos."""
    if len(options) < 2:
        raise PlanError('Una propuesta necesita al menos dos opciones, cada una con nombre y fichero: '
                        '--option "Clara" a.html --option "Oscura" b.html')
    out, errors = [], []
    for label, file in options:
        src = Path(file)
        if src.suffix.lower() not in (".html", ".htm"):
            errors.append(f"«{file}» no es un .html.")
        elif not src.is_file():
            errors.append(f"No encuentro «{file}» (ruta relativa a la carpeta donde ejecutas la orden).")
        elif src.stat().st_size > MAX_PROPOSAL:
            errors.append(f"«{file}» pasa de 2 MB; hazlo más ligero (sin imágenes incrustadas).")
        out.append((label, src))
    if errors:
        raise PlanError("La propuesta no se ha guardado:\n- " + "\n- ".join(errors))
    return out


def add_proposal(plan: Dict[str, Any], folder: Path, title: str, options: List[Tuple[str, Any]], text: str = "",
                 step: Optional[str] = None, branch: Optional[str] = None, by: str = "ia") -> dict:
    """Apunta una propuesta y copia cada HTML a ``<folder>/.unificador/propuestas/<id>/<n>.html``."""
    files = check_proposal_files(options)
    ask = add_ask(plan, title, PROPOSAL, text, step, branch, [{"label": label} for label, _ in files], by)
    target = Path(folder) / PROPOSALS_DIR / ask["id"]
    try:
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for n, (option, (_, src)) in enumerate(zip(ask["options"], files), 1):
            shutil.copyfile(src, target / f"{n}.html")
            option["file"] = f"{PROPOSALS_DIR}/{ask['id']}/{n}.html"
    except OSError:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return ask


def answer_ask(plan: Dict[str, Any], ask_id: str, option: Optional[int] = None, text: str = "",
               by: str = "persona", seen: bool = False) -> dict:
    """La respuesta de la persona (sustituye a la anterior). ``option`` va de 1 a n."""
    ask = find_ask(plan, ask_id)
    text = (text or "").strip()
    if option in ("", None):
        option = None
    else:
        try:
            option = int(option)
        except (TypeError, ValueError):
            raise PlanError(f"La opción debe ser un número: {UNI} answer {ask['id']} 2")
        n = len(ask.get("options") or [])
        if not n:
            raise PlanError(f"{ask['id']} no tiene opciones: apunta la respuesta con -m \"lo que ha dicho\".")
        if not 1 <= option <= n:
            raise PlanError(f"{ask['id']} tiene las opciones 1 a {n}.")
    if option is None and not text:
        raise PlanError(f'Di qué opción eligió (número) o qué dijo: {UNI} answer {ask["id"]} 1 -m "lo que ha dicho"')
    ask["answer"] = {"option": option, "text": text, "by": by, "at": now(), "seen": bool(seen)}
    return ask


def _news(plan: Dict[str, Any], include: Optional[str] = None) -> Tuple[List[dict], List[Tuple[dict, dict]]]:
    """Respuestas y revisiones que el agente no ha visto (y la pregunta ``include`` si ya tiene respuesta)."""
    wanted = (include or "").strip().upper()
    asks = [a for a in plan.get("asks", []) if isinstance(a.get("answer"), dict)
            and (not a["answer"].get("seen") or a["id"].upper() == wanted)]
    reviews = [(b, p) for b in plan.get("branches", []) if not b.get("archived") for p in b.get("phases", [])
               if review_state(p) in (APPROVED, CHANGES) and not p["review"].get("seen")]
    return asks, reviews


def _mark_seen(plan: Dict[str, Any], asks: List[dict], reviews: List[Tuple[dict, dict]]) -> None:
    ids = {a["id"] for a in asks}
    for a in plan.get("asks", []):
        if a["id"] in ids and isinstance(a.get("answer"), dict):
            a["answer"]["seen"] = True
    marks = {(b["key"], p["name"]) for b, p in reviews}
    for b in plan.get("branches", []):
        for p in b.get("phases", []):
            if (b["key"], p["name"]) in marks and isinstance(p.get("review"), dict):
                p["review"]["seen"] = True


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
    branch, phase, step = find_step(plan, step_id)
    _clear_review(phase)
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


def drop_branch(plan: Dict[str, Any], ref: str, folder: Optional[Path] = None) -> dict:
    """Borra la rama, sus preguntas y (con ``folder``, la carpeta del plan) sus ficheros de propuestas."""
    branch = find_branch(plan, ref)
    plan["branches"].remove(branch)
    gone = [a for a in plan.get("asks", []) if a.get("branch") == branch["key"]]
    plan["asks"] = [a for a in plan.get("asks", []) if a not in gone]
    if folder is not None:
        for a in gone:
            shutil.rmtree(Path(folder) / PROPOSALS_DIR / a["id"], ignore_errors=True)
    return branch


# ── Texto para la terminal ───────────────────────────────────────────────────

def _phase_flag(phase: dict) -> str:
    st = review_state(phase)
    if st == WAITING:
        return "  ⏸ esperando tu revisión"
    if st == CHANGES:
        return f"  ⚠ pide cambios: {phase['review'].get('text', '')}"
    if st == APPROVED:
        return "  (aprobada)"
    return ""


def _ask_line(ask: dict) -> str:
    kind = "propuesta" if ask.get("kind") == PROPOSAL else "pregunta"
    where = f" ({ask['step'] or ask['branch']})" if ask.get("step") or ask.get("branch") else ""
    line = f"  {ask['id']}  [{kind}]{where} {ask['title']}"
    opts = ask.get("options") or []
    if opts:
        line += "\n" + "\n".join(f"      {n}) {o['label']}" + (f"  → {o['file']}" if o.get("file") else "")
                                 for n, o in enumerate(opts, 1))
    return line


def _answer_text(ask: dict) -> str:
    ans = ask.get("answer") or {}
    parts = []
    opt = ans.get("option")
    opts = ask.get("options") or []
    if opt and 1 <= opt <= len(opts):
        o = opts[opt - 1]
        parts.append(f"opción {opt}: «{o['label']}»" + (f" ({o['file']})" if o.get("file") else ""))
    if ans.get("text"):
        parts.append(f"«{ans['text']}»")
    return " — ".join(parts) or "(sin texto)"


def render_status(plan: Dict[str, Any]) -> str:
    branches = [b for b in plan.get("branches", []) if not b.get("archived")]
    if not branches:
        lines = [f"{plan.get('title') or 'Proyecto'}: el plan está vacío.\n"
                 "Cuando haya trabajo que hacer, crea una rama con `branch` (ejemplo: python .unificador/uni.py --help)."]
        return "\n".join(lines + _render_open_asks(plan))
    done = sum(branch_progress(b)[0] for b in branches)
    total = sum(branch_progress(b)[1] for b in branches)
    lines = [f"{plan.get('title') or 'Proyecto'}: {done}/{total} pasos hechos en {len(branches)} "
             f"rama{'s' if len(branches) != 1 else ''}"]
    changes = [(b, s) for b, _, s in iter_steps(plan) if s.get("change")]
    phase_changes = [(b, p) for b in branches for p in b["phases"] if review_state(p) == CHANGES]
    if changes or phase_changes:
        lines.append("\n⚠ LA PERSONA PIDE CAMBIOS (hazlos antes que nada):")
        lines += [f"  {s['id']}  {s['title']}: {s['change']}" for _, s in changes]
        lines += [f"  Fase «{p['name']}» [{b['key']}]: {p['review'].get('text', '')}" for b, p in phase_changes]
    waiting = [(b, p) for b in branches for p in b["phases"] if review_state(p) == WAITING]
    if waiting:
        lines.append("\n⏸ FASES ESPERANDO LA REVISIÓN DE LA PERSONA (pregúntale si sigues):")
        lines += [f"  «{p['name']}» [{b['key']}]  → cuando conteste: {UNI} approve {b['key']}  "
                  f'(o  revise {b["key"]} -m "qué quiere cambiar")' for b, p in waiting]
    for b in branches:
        d, t = branch_progress(b)
        lines.append(f"\n{b.get('icon') or '●'} {b['name']} [{b['key']}]  {d}/{t}"
                     + ("  (sin paradas)" if b.get("nonstop") else ""))
        current = next((p for p in b["phases"] if phase_state(p) != DONE), None)
        for p in b["phases"]:
            st = phase_state(p)
            if p is current or st == DOING:
                lines.append(f"  {MARKS[DOING]} {p['name']}{_phase_flag(p)}")
                lines += [f"      {MARKS[s['state']]} {s['id']}  {s['title']}"
                          + ("  (en curso)" if s["state"] == DOING else "") for s in p["steps"]]
            else:
                n = len(p["steps"])
                lines.append(f"  {MARKS[st]} {p['name']}  ({n} paso{'s' if n != 1 else ''}){_phase_flag(p)}")
    doing = [s for _, _, s in iter_steps(plan) if s["state"] == DOING]
    nxt = [n for n in (next_step(b) for b in branches) if n and n["state"] == PENDING]
    if doing:
        lines.append("\nEn curso: " + "; ".join(f"{s['id']} {s['title']}" for s in doing))
    if nxt:
        lines.append("Siguiente: " + "; ".join(f"{s['id']} {s['title']}" for s in nxt))
    if not doing and not nxt:
        lines.append("\nTodo lo planificado está hecho.")
    return "\n".join(lines + _render_open_asks(plan))


def _render_open_asks(plan: Dict[str, Any]) -> List[str]:
    open_asks = [a for a in plan.get("asks", []) if not a.get("answer")]
    if not open_asks:
        return []
    return (["\n? PREGUNTAS SIN RESPONDER (hazlas también en el chat):"] + [_ask_line(a) for a in open_asks]
            + [f'  Si contesta en el chat: {UNI} answer ID [número] -m "lo que ha dicho".  '
               f"Si contesta en la web: {UNI} wait ID"])


def render_step(plan: Dict[str, Any], step_id: str) -> str:
    branch, phase, step = find_step(plan, step_id)
    lines = [f"{step['id']}  {step['title']}  [{STATE_NAMES[step['state']]}]",
             f"Rama: {branch['name']} · Fase: {phase['name']}{_phase_flag(phase)}"]
    if step.get("desc"):
        lines.append(f"\n{step['desc']}")
    if step.get("change"):
        lines.append(f"\n⚠ Cambio pedido por la persona: {step['change']}")
    if step.get("notes"):
        lines.append("\nNotas:")
        lines += [f"  [{n.get('at', '')[:16].replace('T', ' ')} {n.get('by', '')}] {n.get('text', '')}"
                  for n in step["notes"][-8:]]
    asks = [a for a in plan.get("asks", []) if a.get("step") == step["id"]]
    if asks:
        lines.append("\nPreguntas y propuestas:")
        for a in asks:
            lines.append(_ask_line(a))
            lines.append(f"      Respuesta: {_answer_text(a)}" if a.get("answer") else "      Sin respuesta todavía.")
    return "\n".join(lines)


def _render_news(plan: Dict[str, Any], asks: List[dict], reviews: List[Tuple[dict, dict]]) -> str:
    lines = []
    for a in asks:
        lines.append(f"{a['id']}  «{a['title']}»: la persona ha respondido {_answer_text(a)}")
    for b, p in reviews:
        if review_state(p) == APPROVED:
            extra = f" ({p['review']['text']})" if p["review"].get("text") else ""
            lines.append(f"Fase «{p['name']}» de «{b['name']}» [{b['key']}]: APROBADA{extra}. {_branch_next(b)}")
        else:
            lines.append(f"Fase «{p['name']}» de «{b['name']}» [{b['key']}]: PIDE CAMBIOS: {p['review'].get('text', '')}\n"
                         f"  {_revise_hint(b, p)}")
    return "\n".join(lines)


def _revise_hint(branch: dict, phase: dict) -> str:
    return (f'Decide qué rehacer: {UNI} reopen ID -m "por qué"  o añade un paso: '
            f'{UNI} add {branch["key"]} "{phase["name"]}" "Título". Al terminarlos, la fase vuelve a esperar revisión.')


# ── Línea de órdenes ─────────────────────────────────────────────────────────

EXAMPLE = """ejemplo (vale igual en PowerShell, cmd y bash):

  python .unificador/uni.py branch "Carrito de compra" --icon 🛒 --goal "Poder comprar desde la web" \
      --phase "Cimientos" "Modelo del carrito" "Guardar y recuperar" \
      --phase "Pagos" "Pasarela de pago" "Recibo por correo"
  python .unificador/uni.py start CDC-1
  python .unificador/uni.py done CDC-1 -m "qué ha cambiado y cómo lo he comprobado"

Cada --phase lleva el nombre de la fase y después sus pasos, cada cosa entre comillas.
Para un plan con descripciones: `plan --file plan.json` (mismo formato que unificador.json).

Al terminar una fase, para y pregunta a la persona; cuando conteste:
  python .unificador/uni.py approve CDC          (o  revise CDC -m "qué quiere cambiar")
Preguntas y propuestas (se contestan en el chat o en la web):
  python .unificador/uni.py ask "¿Qué color?" --step CDC-1 --option "Azul" --option "Verde"
  python .unificador/uni.py propose "Portada" --option "Clara" a.html --option "Oscura" b.html
  python .unificador/uni.py answer P-1 2 -m "lo que ha dicho en el chat"
  python .unificador/uni.py wait P-1             (espera a que conteste en la web)
"""
BRANCH_HINT = ('Crea la rama con una sola orden, cada cosa entre comillas:\n'
               '  python .unificador/uni.py branch "Nombre de la rama" --goal "Para qué sirve" '
               '--phase "Nombre de fase" "Primer paso" "Segundo paso" --phase "Otra fase" "Otro paso"')
ORDERS = "status, branch, add, start, done, note, show, approve, revise, nonstop, ask, propose, answer, wait, inbox"


def branch_from_args(name: str, icon: str, goal: str, phases: List[List[str]]) -> dict:
    """La rama que describe la orden `branch`: cada --phase es [nombre, paso, paso…]."""
    if not phases:
        raise PlanError("A la rama le faltan las fases.\n" + BRANCH_HINT)
    out = []
    for items in phases:
        if len(items) < 2:
            raise PlanError(f"La fase «{items[0]}» no tiene pasos: detrás del nombre van sus pasos.\n" + BRANCH_HINT)
        steps = []
        for item in items[1:]:
            title, _, desc = item.partition(" :: ")
            steps.append({"title": title, "desc": desc})
        out.append({"name": items[0], "steps": steps})
    return {"branches": [{"name": name, "icon": icon, "goal": goal, "phases": out}]}


def _branch_next(branch: dict) -> str:
    nxt = next_step(branch)
    if nxt is None:
        return f"Rama «{branch['name']}» terminada. Cuéntale a la persona qué has hecho."
    if nxt["state"] == DOING:
        return f"Sigue con {nxt['id']} {nxt['title']} (ya está en curso)."
    return f"Siguiente: {UNI} start {nxt['id']}   ({nxt['title']})"


def _what_next(plan: Dict[str, Any], step_id: str) -> str:
    """Qué orden toca después de cerrar un paso, para que el agente no tenga que deducirlo."""
    branch, phase, _ = find_step(plan, step_id)
    if phase_state(phase) == DONE and review_state(phase) == WAITING:
        last = "" if next_step(branch) else " Es la última fase de la rama."
        return (f"FASE TERMINADA: «{phase['name']}».{last} Para aquí: resume a la persona qué se ha hecho y "
                f"pregúntale si sigues. Cuando conteste: {UNI} approve {branch['key']}  "
                f'(o  {UNI} revise {branch["key"]} -m "qué quiere cambiar")')
    return _branch_next(branch)


def _start_warning(plan: Dict[str, Any], step_id: str) -> str:
    """Sin candado: empezar con una fase anterior sin revisar funciona, pero se avisa."""
    branch, phase, _ = find_step(plan, step_id)
    for p in branch["phases"]:
        if p is phase:
            break
        if review_state(p) == WAITING:
            return (f"Aviso: la fase «{p['name']}» sigue esperando la revisión de la persona. Si ya te ha dicho que "
                    f"sigas: {UNI} approve {branch['key']}")
        if review_state(p) == CHANGES:
            return f"Aviso: la persona pidió cambios en la fase «{p['name']}»: {p['review'].get('text', '')}"
    return ""


def wait_answer(path: Path, ask_id: Optional[str] = None, seconds: float = 240) -> str:
    """Espera (sin bloquear el plan) a que la persona conteste en la web; devuelve el texto a imprimir."""
    path = Path(path)
    if ask_id:
        ask_id = find_ask(load(path), ask_id)["id"]
    deadline = time.time() + max(0.0, float(seconds))
    while True:
        try:
            plan = load(path)
        except (OSError, PlanError):
            plan = None
        if plan is not None:
            asks, reviews = _news(plan, ask_id)
            if asks or reviews:
                text = _render_news(plan, asks, reviews)
                mutate(path, lambda p: _mark_seen(p, asks, reviews))
                return text
            pending = any(not a.get("answer") for a in plan.get("asks", [])) or any(
                review_state(p) == WAITING for b in plan.get("branches", []) for p in b.get("phases", []))
            if not ask_id and not pending:
                return "Nada pendiente: no hay preguntas sin responder ni fases esperando revisión."
        left = deadline - time.time()
        if left <= 0:
            return "Sin respuesta todavía: termina tu turno y pregúntalo en el chat."
        time.sleep(min(POLL, left))


def inbox(path: Path) -> str:
    """Lo nuevo que la persona dejó en la web; lo marca como visto. Vacío si no hay nada."""
    path = Path(path)
    if not path.is_file():
        return ""
    plan = load(path)
    asks, reviews = _news(plan)
    changes = [s for _, _, s in iter_steps(plan) if s.get("change") and s["state"] != DONE]
    if not (asks or reviews or changes):
        return ""
    lines = ["NOVEDADES DE LA PERSONA (atiéndelas antes de seguir):"]
    if asks or reviews:
        lines.append(_render_news(plan, asks, reviews))
        mutate(path, lambda p: _mark_seen(p, asks, reviews))
    lines += [f"{s['id']}  {s['title']}: pide un cambio: {s['change']}  → {UNI} start {s['id']}" for s in changes]
    return "\n".join(lines)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # los errores, en llano y con lo que hay que escribir
        self.print_usage(sys.stderr)
        print(f"No entiendo la orden: {message}\nOrdenes: {ORDERS}. "
              "Ayuda con ejemplo: python .unificador/uni.py --help", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="uni", description="El plan del proyecto en ramas → fases → pasos.",
                                epilog=EXAMPLE, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-f", "--plan-file", metavar="RUTA", help=f"fichero del plan (por defecto, el {PLAN_FILE} más cercano)")
    p.add_argument("--as", dest="by", metavar="NOMBRE", help="quién firma (por defecto $UNI_AGENT o «ia»)")
    sub = p.add_subparsers(dest="cmd", metavar="<orden>")
    sub.add_parser("status", help="cómo va el plan (orden por defecto)")
    s = sub.add_parser("show", help="un paso con su descripción y sus notas")
    s.add_argument("id")
    s = sub.add_parser("branch", help="crea una rama con sus fases y pasos, todo en una orden")
    s.add_argument("name", help="nombre de la rama")
    s.add_argument("--icon", default="", help="un emoji")
    s.add_argument("--goal", default="", help="para qué sirve")
    s.add_argument("--phase", dest="phases", action="append", nargs="+", default=[], metavar="TEXTO",
                   help='nombre de la fase y después sus pasos: --phase "Cimientos" "Paso uno" "Paso dos"')
    s = sub.add_parser("plan", help="crea ramas nuevas desde JSON (--file o entrada estándar)")
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
    s = sub.add_parser("approve", help="la persona da por buena una fase (sin fase: la que espera)")
    s.add_argument("branch")
    s.add_argument("phase", nargs="?", default="")
    s.add_argument("-m", "--message", default="")
    s = sub.add_parser("revise", help="la persona pide cambios en una fase (sin fase: la que espera)")
    s.add_argument("branch")
    s.add_argument("phase", nargs="?", default="")
    s.add_argument("-m", "--message", required=True)
    s = sub.add_parser("nonstop", help="on: la rama no para al terminar cada fase; off: vuelve a parar")
    s.add_argument("branch")
    s.add_argument("mode", help="on u off")
    s = sub.add_parser("ask", help="apunta una pregunta para la persona (házsela también en el chat)")
    s.add_argument("title", help="la pregunta, entre comillas")
    s.add_argument("-d", "--desc", default="", help="más detalle")
    s.add_argument("--step", help="paso al que se refiere")
    s.add_argument("--branch", help="rama a la que se refiere")
    s.add_argument("--option", dest="options", action="append", default=[], metavar="TEXTO",
                   help='una opción; repítelo: --option "A" --option "B" (sin opciones, respuesta libre)')
    s.add_argument("--wait", type=float, default=0, metavar="SEG", help="espera la respuesta de la web")
    s = sub.add_parser("propose", help="propuestas visuales en HTML para que la persona elija")
    s.add_argument("title", help="qué se propone, entre comillas")
    s.add_argument("-d", "--desc", default="", help="más detalle")
    s.add_argument("--step", help="paso al que se refiere")
    s.add_argument("--branch", help="rama a la que se refiere")
    s.add_argument("--option", dest="options", action="append", nargs=2, default=[], metavar=("NOMBRE", "RUTA"),
                   help='nombre y fichero .html; repítelo: --option "Clara" a.html --option "Oscura" b.html')
    s.add_argument("--wait", type=float, default=0, metavar="SEG", help="espera la respuesta de la web")
    s = sub.add_parser("answer", help="apunta lo que la persona contestó en el chat")
    s.add_argument("id", help="la pregunta, p. ej. P-1")
    s.add_argument("option", nargs="?", default=None, help="número de la opción elegida")
    s.add_argument("-m", "--message", default="", help="lo que ha dicho")
    s = sub.add_parser("wait", help="espera a que la persona conteste en la web")
    s.add_argument("id", nargs="?", default=None, help="la pregunta (sin ella, cualquier novedad)")
    s.add_argument("--seconds", type=float, default=240)
    sub.add_parser("inbox", help="lo que la persona dejó en la web y aún no has visto (silencio si no hay nada)")
    return p


def _print_ask(ask: dict, path: Path) -> None:
    folder = Path(path).resolve().parent
    if ask["kind"] == PROPOSAL:
        print(f"Propuesta {ask['id']} guardada: {ask['title']}")
        for n, o in enumerate(ask["options"], 1):
            print(f"  {n}) {o['label']}: {folder / o['file']}")
        print("Ahora enséñale a la persona estas rutas en el chat y pregúntale cuál prefiere (también puede elegir en la web).")
    else:
        print(f"Pregunta {ask['id']} apuntada: {ask['title']}")
        for n, o in enumerate(ask["options"], 1):
            print(f"  {n}) {o['label']}")
        print("Ahora házsela también a la persona en el chat (puede contestar allí o en la web).")
    num = " N" if ask["options"] else ""
    print(f'Si contesta en el chat: {UNI} answer {ask["id"]}{num} -m "lo que ha dicho".  '
          f"Para esperar a la web: {UNI} wait {ask['id']}")


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    signer = None
    for i, a in enumerate(argv):  # --as vale en cualquier sitio, antes o después de la orden
        if a == "--as" and i + 1 < len(argv):
            signer = argv[i + 1]
            del argv[i:i + 2]
            break
        if a.startswith("--as="):
            signer = a[5:]
            del argv[i]
            break
    args = build_parser().parse_args(argv)
    args.by = signer or args.by
    path = Path(args.plan_file) if args.plan_file else find_plan()
    by = args.by or os.environ.get("UNI_AGENT") or "ia"
    cmd = args.cmd or "status"
    if cmd == "inbox":  # se ejecuta sola en cada mensaje: nunca falla ni hace ruido
        try:
            text = inbox(path)
            if text:
                print(text)
        except Exception:
            pass
        return 0
    try:
        if cmd == "status":
            print(render_status(load(path)))
        elif cmd == "show":
            print(render_step(load(path), args.id))
        elif cmd in ("plan", "branch"):
            if cmd == "branch":
                data = branch_from_args(args.name, args.icon, args.goal, args.phases)
            else:
                if not args.file and sys.stdin is not None and sys.stdin.isatty():
                    raise PlanError("No me ha llegado ningún plan.\n" + BRANCH_HINT)
                raw = Path(args.file).read_text(encoding="utf-8-sig") if args.file else sys.stdin.read()
                if not raw.strip():
                    raise PlanError("No me ha llegado ningún plan.\n" + BRANCH_HINT)
                try:
                    data = json.loads(raw.lstrip("﻿"))
                except ValueError as e:
                    raise PlanError(f"El plan no es JSON válido: {e}\n" + BRANCH_HINT)
            first = ""
            for b in mutate(path, lambda plan: add_branches(plan, data, by)):
                print(f"+ rama {b.get('icon') or '●'} {b['name']} [{b['key']}]")
                for ph in b["phases"]:
                    print(f"    {ph['name']}: " + ", ".join(s["id"] for s in ph["steps"]))
                first = first or next((s["id"] for ph in b["phases"] for s in ph["steps"]), "")
            print(f"Plan guardado. Ahora empieza el primer paso: python .unificador/uni.py start {first}")
        elif cmd == "add":
            s = mutate(path, lambda plan: add_step(plan, args.branch, args.phase, args.title, args.desc, by))
            print(f"+ {s['id']}  {s['title']}")
        elif cmd in ("start", "done", "reopen"):
            state = {"start": DOING, "done": DONE, "reopen": PENDING}[cmd]
            s = mutate(path, lambda plan: set_state(plan, args.id, state, by, args.message))
            print(f"{MARKS[state]} {s['id']}  {s['title']}  [{STATE_NAMES[state]}]")
            if cmd == "start":
                warning = _start_warning(load(path), s["id"])
                if warning:
                    print(warning)
                print(f'Cuando lo termines: python .unificador/uni.py done {s["id"]} -m "qué ha cambiado y cómo lo has comprobado"')
            elif cmd == "done":
                print(_what_next(load(path), s["id"]))
        elif cmd == "note":
            s = mutate(path, lambda plan: add_note(plan, args.id, args.text, by))
            print(f"Nota guardada en {s['id']}.")
        elif cmd == "archive":
            b = mutate(path, lambda plan: archive_branch(plan, args.branch, args.force))
            print(f"Rama «{b['name']}» archivada.")
        elif cmd == "drop":
            b = mutate(path, lambda plan: drop_branch(plan, args.branch, path.resolve().parent))
            print(f"Rama «{b['name']}» borrada.")
        elif cmd in ("approve", "revise"):
            verdict = APPROVED if cmd == "approve" else CHANGES
            b, ph = mutate(path, lambda plan: review_phase(plan, args.branch, args.phase, verdict, args.message,
                                                           "persona", True))
            if verdict == APPROVED:
                print(f"✔ Fase «{ph['name']}» aprobada. {_branch_next(b)}")
            else:
                print(f"⚠ Fase «{ph['name']}»: la persona pide cambios: {ph['review']['text']}\n{_revise_hint(b, ph)}")
        elif cmd == "nonstop":
            mode = args.mode.strip().lower()
            if mode not in ("on", "off", "si", "sí", "no"):
                raise PlanError(f"Escribe on u off: {UNI} nonstop {args.branch} on")
            on = mode in ("on", "si", "sí")
            b = mutate(path, lambda plan: set_nonstop(plan, args.branch, on))
            print(f"Rama «{b['name']}»: " + ("sin paradas; no esperará revisión al terminar cada fase."
                                             if on else "vuelve a parar al terminar cada fase para que la persona la revise."))
        elif cmd in ("ask", "propose"):
            if cmd == "ask":
                ask = mutate(path, lambda plan: add_ask(plan, args.title, QUESTION, args.desc, args.step,
                                                        args.branch, args.options, by))
            else:
                check_proposal_files(args.options)  # antes de tocar el plan
                folder = path.resolve().parent
                ask = mutate(path, lambda plan: add_proposal(plan, folder, args.title, args.options, args.desc,
                                                             args.step, args.branch, by))
            _print_ask(ask, path)
            if args.wait > 0:
                print(wait_answer(path, ask["id"], args.wait))
        elif cmd == "answer":
            a = mutate(path, lambda plan: answer_ask(plan, args.id, args.option, args.message, "persona", True))
            print(f"Respuesta apuntada en {a['id']}: {_answer_text(a)}. Sigue con lo que ha elegido.")
        elif cmd == "wait":
            print(wait_answer(path, args.id, args.seconds))
    except PlanError as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print(f"No se pudo leer o escribir el plan: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
