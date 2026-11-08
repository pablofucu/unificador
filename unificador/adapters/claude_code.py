"""
Adaptador para Claude Code (CLI oficial de Anthropic).

Cada conversación de Unificador es una sesión de Claude Code: el primer mensaje la crea con
``--session-id`` y los siguientes la continúan con ``--resume``. Así el agente recuerda el hilo
y la misma sesión aparece en ``claude --resume`` (terminal y cliente de escritorio).
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import uuid
from typing import Any, Dict, Iterator, List, Tuple
from unificador.config import config
from unificador.context_injector import AGENT_SIGNATURES
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter, Event, run_json_lines, short


def describe_tool(name: str, inp: Dict[str, Any]) -> str:
    """Resumen corto de una llamada a herramienta para mostrar en el chat."""
    if not isinstance(inp, dict):
        inp = {}
    target = (inp.get("command") or inp.get("file_path") or inp.get("path") or inp.get("pattern")
              or inp.get("url") or inp.get("description") or "")
    labels = {"Bash": "Ejecuta", "Edit": "Edita", "Write": "Escribe", "Read": "Lee",
              "Grep": "Busca", "Glob": "Busca", "WebFetch": "Abre", "WebSearch": "Busca en la web",
              "TodoWrite": "Actualiza su lista", "Task": "Lanza un subagente", "Agent": "Lanza un subagente"}
    label = labels.get(name, name)
    return f"{label} {short(target, 80)}".strip()


class ClaudeCodeAdapter(BaseAgentAdapter):
    def __init__(self):
        super().__init__(AgentType.CLAUDE_CODE, "Claude Code")

    @property
    def cfg(self):
        return config.get_agent_config(self.agent_type)

    @property
    def cli_command(self) -> str:
        return self.cfg.command or "claude"

    def _exe(self) -> str:
        return shutil.which(self.cli_command) or ""

    def is_installed(self) -> bool:
        return bool(self._exe())

    def build_command(self, context: ExecutionContext, session_id: str, resume: bool) -> List[str]:
        cfg = self.cfg
        cmd = [self._exe() or self.cli_command, "-p", "--output-format", "stream-json",
               "--verbose", "--include-partial-messages"]
        if cfg.permission_mode:
            cmd += ["--permission-mode", cfg.permission_mode]
        if cfg.model:
            cmd += ["--model", cfg.model]
        if resume:
            cmd += ["--resume", session_id]
        else:
            cmd += ["--session-id", session_id]
            title = context.chat_title or context.user_prompt
            cmd += ["-n", short(f"{context.project.name} · {title}", 70)]
        return cmd + list(cfg.extra_args)

    def stream_execute(self, context: ExecutionContext) -> Iterator[Event]:
        if not self.is_installed():
            yield {"type": "error", "text": f"La CLI '{self.cli_command}' no está instalada o no está en el PATH."}
            return
        resume = bool(context.native_session_id)
        sid = context.native_session_id or str(uuid.uuid4())
        if not resume:
            yield {"type": "session", "id": sid}
        state = {"sep": False, "wrote": False}

        def parse(d: Dict[str, Any]):
            t = d.get("type")
            if t == "stream_event":
                ev = d.get("event") or {}
                if ev.get("type") == "message_start" and state["wrote"]:
                    state["sep"] = True
                delta = ev.get("delta") or {}
                if ev.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        if state["sep"]:
                            text, state["sep"] = "\n\n" + text, False
                        state["wrote"] = True
                        yield text
            elif t == "assistant":
                for b in (d.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        yield {"type": "tool", "text": describe_tool(b.get("name", ""), b.get("input"))}
            elif t == "result":
                if d.get("is_error") or d.get("subtype") not in (None, "success"):
                    msg = d.get("result") or "; ".join(map(str, d.get("errors") or [])) or d.get("subtype")
                    yield {"type": "error", "text": f"Claude Code: {msg}"}
                elif not state["wrote"] and d.get("result"):
                    yield d["result"]  # sin mensajes parciales: la respuesta completa al final

        yield from run_json_lines(
            self.build_command(context, sid, resume), str(context.project.path), parse,
            stdin_text=context.final_injected_prompt,
            env_extra={"KANVAS_AGENT": AGENT_SIGNATURES[self.agent_type]}, name="Claude Code")

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        """Abre Claude Code en una terminal: continúa la sesión de la conversación si la hay."""
        if sys.platform != "win32":
            return False, "Lanzador de ventana nativa aún no configurado para este sistema operativo."
        path = str(context.project.path)
        exe = self._exe() or self.cli_command
        env = {**os.environ, "KANVAS_AGENT": AGENT_SIGNATURES[self.agent_type]}
        try:
            if context.native_session_id:
                args = [exe, "--resume", context.native_session_id]
                if shutil.which("wt"):
                    subprocess.Popen(["wt", "-d", path, *args], env=env)
                else:
                    subprocess.Popen(["cmd", "/c", "start", "Claude Code", "/D", path, "cmd", "/k", *args], env=env)
                return True, "Conversación abierta en Claude Code. Lo que escribas allí se verá aquí al volver."
            # Sin sesión todavía: se abre con el contexto del proyecto como primer mensaje
            prompt_file = os.path.join(path, ".unificador_prompt.tmp")
            with open(prompt_file, "w", encoding="utf-8") as f:
                f.write(context.final_injected_prompt)
            ps = ("$p = Get-Content -Raw .unificador_prompt.tmp; Remove-Item .unificador_prompt.tmp; "
                  f"& '{exe}' $p")
            subprocess.Popen(["cmd", "/c", "start", "Claude Code", "/D", path,
                              "powershell", "-NoExit", "-Command", ps], env=env)
            return True, "Claude Code abierto en una terminal con el contexto del proyecto."
        except Exception as e:
            return False, f"Error al abrir la ventana de Claude Code: {e}"
