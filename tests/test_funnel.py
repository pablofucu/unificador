"""Seguridad de Tailscale Funnel: clave cifrada, puerta cerrada, rate limit y ocultación de rutas."""

import http.client
import io
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from unificador import app as A
from unificador import cli
from unificador import funnel as F
from unificador import plan as P
from unificador import projects as R
from unificador import rules

PLAN = {"branches": [{"name": "Carrito", "phases": [
    {"name": "Cimientos", "steps": [{"title": "codigo: Modelo"}]},
]}]}


class FunnelModuleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        env = mock.patch.dict(os.environ, {"UNIFICADOR_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_key_hashing_and_verification(self):
        self.assertFalse(F.has_key())
        with self.assertRaises(ValueError):
            F.set_key("123")
        key = F.set_key("mi-clave-secreta")
        self.assertEqual(key, "mi-clave-secreta")
        self.assertTrue(F.has_key())
        raw = F.config_path().read_text(encoding="utf-8")
        self.assertNotIn("mi-clave-secreta", raw)  # nunca en claro en disco
        self.assertTrue(F.verify_key("mi-clave-secreta"))
        self.assertFalse(F.verify_key("otra-clave"))
        self.assertFalse(F.verify_key(""))

        gen = F.set_key()
        self.assertGreaterEqual(len(gen), 16)
        self.assertTrue(F.verify_key(gen))
        self.assertFalse(F.verify_key("mi-clave-secreta"))

    def test_broken_config_falls_back_to_disabled(self):
        self.home.mkdir(parents=True)
        F.config_path().write_text("{roto", encoding="utf-8")
        cfg = F.load_config()
        self.assertFalse(cfg["enabled"])
        self.assertFalse(F.has_key(cfg))

    def test_signed_sessions_and_reset(self):
        F.set_key("clave-super-segura")
        cfg = F.load_config()
        tok = F.sign_session(cfg["cookie_secret"], ttl=60, now_ts=1000)
        self.assertTrue(F.verify_session(tok, cfg["cookie_secret"], now_ts=1020))
        self.assertFalse(F.verify_session(tok, cfg["cookie_secret"], now_ts=1061))
        self.assertFalse(F.verify_session(tok + "x", cfg["cookie_secret"], now_ts=1020))
        self.assertFalse(F.verify_session("malo", cfg["cookie_secret"], now_ts=1020))
        F.reset_sessions()
        cfg2 = F.load_config()
        self.assertFalse(F.verify_session(tok, cfg2["cookie_secret"], now_ts=1020))

    def test_rate_limiter_and_ts_host(self):
        rl = F.RateLimiter(max_failures=3, window=60, lock_seconds=30)
        self.assertEqual(rl.retry_after("9.9.9.9", now_ts=100), 0)
        self.assertEqual(rl.record_failure("9.9.9.9", now_ts=100), 0)
        self.assertEqual(rl.record_failure("9.9.9.9", now_ts=101), 0)
        self.assertEqual(rl.record_failure("9.9.9.9", now_ts=102), 30)
        self.assertGreater(rl.retry_after("9.9.9.9", now_ts=110), 0)
        self.assertEqual(rl.retry_after("8.8.8.8", now_ts=110), 0)
        rl.record_success("9.9.9.9")
        self.assertEqual(rl.retry_after("9.9.9.9", now_ts=110), 0)

        self.assertTrue(F.is_ts_host("mi-pc.tail1234.ts.net"))
        self.assertFalse(F.is_ts_host("ts.net.evil.com"))
        self.assertFalse(F.is_ts_host("evil.example"))


class FunnelServerTest(unittest.TestCase):
    TS_HOST = "mi-pc.tail1234.ts.net"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "TiendaSecreta"
        self.root.mkdir()
        self.home = Path(self.tmp.name) / "home"
        env = mock.patch.dict(os.environ, {"UNIFICADOR_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)
        limiter = mock.patch.object(A, "RATE_LIMITER", F.RateLimiter())
        limiter.start()
        self.addCleanup(limiter.stop)

        P.mutate(self.root / P.PLAN_FILE, lambda plan: P.add_branches(plan, PLAN, "ia"))
        prop_dir = self.root / P.PROPOSALS_DIR / "P-1"
        prop_dir.mkdir(parents=True)
        (prop_dir / "1.html").write_text("<h1>Propuesta</h1>", encoding="utf-8")

        self.server = A.make_server(self.root, 0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self._stop_server)

    def _stop_server(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}"}
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
        parsed = json.loads(raw) if "application/json" in kind else raw.decode("utf-8", errors="replace")
        return r.status, parsed, r

    def funnel_headers(self, extra=None):
        h = {
            "Host": self.TS_HOST,
            "Tailscale-Funnel-Request": "?1",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "203.0.113.10",
        }
        if extra:
            h.update(extra)
        return h

    def enable_funnel(self, key="clave-correcta", port=443):
        F.set_key(key)
        cfg = F.load_config()
        cfg["enabled"] = True
        cfg["funnel_port"] = port
        cfg["public_url"] = f"https://{self.TS_HOST}" + (f":{port}" if port != 443 else "")
        F.save_config(cfg)

    def test_fail_closed_without_enable_or_key(self):
        status, _, _ = self.call("GET", "/api/plan", headers=self.funnel_headers())
        self.assertEqual(status, 403)
        cfg = F.load_config()
        cfg["enabled"] = True  # activado sin clave
        F.save_config(cfg)
        self.assertEqual(self.call("GET", "/", headers=self.funnel_headers())[0], 403)
        self.assertEqual(self.call("GET", "/api/projects", headers=self.funnel_headers())[0], 403)

    def test_funnel_blocks_everything_until_login_while_local_stays_open(self):
        self.enable_funnel()
        # Local 127.0.0.1 sigue abierto sin clave y muestra path
        st, data, _ = self.call("GET", "/api/projects")
        self.assertEqual(st, 200)
        self.assertIn("TiendaSecreta", data["projects"][0]["path"])
        self.assertEqual(self.call("GET", "/api/health")[0], 200)

        # Por Funnel sin cookie: GET / enseña solo el login (cero fugas de datos)
        st, html, r = self.call("GET", "/", headers=self.funnel_headers())
        self.assertEqual(st, 200)
        self.assertEqual(r.getheader("X-Unificador-Auth"), "login")
        self.assertIn("/auth/login", html)
        self.assertNotIn("TiendaSecreta", html)
        self.assertNotIn("Carrito", html)
        self.assertNotIn("app.js", html)

        # API, estáticos y propuestas devuelven 401 sin cookie
        for path in ("/api/health", "/api/projects", "/api/project", "/api/plan", "/api/events",
                     "/app.js", "/propuestas/P-1/1.html"):
            self.assertEqual(self.call("GET", path, headers=self.funnel_headers())[0], 401, path)
        self.assertEqual(self.call("POST", "/api/plan/steps/CA-1/change", {"text": "hack"},
                                   headers=self.funnel_headers({"Origin": f"https://{self.TS_HOST}"}))[0], 401)
        self.assertEqual(P.load(self.root / P.PLAN_FILE)["branches"][0]["phases"][0]["steps"][0]["state"], P.PENDING)

        # Navegaci?n de primer nivel al abrir enlace desde otra app/web (Sec-Fetch-Site: cross-site) ense?a login
        st_nav, _, r_nav = self.call("GET", "/", headers=self.funnel_headers({
            "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document",
        }))
        self.assertEqual((st_nav, r_nav.getheader("X-Unificador-Auth")), (200, "login"))
        # Pero cross-site en subrecursos o rutas API/propuestas sigue rechazado (403)
        self.assertEqual(self.call("GET", "/", headers=self.funnel_headers({"Sec-Fetch-Site": "cross-site"}))[0], 403)
        self.assertEqual(self.call("GET", "/api/plan", headers=self.funnel_headers({
            "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document",
        }))[0], 403)

        # Proxy Tailscale reescribiendo Host a loopback con X-Forwarded-Host p?blico
        proxy_h = {"Host": f"127.0.0.1:{self.port}", "X-Forwarded-Host": self.TS_HOST,
                   "Origin": f"https://{self.TS_HOST}", "Sec-Fetch-Site": "same-origin",
                   "Tailscale-Funnel-Request": "?1", "X-Forwarded-Proto": "https"}
        self.assertEqual(self.call("POST", "/auth/login", {"key": "mal"}, headers=proxy_h)[0], 401)
        self.assertEqual(self.call("POST", "/auth/login", {"key": "mal"},
                                   headers={**proxy_h, "Origin": "https://evil.example"})[0], 403)

    def test_login_rate_limit_session_path_hiding_and_reset(self):
        self.enable_funnel("mi-clave-123", port=8443)
        origin = f"https://{self.TS_HOST}:8443"
        base_h = {"Host": f"{self.TS_HOST}:8443", "Origin": origin, "Sec-Fetch-Site": "same-origin",
                  "Tailscale-Funnel-Request": "?1", "X-Forwarded-Proto": "https"}

        # Cross-origin rechazado incluso en login
        self.assertEqual(self.call("POST", "/auth/login", {"key": "mi-clave-123"},
                                   headers={**base_h, "Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("GET", "/api/plan", headers={**base_h, "Host": "evil.example"})[0], 403)

        # 5 intentos fallidos desde la misma IP real (aunque falsifiquen el primer salto de XFF) -> 429
        for i in range(4):
            st, _, _ = self.call("POST", "/auth/login", {"key": "mal"},
                                  headers={**base_h, "X-Forwarded-For": f"10.0.0.{i}, 198.51.100.7"})
            self.assertEqual(st, 401)
        st, _, r = self.call("POST", "/auth/login", {"key": "mal"},
                             headers={**base_h, "X-Forwarded-For": "10.0.0.99, 198.51.100.7"})
        self.assertEqual(st, 429)
        self.assertTrue(r.getheader("Retry-After"))
        # Incluso con clave correcta sigue bloqueado mientras dure el rate limit
        self.assertEqual(self.call("POST", "/auth/login", {"key": "mi-clave-123"},
                                   headers={**base_h, "X-Forwarded-For": "198.51.100.7"})[0], 429)

        # Otra IP sí puede iniciar sesión con la clave correcta
        st, body, r = self.call("POST", "/auth/login", {"key": "mi-clave-123"},
                                headers={**base_h, "X-Forwarded-For": "198.51.100.88"})
        self.assertEqual(st, 200, body)
        set_cookie = r.getheader("Set-Cookie") or ""
        self.assertIn(f"{F.SESSION_COOKIE}=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("Secure", set_cookie)
        cookie_kv = set_cookie.split(";", 1)[0]

        auth_h = {**base_h, "Cookie": cookie_kv}
        # Ya entra a la web, ve proyectos sin path del disco y puede operar
        st, page, _ = self.call("GET", "/", headers=auth_h)
        self.assertEqual(st, 200)
        self.assertIn("app.js", page)
        st, projects_data, _ = self.call("GET", "/api/projects", headers=auth_h)
        self.assertEqual(st, 200)
        self.assertTrue(projects_data["remote"])
        self.assertEqual(projects_data["projects"][0]["path"], "")
        st, proj_data, _ = self.call("GET", "/api/project", headers=auth_h)
        self.assertEqual((st, proj_data["path"]), (200, ""))
        self.assertEqual(self.call("GET", "/propuestas/P-1/1.html", headers=auth_h)[0], 200)
        st, _, _ = self.call("POST", "/api/plan/steps/CA-1/state", {"state": "done"}, headers=auth_h)
        self.assertEqual(st, 200)
        self.assertEqual(P.load(self.root / P.PLAN_FILE)["branches"][0]["phases"][0]["steps"][0]["state"], P.DONE)

        # Origin con puerto distinto o http sigue rechazado aunque tenga cookie válida
        self.assertEqual(self.call("POST", "/api/plan/steps/CA-1/state", {"state": "pending"},
                                   headers={**auth_h, "Origin": f"https://{self.TS_HOST}:443"})[0], 403)
        self.assertEqual(self.call("POST", "/api/plan/steps/CA-1/state", {"state": "pending"},
                                   headers={**auth_h, "Origin": f"http://{self.TS_HOST}:8443"})[0], 403)

        # reset_sessions revoca la cookie al instante
        F.reset_sessions()
        self.assertEqual(self.call("GET", "/api/plan", headers=auth_h)[0], 401)
        st, _, r = self.call("GET", "/", headers=auth_h)
        self.assertEqual((st, r.getheader("X-Unificador-Auth")), (200, "login"))

        # Logout borra la cookie
        st, _, r = self.call("POST", "/auth/logout", {}, headers=auth_h)
        self.assertEqual(st, 200)
        self.assertIn("Max-Age=0", r.getheader("Set-Cookie") or "")

    def test_active_project_flag_in_projects_api_local_and_funnel(self):
        other = Path(self.tmp.name) / "OtraApp"
        other.mkdir()
        P.mutate(other / P.PLAN_FILE, lambda plan: P.add_branches(plan, PLAN, "ia"))
        R.register(other)
        R.set_active(other)
        other_id = A.project_id(other)
        self.assertEqual(R.active_id(), other_id)

        st, local_data, _ = self.call("GET", "/api/projects")
        self.assertEqual(st, 200)
        by_name = {p["name"]: p for p in local_data["projects"]}
        self.assertTrue(by_name["TiendaSecreta"]["current"])
        self.assertFalse(by_name["TiendaSecreta"]["active"])
        self.assertFalse(by_name["OtraApp"]["current"])
        self.assertTrue(by_name["OtraApp"]["active"])

        self.enable_funnel("clave-activa")
        origin = f"https://{self.TS_HOST}"
        _, _, r = self.call("POST", "/auth/login", {"key": "clave-activa"},
                            headers={**self.funnel_headers({"Origin": origin})})
        cookie_kv = (r.getheader("Set-Cookie") or "").split(";", 1)[0]
        st, remote_data, _ = self.call("GET", "/api/projects",
                                       headers=self.funnel_headers({"Cookie": cookie_kv}))
        self.assertEqual(st, 200)
        r_by_name = {p["name"]: p for p in remote_data["projects"]}
        self.assertTrue(r_by_name["OtraApp"]["active"])
        self.assertEqual(r_by_name["OtraApp"]["path"], "")


class FunnelCliAndAutostartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        env = mock.patch.dict(os.environ, {"UNIFICADOR_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)

    def _run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def _stop_pid(self, pid: int):
        if not pid:
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.05)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

    def test_port_selection_and_mocked_tailscale_cli(self):
        self.assertEqual(F.choose_funnel_port(None, 8766, {}), 443)
        self.assertEqual(F.choose_funnel_port(None, 8766, {
            "Web": {"pc.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8766"}}}},
            "TCP": {"443": {"HTTPS": True}},
        }), 443)
        self.assertEqual(F.choose_funnel_port(None, 8766, {
            "Web": {"pc.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}}},
        }), 8443)
        self.assertEqual(F.choose_funnel_port(None, 8766, {
            "Web": {"pc.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}}},
            "TCP": {"8443": {"HTTPS": False}},
        }), 10000)
        with self.assertRaises(F.FunnelError):
            F.choose_funnel_port(8080, 8766, {})

        calls = []

        def fake_run(cmd, **_kw):
            calls.append(cmd[1:])
            if cmd[1:3] == ["status", "--json"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=json.dumps({"BackendState": "Running", "Self": {"DNSName": "pc.tail1.ts.net."}}),
                    stderr="")
            if cmd[1:4] == ["serve", "status", "--json"]:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout=json.dumps({"Web": {"pc.tail1.ts.net:443": {
                        "Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}}}}), stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        with mock.patch("subprocess.run", side_effect=fake_run):
            url, port = F.configure_tailscale_funnel(8766, exe="/usr/bin/tailscale")
            self.assertEqual((url, port), ("https://pc.tail1.ts.net:8443/", 8443))
            self.assertIn(["funnel", "--bg", "--https=8443", "http://127.0.0.1:8766"], calls)
            self.assertTrue(F.disable_tailscale_funnel(8443, exe="/usr/bin/tailscale"))
            self.assertIn(["funnel", "--https=8443", "off"], calls)

        stopped = subprocess.CompletedProcess([], 0, stdout=json.dumps({"BackendState": "Stopped"}), stderr="")
        with mock.patch("subprocess.run", return_value=stopped):
            with self.assertRaises(F.FunnelError):
                F.tailscale_dns_name(exe="/usr/bin/tailscale")

    def test_cli_funnel_commands_lifecycle(self):
        proj = Path(self.tmp.name) / "MiProyecto"
        proj.mkdir()
        rules.install(proj)

        code, out, err = self._run_cli("funnel", "enable", str(proj), "--key", "clave-inicial",
                                       "--no-tailscale", "--no-serve", "--local-port", "9876")
        self.assertEqual(code, 0, err)
        self.assertIn("Funnel público activado", out)
        cfg = F.load_config()
        srv = F.load_server()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["server_port"], 9876)
        self.assertTrue(cfg["hide_paths"])
        self.assertTrue(F.verify_key("clave-inicial", cfg))
        self.assertTrue(srv["autostart"])
        self.assertEqual(srv["port"], 9876)
        self.assertEqual(R.active_id(), A.project_id(proj))

        tok = F.sign_session(cfg["cookie_secret"])

        code, out, _ = self._run_cli("funnel", "status")
        self.assertEqual(code, 0)
        self.assertIn("Estado: activado", out)
        self.assertIn("Autoarranque al trabajar: sí", out)
        self.assertIn("MiProyecto", out)

        code, out, err = self._run_cli("funnel", "reset-key", "--key", "nueva-clave-segura")
        self.assertEqual(code, 0, err)
        cfg2 = F.load_config()
        self.assertFalse(F.verify_session(tok, cfg2["cookie_secret"]))
        self.assertFalse(F.verify_key("clave-inicial", cfg2))
        self.assertTrue(F.verify_key("nueva-clave-segura", cfg2))

        # Si tailscale falla al generar nueva clave, no activa ni oculta clave perdida
        proj2 = Path(self.tmp.name) / "ProyectoGen"
        proj2.mkdir()
        rules.install(proj2)
        home2 = Path(self.tmp.name) / "home2"
        with mock.patch.dict(os.environ, {"UNIFICADOR_HOME": str(home2)}), \
             mock.patch("unificador.funnel.configure_tailscale_funnel", side_effect=F.FunnelError("falta permiso")):
            code, _, err = self._run_cli("funnel", "enable", str(proj2), "--generate", "--no-serve")
            self.assertEqual(code, 1)
            self.assertIn("falta permiso", err)
            self.assertFalse(F.load_config()["enabled"])
            self.assertFalse(F.has_key())

        with mock.patch.dict(os.environ, {"UNIFICADOR_HOME": str(home2)}), \
             mock.patch("unificador.funnel.configure_tailscale_funnel",
                        return_value=("https://gen.ts.net/", 443)):
            code, out, err = self._run_cli("funnel", "enable", str(proj2), "--generate", "--no-serve")
            self.assertEqual(code, 0, err)
            self.assertIn("https://gen.ts.net/", out)
            self.assertIn("Clave generada", out)
            gen_key = out.split("Clave generada (guárdala, no se vuelve a mostrar): ", 1)[1].splitlines()[0].strip()
            self.assertTrue(F.verify_key(gen_key))

        code, out, _ = self._run_cli("funnel", "off", "--no-tailscale")
        self.assertEqual(code, 0)
        self.assertFalse(F.load_config()["enabled"])

    def test_uni_autostart_wakes_daemon_and_switches_active_project(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        p1 = Path(self.tmp.name) / "Uno"
        p2 = Path(self.tmp.name) / "Dos"
        p1.mkdir()
        p2.mkdir()
        rules.install(p1)
        rules.install(p2)
        P.mutate(p1 / P.PLAN_FILE, lambda plan: P.add_branches(plan, PLAN, "ia"))
        P.mutate(p2 / P.PLAN_FILE, lambda plan: P.add_branches(plan, PLAN, "ia"))

        F.set_key("clave-daemon")
        cfg = F.load_config()
        cfg["enabled"] = True
        cfg["server_port"] = port
        cfg["public_url"] = "https://mi-pc.tailnet.ts.net/"
        F.save_config(cfg)
        F.register_runtime(port, autostart=True)

        self.addCleanup(lambda: self._stop_pid(F.load_server().get("pid")))

        env = dict(os.environ, UNIFICADOR_HOME=str(self.home))
        run1 = subprocess.run([sys.executable, "-X", "utf8", rules.UNI_REL, "status"],
                              cwd=p1, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(run1.returncode, 0, run1.stderr)
        p1_id = A.project_id(p1)
        p2_id = A.project_id(p2)
        self.assertIn(f"Web: https://mi-pc.tailnet.ts.net/#p={p1_id}", run1.stdout)
        self.assertEqual(R.active_id(), p1_id)
        self.assertTrue(F.is_server_alive(port, timeout=1.0))
        first_pid = F.load_server().get("pid")
        self.assertIsInstance(first_pid, int)

        # Al trabajar en P2 con inbox, cambia active.json al proyecto P2 sin duplicar servidor
        run2 = subprocess.run([sys.executable, "-X", "utf8", rules.UNI_REL, "inbox"],
                              cwd=p2, env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(run2.returncode, 0, run2.stderr)
        self.assertEqual(run2.stdout, "")
        self.assertEqual(R.active_id(), p2_id)
        self.assertEqual(F.load_server().get("pid"), first_pid)

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/projects", headers={"Host": f"127.0.0.1:{port}"})
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        self.assertEqual(resp.status, 200)
        by_name = {item["name"]: item for item in data["projects"]}
        self.assertTrue(by_name["Uno"]["current"])
        self.assertFalse(by_name["Uno"]["active"])
        self.assertFalse(by_name["Dos"]["current"])
        self.assertTrue(by_name["Dos"]["active"])

    def test_doctor_reports_funnel_status(self):
        proj = Path(self.tmp.name) / "DocProj"
        proj.mkdir()
        rules.install(proj)

        code, out, _ = self._run_cli("doctor", str(proj))
        self.assertIn("Funnel público: desactivado", out)

        F.set_key("clave-doc-123")
        cfg = F.load_config()
        cfg["enabled"] = True
        cfg["public_url"] = "https://doc.ts.net/"
        F.save_config(cfg)
        code, out, _ = self._run_cli("doctor", str(proj))
        self.assertIn("Funnel público: https://doc.ts.net/", out)


class FunnelOfflineCacheTest(FunnelServerTest):
    def test_pwa_assets_blocked_without_auth_and_login_cleans_sw(self):
        self.enable_funnel("clave-sw-123")

        # Puerta cerrada: ni el Service Worker ni el manifiesto ni el icono salen sin sesión
        for path in ("/sw.js", "/manifest.webmanifest", "/icon.svg"):
            st, body, _ = self.call("GET", path, headers=self.funnel_headers())
            self.assertEqual(st, 401, path)
            self.assertEqual(body.get("error"), "Necesitas iniciar sesión.")

        # El login no expone SW/manifest/app, avisa con cabecera y limpia SW/caches previos
        st, html, r = self.call("GET", "/", headers=self.funnel_headers())
        self.assertEqual(st, 200)
        self.assertEqual(r.getheader("X-Unificador-Auth"), "login")
        self.assertNotIn("sw.js", html)
        self.assertNotIn("manifest.webmanifest", html)
        self.assertNotIn("app.js", html)
        self.assertIn("serviceWorker", html)
        self.assertIn("caches", html)
        self.assertIn("reset-key", html)

    def test_authenticated_pwa_shell_manifest_sw_and_cleanup_contracts(self):
        self.enable_funnel("clave-sw-123")
        origin = f"https://{self.TS_HOST}"
        _, _, r = self.call("POST", "/auth/login", {"key": "clave-sw-123"},
                            headers=self.funnel_headers({"Origin": origin}))
        cookie_kv = (r.getheader("Set-Cookie") or "").split(";", 1)[0]
        auth_h = self.funnel_headers({"Cookie": cookie_kv})

        # index.html autenticado incluye manifest, banner offline, botones logout y CSP para SW/manifest
        st, html, r = self.call("GET", "/", headers=auth_h)
        self.assertEqual(st, 200)
        csp = r.getheader("Content-Security-Policy") or ""
        self.assertIn("worker-src 'self'", csp)
        self.assertIn("manifest-src 'self'", csp)
        for token in ("manifest.webmanifest", "offline-banner", "offline-retry", "logout-home", "logout-board"):
            self.assertIn(token, html)

        # Manifiesto válido y MIME correcto
        st, raw_manifest, r = self.call("GET", "/manifest.webmanifest", headers=auth_h)
        self.assertEqual(st, 200)
        self.assertIn("application/manifest+json", r.getheader("Content-Type") or "")
        manifest = json.loads(raw_manifest)
        self.assertEqual(manifest["name"], "Unificador")
        self.assertEqual(manifest["icons"][0]["src"], "icon.svg")

        # Icono SVG válido
        st, svg, r = self.call("GET", "/icon.svg", headers=auth_h)
        self.assertEqual(st, 200)
        self.assertIn("image/svg+xml", r.getheader("Content-Type") or "")
        self.assertIn("<svg", svg)

        # Service Worker servido con MIME JS, reglas network-first, limpieza en 401/logout y sin tocar SSE/auth
        st, sw_code, r = self.call("GET", "/sw.js", headers=auth_h)
        self.assertEqual(st, 200)
        ct = r.getheader("Content-Type") or ""
        self.assertTrue("javascript" in ct, ct)
        for needle in ("networkFirst", "X-Unificador-Offline", "X-Unificador-Cached-At",
                       "X-Unificador-Auth", "wipeAll", "CLEAR_CACHE", "/auth/", "/api/events"):
            self.assertIn(needle, sw_code)

        # Cada ruta declarada en SHELL dentro de sw.js existe y responde 200 autenticada
        import re as _re
        shell_block = _re.search(r"const SHELL = \[(.*?)\];", sw_code, _re.S)
        self.assertIsNotNone(shell_block)
        shell_paths = _re.findall(r'"(\./[^"]*)"', shell_block.group(1))
        self.assertGreaterEqual(len(shell_paths), 10)
        for rel in shell_paths:
            route_path = "/" + rel[2:]
            st_asset, _, _ = self.call("GET", route_path, headers=auth_h)
            self.assertEqual(st_asset, 200, route_path)

        # El registro de SW solo ocurre cuando app.remote es true (nunca en sesión local 127.0.0.1)
        st, app_js, _ = self.call("GET", "/app.js", headers=auth_h)
        self.assertEqual(st, 200)
        self.assertIn("if (app.remote && !swRegistered", app_js)
        st, util_js, _ = self.call("GET", "/util.js", headers=auth_h)
        self.assertEqual(st, 200)
        self.assertIn("clearOfflineCache", util_js)
        self.assertIn("/auth/logout", util_js)


if __name__ == "__main__":
    unittest.main()
