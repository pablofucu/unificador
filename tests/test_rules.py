"""Lo que Unificador instala en cada proyecto."""

import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from unificador import rules as R


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_is_complete_and_idempotent(self):
        changed = R.install(self.root)
        self.assertEqual(changed, [".unificador/uni.py", ".unificador/.gitignore", "AGENTS.md",
                                   "CLAUDE.md", ".claude/settings.json"])
        self.assertEqual(R.install(self.root), [])
        self.assertIn("@AGENTS.md", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        hooks = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"], R.HOOK_COMMAND)

    def test_copied_cli_works_alone_and_example_in_rules_is_valid(self):
        R.install(self.root)
        block = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        line = next(l for l in block.splitlines() if " branch " in l and "--phase" in l)
        example = shlex.split(line.strip())[2:]  # la orden tal cual sale en las reglas, sin «python uni.py»
        self.assertNotIn("<<", block)  # nada que solo valga en bash
        run = lambda *a, **k: subprocess.run(
            [sys.executable, "-X", "utf8", R.UNI_REL, *a], cwd=self.root, capture_output=True,
            text=True, encoding="utf-8", **k)
        made = run("--as", "claude", *example)
        self.assertEqual(made.returncode, 0, made.stderr)
        self.assertEqual(run("start", "CDC-1").returncode, 0)
        status = run("status")
        self.assertIn("Carrito de compra", status.stdout)
        self.assertTrue((self.root / "unificador.json").is_file())

    def test_keeps_the_persons_text_and_replaces_old_block_and_hook(self):
        (self.root / "AGENTS.md").write_text(
            f"# Mis reglas\n\n{R.BLOCK_START}\nviejo kanvas batch\n{R.BLOCK_END}\n\nFinal mío\n", encoding="utf-8")
        (self.root / "CLAUDE.md").write_text("Notas\n\n@AGENTS.md\n", encoding="utf-8")
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text(json.dumps({
            "permissions": {"allow": ["Bash(ls)"]},
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": R.OLD_HOOK_COMMAND}]},
                                       {"hooks": [{"type": "command", "command": "echo hola"}]}]}}),
            encoding="utf-8")
        changed = R.install(self.root)
        self.assertNotIn("CLAUDE.md", changed)
        text = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Mis reglas"))
        self.assertIn("Final mío", text)
        self.assertNotIn("kanvas", text.lower())
        self.assertEqual(text.count(R.BLOCK_START), 1)
        data = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        commands = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
        self.assertEqual(commands, ["echo hola", R.HOOK_COMMAND])
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})

    def test_unreadable_settings_are_left_alone(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude/settings.json").write_text("{roto", encoding="utf-8")
        self.assertNotIn(".claude/settings.json", R.install(self.root))
        self.assertEqual((self.root / ".claude/settings.json").read_text(encoding="utf-8"), "{roto")

    def test_outdated_cli_copy_is_refreshed(self):
        R.install(self.root)
        (self.root / R.UNI_REL).write_text("# viejo\n", encoding="utf-8")
        self.assertEqual(R.install(self.root), [R.UNI_REL])


if __name__ == "__main__":
    unittest.main()
