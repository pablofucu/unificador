"""
Motor de Inyección de Contexto y Prompts para Unificador.
Inyecta automáticamente el estado del proyecto, fase, tarea activa y reglas de Kanvas en el mensaje.

- Primer mensaje de una conversación: contexto completo (proyecto, tablero, reglas, plan por fases).
- Mensajes siguientes de la misma sesión nativa (``followup``): solo lo que ha cambiado,
  porque el agente ya tiene las reglas en su historial.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from unificador.models import Project, Phase, Task, TaskState, AgentType, ExecutionContext
from unificador.conventions import PHASES_GUIDE, PLAN_RULES


USER_MARKER = "[INSTRUCCIÓN DEL USUARIO]:"

AGENT_NAMES = {
    AgentType.CLAUDE_CODE: "Claude Code",
    AgentType.ANTIGRAVITY: "Google Antigravity",
    AgentType.CODEX: "OpenAI Codex / Cursor",
    AgentType.DEEPSEEK: "DeepSeek",
}

# Nombre con el que cada agente firma en Kanvas (se pasa como KANVAS_AGENT al lanzarlo)
AGENT_SIGNATURES = {
    AgentType.CLAUDE_CODE: "claude-code",
    AgentType.ANTIGRAVITY: "gemini",
    AgentType.CODEX: "codex",
    AgentType.DEEPSEEK: "deepseek",
}

SYSTEM_HEADER = """[SISTEMA: CONTEXTO DEL PROYECTO INYECTADO AUTOMÁTICAMENTE POR UNIFICADOR]
Estás colaborando como agente de IA ({agent_name}) en este proyecto. La persona te habla desde
Unificador, una app que muestra el tablero Kanvas del proyecto como ramas, fases y pasos."""

KANVAS_RULES_TEMPLATE = """
### REGLAS DE SEGUIMIENTO EN EL TABLERO (Kanvas):
1. El trabajo de este proyecto vive en `{board_file}`. Cámbialo SOLO con la CLI (`{kanvas}`).
2. Antes de empezar un paso aprobado (estado todo), ejecuta:
   {kanvas} start {task_id} -m "Plan: cómo lo vas a hacer"
3. Para registrar avances mientras trabajas, ejecuta:
   {kanvas} note {task_id} "Descripción concisa de lo implementado"
4. Cuando termines por completo el paso, ejecuta:
   {kanvas} finish {task_id} -m "Qué ha cambiado, cómo lo has comprobado y qué debe revisar la persona"
5. Si necesitas una decisión de la persona, ejecuta `{kanvas} ask {task_id} "Tu pregunta"`, hazle la pregunta en tu respuesta y para.
6. Aprobar propuestas y dar un paso por hecho es cosa de la persona (lo hace desde Unificador). NUNCA edites `kanvas.json` a mano.
"""

PLAN_TEMPLATE = """
### PRIMERO, PLANIFICA POR FASES
{reason} Antes de escribir código, propón el plan en el tablero con UNA sola orden `batch`:

{kanvas} batch <<'EOF'
{{
  "groups": ["Rama A", "Rama B"],
  "tasks": [
    {{"title": "Paso 1 de A", "group": "Rama A", "desc": "Qué consigue y cuándo está terminado"}},
    {{"title": "Paso 2 de A", "group": "Rama A", "deps": ["Paso 1 de A"], "desc": "..."}},
    {{"title": "Paso 1 de B", "group": "Rama B", "desc": "..."}}
  ]
}}
EOF

