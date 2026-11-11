"""Servidor por proyecto: rutas, seguridad y ajustes."""

import http.client
import json
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

from unificador import app as A
from unificador import cli
from unificador import plan as P

PLAN = {"branches": [{"name": "Carrito", "phases": [
    {"name": "Cimientos", "steps": [{"title": "Modelo"}]},
    {"name": "Pagos", "steps": [{"title": "Pasarela"}]}]}]}


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
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
        self.assertEqual([a["id"] for a in data["agents"]], ["claude", "antigravity"])
        self.assertEqual(data["settings"]["agent"], "claude")
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

    def test_agent_path_from_the_web(self):
        with mock.patch.object(A.G, "set_path", side_effect=A.G.AgentError("Ahí no hay ningún programa: x")) as fake:
            status, data, _ = self.call("POST", "/api/settings", {"paths": {"antigravity": "x"}})
        self.assertEqual((status, fake.call_args.args), (400, ("antigravity", "x")))
        self.assertIn("no hay ningún programa", data["error"])

    def test_settings_are_cleaned_and_kept_local(self):
        status, data, _ = self.call("POST", "/api/settings", {
            "agent": "antigravity", "otra": "cosa",
            "agents": {"claude": {"model": "opus", "effort": "high", "mode": "bypassPermissions"},
                       "antigravity": {"model": "gemini; rm -rf", "effort": "max"}}})
        self.assertEqual(status, 200)
        self.assertEqual(data, {"agent": "antigravity", "agents": {
            "claude": {"model": "opus", "effort": "high", "mode": "auto"},
            "antigravity": {"model": "", "effort": "", "mode": "auto"}}})
        self.assertEqual(self.call("GET", "/api/project")[1]["settings"], data)
        self.assertTrue((self.root / ".unificador/local.json").is_file())

    def test_live_events(self):
        from unittest import mock
        from unificador import agents as G
        with mock.patch.object(G, "WATCH_EVERY", 0.05):
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

    def test_bad_requests(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/api/settings", body=b"{roto", headers={"Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 400)
        conn.close()
        self.assertEqual(self.call("GET", "/api/sessions?agent=otro")[0], 400)
        self.assertEqual(self.call("GET", "/api/sessions/claude/..%2F..%2Fx")[0], 400)

    def test_next_free_port_and_cli(self):
        other = A.make_server(self.root, self.port)
        try:
            self.assertGreater(other.server_address[1], self.port)
        finally:
            other.server_close()
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cli, "_agent_lines", lambda: ["  ✔ Claude Code: x"]):
                self.assertEqual(cli.main(["doctor", tmp]), 1)  # faltan las reglas, y no las pone él
                self.assertEqual(list(Path(tmp).iterdir()), [])
                self.assertEqual(cli.main(["install", tmp]), 0)
                self.assertEqual(cli.main(["doctor", tmp]), 0)
            with mock.patch.object(cli, "_agent_lines", lambda: ["  ✘ Claude Code: no lo encuentro."]):
                self.assertEqual(cli.main(["doctor", tmp]), 1)
            self.assertTrue((Path(tmp) / ".unificador/uni.py").is_file())
            self.assertEqual(cli.main(["import-kanvas", tmp]), 1)
            (Path(tmp) / "kanvas.json").write_text(json.dumps({"tasks": [
                {"id": "A-1", "title": "Uno", "state": "todo", "group": "A"}]}), encoding="utf-8")
            self.assertEqual(cli.main(["import-kanvas", tmp]), 0)
            self.assertEqual(cli.main(["import-kanvas", str(Path(tmp) / "no-existe")]), 1)


if __name__ == "__main__":
    unittest.main()
