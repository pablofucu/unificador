"""
Motor de Inyección de Contexto y Prompts para Unificador.
Inyecta automáticamente el estado del proyecto, fase, tarea activa y reglas de Kanvas en el mensaje.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from unificador.models import Project, Phase, Task, AgentType, ExecutionContext


SYSTEM_HEADER = """[SISTEMA: CONTEXTO DEL PROYECTO INYECTADO AUTOMÁTICAMENTE POR UNIFICADOR]
Estás colaborando como agente de IA ({agent_name}) en este proyecto."""

KANVAS_RULES_TEMPLATE = """
### REGLAS DE SEGUIMIENTO EN EL TABLERO (Kanvas):
1. Este proyecto organiza su trabajo a través de Kanvas en `{project_path}\\kanvas.json`.
2. Para registrar avances mientras trabajas, ejecuta en la terminal:
   kanvas note {task_id} -m "Descripción concisa de lo implementado"
3. Cuando termines por completo la tarea actual, ejecuta:
   kanvas finish {task_id} -m "Resumen final de cambios para revisión"
4. Si necesitas hacer una pregunta o pedir una decisión al usuario, ejecuta:
   kanvas ask {task_id} "Tu pregunta aquí"
5. NUNCA edites `kanvas.json` a mano; usa siempre el comando `kanvas`.
"""

GENERAL_AGENT_RULES = """
### DIRECTRICES DE EJECUCIÓN:
- Trabaja exclusivamente dentro del directorio: `{project_path}`.
- Realiza cambios limpios, modulares y verificables.
- Si ejecutas pruebas o comandos, asegúrate de no romper funcionalidades existentes.
"""


class ContextInjector:
    def __init__(self):
        pass

    def build_context(
        self,
        project: Project,
        user_prompt: str,
        target_agent: AgentType,
        phase: Optional[Phase] = None,
        active_task: Optional[Task] = None,
        recent_notes: Optional[List[Dict[str, Any]]] = None
    ) -> ExecutionContext:
        """Construye el contexto completo e inyecta el prompt final enriquecido."""

        agent_names = {
            AgentType.CLAUDE_CODE: "Claude Code",
            AgentType.ANTIGRAVITY: "Google Antigravity",
            AgentType.CODEX: "OpenAI Codex / Cursor",
            AgentType.DEEPSEEK: "DeepSeek Coder"
        }
        agent_name = agent_names.get(target_agent, target_agent.value)

        # 1. Cabecera y datos del proyecto
        sections: List[str] = [
            SYSTEM_HEADER.format(agent_name=agent_name),
            f"- **Proyecto:** {project.name}",
            f"- **Ruta local:** `{project.path}`",
            f"- **Rama Git:** `{project.git_branch}`"
        ]

        # 2. Información de la Fase
        if phase:
            sections.append(f"- **Fase Actual:** {phase.name} (Progreso: {phase.progress_percent}%)")

        # 3. Información de la Tarea Activa
        task_id = "GENERAL"
        if active_task:
            task_id = active_task.id
            sections.append(f"\n### TAREA EN CURSO: [{active_task.id}] {active_task.title}")
            sections.append(f"- **Estado:** {active_task.state.value.upper()}")
            if active_task.description:
                sections.append(f"- **Descripción:** {active_task.description}")
            if active_task.deps:
                sections.append(f"- **Dependencias completadas:** {', '.join(active_task.deps)}")

            # Notas recientes
            notes = active_task.notes or (recent_notes or [])
            if notes:
                sections.append("- **Últimas notas registradas en esta tarea:**")
                for n in notes[-3:]:  # Últimas 3 notas
                    author = n.get("by", n.get("author", "agente"))
                    text = n.get("text", n.get("msg", ""))
                    sections.append(f"  * [{author}]: {text}")

        # 4. Reglas del Tablero Kanvas
        sections.append(KANVAS_RULES_TEMPLATE.format(
            project_path=project.path,
            task_id=task_id
        ))

        # 5. Directrices del agente
        sections.append(GENERAL_AGENT_RULES.format(project_path=project.path))

        sections.append("=" * 80)
        sections.append(f"[INSTRUCCIÓN DEL USUARIO]:\n{user_prompt.strip()}")

        injected_prompt = "\n".join(sections)

        return ExecutionContext(
            project=project,
            phase=phase,
            active_task=active_task,
            user_prompt=user_prompt,
            target_agent=target_agent,
            board_rules=KANVAS_RULES_TEMPLATE.format(project_path=project.path, task_id=task_id),
            final_injected_prompt=injected_prompt
        )

    def format_for_cli(self, context: ExecutionContext) -> str:
        """Devuelve el prompt formateado como un solo string seguro para pasar por CLI."""
        return context.final_injected_prompt

    def format_for_api(self, context: ExecutionContext) -> Tuple[str, str]:
        """Separa el contexto en System Prompt y User Prompt para APIs tipo OpenAI/DeepSeek."""
        parts = context.final_injected_prompt.split("[INSTRUCCIÓN DEL USUARIO]:")
        system_part = parts[0].strip()
        user_part = parts[1].strip() if len(parts) > 1 else context.user_prompt
        return system_part, user_part
