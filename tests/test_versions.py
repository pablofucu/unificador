"""Versiones (SemVer) y novedades: apuntar, cerrar fase, sacar versión."""

import json
import tempfile
import unittest
from pathlib import Path

from unificador import plan as P
from tests.test_plan import SAMPLE, run


class Versions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / P.PLAN_FILE
        run(self.path, "plan", stdin=json.dumps(SAMPLE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_apuntar_y_listar(self):
        code, out, err = run(self.path, "news", "Ya se puede pagar con tarjeta")
        self.assertEqual(code, 0, err)
        run(self.path, "news", "El total no redondeaba", "--kind", "fix")
        news = P.load(self.path)["news"]
        self.assertEqual([n["kind"] for n in news], ["nuevo", "arreglo"])
        out = run(self.path, "news")[1]
        self.assertIn("Próxima versión: 0.1.0", out)
        self.assertIn("pagar con tarjeta", out)
        self.assertEqual(run(self.path, "news", "x", "--kind", "raro")[0], 1)
        self.assertIn("Aún no hay versiones", run(self.path, "versions")[1])

    def test_semver(self):
        plan = {"news": []}
        self.assertEqual(P.next_version(plan), "0.1.0")
        P.add_news(plan, "Algo", "nuevo")
        v = P.cut_version(plan)
        self.assertEqual((v["version"], plan["news"]), ("0.1.0", []))
        P.add_news(plan, "Un arreglo", "arreglo")
        self.assertEqual(P.next_version(plan), "0.1.1")
        P.add_news(plan, "Una fase", "fase")
        self.assertEqual(P.next_version(plan), "0.2.0")
        self.assertEqual(P.next_version(plan, "major"), "1.0.0")
        with self.assertRaises(P.PlanError):
            P.cut_version(plan, "0.0.9")  # no puede ir hacia atrás
        with self.assertRaises(P.PlanError):
            P.cut_version(plan, "dos")
        self.assertEqual(P.cut_version(plan, "v1.0.0")["version"], "1.0.0")
        with self.assertRaises(P.PlanError):
            P.cut_version(plan)  # sin novedades
        self.assertIn("1.0.0", P.render_versions(plan))

    def test_fase_cerrada_es_novedad(self):
        plan = P.load(self.path)
        branch = plan["branches"][0]
        phase = branch["phases"][0]
        for st in phase["steps"]:
            P.set_state(plan, st["id"], P.DONE, text="hecho")
        news = [n for n in plan.get("news", []) if n["kind"] == "fase"]
        self.assertEqual(len(news), 1)
        self.assertIn(phase["name"], news[0]["text"])
        # reabrir y volver a cerrar no la repite
        sid = phase["steps"][0]["id"]
        P.set_state(plan, sid, P.PENDING)
        P.set_state(plan, sid, P.DONE, text="otra vez")
        self.assertEqual(len([n for n in plan["news"] if n["kind"] == "fase"]), 1)

    def test_release_con_tag_y_lo_no_publicado(self):
        import subprocess
        d = self.path.parent
        g = lambda *a: subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True).stdout
        g("init", "-q")
        g("config", "user.email", "t@t"); g("config", "user.name", "t")
        (d / "a.txt").write_text("1"); g("add", "a.txt"); g("commit", "-qm", "primero")
        self.assertIn("primero", P.render_unreleased(P.load(self.path), P.unreleased_commits(P.load(self.path), d)))
        self.assertEqual(run(self.path, "release")[0], 1)  # sin novedades no se publica
        run(self.path, "news", "Algo nuevo")
        code, out, err = run(self.path, "release")
        self.assertEqual(code, 0, err)
        self.assertIn("v0.1.0", out)
        v = P.load(self.path)["versions"][-1]
        self.assertEqual((v["version"], v["tag"]), ("0.1.0", "v0.1.0"))
        self.assertIn("Algo nuevo", g("tag", "-n9", "-l", "v0.1.0"))
        plan = P.load(self.path)
        self.assertEqual(P.unreleased_commits(plan, d), [])
        (d / "a.txt").write_text("2"); g("commit", "-qam", "segundo")
        self.assertEqual([c["subject"] for c in P.unreleased_commits(plan, d)], ["segundo"])
        run(self.path, "news", "Un arreglo", "--kind", "arreglo")
        self.assertEqual(run(self.path, "release", "0.1.0")[0], 1)  # no puede repetir
        self.assertEqual(run(self.path, "release", "--bump", "major")[0], 0)
        self.assertEqual(P.load(self.path)["versions"][-1]["version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
