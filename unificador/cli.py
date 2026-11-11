"""
Comando ``unificador``: abre la web del proyecto en el que estás.

    unificador                 abre la carpeta actual
    unificador RUTA            abre otro proyecto
    unificador install [RUTA]  solo deja las reglas y el plan listos, sin abrir la web
    unificador doctor [RUTA]   comprueba que todo está listo y dice qué falta
    unificador import-kanvas [RUTA] [--force]   convierte un tablero Kanvas en plan
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from unificador import plan as P
from unificador import rules

COMMANDS = ("install", "doctor", "import-kanvas")


def _project(path: str) -> Path:
    root = Path(path or ".").resolve()
    if not root.is_dir():
        raise P.PlanError(f"No existe la carpeta {root}.")
    return root


def serve(root: Path, port: int, open_browser: bool) -> int:
    from unificador import agents, app
    changed = rules.install(root)
    server = app.make_server(root, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Unificador · {root.name}")
    if changed:
        print("  Preparado: " + ", ".join(changed))
    print("\n".join(_agent_lines()))
    print(f"  {url}   (Ctrl+C para cerrar)", flush=True)
    agents.warm_up()
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHasta luego.")
    finally:
        server.server_close()
    return 0


def _agent_lines() -> List[str]:
    from unificador import agents
    lines = []
    for a in agents.available():
        if not a["installed"]:
            lines.append(f"  ✘ {a['name']}: no lo encuentro. Instálalo o pega su ruta desde la web (clic en su icono).")
        elif a["id"] == "antigravity" and a["path"].lower().endswith((".cmd", ".bat")):
            lines.append(f"  ! {a['name']}: {a['path']} es un .cmd y no se puede usar con seguridad; hace falta agy.exe.")
        else:
            lines.append(f"  ✔ {a['name']}: {a['path']}")
    return lines


def doctor(root: Path) -> int:
    """Repasa lo que hace falta para que funcione y dice, en llano, qué arreglar."""
    from unificador import agents
    print(f"Unificador · comprobación de {root}")
    lines = _agent_lines()
    print("\n".join(lines))
    ok = any(line.startswith("  ✔") for line in lines)
    if not ok:
        print("    Sin ningún agente no se puede escribir desde la web.")
    pending = rules.missing(root)
    if pending:
        ok = False
        print("  ✘ Faltan las reglas del proyecto (" + ", ".join(pending) + "). Se arregla con: unificador install")
    else:
        print("  ✔ Reglas del proyecto en su sitio (AGENTS.md, CLAUDE.md, .unificador/uni.py)")
        try:
            run = subprocess.run([sys.executable, str(root / rules.UNI_REL), "status"], cwd=str(root),
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
            first = (run.stdout or run.stderr).strip().splitlines()[:1]
            good = run.returncode == 0
        except (OSError, subprocess.SubprocessError) as e:
            first, good = [str(e)], False
        ok = ok and good
        print(f"  {'✔' if good else '✘'} El plan responde: {first[0] if first else '(sin respuesta)'}")
    try:
        subprocess.run(["python", "--version"], capture_output=True, timeout=10, check=True)
        print("  ✔ «python» funciona en la terminal (los agentes lo usan para apuntar el plan)")
    except (OSError, subprocess.SubprocessError):
        ok = False
        print("  ✘ La orden «python» no funciona en la terminal: los agentes no podrán apuntar el plan.")
    if sys.platform == "win32":
        mode = agents.clean_settings(agents_settings(root))["agents"]["antigravity"]["mode"]
        if mode != "auto":
            print("  ! Antigravity no está en modo Autónomo: en Windows no podrá ejecutar órdenes ni apuntar el plan.")
    print("Todo listo." if ok else "Hay cosas que arreglar (arriba, con ✘).")
    return 0 if ok else 1


def agents_settings(root: Path) -> dict:
    import json
    try:
        return json.loads((root / rules.LOCAL_DIR / rules.LOCAL_SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv and argv[0] in COMMANDS else "serve"
    parser = argparse.ArgumentParser(prog="unificador" + ("" if command == "serve" else f" {command}"),
                                     description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=".", help="carpeta del proyecto (por defecto, la actual)")
    if command == "serve":
        from unificador.app import DEFAULT_PORT
        parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"puerto (por defecto {DEFAULT_PORT})")
        parser.add_argument("--no-open", action="store_true", help="no abrir el navegador")
    elif command == "import-kanvas":
        parser.add_argument("--force", action="store_true", help="sustituir el plan que ya haya")
    args = parser.parse_args(argv)
    try:
        root = _project(args.path)
        if command == "serve":
            return serve(root, args.port, not args.no_open)
        if command == "install":
            changed = rules.install(root)
            print("Preparado: " + ", ".join(changed) if changed else "Ya estaba todo al día.")
            return 0
        if command == "doctor":
            return doctor(root)
        from unificador import kanvas_import
        plan = kanvas_import.import_board(root, force=args.force)
        print(f"Plan creado con {len(plan['branches'])} ramas en {root / P.PLAN_FILE}.")
        return 0
    except (P.PlanError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
