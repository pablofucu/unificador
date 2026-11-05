"""
Adaptador para DeepSeek API.
Permite llamadas directas por API REST con streaming de respuesta (SSE).
"""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from typing import Generator, Tuple
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter
from unificador.config import config


DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekAdapter(BaseAgentAdapter):
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(AgentType.DEEPSEEK, "DeepSeek API")
        self._api_key = api_key

    @property
    def api_key(self) -> str:
        return self._api_key or config.get_api_key("deepseek") or os.getenv("DEEPSEEK_API_KEY", "")

    def is_installed(self) -> bool:
        # Para DeepSeek solo necesitamos tener configurada la clave API
        return bool(self.api_key.strip())

    def _prepare_payload(self, context: ExecutionContext, stream: bool = False) -> dict:
        system_content = (
            f"Eres DeepSeek Coder, un asistente experto de desarrollo. "
            f"Estás asignado al proyecto '{context.project.name}' en la fase '{context.phase.name if context.phase else 'General'}'.\n"
            f"{context.board_rules}"
        )

        user_content = context.final_injected_prompt

        return {
            "model": "deepseek-coder",
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            "stream": stream,
            "temperature": 0.2
        }

    def execute_sync(self, context: ExecutionContext) -> Tuple[int, str]:
        if not self.is_installed():
            return 1, "Error: No se ha configurado la clave API de DeepSeek (DEEPSEEK_API_KEY)."

        payload = self._prepare_payload(context, stream=False)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                return 0, content
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            return e.code, f"Error HTTP {e.code} de DeepSeek: {err_body}"
        except Exception as e:
            return 1, f"Error de conexión con DeepSeek API: {e}"

    def stream_execute(self, context: ExecutionContext) -> Generator[str, None, None]:
        if not self.is_installed():
            yield "Error: No se ha configurado la clave API de DeepSeek. Por favor, añádela en la configuración.\n"
            return

        payload = self._prepare_payload(context, stream=True)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        req = urllib.request.Request(
            DEEPSEEK_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except Exception:
                            continue
        except Exception as e:
            yield f"\n[DeepSeek Stream Error]: {e}\n"

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        return False, "DeepSeek se ejecuta directamente vía API en la interfaz del Unificador (no tiene aplicación local de escritorio)."
