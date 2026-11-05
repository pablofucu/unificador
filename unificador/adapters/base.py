"""
Clase base para adaptadores de agentes de Inteligencia Artificial.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Generator, Tuple, Optional
from unificador.models import AgentType, ExecutionContext


class BaseAgentAdapter(ABC):
    def __init__(self, agent_type: AgentType, name: str):
        self.agent_type = agent_type
        self.name = name

    @abstractmethod
    def is_installed(self) -> bool:
        """Verifica si la herramienta o CLI está disponible en el sistema."""
        pass

    @abstractmethod
    def execute_sync(self, context: ExecutionContext) -> Tuple[int, str]:
        """Ejecuta la orden en modo no interactivo/síncrono y devuelve el resultado."""
        pass

    @abstractmethod
    def stream_execute(self, context: ExecutionContext) -> Generator[str, None, None]:
        """Ejecuta la orden emitiendo chunks de texto en streaming para el chat."""
        pass

    @abstractmethod
    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        """Abre la aplicación nativa en Windows con la sesión y el prompt preinyectado."""
        pass
