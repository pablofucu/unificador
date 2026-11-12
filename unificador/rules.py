"""
Lo que Unificador instala dentro de cada proyecto para que Claude Code, Antigravity y Codex
trabajen igual con el mismo plan:

- ``.unificador/uni.py``: copia de ``plan.py`` (un solo fichero, sin dependencias). Viaja con el proyecto.
- Un bloque gestionado en ``AGENTS.md`` con las reglas del plan (ramas → fases → pasos, paradas, propuestas).
- ``CLAUDE.md`` con ``@AGENTS.md`` (Claude Code no lee AGENTS.md por su cuenta).
- Avisos automáticos, para que el agente se entere solo de lo que la persona contesta en la web:
  Claude Code (``.claude/settings.json``): SessionStart (status) y UserPromptSubmit (inbox);
  Codex (``.codex/hooks.json``): lo mismo; Antigravity: sin fichero, se cubre con la regla de AGENTS.md.
- El proyecto se apunta en el registro de proyectos (``projects.py``).

Unificador es un apoyo: nada bloquea; la persona trabaja en el chat de su agente.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from unificador import plan as plan_module
from unificador import projects

LOCAL_DIR = ".unificador"
UNI_REL = f"{LOCAL_DIR}/uni.py"
UNI = f"python {UNI_REL}"

# Bloque gestionado de AGENTS.md: Unificador lo reescribe entero; el resto del fichero es de la persona.
BLOCK_START = "<!-- unificador:inicio (lo mantiene Unificador; los cambios aquí se pierden) -->"
BLOCK_END = "<!-- unificador:fin -->"

AGENTS_BLOCK = f"""{BLOCK_START}
## El plan del proyecto (Unificador)

La persona sigue este proyecto en Unificador, que enseña el plan como **ramas → fases → pasos**.
El plan vive en `{plan_module.PLAN_FILE}` y se toca solo con `{UNI}` (nunca edites el JSON a mano).
Unificador es un apoyo: la persona te habla en tu chat y puede contestar también en la web.
Cuando preguntes algo, pregúntalo SIEMPRE en el chat (y apúntalo con `ask` si quieres que se vea en la web).

- **Al empezar**, mira cómo va: `{UNI} status`. Si un paso dice «PIDE CAMBIOS», atiéndelo lo primero.
- **Al empezar tu turno**, si no te ha llegado ya un aviso automático, ejecuta `{UNI} inbox`:
  imprime lo que la persona dejó en la web (y nada si no hay nada). Hazle caso.
- **Trabajo nuevo** (algo más que una pregunta o un retoque): apúntalo ANTES de empezar, como una rama,
  con esta única orden (vale en PowerShell, cmd y bash; cada cosa entre comillas dobles):

  ```
  {UNI} branch "Carrito de compra" --icon 🛒 --goal "Poder comprar desde la web" --phase "Cimientos" "codigo: Modelo del carrito" "codigo: Guardar y recuperar" "+pruebas: Probar el guardado" --phase "Pagos" "decidir: Elegir pasarela" "codigo: Pasarela de pago"
  ```

  - Una **rama** es una función o un conjunto de cosas que hacer. Detrás de cada `--phase` va el nombre
    de la fase y después sus pasos.
  - Cada **paso** empieza por su categoría: `codigo:`, `interfaz:`, `pruebas:`, `investigar:` o `decidir:`.
    Un `+` delante (`"+pruebas: …"`) = se hace a la vez que el anterior. Sin categoría se rechaza.
    Cambiar la de un paso: `{UNI} cat ID pruebas`.
  - Si una fase no puede empezar hasta que acabe otra (de esta u otra rama):
    `{UNI} after RAMA "Fase" OTRA "Fase de la otra"`.
  - Entre 2 y 4 **fases** por rama, en orden, con un nombre que se reconozca («Cimientos», «Pagos», «Pulido»).
    «Fase 1» o «Etapa 2» se rechazan. **Pasos** pequeños y comprobables, con título corto en lenguaje llano.
  - No pidas permiso ni confirmación para apuntar el plan: hazlo y sigue. La persona te corregirá si algo no encaja.
  - Para añadir un paso suelto a una rama que ya existe: `{UNI} add RAMA "Fase" "codigo: Título"`.
- **En cada paso**: `{UNI} start ID` → trabaja → `{UNI} done ID -m "qué ha cambiado y cómo lo has comprobado"`.
  Cada orden te dice cuál es la siguiente. Termina las fases en orden; si descubres algo que la persona
  deba saber, `{UNI} note ID "…"`.
