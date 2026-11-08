"""
Adaptador para Google Antigravity (CLI ``agy``).

``agy -p --output-format stream-json`` da el id de la conversación en el evento ``init``; los
mensajes siguientes la continúan con ``--conversation <id>``. La conversación queda en el
historial de la CLI (``~/.gemini/antigravity-cli``) y se puede retomar en una terminal.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, Iterator, List, Tuple
from unificador.config import config
from unificador.context_injector import AGENT_SIGNATURES
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter, Event, run_json_lines, short

# agy en Windows recibe el prompt como argumento: por encima de esto se pasa por fichero
MAX_ARG_PROMPT = 24000
PERMISSION_MODES = {"auto": "auto", "acceptEdits": "accept-edits", "accept-edits": "accept-edits", "plan": "plan"}
STEP_LABELS = {"run_command": "Ejecuta", "write_to_file": "Escribe", "replace_file_content": "Edita",
               "multi_replace_file_content": "Edita", "view_file": "Lee", "list_dir": "Mira la carpeta",
               "grep_search": "Busca", "find_by_name": "Busca", "search_web": "Busca en la web",
               "read_url_content": "Abre"}
# Pasos internos de agy que no son acciones del agente
HIDDEN_STEPS = {"user_input", "system_message", "ephemeral_message", "checkpoint", "conversation_history",
                "planner_response", "error_message"}


class AntigravityAdapter(BaseAgentAdapter):
    def __init__(self):
        super().__init__(AgentType.ANTIGRAVITY, "Google Antigravity")

    @property
    def cfg(self):
        return config.get_agent_config(self.agent_type)

    @property
    def cli_command(self) -> str:
        return self.cfg.command or "agy"

    def _exe(self) -> str:
        return shutil.which(self.cli_command) or ""

    def is_installed(self) -> bool:
        return bool(self._exe())

    def build_command(self, context: ExecutionContext) -> List[str]:
        cfg = self.cfg
        cmd = [self._exe() or self.cli_command, "--output-format", "stream-json"]
        mode = PERMISSION_MODES.get(cfg.permission_mode)
        if cfg.permission_mode == "bypassPermissions":
            cmd.append("--dangerously-skip-permissions")
        elif mode:
            cmd += ["--mode", mode]
        if cfg.model:
            cmd += ["--model", cfg.model]
        if context.native_session_id:
            cmd += ["--conversation", context.native_session_id]
        prompt = context.final_injected_prompt
        if len(prompt) > MAX_ARG_PROMPT:
            path = os.path.join(str(context.project.path), ".unificador_prompt.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(prompt)
            prompt = ("Lee el fichero .unificador_prompt.md de la raíz del proyecto: contiene tu contexto "
                      "y la instrucción de la persona. Síguelo y después bórralo.")
        return cmd + list(cfg.extra_args) + ["-p", prompt]

    def stream_execute(self, context: ExecutionContext) -> Iterator[Event]:
        if not self.is_installed():
            yield {"type": "error", "text": f"La CLI '{self.cli_command}' de Antigravity no está instalada o no está en el PATH."}
            return
        seen_steps = set()
        state = {"session": context.native_session_id, "wrote": False}

        def parse(d: Dict[str, Any]):
            ev = d.get("event")
            cid = d.get("conversation_id") or (d.get(ev) or {}).get("conversation_id") if ev else None
            if cid and cid != state["session"]:
                state["session"] = cid
                yield {"type": "session", "id": cid}
            if ev == "step_update":
                s = d.get("step_update") or {}
                kind = s.get("step_type", "")
                if kind == "agent_response":
                    if s.get("text_delta"):
                        state["wrote"] = True
                        yield s["text_delta"]
                elif kind and kind not in HIDDEN_STEPS and s.get("step_index") not in seen_steps:
                    seen_steps.add(s.get("step_index"))
                    label = STEP_LABELS.get(kind, kind.replace("_", " "))
                    detail = s.get("command") or s.get("file_path") or s.get("summary") or ""
                    yield {"type": "tool", "text": short(f"{label} {detail}".strip())}
            elif ev == "result":
                r = d.get("result") or {}
                if r.get("status") not in (None, "SUCCESS"):
                    yield {"type": "error", "text": f"Antigravity: {r.get('response') or r.get('status')}"}
                elif not state["wrote"] and r.get("response"):
                    yield r["response"]

        yield from run_json_lines(
            self.build_command(context), str(context.project.path), parse,
            env_extra={"KANVAS_AGENT": AGENT_SIGNATURES[self.agent_type]}, name="Antigravity")

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        """Continúa la conversación en una terminal con `agy`, o abre el IDE si no hay conversación."""
        if sys.platform != "win32":
            return False, "Plataforma no soportada para lanzamiento nativo."
        path = str(context.project.path)
        env = {**os.environ, "KANVAS_AGENT": AGENT_SIGNATURES[self.agent_type]}
        try:
            if context.native_session_id and self.is_installed():
                args = [self._exe(), "--conversation", context.native_session_id]
                if shutil.which("wt"):
                    subprocess.Popen(["wt", "-d", path, *args], env=env)
                else:
                    subprocess.Popen(["cmd", "/c", "start", "Antigravity", "/D", path, "cmd", "/k", *args], env=env)
                return True, "Conversación abierta en Antigravity (terminal)."
            ide = shutil.which("antigravity-ide") or shutil.which("antigravity")
            if ide:
                subprocess.Popen([ide, path], env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return True, "Proyecto abierto en Antigravity."
            return False, "No se encuentra Antigravity en este ordenador."
        except Exception as e:
            return False, f"Error al lanzar Antigravity: {e}"
