"""Fase 6: conversaciones guardadas, sesiones nativas, aprobar plan y proyectos nuevos."""
import json
import shutil
from pathlib import Path
from unittest import mock

import pytest

from unificador.adapters.antigravity import AntigravityAdapter
from unificador.adapters.claude_code import ClaudeCodeAdapter
from unificador.chats import ChatStore, claude_transcript_path
from unificador.context_injector import ContextInjector, USER_MARKER
from unificador.kanvas_bridge import KanvasBridge
from unificador.models import AgentType, ExecutionContext, Project
from tests.test_in01 import api, call  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parent.parent


def _ctx(tmp_path, agent, session=None):
    p = Project(id="p", name="P", path=str(tmp_path))
    return ExecutionContext(project=p, phase=None, active_task=None, user_prompt="hola",
                            target_agent=agent, final_injected_prompt="hola", native_session_id=session)


def _fake_run(lines):
    """Sustituye run_json_lines: pasa las líneas JSON por el parser del adaptador."""
    def run(cmd, cwd, parse, **kw):
        run.cmd, run.kw = cmd, kw
        for d in lines:
            yield from parse(d)
    return run


# ---------- Adaptadores ----------
def test_claude_parses_stream_and_resumes(tmp_path):
    lines = [
        {"type": "system", "subtype": "init", "session_id": "s"},
        {"type": "stream_event", "event": {"type": "message_start"}},
        {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Ho"}}},
        {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "la"}}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}]}},
        {"type": "stream_event", "event": {"type": "message_start"}},
        {"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hecho"}}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Hecho"},
    ]
    ad = ClaudeCodeAdapter()
    run = _fake_run(lines)
    with mock.patch.object(ad, "_exe", return_value="claude"), \
         mock.patch("unificador.adapters.claude_code.run_json_lines", run):
        evs = list(ad.stream_execute(_ctx(tmp_path, AgentType.CLAUDE_CODE)))
    assert evs[0]["type"] == "session" and "--session-id" in run.cmd and evs[0]["id"] in run.cmd
    assert "".join(e for e in evs if isinstance(e, str)) == "Hola\n\nHecho"
    assert {"type": "tool", "text": "Ejecuta ls"} in evs
    assert run.kw["stdin_text"] == "hola" and run.kw["env_extra"]["KANVAS_AGENT"] == "claude-code"

    run = _fake_run([{"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "mal"}])
    with mock.patch.object(ad, "_exe", return_value="claude"), \
         mock.patch("unificador.adapters.claude_code.run_json_lines", run):
        evs = list(ad.stream_execute(_ctx(tmp_path, AgentType.CLAUDE_CODE, session="abc")))
    assert run.cmd[run.cmd.index("--resume") + 1] == "abc" and "--session-id" not in run.cmd
    assert evs == [{"type": "error", "text": "Claude Code: mal"}]


def test_antigravity_parses_stream_and_resumes(tmp_path):
    lines = [
        {"event": "init", "conversation_id": "conv1"},
        {"event": "step_update", "step_update": {"step_type": "user_input", "step_index": 0}},
        {"event": "step_update", "step_update": {"step_type": "run_command", "step_index": 1, "command": "dir"}},
        {"event": "step_update", "step_update": {"step_type": "run_command", "step_index": 1, "command": "dir"}},
        {"event": "step_update", "step_update": {"step_type": "agent_response", "step_index": 2, "text_delta": "Lis"}},
        {"event": "step_update", "step_update": {"step_type": "agent_response", "step_index": 2, "text_delta": "to"}},
        {"event": "result", "result": {"status": "SUCCESS", "response": "Listo"}},
    ]
    ad = AntigravityAdapter()
    run = _fake_run(lines)
    with mock.patch.object(ad, "_exe", return_value="agy"), \
         mock.patch("unificador.adapters.antigravity.run_json_lines", run):
        evs = list(ad.stream_execute(_ctx(tmp_path, AgentType.ANTIGRAVITY, session="conv0")))
    assert run.cmd[run.cmd.index("--conversation") + 1] == "conv0" and run.cmd[-2:] == ["-p", "hola"]
    assert {"type": "session", "id": "conv1"} in evs
    assert [e for e in evs if isinstance(e, dict) and e["type"] == "tool"] == [{"type": "tool", "text": "Ejecuta dir"}]
    assert "".join(e for e in evs if isinstance(e, str)) == "Listo"


# ---------- Contexto ----------
def test_injector_asks_for_phased_plan_and_shortens_followups(tmp_path):
    proj = Project(id="p", name="P", path=str(tmp_path))
    inj = ContextInjector()
    first = inj.build_context(proj, "haz una app", AgentType.CLAUDE_CODE, tasks=[]).final_injected_prompt
    assert "batch" in first and "deps" in first and "Aprobar plan" in first
    follow = inj.build_context(proj, "y ahora", AgentType.CLAUDE_CODE, tasks=[], followup=True).final_injected_prompt
    assert len(follow) < len(first) and "REGLAS DE SEGUIMIENTO" not in follow
    assert follow.rstrip().endswith(f"{USER_MARKER}\ny ahora")


# ---------- Conversaciones ----------
def test_chat_store_and_claude_sync(tmp_path):
    store = ChatStore(tmp_path / "chats", tmp_path / "claude")
    chat = store.create("p", "claude_code")
    store.append("p", chat["id"], {"role": "user", "content": "primera pregunta"})
    store.append("p", chat["id"], {"role": "assistant", "content": "respuesta"})
    store.update("p", chat["id"], native_session_id="sid")
    assert store.list("p")[0]["title"] == "primera pregunta"

    # La persona sigue la conversación en la terminal de Claude Code
    tpath = claude_transcript_path(str(tmp_path), "sid", tmp_path / "claude")
    tpath.parent.mkdir(parents=True)
    entries = [
        {"type": "user", "message": {"content": f"contexto\n{USER_MARKER}\nprimera pregunta"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "respuesta"}]}},
        {"type": "user", "message": {"content": "segunda desde la terminal"}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hecho"}]}},
    ]
    tpath.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    msgs = store.sync_from_claude("p", chat["id"], str(tmp_path))["messages"]
    assert [m["content"] for m in msgs] == ["primera pregunta", "respuesta", "segunda desde la terminal", "hecho"]
    assert len(store.sync_from_claude("p", chat["id"], str(tmp_path))["messages"]) == 4  # idempotente
    assert store.delete("p", chat["id"]) and store.get("p", chat["id"]) is None


def test_stream_saves_conversation_and_session(api, monkeypatch):  # noqa: F811
    from unificador import server
    seen = []

    class Fake:
        def stream_execute(self, ctx):
            seen.append(ctx)
            yield {"type": "session", "id": "nat-1"}
            yield {"type": "tool", "text": "Edita a.py"}
            yield "listo"

    monkeypatch.setattr(server, "get_adapter", lambda t: Fake())
    base, _ = api
    st, body = call(f"{base}/api/chat/stream", {"project_id": "t", "prompt": "hola", "agent": "claude_code"})
    assert st == 200 and "event: chat" in body and "event: tool" in body
    chat_id = json.loads(body.split("event: chat\ndata: ")[1].split("\n")[0])["id"]
    chat = json.loads(call(f"{base}/api/projects/t/chats/{chat_id}")[1])
    assert chat["native_session_id"] == "nat-1"
    assert [(m["role"], m["content"]) for m in chat["messages"]] == [("user", "hola"), ("assistant", "listo")]
    assert chat["messages"][1]["tools"] == ["Edita a.py"]

    # Segundo mensaje: continúa la sesión nativa con contexto corto
    call(f"{base}/api/chat/stream", {"project_id": "t", "prompt": "otra", "agent": "claude_code", "chat_id": chat_id})
    assert seen[1].native_session_id == "nat-1" and "REGLAS DE SEGUIMIENTO" not in seen[1].final_injected_prompt
    assert len(seen[1].history) == 2  # lo anterior; el mensaje nuevo va aparte
    # Con otro agente, la sesión no se reutiliza
    call(f"{base}/api/chat/stream", {"project_id": "t", "prompt": "y tú", "agent": "deepseek", "chat_id": chat_id})
    assert seen[2].native_session_id is None
    lst = json.loads(call(f"{base}/api/projects/t/chats")[1])["chats"]
    assert lst[0]["id"] == chat_id and lst[0]["count"] == 6
    assert call(f"{base}/api/chat/stream", {"project_id": "t", "prompt": "x", "chat_id": "nope"})[0] == 404


def test_approve_plan_endpoint(api):  # noqa: F811
    base, path = api
    KanvasBridge.init_project(path)
    board = json.loads((path / "kanvas.json").read_text(encoding="utf-8"))
    board["groups"] = [{"id": "AA", "name": "Rama A"}]
    board["tasks"] = [{"id": "AA-01", "title": "Uno", "state": "proposed", "group": "AA"},
                      {"id": "AA-02", "title": "Dos", "state": "proposed", "group": "AA", "deps": ["AA-01"]},
                      {"id": "AA-03", "title": "Tres", "state": "done", "group": "AA"}]
    (path / "kanvas.json").write_text(json.dumps(board), encoding="utf-8")
    st, body = call(f"{base}/api/projects/t/plan/approve", {"ids": ["aa-01"]})
    assert st == 200 and json.loads(body)["approved"] == ["AA-01"]
    st, body = call(f"{base}/api/projects/t/plan/approve", {})
    assert json.loads(body)["approved"] == ["AA-02"]
    states = {t.id: t.state.value for t in KanvasBridge(path).get_phases_and_tasks()[1]}
    assert states == {"AA-01": "todo", "AA-02": "todo", "AA-03": "done"}


def test_new_project_is_ready_to_plan(tmp_path, monkeypatch):
    from unificador import server
    from unificador.config import config
    added = []
    monkeypatch.setattr(config, "get_project", lambda pid: None)
    monkeypatch.setattr(config, "add_project", added.append)
    srv = server.ThreadedHTTPServer(("127.0.0.1", 0), server.UnificadorAPIHandler)
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        target = tmp_path / "nuevo"
        st, body = call(f"http://127.0.0.1:{srv.server_address[1]}/api/projects",
                        {"name": "Nuevo", "path": str(target)})
    finally:
        srv.shutdown()
        srv.server_close()
    assert st == 201, body
    assert (target / "kanvas.json").is_file() and (target / ".agents/skills/kanvas/kanvas.py").is_file()
    assert (target / "AGENTS.md").is_file() and (target / ".git").is_dir()
    assert added and added[0].path == str(target)
