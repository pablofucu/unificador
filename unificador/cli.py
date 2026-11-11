"""
Comando ``unificador``: abre la web del proyecto en el que estás.

    unificador                 abre la carpeta actual
    unificador RUTA            abre otro proyecto
    unificador install [RUTA]  solo deja las reglas y el plan listos, sin abrir la web
    unificador import-kanvas [RUTA] [--force]   convierte un tablero Kanvas en plan
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from unificador import plan as P
from unificador import rules

COMMANDS = ("install", "import-kanvas")


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
        from unificador import kanvas_import
        plan = kanvas_import.import_board(root, force=args.force)
        print(f"Plan creado con {len(plan['branches'])} ramas en {root / P.PLAN_FILE}.")
        return 0
    except (P.PlanError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
