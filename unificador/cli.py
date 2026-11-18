"""
Comando ``unificador``: abre la web del proyecto en el que estás.

    unificador                      abre la carpeta actual
    unificador RUTA                 abre otro proyecto
    unificador install [RUTA]       solo deja las reglas y el plan listos, sin abrir la web
    unificador doctor [RUTA]        comprueba que todo está listo y dice qué falta
    unificador import-kanvas [RUTA] [--force]   convierte un tablero Kanvas en plan
    unificador funnel enable|status|off|reset-key  acceso público con Tailscale Funnel y clave
    unificador update [--check] [--auto on|off]  instala la versión nueva, pone al día los proyectos y reinicia
"""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import List, Optional, Tuple

from unificador import funnel
from unificador import plan as P
from unificador import projects
from unificador import rules

COMMANDS = ("install", "doctor", "import-kanvas", "funnel", "update", "restart")


def _project(path: str) -> Path:
    root = Path(path or ".").resolve()
    if not root.is_dir():
        raise P.PlanError(f"No existe la carpeta {root}.")
    return root


def serve(root: Path, port: int, open_browser: bool, host: str = "127.0.0.1",
          tailscale: bool = False, daemon: bool = False) -> int:
    from unificador import app
    changed = rules.install(root)
    try:
        projects.register(root)
        projects.set_active(root)
    except OSError:
        pass
    fcfg = funnel.load_config()
    server = app.make_server(root, port, host=host, tailscale=bool(tailscale or fcfg.get("enabled")))
    actual_port = server.server_address[1]
    from unificador import update
    update.on_start(root, port=actual_port)
    pid = os.getpid()
    official = funnel.home_port()
    if actual_port == official:
        try:
            funnel.register_runtime(actual_port, pid=pid)
        except OSError:
            pass
    elif daemon:
        print(f"Aviso: el puerto {official} está ocupado; este servidor queda en {actual_port} y Funnel no llega aquí.",
              file=sys.stderr, flush=True)
    url = f"http://127.0.0.1:{actual_port}/"
    if not daemon:
        print(f"Unificador · {root.name}")
        if changed:
            print("  Preparado: " + ", ".join(changed))
        print(f"  {url}   (Ctrl+C para cerrar)", flush=True)
        if fcfg.get("enabled") and fcfg.get("public_url"):
            print(f"  {fcfg['public_url']}   (Funnel público, protegido por clave)", flush=True)
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
        if not daemon:
            print("\nHasta luego.")
    finally:
        try:
            funnel.clear_runtime_pid(pid)
        except OSError:
            pass
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
    fcfg = funnel.load_config()
    if fcfg.get("enabled"):
        url = fcfg.get("public_url") or "(sin URL pública todavía)"
        key_ok = funnel.has_key(fcfg)
        print(f"  {'✔' if key_ok else '⚠'} Funnel público: {url}"
              + ("" if key_ok else " (falta clave: unificador funnel reset-key)"))
    else:
        print("  - Funnel público: desactivado (opcional: unificador funnel enable)")
    print("Todo listo." if ok else "Hay cosas que arreglar (arriba, con ✘).")
    return 0 if ok else 1


def _choose_key(raw_key: Optional[str], generate: bool) -> Tuple[Optional[str], bool]:
    """Devuelve ``(clave_en_claro, fue_generada)`` según los flags o entrada interactiva."""
    if raw_key is not None:
        return funnel.set_key(raw_key), False
    if generate or not (sys.stdin and sys.stdin.isatty()):
        return funnel.set_key(None), True
    entered = getpass.getpass("Elige una clave para entrar desde fuera (mín. 6 caracteres, Enter para generar): ")
    if entered.strip():
        return funnel.set_key(entered), False
    return funnel.set_key(None), True


