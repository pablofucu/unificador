"""
Modelos de datos para el proyecto Unificador.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Dict, Optional, Any
import time


class AgentType(str, Enum):
    ANTIGRAVITY = "antigravity"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    DEEPSEEK = "deepseek"


class TaskState(str, Enum):
    PROPOSED = "proposed"
    TODO = "todo"
    DOING = "doing"
    REVIEW = "review"
    DONE = "done"


@dataclass
class TaskNote:
    text: str
    author: str = "agent"
    time: float = field(default_factory=time.time)


@dataclass
class Task:
    id: str
    title: str
    description: str = ""
    state: TaskState = TaskState.PROPOSED
    group: str = ""
    deps: List[str] = field(default_factory=list)
    notes: List[Dict[str, Any]] = field(default_factory=list)
    depth: int = 0
    assigned_agent: Optional[AgentType] = None


@dataclass
class Phase:
    id: str
    name: str
    order: int
    color_tone: str  # Código hex o hsl representativo
    tasks: List[Task] = field(default_factory=list)
    prefix: str = ""

    @property
    def total_tasks(self) -> int:
        return len(self.tasks)

    @property
    def completed_tasks(self) -> int:
        return sum(1 for t in self.tasks if t.state == TaskState.DONE)

    @property
    def progress_percent(self) -> float:
        if not self.tasks:
            return 0.0
        return round((self.completed_tasks / self.total_tasks) * 100, 1)


@dataclass
class Project:
    id: str
    name: str
    path: str
    color_theme: str = "#3b82f6"  # Color principal del proyecto
    active_phase_id: Optional[str] = None
    default_agent: AgentType = AgentType.CLAUDE_CODE
    git_repo: Optional[str] = None
    git_branch: str = "main"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["default_agent"] = self.default_agent.value
        return d


@dataclass
class ChatMessage:
    role: str  # "user", "assistant", "system"
    content: str
    agent_type: AgentType
    timestamp: float = field(default_factory=time.time)
    task_id: Optional[str] = None
    injected_context: Optional[str] = None


@dataclass
class ExecutionContext:
    project: Project
    phase: Optional[Phase]
    active_task: Optional[Task]
    user_prompt: str
    target_agent: AgentType
    history: List[ChatMessage] = field(default_factory=list)
    board_rules: str = ""
    final_injected_prompt: str = ""
