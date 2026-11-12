"""Clientes de IA (Claude Code, Antigravity, Codex) y la orden doctor."""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from unificador import agents as G
from unificador import cli
from unificador import rules


class FindTest(unittest.TestCase):
    """Encontrar los clientes aunque la terminal no los tenga en el PATH."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        for target, value in (("shutil.which", lambda name: None), ("pathlib.Path.home", lambda: self.home)):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.home / "L"), "APPDATA": str(self.home / "R")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def exe(self, folder, command):
        path = self.home / folder / (command + (".exe" if sys.platform == "win32" else ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def test_usual_folder_without_path(self):
        self.assertEqual(G.find("claude"), "")
        found = self.exe(".local/bin", "claude")
        self.assertEqual(G.find("claude"), str(found))
        clients = {a["id"]: a for a in G.available()}
        self.assertEqual(list(clients), ["claude", "antigravity", "codex"])
        self.assertEqual((clients["claude"]["installed"], clients["claude"]["path"]), (True, str(found)))
        self.assertFalse(clients["antigravity"]["installed"])
        self.assertFalse(clients["codex"]["installed"])
        codex = self.exe(".npm-global/bin", "codex")
        self.assertEqual(G.find("codex"), str(codex))


class DoctorTest(FindTest):
    def run_doctor(self, root):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.doctor(Path(root))
        return code, out.getvalue()

    def test_reports_all_three_and_missing_client_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as proj:
            code, text = self.run_doctor(proj)
            self.assertEqual(code, 1)  # faltan las reglas
            for name in ("Claude Code", "Antigravity", "Codex"):
                self.assertIn(name, text)
            rules.install(proj)
            code, text = self.run_doctor(proj)
            self.assertEqual(code, 0, text)  # ningún cliente instalado y aun así bien
            self.assertIn("no lo encuentro", text)
            self.assertIn("avisos: al iniciar y en cada mensaje", text)
            self.assertIn("reglas en AGENTS.md", text)

    def test_missing_hook_is_reported(self):
        with tempfile.TemporaryDirectory() as proj:
            rules.install(proj)
            (Path(proj) / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
            code, text = self.run_doctor(proj)
            self.assertEqual(code, 1)
            self.assertIn("faltan CLAUDE.md, las reglas o los avisos", text)


if __name__ == "__main__":
    unittest.main()
