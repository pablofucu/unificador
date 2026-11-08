from unittest import mock
from unificador.adapters import ADAPTERS, get_adapter, list_adapters_status
from unificador.adapters.base import BaseAgentAdapter
from unificador.adapters.deepseek import DeepSeekAdapter
from unificador.models import AgentType, ExecutionContext, Project


def _ctx(agent):
    p = Project(id="p", name="P", path=".")
    return ExecutionContext(project=p, phase=None, active_task=None, user_prompt="hola",
                            target_agent=agent, final_injected_prompt="hola")


def test_registry_covers_all_agents():
    for a in AgentType:
        assert isinstance(get_adapter(a), BaseAgentAdapter)
    assert set(list_adapters_status()) == {a.value for a in AgentType}


def test_deepseek_without_key():
    ad = DeepSeekAdapter(api_key="")
    with mock.patch.dict("os.environ", {}, clear=True), \
         mock.patch("unificador.adapters.deepseek.config.get_api_key", return_value=""):
        assert not ad.is_installed()
        assert ad.execute_sync(_ctx(AgentType.DEEPSEEK))[0] == 1


def test_codex_stream_and_sync():
    ad = get_adapter(AgentType.CODEX)
    code, text = ad.execute_sync(_ctx(AgentType.CODEX))
    assert code == 1 and "no puede chatear" in text  # no finge una respuesta
