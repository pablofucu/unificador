"""
Adaptador para la API de DeepSeek (chat con streaming SSE).

No tiene herramientas: responde en el chat. Para seguir el hilo se le manda el historial
de la conversación guardada (``context.history``).
"""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from typing import Iterator, Optional, Tuple
from unificador.models import AgentType, ExecutionContext
from unificador.adapters.base import BaseAgentAdapter, Event
from unificador.config import config
from unificador.context_injector import ContextInjector

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
MAX_HISTORY = 20


class DeepSeekAdapter(BaseAgentAdapter):
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(AgentType.DEEPSEEK, "DeepSeek API")
        self._api_key = api_key

    @property
    def api_key(self) -> str:
        return self._api_key or config.get_api_key("deepseek") or os.getenv("DEEPSEEK_API_KEY", "")

    def is_installed(self) -> bool:
        return bool(self.api_key.strip())

    def _prepare_payload(self, context: ExecutionContext, stream: bool = False) -> dict:
        system, user = ContextInjector().format_for_api(context)
        messages = [{"role": "system", "content": system}]
        for m in (context.history or [])[-MAX_HISTORY:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user})
        model = config.get_agent_config(self.agent_type).model or "deepseek-chat"
        return {"model": model, "messages": messages, "stream": stream, "temperature": 0.2}

    def _request(self, payload: dict) -> urllib.request.Request:
        return urllib.request.Request(
            DEEPSEEK_API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})

    def stream_execute(self, context: ExecutionContext) -> Iterator[Event]:
        if not self.is_installed():
            yield {"type": "error", "text": "No se ha configurado la clave API de DeepSeek. Añádela en Ajustes."}
            return
        try:
            with urllib.request.urlopen(self._request(self._prepare_payload(context, True)), timeout=120) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        content = json.loads(data)["choices"][0].get("delta", {}).get("content", "")
                    except (ValueError, KeyError, IndexError):
                        continue
                    if content:
                        yield content
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            yield {"type": "error", "text": f"Error HTTP {e.code} de DeepSeek: {body[:300]}"}
        except Exception as e:
            yield {"type": "error", "text": f"Error de conexión con DeepSeek: {e}"}

    def launch_native_window(self, context: ExecutionContext) -> Tuple[bool, str]:
        return False, "DeepSeek se usa por API desde el chat de Unificador (no tiene aplicación de escritorio)."
