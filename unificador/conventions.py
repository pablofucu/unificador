"""
Convenciones de trabajo compartidas por Unificador y por la terminal.

Las reglas de ramas → fases → pasos viven aquí y solo aquí:

- ``context_injector`` las añade al prompt cuando la persona habla desde Unificador.
- ``ensure_project_files`` las escribe en un bloque de ``AGENTS.md`` de cada proyecto,
  para que Claude Code, Antigravity o Codex las lean igual al abrirlos en la terminal.
  También deja un ``CLAUDE.md`` que importa ``AGENTS.md`` y un hook de Claude Code que
  muestra el tablero al empezar cada sesión.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

KANVAS_REL = ".agents/skills/kanvas/kanvas.py"

PHASES_GUIDE = """
### CÓMO SE ORGANIZA EL TRABAJO: RAMAS → FASES → PASOS
- Cada **grupo** de Kanvas es una **rama**: un área del proyecto que puede avanzar por su cuenta (p. ej. «Interfaz», «Datos», «Despliegue»). Nombra los grupos por el área, no por el orden: nada de «Fase 1: …».
- Dentro de cada rama, las **fases** salen de las dependencias: un paso que depende (`deps`) de otro de la misma rama va en la fase siguiente. Sin dependencias, todo cae en la fase 1.
- Cada **paso** es una tarea pequeña y comprobable (una sesión de trabajo), con una `desc` que diga qué consigue y cuándo está terminada.
- Trabaja fase a fase: no empieces un paso cuyas dependencias no estén hechas.
"""

PLAN_RULES = """
- Encadena los pasos con `deps` para que cada rama tenga entre 2 y 5 fases; evita ramas de un solo paso gigante.
- `deps` acepta los títulos de pasos del mismo batch. Si la orden falla, lee el error y corrige el JSON.
- Si la petición es una pregunta o un cambio diminuto, contesta sin planificar.
"""

# Bloque gestionado de AGENTS.md: Unificador lo reescribe entero; el resto del fichero es de la persona.
BLOCK_START = "<!-- unificador:inicio (lo mantiene Unificador; los cambios aquí se pierden) -->"
BLOCK_END = "<!-- unificador:fin -->"

AGENTS_BLOCK = f"""{BLOCK_START}
## Trabajo por ramas, fases y pasos (Unificador)

La persona sigue este proyecto en Unificador, que muestra el tablero Kanvas como ramas → fases → pasos,
y también te habla desde la terminal. Trabaja igual en los dos sitios:

1. Al empezar, mira el tablero (`python {KANVAS_REL} status`) y cuéntale a la persona qué le toca revisar,
   qué está en curso y qué sigue.
2. Todo trabajo nuevo que no esté ya en el tablero se planifica antes de programar: propón los pasos con
   **una sola** orden `batch` (llegan como propuestas), resume el plan fase a fase y **para** hasta que la
   persona lo apruebe en Unificador o en el tablero.
3. Haz cada paso con `start` → `note` → `finish` (firma con `--as`); no programes trabajo que no tenga paso.
{PHASES_GUIDE}{PLAN_RULES}{BLOCK_END}"""

CLAUDE_IMPORT = "@AGENTS.md"

HOOK_COMMAND = f'python "$CLAUDE_PROJECT_DIR/{KANVAS_REL}" status'


def _upsert_block(text: str) -> str:
    """Devuelve ``text`` con el bloque gestionado puesto al día (o añadido al final)."""
    start, end = text.find(BLOCK_START), text.find(BLOCK_END)
    if start != -1 and end > start:
        return text[:start] + AGENTS_BLOCK + text[end + len(BLOCK_END):]
    return text.rstrip("\n") + "\n\n" + AGENTS_BLOCK + "\n" if text.strip() else AGENTS_BLOCK + "\n"


def _write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _ensure_agents(root: Path) -> bool:
    p = root / "AGENTS.md"
    old = p.read_text(encoding="utf-8") if p.is_file() else ""
    new = _upsert_block(old)
    if new == old:
        return False
    _write(p, new)
    return True


def _ensure_claude(root: Path) -> bool:
    """Claude Code lee CLAUDE.md, no AGENTS.md: se importa con ``@AGENTS.md``."""
    p = root / "CLAUDE.md"
    old = p.read_text(encoding="utf-8") if p.is_file() else ""
    if CLAUDE_IMPORT in old:
        return False
    _write(p, (old.rstrip("\n") + "\n\n" if old.strip() else "") + CLAUDE_IMPORT + "\n")
    return True


def _ensure_hook(root: Path) -> bool:
    """Hook SessionStart de Claude Code: el estado del tablero entra en el contexto de cada sesión."""
    p = root / ".claude" / "settings.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, ValueError):
        return False  # no se toca un settings.json que no se entiende
    if not isinstance(data, dict):
        return False
    groups = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    if any(h.get("command") == HOOK_COMMAND
           for g in groups if isinstance(g, dict) for h in g.get("hooks", []) if isinstance(h, dict)):
        return False
    groups.append({"hooks": [{"type": "command", "command": HOOK_COMMAND}]})
    p.parent.mkdir(parents=True, exist_ok=True)
    _write(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return True


def ensure_project_files(project_path: str | Path) -> List[str]:
    """Deja el proyecto con las reglas compartidas. Devuelve qué ficheros ha cambiado."""
    root = Path(project_path)
    if not root.is_dir():
        return []
    changed = []
    for name, fn in (("AGENTS.md", _ensure_agents), ("CLAUDE.md", _ensure_claude),
                     (".claude/settings.json", _ensure_hook)):
        try:
            if fn(root):
                changed.append(name)
        except OSError as e:
            changed.append(f"{name} (error: {e})")
    return changed
