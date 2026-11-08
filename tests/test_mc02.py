import json
from unificador.context_injector import ContextInjector
from unificador.kanvas_bridge import KanvasBridge
from unificador.models import AgentType, Project, TaskState


def make_board(tmp_path):
    board = {
        "groups": [{"id": "AA", "name": "Fase A"}],
        "tasks": [
            {"id": "AA-01", "title": "Uno", "state": "done", "group": "AA"},
            {"id": "AA-02", "title": "Dos", "state": "doing", "group": "AA",
             "deps": ["AA-01"], "desc": "desc",
             "notes": [{"by": "x", "text": "nota"}]},
        ],
    }
    (tmp_path / "kanvas.json").write_text(json.dumps(board), encoding="utf-8")
    return KanvasBridge(tmp_path)


def test_phases_and_progress(tmp_path):
    b = make_board(tmp_path)
    phases, tasks = b.get_phases_and_tasks()
    assert len(phases) == 1 and phases[0].progress_percent == 50.0
    assert b.get_task("AA-02").state == TaskState.DOING
    assert b.get_task("AA-02").depth == 1


def test_injection_and_split(tmp_path):
    b = make_board(tmp_path)
    phases, _ = b.get_phases_and_tasks()
    proj = Project(id="p", name="P", path=str(tmp_path))
    inj = ContextInjector()
    p = inj.build_context(proj, "haz algo", AgentType.CLAUDE_CODE, phases[0], b.get_task("AA-02")).final_injected_prompt
    assert 'kanvas note AA-02 "' in p and "-m" not in p.split("kanvas note")[1].split("\n")[0]
    ctx = inj.build_context(proj, "haz algo", AgentType.DEEPSEEK, phases[0], b.get_task("AA-02"))
    p = ctx.final_injected_prompt
    assert "AA-02" in p and "[x]: nota" in p and "Fase A" in p
    assert "kanvas note" not in p  # DeepSeek no ejecuta comandos
    system, user = inj.format_for_api(ctx)
    assert user == "haz algo" and "Fase A" in system