- **Al cerrar una fase**: pasa `{UNI} check` y arregla sus errores. Después PARA, resume qué se ha hecho y pregunta en el chat si sigues.
  Si dice que sí: `{UNI} approve RAMA`. Si pide cambios: `{UNI} revise RAMA -m "qué quiere cambiar"`.
  Si la rama es «sin paradas», no hace falta preguntar.
- **Dudas con opciones**: ficha fija: contexto corto en `-d` (Markdown ligero, máx. 800), cada opción
  `"Título | qué implica"` y la que recomiendas con `--recommend N` (0 = sin preferencia):
  `{UNI} ask "¿Qué color?" --step ID -d "Por qué importa" --option "Azul | más sobrio" --option "Verde | más contraste" --recommend 1`.
- **Varias propuestas de diseño o estilos**: haz un HTML por propuesta. Cada uno AUTOCONTENIDO
  (CSS y JS dentro del fichero, sin recursos de internet, imágenes como `data:` o SVG en línea),
  que se vea bien a cualquier ancho (móvil incluido), con contenido realista del proyecto,
  y que solo sea distinto lo que cambia entre propuestas. Después:
  `{UNI} propose "Título" --step ID --option "Clara | fondo blanco" a.html --option "Oscura | fondo negro" b.html --recommend 1`
  (un fragmento sin `<html>` se envuelve solo; si carga algo de internet se rechaza con la línea),
  enseña las rutas en el chat y pregunta cuál prefiere.
  Si contesta en el chat: `{UNI} answer P-1 N -m "lo que dijo"`. Para esperar un rato a la web: `{UNI} wait P-1`.
