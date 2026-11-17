"""Retoques (tweak) y commits sin apuntar."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from unificador import plan as P
from tests.test_plan import SAMPLE, run

HAS_GIT = shutil.which("git") is not None


def git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)


def commit(folder, name, message):
    (Path(folder) / name).write_text(message, encoding="utf-8")
    git(folder, "add", name)
    git(folder, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)
    return subprocess.run(["git", "-C", str(folder), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


class TweakTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / P.PLAN_FILE
        run(self.path, "plan", stdin=json.dumps(SAMPLE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_tweak_sin_git(self):
        code, out, _ = run(self.path, "tweak", "interfaz: Botón más grande")
        self.assertEqual(code, 0)
        self.assertIn("R-1", out)
        t = P.load(self.path)["tweaks"][0]
        self.assertEqual((t["title"], t["cat"], t["commits"]), ("Botón más grande", "interfaz", []))
        run(self.path, "tweak", "Otro")
        self.assertEqual(P.load(self.path)["tweaks"][1]["id"], "R-2")
        code, out, _ = run(self.path, "tweaks")
        self.assertLess(out.index("R-2"), out.index("R-1"))  # los nuevos primero

    def test_tweak_vacio(self):
        code, _, err = run(self.path, "tweak", "  ")
        self.assertEqual(code, 1)
        self.assertIn("título", err)

    @unittest.skipUnless(HAS_GIT, "sin git")
    def test_commits_sin_apuntar(self):
        git(self.dir, "init", "-q")
        a = commit(self.dir, "a.txt", "Arreglo suelto")
        commit(self.dir, "b.txt", "Modelo del carrito (CDC-1)")
        commit(self.dir, P.PLAN_FILE + ".x", "solo otra cosa")
        loose = P.unlogged_commits(P.load(self.path), self.dir)
        self.assertEqual([c["subject"] for c in loose], ["solo otra cosa", "Arreglo suelto"])
        code, out, _ = run(self.path, "tweak", "Arreglo suelto", "--commit", a[:8])
        self.assertEqual(code, 0)
        self.assertEqual(P.load(self.path)["tweaks"][0]["commits"], [a])
        loose = P.unlogged_commits(P.load(self.path), self.dir)
        self.assertEqual([c["subject"] for c in loose], ["solo otra cosa"])
        self.assertTrue(any("sin apuntar" in i["text"] for i in P.audit_file(self.path)))
        run(self.path, "link", "CDC-2", "HEAD")
        self.assertEqual(P.unlogged_commits(P.load(self.path), self.dir), [])
        code, out, _ = run(self.path, "commits")
        self.assertIn("Todos los commits", out)

    @unittest.skipUnless(HAS_GIT, "sin git")
    def test_from_now_y_solo_plan(self):
        git(self.dir, "init", "-q")
        commit(self.dir, "a.txt", "Viejo")
        run(self.path, "commits", "--from-now")
        self.assertEqual(P.unlogged_commits(P.load(self.path), self.dir), [])
        git(self.dir, "add", P.PLAN_FILE)
        git(self.dir, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "chore: plan")
        self.assertEqual(P.unlogged_commits(P.load(self.path), self.dir), [])  # solo toca el plan
        commit(self.dir, "c.txt", "Nuevo")
        self.assertEqual(len(P.unlogged_commits(P.load(self.path), self.dir)), 1)

    def test_sin_repositorio(self):
        self.assertIsNone(P.unlogged_commits(P.load(self.path), self.dir / "no-existe"))
        code, out, _ = run(self.path, "link", "CDC-1", "HEAD")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