def funnel_command(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(prog="unificador funnel",
                                     description="Configura el acceso público con Tailscale Funnel y clave.")
    sub = parser.add_subparsers(dest="sub", metavar="<acción>")

    p_en = sub.add_parser("enable", help="activa Tailscale Funnel protegido por clave y autoarranque")
    p_en.add_argument("path", nargs="?", default=".", help="carpeta del proyecto (por defecto, la actual)")
    p_en.add_argument("--port", type=int, default=None, help="puerto público de Funnel (443, 8443 o 10000)")
    p_en.add_argument("--local-port", type=int, default=8766, help="puerto local de Unificador (por defecto 8766)")
    p_en.add_argument("--key", default=None, help="clave de acceso remoto (mín. 6 caracteres)")
    p_en.add_argument("--generate", action="store_true", help="genera una clave aleatoria sin preguntar")
    p_en.add_argument("--no-tailscale", action="store_true", help="configura clave y autoarranque sin llamar a tailscale")
    p_en.add_argument("--no-autostart", action="store_true", help="no arrancar automáticamente al trabajar con uni.py")
    p_en.add_argument("--no-serve", action="store_true", help="no arrancar el servidor en segundo plano ahora")

    sub.add_parser("status", help="muestra el estado de Funnel, servidor local y autoarranque")

    p_off = sub.add_parser("off", help="desactiva Tailscale Funnel público")
    p_off.add_argument("--no-tailscale", action="store_true", help="solo desactiva la configuración local")

    p_rk = sub.add_parser("reset-key", help="cambia la clave y cierra todas las sesiones abiertas")
    p_rk.add_argument("--key", default=None, help="nueva clave (mín. 6 caracteres)")
    p_rk.add_argument("--generate", action="store_true", help="genera una nueva clave aleatoria sin preguntar")

    args = parser.parse_args(argv)
    action = args.sub or "status"
    try:
        if action == "status":
            cfg = funnel.load_config()
            srv = funnel.load_server()
            local_port = funnel.home_port()
            alive = funnel.is_server_alive(local_port)
            ts = funnel.tailscale_exe()
            active = projects.active_id()
            print("Unificador · Funnel remoto")
            print(f"  Estado: {'activado' if cfg.get('enabled') else 'desactivado'}")
            print(f"  Clave: {'configurada' if funnel.has_key(cfg) else 'sin configurar'}")
            print(f"  URL pública: {cfg.get('public_url') or '(sin configurar)'}")
            print(f"  Servidor local: {'activo' if alive else 'parado'} (127.0.0.1:{local_port})")
            print(f"  Autoarranque al trabajar: {'sí' if srv.get('autostart') else 'no'}")
            if active:
                p = projects.find(active)
                print(f"  Proyecto activo: {p.name if p else active} [{active}]")
            print(f"  Tailscale CLI: {ts or 'no encontrado'}")
            if ts:
                try:
                    print(f"  MagicDNS: {funnel.tailscale_dns_name(ts)}")
                except funnel.FunnelError as e:
                    print(f"  MagicDNS: {e}")
            return 0

        if action == "enable":
            root = _project(args.path)
            if not (1 <= args.local_port <= 65535):
                raise funnel.FunnelError("El puerto local debe estar entre 1 y 65535.")
            if args.key is not None:
                if not isinstance(args.key, str) or len(args.key.strip()) < funnel.MIN_KEY_LENGTH:
                    raise ValueError(f"La clave debe tener al menos {funnel.MIN_KEY_LENGTH} caracteres.")
            cfg = funnel.load_config()
            if args.no_tailscale:
                chosen_port = args.port or cfg.get("funnel_port") or funnel.DEFAULT_FUNNEL_PORT
                if chosen_port not in funnel.ALLOWED_FUNNEL_PORTS:
                    raise funnel.FunnelError("Funnel solo admite los puertos 443, 8443 o 10000.")
                public_url = cfg.get("public_url") or ""
            else:
                public_url, chosen_port = funnel.configure_tailscale_funnel(args.local_port, args.port)
            shown_key: Optional[str] = None
            generated = False
            if args.key is not None or args.generate or not funnel.has_key(cfg):
                shown_key, generated = _choose_key(args.key, args.generate)
                cfg = funnel.load_config()
            cfg["enabled"] = True
            cfg["server_port"] = int(args.local_port)
            cfg["funnel_port"] = int(chosen_port)
            cfg["public_url"] = public_url
            cfg["hide_paths"] = True
            funnel.save_config(cfg)
            funnel.register_runtime(args.local_port, autostart=not args.no_autostart)
            if (root / P.PLAN_FILE).is_file() or (root / rules.LOCAL_DIR).is_dir():
                projects.register(root)
                projects.set_active(root)
            started = False if args.no_serve else funnel.start_daemon(root, port=args.local_port)
            print("Funnel público activado (puerta cerrada con clave).")
            if public_url:
                print(f"  URL pública: {public_url}")
            print(f"  Local:       http://127.0.0.1:{args.local_port}/")
            print(f"  Autoarranque: {'sí' if not args.no_autostart else 'no'}")
            if not args.no_serve:
                print(f"  Servidor:    {'en marcha' if started else 'no arrancó (revisa server.log)'}")
            if shown_key and generated:
                print(f"  Clave generada (guárdala, no se vuelve a mostrar): {shown_key}")
            elif shown_key:
                print("  Clave guardada (cifrada).")
            return 0

        if action == "off":
            cfg = funnel.load_config()
            if not args.no_tailscale:
                funnel.disable_tailscale_funnel(int(cfg.get("funnel_port") or funnel.DEFAULT_FUNNEL_PORT))
            cfg["enabled"] = False
            funnel.save_config(cfg)
            print("Funnel público desactivado.")
            return 0

        if action == "reset-key":
            key, generated = _choose_key(args.key, args.generate)
            print("Clave actualizada y todas las sesiones remotas cerradas.")
            if generated and key:
                print(f"  Nueva clave (guárdala, no se vuelve a mostrar): {key}")
            return 0
    except (funnel.FunnelError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def update_command(root: Path, check_only: bool, auto: Optional[str]) -> int:
    from unificador import update
    if auto:
        st = update.set_auto(auto == "on")
        print("Actualizar solo: " + ("encendido (al arrancar y una vez al día)." if st["auto"] else "apagado."))
        return 0
    st = update.check(force=True)
    if st["error"]:
        print(f"No se pudo mirar si hay versión nueva: {st['error']}")
        if check_only:
            return 1
    elif not st["available"]:
        print(f"Unificador {st['current']} está al día.")
    elif st["kind"] == "git":
        print(f"Hay {st['behind']} commit(s) nuevos en origin.")
    else:
        print(f"Hay versión nueva: {st['latest']} (tienes {st['current']}).")
    if check_only:
        return 0
    if not st["available"] and not st["error"]:
        changed = update.refresh_all()
        if changed:
            print(f"Puestos al día {len(changed)} proyecto(s).")
        return 0
    try:
        print(update.apply())
    except update.UpdateError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    # El código nuevo ya está en disco: la puesta al día y el reinicio van en un proceso nuevo.
    env = dict(os.environ)
    r = subprocess.run([sys.executable, "-m", "unificador", "restart", str(root), "--refresh"], env=env)
    return r.returncode


def restart_command(root: Path, delay: float, refresh: bool, pid: Optional[int] = None,
                    port: Optional[int] = None) -> int:
    from unificador import update
    if refresh:
        changed = update.refresh_all()
        if changed:
            print(f"Puestos al día {len(changed)} proyecto(s): " + ", ".join(Path(p).name for p in changed))
    ok = update.restart(root, delay=delay, pid=pid, port=port)
    print("Servidor reiniciado." if ok else "El servidor no ha vuelto a arrancar; ábrelo con: unificador")
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv and argv[0] in COMMANDS else "serve"
    if command == "funnel":
        try:
            return funnel_command(argv)
        except (P.PlanError, OSError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser(prog="unificador" + ("" if command == "serve" else f" {command}"),
                                     description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=".", help="carpeta del proyecto (por defecto, la actual)")
    if command == "serve":
        from unificador.app import DEFAULT_PORT
        parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"puerto (por defecto {DEFAULT_PORT})")
        parser.add_argument("--host", default=None, help="dirección IP en la que escuchar (por defecto 127.0.0.1)")
        parser.add_argument("--lan", action="store_true", help="permitir acceso desde otros equipos de la red local (escucha en 0.0.0.0)")
        parser.add_argument("--tailscale", action="store_true", help="aceptar peticiones proxificadas de Tailscale Serve/Funnel")
        parser.add_argument("--daemon", action="store_true", help=argparse.SUPPRESS)
        parser.add_argument("--no-open", action="store_true", help="no abrir el navegador")
    elif command == "update":
        parser.add_argument("--check", action="store_true", help="solo mirar si hay versión nueva")
        parser.add_argument("--auto", choices=("on", "off"), help="encender o apagar «actualizar solo»")
    elif command == "restart":
        parser.add_argument("--delay", type=float, default=0.0, help=argparse.SUPPRESS)
        parser.add_argument("--pid", type=int, default=None, help=argparse.SUPPRESS)
        parser.add_argument("--port", type=int, default=None, help=argparse.SUPPRESS)
        parser.add_argument("--refresh", action="store_true", help="poner al día antes todos los proyectos")
    elif command == "import-kanvas":
        parser.add_argument("--force", action="store_true", help="sustituir el plan que ya haya")
    args = parser.parse_args(argv)
    try:
        root = _project(args.path)
        if command == "serve":
            host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
            return serve(root, args.port, not args.no_open and not args.daemon, host=host,
                         tailscale=args.tailscale, daemon=args.daemon)
        if command == "install":
            changed = rules.install(root)
            print("Preparado: " + ", ".join(changed) if changed else "Ya estaba todo al día.")
            return 0
        if command == "update":
            return update_command(root, args.check, args.auto)
        if command == "restart":
            return restart_command(root, args.delay, args.refresh, args.pid, args.port)
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

