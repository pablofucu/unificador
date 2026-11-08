"""Reglas compartidas de ramas/fases/pasos: AGENTS.md, CLAUDE.md, hook y prompt de Unificador."""

import json
import tempfile
import unittest
from pathlib import Path

from unificador import conventions as cv
from unificador.context_injector import ContextInjector
from unificador.models import AgentType, Project


class EnsureProjectFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_project_gets_all_files(self):
        changed = cv.ensure_project_files(self.root)
        self.assertEqual(changed, ["AGENTS.md", "CLAUDE.md", ".claude/settings.json"])
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(cv.BLOCK_START, agents)
        self.assertIn("RAMAS → FASES → PASOS", agents)
        self.assertIn("@AGENTS.md", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        hooks = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(hooks["SessionStart"][0]["hooks"][0]["command"], cv.HOOK_COMMAND)

    def test_idempotent(self):
        cv.ensure_project_files(self.root)
        self.assertEqual(cv.ensure_project_files(self.root), [])

    def test_keeps_user_text_and_replaces_stale_block(self):
        (self.root / "AGENTS.md").write_text(
            f"# Mío\n\nTexto propio.\n\n{cv.BLOCK_START}\nviejo\n{cv.BLOCK_END}\n\nFinal propio.\n", encoding="utf-8")
        cv.ensure_project_files(self.root)
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Texto propio.", text)
        self.assertIn("Final propio.", text)
        self.assertNotIn("viejo", text)
        self.assertEqual(text.count(cv.BLOCK_START), 1)

    def test_merges_existing_settings(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls)"]},
                        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hola"}]}]}}),
            encoding="utf-8")
        cv.ensure_project_files(self.root)
        data = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        cmds = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertEqual(cmds, ["echo hola", cv.HOOK_COMMAND])

    def test_broken_settings_untouched(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text("{roto", encoding="utf-8")
        self.assertNotIn(".claude/settings.json", cv.ensure_project_files(self.root))
        self.assertEqual((self.root / ".claude/settings.json").read_text(encoding="utf-8"), "{roto")


class PromptUsesSameRules(unittest.TestCase):
    def test_gui_prompt_contains_shared_guide_and_plan_rules(self):
        project = Project(id="p", name="P", path=tempfile.gettempdir())
        ctx = ContextInjector().build_context(project, "haz una web", AgentType.CLAUDE_CODE, tasks=[])
        prompt = ctx.final_injected_prompt
        self.assertIn(cv.PHASES_GUIDE.strip(), prompt)
        self.assertIn(cv.PLAN_RULES.strip(), prompt)
        self.assertIn("PRIMERO, PLANIFICA POR FASES", prompt)


if __name__ == "__main__":
    unittest.main()
