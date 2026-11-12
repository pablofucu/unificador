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
import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional

from unificador import plan as P
from unificador import projects
from unificador import rules

COMMANDS = ("install", "doctor", "import-kanvas")


def _project(path: str) -> Path:
    root = Path(path or ".").resolve()
    if not root.is_dir():
        raise P.PlanError(f"No existe la carpeta {root}.")
    return root


def serve(root: Path, port: int, open_browser: bool, host: str = "127.0.0.1") -> int:
    from unificador import app
    changed = rules.install(root)
    try:
        projects.register(root)
    except OSError:
        pass
    server = app.make_server(root, port, host=host)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"
    print(f"Unificador · {root.name}")
    if changed:
        print("  Preparado: " + ", ".join(changed))
    print(f"  {url}   (Ctrl+C para cerrar)", flush=True)
    if host not in ("127.0.0.1", "localhost", "::1"):
        import socket
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if not ip.startswith("127."):
                    print(f"  http://{ip}:{actual_port}/   (desde otros equipos)")
        except Exception:
            pass
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


def _client_lines(root: Path) -> List[str]:
    """Una línea por cliente: (¿listo?, texto). Que falte un cliente no es un error."""
    from unificador import agents
    out = []
    for c in agents.available():
        where = f"{c['path']}" if c["installed"] else "no lo encuentro (no pasa nada si no lo usas)"
        out.append(f"{'✔' if c['installed'] else '-'} {c['name']} ({c['command']}): {where}")
        out.append(f"    {_rules_line(root, c['id'])}")
    return out


def _rules_line(root: Path, client: str) -> str:
    missing = rules.missing(root)
    fix = " (unificador install)"
    if client == "claude":
        h = rules.claude_hooks(root)
        if "CLAUDE.md" in missing or "AGENTS.md" in missing or not all(h.values()):
            return "✘ faltan CLAUDE.md, las reglas o los avisos de .claude/settings.json" + fix
        return "✔ reglas en CLAUDE.md; avisos: al iniciar y en cada mensaje (.claude/settings.json)"
    if "AGENTS.md" in missing:
        return "✘ faltan las reglas en AGENTS.md" + fix
    if client == "codex":
        h = rules.codex_hooks(root)
        if not all(h.values()):
            return "✘ falta el fichero de avisos .codex/hooks.json" + fix
        return ("✔ reglas en AGENTS.md; avisos en .codex/hooks.json "
                "(la primera vez hay que darlos por buenos con /hooks dentro de Codex)")
    if client == "antigravity":
        return "✔ reglas en AGENTS.md; se entera de la web por las reglas (ejecuta inbox al empezar)"
    return "✔ reglas en AGENTS.md"


def doctor(root: Path) -> int:
    """Repasa lo que hace falta para que funcione y dice, en llano, qué arreglar."""
    print(f"Unificador · comprobación de {root}")
    ok = True
    for line in _client_lines(root):
        print("  " + line)
        ok = ok and "✘" not in line
    pending = rules.missing(root)
    if pending:
        ok = False
        print("  ✘ Faltan las reglas del proyecto (" + ", ".join(pending) + "). Se arregla con: unificador install")
    else:
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
    print("Todo listo." if ok else "Hay cosas que arreglar (arriba, con ✘).")
    return 0 if ok else 1


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
        parser.add_argument("--host", default=None, help="dirección IP en la que escuchar (por defecto 127.0.0.1)")
        parser.add_argument("--lan", action="store_true", help="permitir acceso desde otros equipos de la red local (escucha en 0.0.0.0)")
        parser.add_argument("--no-open", action="store_true", help="no abrir el navegador")
    elif command == "import-kanvas":
        parser.add_argument("--force", action="store_true", help="sustituir el plan que ya haya")
    args = parser.parse_args(argv)
    try:
        root = _project(args.path)
        if command == "serve":
            host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
            return serve(root, args.port, not args.no_open, host=host)
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
