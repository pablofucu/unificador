"""Servidor por proyecto: rutas, seguridad y ajustes."""

import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

from unificador import app as A
from unificador import cli
from unificador import plan as P
from unificador import projects as R

PLAN = {"branches": [{"name": "Carrito", "phases": [
    {"name": "Cimientos", "steps": [{"title": "codigo: Modelo"}]},
    {"name": "Pagos", "steps": [{"title": "codigo: Pasarela"}]}]}]}


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Tienda"
        self.root.mkdir()
        self.home = Path(self.tmp.name) / "home"  # registro de proyectos de mentira
        env = mock.patch.dict(os.environ, {"UNIFICADOR_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        P.mutate(self.root / P.PLAN_FILE, lambda plan: P.add_branches(plan, PLAN, "ia"))
        self.server = A.make_server(self.root, 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def call(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        raw = r.read()
        conn.close()
        kind = r.getheader("Content-Type") or ""
        return r.status, (json.loads(raw) if "application/json" in kind else raw.decode("utf-8")), r


class AppTest(ServerCase):
    def test_project_plan_and_static(self):
        status, data, r = self.call("GET", "/api/project")
        self.assertEqual(status, 200)
        self.assertEqual(data["name"], self.root.resolve().name)
        self.assertEqual(sorted(data), ["id", "name", "path"])
        self.assertIsNone(r.getheader("Access-Control-Allow-Origin"))
        status, plan, _ = self.call("GET", "/api/plan")
        self.assertEqual(plan["branches"][0]["name"], "Carrito")
        status, page, _ = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("<html", page)
        self.assertEqual(self.call("GET", "/../plan.py")[0], 404)
        self.assertEqual(self.call("GET", "/%2e%2e/%2e%2e/pyproject.toml")[0], 404)
        self.assertEqual(self.call("GET", "/api/nada")[0], 404)
        self.assertEqual(self.call("POST", "/api/plan", {})[0], 405)

    def test_plan_carries_audit_without_saving_it(self):
        P.mutate(self.root / P.PLAN_FILE, lambda plan: plan["branches"][0]["phases"][0]["steps"][0].pop("cat", None))
        status, plan, _ = self.call("GET", "/api/plan")
        self.assertEqual(status, 200)
        self.assertIsInstance(plan["audit"], list)
        self.assertTrue(plan["audit"])  # un paso sin categoría (plan viejo)
        self.assertTrue(all(set(i) == {"level", "ref", "text"} for i in plan["audit"]))
        self.assertNotIn("audit", json.loads((self.root / P.PLAN_FILE).read_text(encoding="utf-8")))

    def test_person_changes_steps(self):
        status, plan, _ = self.call("POST", "/api/plan/steps/CA-1/state", {"state": "done", "text": "ok"})
        self.assertEqual(status, 200, plan)
        self.assertEqual(plan["branches"][0]["phases"][0]["steps"][0]["state"], "done")
        status, plan, _ = self.call("POST", "/api/plan/steps/ca-1/change", {"text": "Falta el IVA"})
        step = plan["branches"][0]["phases"][0]["steps"][0]
        self.assertEqual((step["state"], step["change"]), ("pending", "Falta el IVA"))
        self.assertEqual(step["notes"][-1]["by"], "persona")
        self.assertEqual(self.call("POST", "/api/plan/steps/CA-1/change", {"text": ""})[0], 400)
        self.assertEqual(self.call("POST", "/api/plan/steps/NO-9/state", {"state": "done"})[0], 400)
        self.assertEqual(self.call("POST", "/api/plan/steps/CA-1/state", {"state": "raro"})[0], 400)

    def test_other_sites_are_refused(self):
        ok = f"http://127.0.0.1:{self.port}"
        body = {"state": "done"}
        path = "/api/plan/steps/CA-1/state"
        self.assertEqual(self.call("GET", "/api/plan", host="evil.example")[0], 403)
        self.assertEqual(self.call("GET", "/api/plan", host=f"evil.example:{self.port}")[0], 403)
        self.assertEqual(self.call("POST", path, body, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("POST", path, body, {"Origin": "http://127.0.0.1:9"})[0], 403)
        self.assertEqual(self.call("GET", "/api/plan", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.call("POST", path, body, {"Content-Type": "text/plain"})[0], 403)
        self.assertEqual(self.call("OPTIONS", path, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(P.load(self.root / P.PLAN_FILE)["branches"][0]["phases"][0]["steps"][0]["state"], "pending")
        self.assertEqual(self.call("POST", path, body, {"Origin": ok, "Sec-Fetch-Site": "same-origin"})[0], 200)
        self.assertEqual(self.call("GET", "/api/plan", host=f"localhost:{self.port}")[0], 200)

    def test_live_events(self):
        with mock.patch.object(A, "WATCH_EVERY", 0.05):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.request("GET", "/api/events", headers={"Host": f"127.0.0.1:{self.port}"})
            r = conn.getresponse()
            self.assertIn("text/event-stream", r.getheader("Content-Type"))
            self.assertEqual(r.fp.readline(), b"retry: 2000\n")
            self.call("POST", "/api/plan/steps/CA-1/state", {"state": "doing"})
            lines = [r.fp.readline() for _ in range(3)]
            self.assertIn(b"event: plan\n", lines)
            conn.close()
        self.assertEqual(self.call("GET", "/api/events", host="evil.example")[0], 403)

    def test_review_phase_and_nonstop(self):
        path = "/api/plan/phases/review"
        status, plan, _ = self.call("POST", path, {"branch": "CA", "phase": "Cimientos", "verdict": "approved"})
        self.assertEqual(status, 200, plan)
        review = plan["branches"][0]["phases"][0]["review"]
        self.assertEqual((review["state"], review["by"], review["seen"]), ("approved", "persona", False))
        status, plan, _ = self.call("POST", path, {"branch": "Carrito", "phase": "Pagos", "verdict": "changes",
                                                   "text": "Más colores"})
        review = plan["branches"][0]["phases"][1]["review"]
        self.assertEqual((review["state"], review["text"], review["seen"]), ("changes", "Más colores", False))
        self.assertEqual(self.call("POST", path, {"branch": "CA", "phase": "Pagos", "verdict": "changes"})[0], 400)
        self.assertEqual(self.call("POST", path, {"branch": "CA", "phase": "Pagos", "verdict": "quizá"})[0], 400)
        self.assertEqual(self.call("POST", path, {"branch": "CA", "verdict": "approved"})[0], 400)
        self.assertEqual(self.call("POST", path, {"branch": "XX", "phase": "Pagos", "verdict": "approved"})[0], 400)

        status, plan, _ = self.call("POST", "/api/plan/branches/CA/nonstop", {"on": True})
        self.assertTrue(plan["branches"][0]["nonstop"])
        status, plan, _ = self.call("POST", "/api/plan/branches/ca/nonstop", {"on": False})
        self.assertNotIn("nonstop", plan["branches"][0])
        self.assertEqual(self.call("POST", "/api/plan/branches/CA/nonstop", {"on": "sí"})[0], 400)
        self.assertEqual(self.call("POST", "/api/plan/branches/XX/nonstop", {"on": True})[0], 400)

    def test_answer_asks(self):
        def add(plan):
            P.add_ask(plan, "¿Color?", options=["Azul | claro", "Verde | oscuro"], step="CA-1", recommend=1)
            P.add_ask(plan, "¿Nombre?")
        P.mutate(self.root / P.PLAN_FILE, add)
        path = "/api/plan/asks/P-1/answer"
        status, plan, _ = self.call("POST", path, {"option": 2, "text": "mejor así"})
        self.assertEqual(status, 200, plan)
        answer = plan["asks"][0]["answer"]
        self.assertEqual((answer["option"], answer["text"], answer["by"], answer["seen"]),
                         (2, "mejor así", "persona", False))
        status, plan, _ = self.call("POST", "/api/plan/asks/p-2/answer", {"option": None, "text": "Tiendita"})
        self.assertEqual(plan["asks"][1]["answer"]["text"], "Tiendita")
        self.assertEqual(self.call("POST", path, {"option": 3})[0], 400)
        self.assertEqual(self.call("POST", path, {"option": "1"})[0], 400)
        self.assertEqual(self.call("POST", path, {"option": True})[0], 400)
        self.assertEqual(self.call("POST", path, {})[0], 400)
        self.assertEqual(self.call("POST", "/api/plan/asks/P-9/answer", {"option": 1})[0], 400)

    def test_proposals_are_sandboxed(self):
        folder = self.root / P.PROPOSALS_DIR / "P-1"
        folder.mkdir(parents=True)
        (folder / "1.html").write_text("<h1>Clara</h1>", encoding="utf-8")
        (self.root / "secreto.html").write_text("no", encoding="utf-8")
        status, page, r = self.call("GET", "/propuestas/P-1/1.html",
                                    headers={"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Dest": "iframe"})
        self.assertEqual(status, 200)
        self.assertIn("Clara", page)
        self.assertIn("text/html", r.getheader("Content-Type"))
        csp = r.getheader("Content-Security-Policy")
        self.assertTrue(csp.startswith("sandbox allow-scripts;"), csp)
        self.assertIn("default-src 'none'", csp)
        self.assertNotIn("allow-same-origin", csp)
        self.assertEqual(self.call("GET", f"/propuestas/P-1/1.html?project={A.project_id(self.root)}")[0], 200)
        for bad in ("/propuestas/P-1/2.html", "/propuestas/P-1/../../secreto.html", "/propuestas/../secreto.html",
                    "/propuestas/P-1/%2e%2e/%2e%2e/secreto.html", "/propuestas/P-1/1.htm", "/propuestas/x/1.html",
                    "/propuestas/P-1/1.html/", "/propuestas/P-1/a.html", "/propuestas/P-1/1.html?project=../..",
                    "/propuestas/P-1/1.html?project=abcdef1234", "/propuestas/P-1/..%5C..%5Csecreto.html"):
            self.assertEqual(self.call("GET", bad)[0], 404, bad)
        self.assertEqual(self.call("POST", "/propuestas/P-1/1.html", {})[0], 405)
        self.assertEqual(self.call("GET", "/propuestas/P-1/1.html", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        _, _, r = self.call("GET", "/")
        self.assertIn("frame-src 'self'", r.getheader("Content-Security-Policy"))

    def test_several_projects(self):
        other = Path(self.tmp.name) / "Blog"
        other.mkdir()
        P.mutate(other / P.PLAN_FILE, lambda plan: P.add_branches(plan, {"branches": [
            {"name": "Entradas", "phases": [{"name": "Base", "steps": [{"title": "codigo: Uno"}, {"title": "pruebas: Dos"}]}]}]}, "ia"))
        P.mutate(other / P.PLAN_FILE, lambda plan: P.add_ask(plan, "¿Título?"))
        (other / P.PROPOSALS_DIR / "P-1").mkdir(parents=True)
        (other / P.PROPOSALS_DIR / "P-1" / "1.html").write_text("blog", encoding="utf-8")
        gone = Path(self.tmp.name) / "Borrado"
        R.register(other)
        R.register(gone)
        status, data, _ = self.call("GET", "/api/projects")
        self.assertEqual(status, 200)
        items = {p["name"]: p for p in data["projects"]}
        self.assertEqual(sorted(items), ["Blog", "Borrado", "Tienda"])
        self.assertTrue(items["Tienda"]["current"])
        self.assertFalse(items["Blog"]["current"])
        self.assertEqual((items["Tienda"]["done"], items["Tienda"]["total"], items["Tienda"]["waiting"]), (0, 2, 0))
        self.assertEqual((items["Blog"]["done"], items["Blog"]["total"], items["Blog"]["waiting"]), (0, 2, 1))
        self.assertFalse(items["Borrado"]["exists"])
        blog = items["Blog"]["id"]

        status, plan, _ = self.call("GET", f"/api/plan?project={blog}")
        self.assertEqual(plan["branches"][0]["name"], "Entradas")
        self.assertEqual(self.call("GET", f"/api/project?project={blog}")[1]["name"], "Blog")
        tienda = items["Tienda"]["id"]
        self.assertEqual(self.call("GET", f"/api/plan?project={tienda}")[1]["branches"][0]["name"], "Carrito")
        status, plan, _ = self.call("POST", f"/api/plan/steps/EN-1/state?project={blog}", {"state": "done"})
        self.assertEqual(status, 200, plan)
        self.assertEqual(P.load(other / P.PLAN_FILE)["branches"][0]["phases"][0]["steps"][0]["state"], "done")
        self.assertEqual(self.call("GET", f"/propuestas/P-1/1.html?project={blog}")[1], "blog")
        # nada fuera del registro: ids inventados, rutas o carpetas que ya no existen
        for pid in ("abcdef1234", "..", str(other), items["Borrado"]["id"]):
            self.assertEqual(self.call("GET", f"/api/plan?project={pid}")[0], 404, pid)
        R.forget(other)
        self.assertEqual(self.call("GET", f"/api/plan?project={blog}")[0], 404)

    def test_live_events_follow_the_project(self):
        other = Path(self.tmp.name) / "Blog"
        other.mkdir()
        R.register(other)
        pid = A.project_id(other)
        with mock.patch.object(A, "WATCH_EVERY", 0.05):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.request("GET", f"/api/events?project={pid}", headers={"Host": f"127.0.0.1:{self.port}"})
            r = conn.getresponse()
            self.assertEqual(r.fp.readline(), b"retry: 2000\n")
            P.mutate(other / P.PLAN_FILE, lambda plan: P.add_ask(plan, "¿Algo?"))
            lines = [r.fp.readline() for _ in range(3)]
            self.assertIn(b"event: plan\n", lines)
            conn.close()

    def test_chat_routes_are_gone(self):
        for method, path in (("GET", "/api/sessions"), ("GET", "/api/sessions/claude/x"),
                             ("POST", "/api/settings"), ("POST", "/api/chat"),
                             ("POST", "/api/chat/stop"), ("POST", "/api/open-native")):
            self.assertEqual(self.call(method, path, {} if method == "POST" else None)[0], 404, path)

    def test_bad_requests(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/api/plan/steps/CA-1/state", body=b"{roto", headers={"Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()

    def test_next_free_port_and_cli(self):
        other = A.make_server(self.root, self.port)
        try:
            self.assertGreater(other.server_address[1], self.port)
        finally:
            other.server_close()
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cli.main(["doctor", tmp]), 1)  # faltan las reglas, y no las pone él
            self.assertEqual(list(Path(tmp).iterdir()), [])
            self.assertEqual(cli.main(["install", tmp]), 0)
            self.assertEqual(cli.main(["doctor", tmp]), 0)  # sin ningún cliente instalado tampoco es error
            self.assertTrue((Path(tmp) / ".unificador/uni.py").is_file())
            self.assertEqual(cli.main(["import-kanvas", tmp]), 1)
            (Path(tmp) / "kanvas.json").write_text(json.dumps({"tasks": [
                {"id": "A-1", "title": "Uno", "state": "todo", "group": "A"}]}), encoding="utf-8")
            self.assertEqual(cli.main(["import-kanvas", tmp]), 0)
            self.assertEqual(cli.main(["import-kanvas", str(Path(tmp) / "no-existe")]), 1)


if __name__ == "__main__":
    unittest.main()
