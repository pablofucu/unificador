"""
Punto de entrada principal para Unificador.
Permite iniciar el servidor backend, registrar proyectos y probar inyecciones de contexto.
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Asegurar que el paquete sea localizable
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from unificador.config import config
from unificador.models import Project, AgentType
from unificador.kanvas_bridge import KanvasBridge
from unificador.context_injector import ContextInjector
from unificador.server import start_server
from unificador.git_service import GitService


def ensure_default_project():
    """Registra el propio proyecto Unificador si la lista está vacía."""
    projects = config.get_projects()
    current_dir = Path(__file__).parent.resolve()
    if not any(Path(p.path).resolve() == current_dir for p in projects):
        default_proj = Project(
            id="unificador",
            name="Unificador",
            path=str(current_dir),
            color_theme="#3b82f6",
            default_agent=AgentType.CLAUDE_CODE
        )
        config.add_project(default_proj)
        print(f"[Init] Proyecto actual registrado como '{default_proj.name}' ({default_proj.path})")


def cmd_serve(args):
    ensure_default_project()
    host = args.host or config.data.get("settings", {}).get("host", "127.0.0.1")
    port = args.port or config.data.get("settings", {}).get("port", 8766)
    start_server(host=host, port=port)


def cmd_register(args):
    target = Path(args.path).resolve()
    if not target.is_dir():
        print(f"Error: La ruta '{args.path}' no existe o no es un directorio.")
        sys.exit(1)

    name = args.name or target.name
    proj_id = args.id or name.lower().replace(" ", "_")
    agent = AgentType(args.agent) if args.agent else AgentType.CLAUDE_CODE

    proj = Project(
        id=proj_id,
        name=name,
        path=str(target),
        color_theme=args.color or "#10b981",
        default_agent=agent
    )
    config.add_project(proj)
    print(f"Proyecto '{name}' registrado con éxito con ID '{proj_id}'.")


def cmd_test_prompt(args):
    ensure_default_project()
    proj = config.get_project(args.project or "unificador")
    if not proj:
        print(f"Error: Proyecto '{args.project}' no encontrado.")
        sys.exit(1)

    agent_type = AgentType(args.agent) if args.agent else proj.default_agent
    bridge = KanvasBridge(proj.path)
    task = bridge.get_task(args.task) if args.task else None
    phases, _ = bridge.get_phases_and_tasks()
    active_phase = next((ph for ph in phases if task and task.group == ph.name), None)

    injector = ContextInjector()
    ctx = injector.build_context(
        project=proj,
        user_prompt=args.prompt,
        target_agent=agent_type,
        phase=active_phase,
        active_task=task
    )

    print("\n" + "=" * 80)
    print(f"PROMPT GENERADO E INYECTADO PARA {agent_type.value.upper()}:")
    print("=" * 80)
    print(ctx.final_injected_prompt)
    print("=" * 80 + "\n")


def cmd_git(args):
    ensure_default_project()
    proj = config.get_project(args.project or "unificador")
    if not proj:
        print(f"Error: Proyecto '{args.project}' no encontrado.")
        sys.exit(1)

    git = GitService(proj.path)
    status = git.get_status()
    print(f"\nEstado de Git para {proj.name} ({status['branch']}):")
    print(f"- Repositorio: {'Sí' if status['is_repo'] else 'No'}")
    print(f"- Limpio: {'Sí' if status['clean'] else 'No'}")
    print(f"- Archivos modificados ({status.get('changed_count', 0)}):")
    for f in status.get("files", []):
        print(f"   [{f['status']}] {f['file']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Unificador - Orquestador Multi-Agente y Tablero por Fases")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # serve
    p_serve = subparsers.add_parser("serve", help="Inicia el servidor API backend")
    p_serve.add_argument("--host", type=str, default="127.0.0.1", help="Host IP")
    p_serve.add_argument("--port", type=int, default=8766, help="Puerto HTTP")
    p_serve.set_defaults(func=cmd_serve)

    # register
    p_reg = subparsers.add_parser("register", help="Registra un nuevo proyecto en Unificador")
    p_reg.add_argument("path", type=str, help="Ruta de la carpeta del proyecto")
    p_reg.add_argument("--name", type=str, help="Nombre del proyecto")
    p_reg.add_argument("--id", type=str, help="ID único")
    p_reg.add_argument("--color", type=str, default="#3b82f6", help="Color distintivo (#hex)")
    p_reg.add_argument("--agent", type=str, choices=[a.value for a in AgentType], default="claude_code")
    p_reg.set_defaults(func=cmd_register)

    # test-prompt
    p_test = subparsers.add_parser("test-prompt", help="Prueba la inyección automática de prompts")
    p_test.add_argument("--prompt", type=str, required=True, help="Texto de la orden del usuario")
    p_test.add_argument("--project", type=str, default="unificador", help="ID del proyecto")
    p_test.add_argument("--task", type=str, help="ID de la tarea activa (ej. MC-02)")
    p_test.add_argument("--agent", type=str, choices=[a.value for a in AgentType], default="claude_code")
    p_test.set_defaults(func=cmd_test_prompt)

    # git-status
    p_git = subparsers.add_parser("git-status", help="Muestra el estado de Git del proyecto")
    p_git.add_argument("--project", type=str, default="unificador", help="ID del proyecto")
    p_git.set_defaults(func=cmd_git)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
