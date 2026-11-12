"""Lo que Unificador instala en cada proyecto."""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from unificador import rules as R


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        home = tempfile.TemporaryDirectory()  # que install no escriba el registro real
        self.addCleanup(home.cleanup)
        self.env = mock.patch.dict(os.environ, {"UNIFICADOR_HOME": home.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_is_complete_and_idempotent(self):
        changed = R.install(self.root)
        self.assertEqual(changed, [".unificador/uni.py", ".unificador/.gitignore", "AGENTS.md",
                                   "CLAUDE.md", ".claude/settings.json", ".codex/hooks.json"])
        self.assertEqual(R.install(self.root), [])
        self.assertEqual(R.missing(self.root), [])
        self.assertIn("@AGENTS.md", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        hooks = json.loads((self.root / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertEqual(hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"], R.HOOK_COMMAND)
        prompt = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertEqual((prompt["type"], prompt["command"], prompt["timeout"]),
                         ("command", R.INBOX_COMMAND, 30))
        self.assertIn(" inbox", prompt["command"])
        codex = json.loads((self.root / ".codex/hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(codex["hooks"]["UserPromptSubmit"][0]["hooks"][0], {
            "type": "command", "command": "python3 .unificador/uni.py inbox",
            "commandWindows": "python .unificador/uni.py inbox", "timeout": 30})
        self.assertEqual(codex["hooks"]["SessionStart"][0]["hooks"][0]["command"],
                         "python3 .unificador/uni.py status")
        self.assertFalse((self.root / ".agents").exists())  # Antigravity: sin ficheros de hooks

    def test_install_keeps_crlf_files_in_crlf(self):
        (self.root / "CLAUDE.md").write_bytes(b"# Proyecto\r\n\r\nReglas.\r\n")
        (self.root / "AGENTS.md").write_bytes(b"# Agentes\n\nLF.\n")
        R.install(self.root)
        claude = (self.root / "CLAUDE.md").read_bytes()
        self.assertIn(b"@AGENTS.md", claude)
        self.assertEqual(claude.count(b"\n"), claude.count(b"\r\n"))
        self.assertNotIn(b"\r\n", (self.root / "AGENTS.md").read_bytes())

    def test_codex_hooks_merge_keeps_foreign_content(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex/hooks.json").write_text(json.dumps({
            "extra": 1, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}],
                                  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "mio"}]}]}}),
            encoding="utf-8")
        R.install(self.root)
        R.install(self.root)
        data = json.loads((self.root / ".codex/hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(data["extra"], 1)
        self.assertEqual(len(data["hooks"]["Stop"]), 1)
        cmds = [h["command"] for g in data["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
        self.assertEqual(cmds, ["mio", R.CODEX_INBOX])

    def test_missing_reports_each_notice_and_rules_text(self):
        self.assertIn(".claude/settings.json", R.missing(self.root))
        self.assertIn(".codex/hooks.json", R.missing(self.root))
        R.install(self.root)
        p = self.root / ".claude/settings.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        del data["hooks"]["UserPromptSubmit"]
        p.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(R.missing(self.root), [".claude/settings.json"])
        self.assertEqual(R.claude_hooks(self.root), {"start": True, "message": False})
        for word in ("inbox", "approve RAMA", "revise RAMA", "ask ", "propose ", "answer P-1", "wait P-1",
                     "AUTOCONTENIDO"):
            self.assertIn(word, R.AGENTS_BLOCK)

    def test_install_registers_the_project(self):
        from unificador import projects
        R.install(self.root)
        self.assertEqual([p["path"] for p in projects.listing()], [os.path.abspath(self.root)])

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