- Firma con `--as <tu nombre>` (por ejemplo `--as claude`) salvo que `UNI_AGENT` ya esté puesto.
- Preguntas y cambios diminutos: contesta sin tocar el plan.
{BLOCK_END}"""

CLAUDE_IMPORT = "@AGENTS.md"
HOOK_COMMAND = f'python "$CLAUDE_PROJECT_DIR/{UNI_REL}" status'
INBOX_COMMAND = f'python "$CLAUDE_PROJECT_DIR/{UNI_REL}" inbox'
HOOK_TIMEOUT = 30
CODEX_FILE = ".codex/hooks.json"
CODEX_STATUS = f"python3 {UNI_REL} status"
CODEX_INBOX = f"python3 {UNI_REL} inbox"
# Hook que instalaba la versión anterior (basada en Kanvas): se sustituye por el nuevo.
OLD_HOOK_COMMAND = 'python "$CLAUDE_PROJECT_DIR/.agents/skills/kanvas/kanvas.py" status'


def _write(path: Path, text: str) -> None:
    # Conserva los finales de línea que ya tuviera el fichero (CRLF o LF).
    eol = "\r\n" if path.is_file() and b"\r\n" in path.read_bytes() else "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline=eol) as f:
        f.write(text)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def upsert_block(text: str) -> str:
    """Devuelve ``text`` con el bloque gestionado puesto al día (o añadido al final)."""
    start, end = text.find(BLOCK_START), text.find(BLOCK_END)
    if start != -1 and end > start:
        return text[:start] + AGENTS_BLOCK + text[end + len(BLOCK_END):]
    return text.rstrip("\n") + "\n\n" + AGENTS_BLOCK + "\n" if text.strip() else AGENTS_BLOCK + "\n"


def _uni_source() -> bytes:
    return Path(plan_module.__file__).read_bytes().replace(b"\r\n", b"\n")


def _ensure_uni(root: Path) -> bool:
    source = _uni_source()
    target = root / UNI_REL
    if target.is_file() and target.read_bytes() == source:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source)
    return True


def _ensure_local_ignore(root: Path) -> bool:
    """Los ajustes locales y el cerrojo del plan no van al repositorio."""
    p = root / LOCAL_DIR / ".gitignore"
    wanted = "local.json\n__pycache__/\n"
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


def _commands(data, event: str) -> List[str]:
    """Las órdenes de un evento de hooks; vacío si el JSON no tiene esa forma."""
    try:
        return [h.get("command") for g in data["hooks"][event] for h in g["hooks"]]
    except (KeyError, TypeError, AttributeError):
        return []


def _add_hook(data: dict, event: str, command: str, extra: dict) -> bool:
    """Pone la orden en el evento si no está, sin tocar lo demás. False si el JSON no tiene la forma esperada."""
    groups = data["hooks"].setdefault(event, [])
    if not isinstance(groups, list):
        return False
    for g in groups:
        if isinstance(g, dict) and isinstance(g.get("hooks"), list):
            g["hooks"] = [h for h in g["hooks"]
                          if not (isinstance(h, dict) and h.get("command") == OLD_HOOK_COMMAND)]
    groups[:] = [g for g in groups if not (isinstance(g, dict) and g.get("hooks") == [])]
    if command not in _commands(data, event):
        groups.append({"hooks": [{"type": "command", "command": command, **extra}]})
    return True


def _ensure_hooks_file(root: Path, rel: str, wanted: list) -> bool:
    """``wanted``: (evento, orden, campos extra). Fusiona con lo que ya haya en el fichero."""
    p = root / rel
    try:
        data = json.loads(_read(p) or "{}")
    except (OSError, ValueError):
        return False  # no se toca un fichero que no se entiende
    if not isinstance(data, dict) or not isinstance(data.setdefault("hooks", {}), dict):
        return False
    before = json.dumps(data, sort_keys=True)
    for event, command, extra in wanted:
        if not _add_hook(data, event, command, extra):
            return False
    if json.dumps(data, sort_keys=True) == before:
        return False
    _write(p, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return True


def _ensure_hook(root: Path) -> bool:
    return _ensure_hooks_file(root, ".claude/settings.json", [
        ("SessionStart", HOOK_COMMAND, {}),
        ("UserPromptSubmit", INBOX_COMMAND, {"timeout": HOOK_TIMEOUT})])


def _ensure_codex(root: Path) -> bool:
    return _ensure_hooks_file(root, CODEX_FILE, [
        ("SessionStart", CODEX_STATUS, {"commandWindows": f"python {UNI_REL} status", "timeout": HOOK_TIMEOUT}),
        ("UserPromptSubmit", CODEX_INBOX, {"commandWindows": f"python {UNI_REL} inbox", "timeout": HOOK_TIMEOUT})])


def _load_json(root: Path, rel: str):
    try:
        return json.loads(_read(root / rel))
    except (OSError, ValueError):
        return {}


def claude_hooks(root: Path) -> dict:
    """Qué avisos de Claude Code hay puestos: ``{"start": bool, "message": bool}``."""
    data = _load_json(root, ".claude/settings.json")
    return {"start": HOOK_COMMAND in _commands(data, "SessionStart"),
            "message": INBOX_COMMAND in _commands(data, "UserPromptSubmit")}


def codex_hooks(root: Path) -> dict:
    """Qué avisos de Codex hay puestos: ``{"start": bool, "message": bool}``."""
    data = _load_json(root, CODEX_FILE)
    return {"start": CODEX_STATUS in _commands(data, "SessionStart"),
            "message": CODEX_INBOX in _commands(data, "UserPromptSubmit")}


STEPS = ((UNI_REL, _ensure_uni), (f"{LOCAL_DIR}/.gitignore", _ensure_local_ignore),
         ("AGENTS.md", _ensure_agents), ("CLAUDE.md", _ensure_claude),
         (".claude/settings.json", _ensure_hook), (CODEX_FILE, _ensure_codex))


def missing(project_path: str | Path) -> List[str]:
    """Qué le falta al proyecto para que los agentes sigan el plan (sin tocar nada)."""
    root = Path(project_path)
    out = []
    target = root / UNI_REL
    if not target.is_file() or target.read_bytes() != _uni_source():
        out.append(UNI_REL)
    if upsert_block(_read(root / "AGENTS.md")) != _read(root / "AGENTS.md"):
        out.append("AGENTS.md")
    if CLAUDE_IMPORT not in _read(root / "CLAUDE.md"):
        out.append("CLAUDE.md")
    if not all(claude_hooks(root).values()):
        out.append(".claude/settings.json")
    if not all(codex_hooks(root).values()):
        out.append(CODEX_FILE)
    return out


def install(project_path: str | Path) -> List[str]:
    """Deja el proyecto listo. Devuelve qué ficheros ha cambiado (vacío si ya estaba al día)."""
    root = Path(project_path)
    if not root.is_dir():
        return []
    changed = []
    try:
        projects.register(root)
    except OSError:
        pass
    for name, fn in STEPS:
        try:
            if fn(root):
                changed.append(name)
        except OSError as e:
            changed.append(f"{name} (error: {e})")
    return changed
