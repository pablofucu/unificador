"""
Lo que Unificador instala dentro de cada proyecto para que cualquier IA trabaje igual
desde la web, la terminal o la app de escritorio:

- ``.unificador/uni.py``: copia de ``plan.py`` (un solo fichero, sin dependencias). Viaja con el proyecto.
- Un bloque gestionado en ``AGENTS.md`` con las reglas del plan (ramas → fases → pasos).
- ``CLAUDE.md`` con ``@AGENTS.md`` (Claude Code no lee AGENTS.md por su cuenta).
- Un hook SessionStart de Claude Code que enseña el plan al empezar cada sesión.

No hay aprobaciones: la IA planifica y sigue; la persona corrige cuando quiere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from unificador import plan as plan_module

LOCAL_DIR = ".unificador"
UNI_REL = f"{LOCAL_DIR}/uni.py"
UNI = f"python {UNI_REL}"
LOCAL_SETTINGS = "local.json"  # ajustes de esta máquina (modelo elegido…): no se comparten

# Bloque gestionado de AGENTS.md: Unificador lo reescribe entero; el resto del fichero es de la persona.
BLOCK_START = "<!-- unificador:inicio (lo mantiene Unificador; los cambios aquí se pierden) -->"
BLOCK_END = "<!-- unificador:fin -->"

AGENTS_BLOCK = f"""{BLOCK_START}
## El plan del proyecto (Unificador)

La persona sigue este proyecto en Unificador, que enseña el plan como **ramas → fases → pasos**.
El plan vive en `{plan_module.PLAN_FILE}` y se toca solo con `{UNI}` (nunca edites el JSON a mano).
Vale igual si te hablan desde la web, la terminal o la app.

- **Al empezar**, mira cómo va: `{UNI} status`. Si un paso dice «PIDE CAMBIOS», atiéndelo lo primero.
- **Trabajo nuevo** (algo más que una pregunta o un retoque): apúntalo como una rama y ponte con él.
  No hace falta que nadie lo apruebe; la persona te corregirá si algo no le encaja.

  ```
  {UNI} plan <<'EOF'
  {{"branches": [{{
    "name": "Carrito de compra", "icon": "🛒", "goal": "Poder comprar desde la web",
    "phases": [
      {{"name": "Cimientos", "steps": [{{"title": "Modelo del carrito", "desc": "Hecho cuando se guarda y se recupera"}}]}},
      {{"name": "Pagos", "steps": [{{"title": "Pasarela de pago"}}, {{"title": "Recibo por correo"}}]}}
    ]}}]}}
  EOF
  ```

  - Una **rama** es un cambio o un área que avanza por su cuenta. Ponle un emoji en `icon`.
  - Entre 2 y 4 **fases** por rama, en orden, con un nombre que se reconozca de un vistazo
    («Cimientos», «Pagos», «Pulido»). «Fase 1» o «Etapa 2» se rechazan.
  - **Pasos** pequeños y comprobables, con título corto en lenguaje llano.
  - Para añadir un paso suelto a una rama que ya existe: `{UNI} add RAMA "Fase" "Título" -d "…"`.
- **En cada paso**: `{UNI} start ID` → trabaja → `{UNI} done ID -m "qué ha cambiado y cómo lo has comprobado"`.
  Si descubres algo que la persona deba saber, `{UNI} note ID "…"`. Termina las fases en orden.
- Firma con `--as <tu nombre>` (por ejemplo `--as claude`) salvo que `UNI_AGENT` ya esté puesto.
- Preguntas y cambios diminutos: contesta sin tocar el plan.
{BLOCK_END}"""

CLAUDE_IMPORT = "@AGENTS.md"
HOOK_COMMAND = f'python "$CLAUDE_PROJECT_DIR/{UNI_REL}" status'
# Hook que instalaba la versión anterior (basada en Kanvas): se sustituye por el nuevo.
OLD_HOOK_COMMAND = 'python "$CLAUDE_PROJECT_DIR/.agents/skills/kanvas/kanvas.py" status'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def upsert_block(text: str) -> str:
    """Devuelve ``text`` con el bloque gestionado puesto al día (o añadido al final)."""
    start, end = text.find(BLOCK_START), text.find(BLOCK_END)
    if start != -1 and end > start:
        return text[:start] + AGENTS_BLOCK + text[end + len(BLOCK_END):]
    return text.rstrip("\n") + "\n\n" + AGENTS_BLOCK + "\n" if text.strip() else AGENTS_BLOCK + "\n"


def _ensure_uni(root: Path) -> bool:
    source = Path(plan_module.__file__).read_bytes().replace(b"\r\n", b"\n")
    target = root / UNI_REL
    if target.is_file() and target.read_bytes() == source:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source)
    return True


def _ensure_local_ignore(root: Path) -> bool:
    """Los ajustes locales y el cerrojo del plan no van al repositorio."""
    p = root / LOCAL_DIR / ".gitignore"
    wanted = f"{LOCAL_SETTINGS}\n__pycache__/\n"
    if _read(p) == wanted:
        return False
    _write(p, wanted)
    return True


def _ensure_agents(root: Path) -> bool:
    p = root / "AGENTS.md"
    old = _read(p)
    new = upsert_block(old)
    if new == old:
        return False
    _write(p, new)
    return True


def _ensure_claude(root: Path) -> bool:
    p = root / "CLAUDE.md"
    old = _read(p)
    if CLAUDE_IMPORT in old:
        return False
    _write(p, (old.rstrip("\n") + "\n\n" if old.strip() else "") + CLAUDE_IMPORT + "\n")
    return True


def _ensure_hook(root: Path) -> bool:
    p = root / ".claude" / "settings.json"
    try:
        data = json.loads(_read(p) or "{}")
    except (OSError, ValueError):
        return False  # no se toca un settings.json que no se entiende
    if not isinstance(data, dict) or not isinstance(data.setdefault("hooks", {}), dict):
        return False
    groups = data["hooks"].setdefault("SessionStart", [])
    if not isinstance(groups, list):
        return False
    before = json.dumps(data, sort_keys=True)
    found = False
    for g in groups:
        if not isinstance(g, dict) or not isinstance(g.get("hooks"), list):
            continue
        g["hooks"] = [h for h in g["hooks"]
                      if not (isinstance(h, dict) and h.get("command") == OLD_HOOK_COMMAND)]
        found = found or any(isinstance(h, dict) and h.get("command") == HOOK_COMMAND for h in g["hooks"])
    groups[:] = [g for g in groups if not (isinstance(g, dict) and g.get("hooks") == [])]
    if not found:
        groups.append({"hooks": [{"type": "command", "command": HOOK_COMMAND}]})
    if json.dumps(data, sort_keys=True) == before:
        return False
    _write(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return True


STEPS = ((UNI_REL, _ensure_uni), (f"{LOCAL_DIR}/.gitignore", _ensure_local_ignore),
         ("AGENTS.md", _ensure_agents), ("CLAUDE.md", _ensure_claude),
         (".claude/settings.json", _ensure_hook))


def install(project_path: str | Path) -> List[str]:
    """Deja el proyecto listo. Devuelve qué ficheros ha cambiado (vacío si ya estaba al día)."""
    root = Path(project_path)
    if not root.is_dir():
        return []
    changed = []
    for name, fn in STEPS:
        try:
            if fn(root):
                changed.append(name)
        except OSError as e:
            changed.append(f"{name} (error: {e})")
    return changed
