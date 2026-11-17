"""Caja de ideas, prompts maestros y cola de encargos: órdenes, inbox y API."""

import json
import tempfile
import unittest
from pathlib import Path

from unificador import plan as P
from tests.test_plan import SAMPLE, run
from tests.test_app import ServerCase


class BoxCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / P.PLAN_FILE
        run(self.path, "plan", stdin=json.dumps(SAMPLE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_idea_y_planificar(self):
        code, out, _ = run(self.path, "idea", "Modo oscuro")
        self.assertEqual(code, 0)
        self.assertIn("I-1", out)
        run(self.path, "idea", "Exportar a PDF")
        code, out, _ = run(self.path, "ideas")
        self.assertIn("Modo oscuro", out)
        self.assertEqual(run(self.path, "inbox")[1], "")  # las del agente no son novedad
        code, out, _ = run(self.path, "ideas", "plan", "I-1", "--branch", "CDC")
        self.assertEqual(code, 0)
        plan = P.load(self.path)
        self.assertEqual(plan["ideas"][0]["state"], "planned")
        self.assertIn("I-1", plan["branches"][0]["ideas"])
        run(self.path, "ideas", "drop", "I-2", "-m", "no hace falta")
        self.assertEqual(P.load(self.path)["ideas"][1]["note"], "no hace falta")
        run(self.path, "ideas", "reopen", "I-2")
        self.assertEqual(P.load(self.path)["ideas"][1]["state"], "open")
        self.assertEqual(run(self.path, "ideas", "plan", "I-9", "--branch", "CDC")[0], 1)

    def test_rama_nueva_con_ideas(self):
        run(self.path, "idea", "Cupones")
        code, out, err = run(self.path, "branch", "Descuentos", "--ideas", "I-1",
                             "--phase", "Base", "codigo: Modelo de cupón")
        self.assertEqual(code, 0, err)
        plan = P.load(self.path)
        self.assertEqual(plan["ideas"][0]["state"], "planned")
        self.assertEqual(plan["ideas"][0]["branch"], plan["branches"][-1]["key"])
        # una idea que no existe no deja la rama a medias
        code, _, _ = run(self.path, "branch", "Otra", "--ideas", "I-7", "--phase", "Base", "codigo: Algo")
        self.assertEqual(code, 1)
        self.assertEqual(len(P.load(self.path)["branches"]), 2)

    def test_prompts_y_cola(self):
        code, out, _ = run(self.path, "prompts")
        self.assertIn("revisar-codigo", out)
        own = self.dir / ".unificador" / "prompts"
        own.mkdir(parents=True)
        (own / "revisar-codigo.md").write_text("# Mi revisión\nMira solo los tests.", encoding="utf-8")
        code, out, _ = run(self.path, "prompts", "revisar-codigo")
        self.assertIn("Mi revisión", out)
        self.assertIn("Mira solo los tests.", out)
        code, out, err = run(self.path, "queue", "add", "revisar-interfaz", "--branch", "CDC", "--text", "Sobre todo móvil")
        self.assertEqual(code, 0, err)
        job = P.load(self.path)["queue"][0]
        self.assertEqual((job["id"], job["branch"], job["prompt"]), ("C-1", "CDC", "revisar-interfaz"))
        self.assertIn("Sobre todo móvil", job["text"])
        self.assertIn("C-1", run(self.path, "queue")[1])
        run(self.path, "queue", "done", "C-1", "-m", "Revisada")
        self.assertEqual(P.load(self.path)["queue"][0]["state"], "done")
        self.assertIn("No hay encargos", run(self.path, "queue")[1])
        self.assertEqual(run(self.path, "queue", "add", "no-existe")[0], 1)
        self.assertEqual(run(self.path, "queue", "add", "--text", "x", "--phase", "Pagos")[0], 1)  # fase sin rama


class BoxApi(ServerCase):
    def test_idea_desde_la_web_llega_por_inbox(self):
        status, plan, _ = self.call("POST", "/api/plan/ideas", {"text": "Avisar por correo"})
        self.assertEqual(status, 200)
        idea = plan["ideas"][0]
        self.assertEqual((idea["by"], idea["seen"]), ("persona", False))
        path = self.root / P.PLAN_FILE
        out = run(path, "inbox")[1]
        self.assertIn("Avisar por correo", out)
        self.assertEqual(run(path, "inbox")[1], "")  # ya vista
        self.assertEqual(self.call("POST", "/api/plan/ideas", {"text": "  "})[0], 400)
        status, plan, _ = self.call("POST", "/api/plan/ideas/I-1/drop", {})
        self.assertEqual(plan["ideas"][0]["state"], "dropped")
        status, plan, _ = self.call("POST", "/api/plan/ideas/I-1/reopen", {})
        self.assertEqual(plan["ideas"][0]["state"], "open")

    def test_encargo_desde_la_web(self):
        status, data, _ = self.call("GET", "/api/prompts")
        self.assertEqual(status, 200)
        self.assertTrue(any(p["name"] == "a-prueba-de-errores" for p in data["prompts"]))
        key = P.load(self.root / P.PLAN_FILE)["branches"][0]["key"]
        status, plan, _ = self.call("POST", "/api/plan/queue", {"prompt": "a-prueba-de-errores", "branch": key})
        self.assertEqual(status, 200)
        job = plan["queue"][0]
        self.assertEqual((job["state"], job["seen"], job["branch"]), ("pending", False, key))
        out = run(self.root / P.PLAN_FILE, "inbox")[1]
        self.assertIn("ENCARGO EN COLA", out)
        self.assertIn("queue done", out)
        self.assertEqual(self.call("POST", "/api/plan/queue", {"prompt": "nada"})[0], 400)
        status, plan, _ = self.call("POST", "/api/plan/queue/C-1/drop", {})
        self.assertEqual(plan["queue"], [])

    def test_versiones(self):
        path = self.root / P.PLAN_FILE
        run(path, "news", "Algo nuevo")
        status, data, _ = self.call("GET", "/api/versions")
        self.assertEqual(status, 200)
        self.assertEqual((data["next"], data["last"], data["versions"]), ("0.1.0", "", []))
        self.assertEqual(data["news"][0]["text"], "Algo nuevo")
        self.assertIsInstance(data["unreleased"], list)
        run(path, "release", "--no-tag")
        data = self.call("GET", "/api/versions")[1]
        self.assertEqual((data["last"], data["news"]), ("0.1.0", []))
        self.assertEqual(data["versions"][0]["news"][0]["text"], "Algo nuevo")


if __name__ == "__main__":
    unittest.main()
