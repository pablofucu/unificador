"""
Registro y factoría de adaptadores de agentes.
"""

from __future__ import annotations
from typing import Dict
from unificador.models import AgentType
from unificador.adapters.base import BaseAgentAdapter
from unificador.adapters.claude_code import ClaudeCodeAdapter
from unificador.adapters.antigravity import AntigravityAdapter
from unificador.adapters.codex import CodexAdapter
from unificador.adapters.deepseek import DeepSeekAdapter


ADAPTERS: Dict[AgentType, BaseAgentAdapter] = {
    AgentType.CLAUDE_CODE: ClaudeCodeAdapter(),
    AgentType.ANTIGRAVITY: AntigravityAdapter(),
    AgentType.CODEX: CodexAdapter(),
    AgentType.DEEPSEEK: DeepSeekAdapter()
}


def get_adapter(agent_type: AgentType) -> BaseAgentAdapter:
    if agent_type in ADAPTERS:
        return ADAPTERS[agent_type]
    raise ValueError(f"No existe adaptador registrado para {agent_type}")


def list_adapters_status() -> Dict[str, Dict[str, any]]:
    result = {}
    for agent_type, adapter in ADAPTERS.items():
        result[agent_type.value] = {
            "name": adapter.name,
            "installed": adapter.is_installed()
        }
    return result