- En tu respuesta, resume el plan fase por fase y dile a la persona que lo apruebe con «Aprobar plan» en Unificador. Después PARA: no implementes nada hasta que esté aprobado.""" + PLAN_RULES.replace("{", "{{").replace("}", "}}")

NO_TOOLS_NOTE = """
### LIMITACIÓN
No puedes ejecutar comandos ni editar ficheros: responde en el chat. Si hace falta un plan, escríbelo
fase a fase en tu respuesta para que otro agente lo registre en el tablero.
"""

GENERAL_AGENT_RULES = """
### DIRECTRICES DE EJECUCIÓN:
- Trabaja exclusivamente dentro del directorio: `{project_path}`.
- Realiza cambios limpios, modulares y verificables.
- Si ejecutas pruebas o comandos, asegúrate de no romper funcionalidades existentes.
- Responde en español y de forma breve: la persona lee tu respuesta en un chat.
"""


def kanvas_command(project_path: str) -> str:
    """Orden que deben usar los agentes: el kanvas.py del proyecto si existe, si no `kanvas`."""
    local = Path(project_path) / ".agents" / "skills" / "kanvas" / "kanvas.py"
    return "python .agents/skills/kanvas/kanvas.py" if local.is_file() else "kanvas"


def _board_summary(tasks: List[Task]) -> str:
    if not tasks:
        return "- **Tablero:** vacío (sin pasos todavía)."
    count = {s: sum(1 for t in tasks if t.state == s) for s in TaskState}
    parts = [f"{count[TaskState.DONE]} hechos", f"{count[TaskState.DOING]} en curso",
             f"{count[TaskState.REVIEW]} en revisión", f"{count[TaskState.TODO]} aprobados",
             f"{count[TaskState.PROPOSED]} propuestos sin aprobar"]
    lines = [f"- **Tablero:** {len(tasks)} pasos ({', '.join(parts)})."]
    ready = [t for t in tasks if t.state in (TaskState.DOING, TaskState.TODO)][:6]
    if ready:
        lines.append("- **Pasos aprobados o en curso:** " +
                     "; ".join(f"[{t.id}] {t.title} ({t.state.value})" for t in ready))
    return "\n".join(lines)


def _plan_reason(tasks: List[Task]) -> Optional[str]:
    """Motivo para pedir un plan, o None si el tablero ya tiene trabajo por hacer."""
    if not tasks:
        return "El tablero está vacío."
    if all(t.state == TaskState.DONE for t in tasks):
        return "Todo lo planificado está hecho; si la petición es trabajo nuevo, planifícalo."
    return None


class ContextInjector:
    def build_context(
        self,
        project: Project,
        user_prompt: str,
        target_agent: AgentType,
        phase: Optional[Phase] = None,
        active_task: Optional[Task] = None,
        recent_notes: Optional[List[Dict[str, Any]]] = None,
        tasks: Optional[List[Task]] = None,
        followup: bool = False,
    ) -> ExecutionContext:
        """Construye el contexto completo e inyecta el prompt final enriquecido."""
        agent_name = AGENT_NAMES.get(target_agent, target_agent.value)
        kanvas = kanvas_command(project.path)
        task_id = active_task.id if active_task else "<ID>"
        can_run = target_agent != AgentType.DEEPSEEK
        board_file = str(Path(project.path) / "kanvas.json")
        rules = KANVAS_RULES_TEMPLATE.format(board_file=board_file, kanvas=kanvas, task_id=task_id)
        plan_reason = _plan_reason(tasks) if tasks is not None and not active_task else None

        sections: List[str] = []
        if followup:
            sections.append("[UNIFICADOR: estado actual del proyecto; sigue las reglas de Kanvas del principio de esta conversación]")
        else:
            sections += [
                SYSTEM_HEADER.format(agent_name=agent_name),
                f"- **Proyecto:** {project.name}",
                f"- **Ruta local:** `{project.path}`",
                f"- **Rama Git:** `{project.git_branch}`",
            ]
        if tasks is not None:
            sections.append(_board_summary(tasks))
        if phase:
            sections.append(f"- **Rama del paso:** {phase.name} (Progreso: {phase.progress_percent}%)")

        if active_task:
            sections.append(f"\n### PASO ELEGIDO: [{active_task.id}] {active_task.title}")
            sections.append(f"- **Estado:** {active_task.state.value.upper()}")
            if active_task.description:
                sections.append(f"- **Descripción:** {active_task.description}")
            if active_task.deps:
                sections.append(f"- **Dependencias:** {', '.join(active_task.deps)}")
            notes = active_task.notes or (recent_notes or [])
            if notes:
                sections.append("- **Últimas notas registradas en esta tarea:**")
                for n in notes[-3:]:
                    author = n.get("by", n.get("author", "agente"))
                    text = n.get("text", n.get("msg", ""))
                    sections.append(f"  * [{author}]: {text}")
            if active_task.state == TaskState.PROPOSED:
                sections.append("- Este paso aún no está aprobado: puedes revisarlo con "
                                f"`{kanvas} edit {active_task.id}`, pero no lo empieces.")
        elif not followup:
            sections.append("\n### SIN PASO ELEGIDO: la persona habla del proyecto en general.")

        if not followup:
            if can_run:
                sections.append(rules)
            sections.append(PHASES_GUIDE)
        if plan_reason and can_run:
            sections.append(PLAN_TEMPLATE.format(reason=plan_reason, kanvas=kanvas))
        if not can_run and not followup:
            sections.append(NO_TOOLS_NOTE)
        if not followup:
            sections.append(GENERAL_AGENT_RULES.format(project_path=project.path))

        sections.append("=" * 80)
        sections.append(f"{USER_MARKER}\n{user_prompt.strip()}")

        return ExecutionContext(
            project=project,
            phase=phase,
            active_task=active_task,
            user_prompt=user_prompt,
            target_agent=target_agent,
            board_rules=rules,
            final_injected_prompt="\n".join(sections),
        )

    def format_for_cli(self, context: ExecutionContext) -> str:
        """Devuelve el prompt formateado como un solo string seguro para pasar por CLI."""
        return context.final_injected_prompt

    def format_for_api(self, context: ExecutionContext) -> Tuple[str, str]:
        """Separa el contexto en System Prompt y User Prompt para APIs tipo OpenAI/DeepSeek."""
        system_part, sep, user_part = context.final_injected_prompt.partition(USER_MARKER)
        if not sep:
            return context.final_injected_prompt.strip(), context.user_prompt
        return system_part.strip(), user_part.strip()
