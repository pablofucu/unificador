"""Agentes: órdenes, lectura de su salida y envío sin tocar el mensaje."""

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from unificador import agents as G

sys.path.insert(0, str(Path(__file__).parent))
from test_app import ServerCase  # noqa: E402

FAKE = str(Path(__file__).with_name("fake_agent.py"))
real_build = G.build_command


class FakeAgents:
    """Sustituye las CLI por ``fake_agent.py`` conservando los argumentos reales."""

    def start_fakes(self, folder):
        self.log = str(Path(folder) / "recibido.json")

        def build(agent, exe, *rest, **kw):
            cmd, stdin = real_build(agent, exe, *rest, **kw)
            return [sys.executable, "-X", "utf8", FAKE, agent, self.log] + cmd[1:], stdin

        for target, value in (("build_command", build), ("_exe", lambda agent: "falso.exe")):
            p = mock.patch.object(G, target, value)
            p.start()
            self.addCleanup(p.stop)

    def received(self):
        return json.loads(Path(self.log).read_text(encoding="utf-8"))


class CommandTest(unittest.TestCase):
    def test_claude_command(self):
        cmd, stdin = G.build_command("claude", "claude", "hola", "abc", True, "opus", "high", "plan")
        self.assertEqual(stdin, "hola")
        self.assertNotIn("hola", cmd)
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
        self.assertEqual(cmd[cmd.index("--effort") + 1], "high")
        self.assertEqual(cmd[cmd.index("--permission-mode") + 1], "plan")
        self.assertEqual(cmd[-2:], ["--session-id", "abc"])
        cmd, _ = G.build_command("claude", "claude", "hola", "abc", False)
        self.assertEqual(cmd[-2:], ["--resume", "abc"])
        self.assertNotIn("--model", cmd)
        self.assertNotIn("--effort", cmd)

    def test_agy_command(self):
        cmd, stdin = G.build_command("antigravity", "agy", "hola", "", True, "gemini-4-argon-high", "", "acceptEdits")
        self.assertIsNone(stdin)
        self.assertEqual(cmd[-2:], ["-p", "hola"])
        self.assertEqual(cmd[cmd.index("--mode") + 1], "accept-edits")
        self.assertEqual(cmd[cmd.index("--model") + 1], "gemini-4-argon-high")
        self.assertNotIn("--conversation", cmd)
        cmd, _ = G.build_command("antigravity", "agy", "hola", "c1", False)
        self.assertEqual(cmd[cmd.index("--conversation") + 1], "c1")

    def test_models_and_settings(self):
        out = "Fetching available models...\ngemini-4-argon-high\tGemini 4 Argon (High)\nraro; rm\tX\n\n"
        self.assertEqual(G.parse_agy_models(out), [{"id": "gemini-4-argon-high", "name": "Gemini 4 Argon (High)"}])
        clean = G.clean_settings({"agent": "codex", "agents": {"claude": {"model": "-x; rm", "effort": "x"}}})
        self.assertEqual(clean["agent"], "claude")
        self.assertEqual(clean["agents"]["claude"], {"model": "", "effort": "", "mode": "auto"})
        self.assertEqual(G.clean_settings("x")["agents"]["antigravity"]["mode"], "auto")
        self.assertEqual(G.clean_settings({"agents": {"claude": {"model": "--resume"}}})["agents"]["claude"]["model"], "")


class StreamTest(FakeAgents, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.start_fakes(self.tmp.name)

    def test_claude_message_goes_untouched(self):
        text = "Arregla   esto\n  «con» \"comillas\" & cosas raras %PATH% ñ"
        events = list(G.stream(self.tmp.name, "claude", text, model="sonnet", effort="low"))
        self.assertEqual([e["type"] for e in events], ["run", "session", "text", "model", "tool", "text", "done"])
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "text"), "Hola \n\nmundo")
        got = self.received()
        self.assertEqual(got["stdin"], text)
        self.assertEqual(got["agent"], "claude")
        args = got["args"]
        session = events[1]["id"]
        self.assertEqual(args[args.index("--session-id") + 1], session)
        self.assertEqual((args[args.index("--model") + 1], args[args.index("--effort") + 1]), ("sonnet", "low"))
        list(G.stream(self.tmp.name, "claude", "sigue", session))
        args = self.received()["args"]
        self.assertEqual(args[args.index("--resume") + 1], session)
        self.assertEqual(G.busy_sessions(), [])

    def test_antigravity(self):
        events = list(G.stream(self.tmp.name, "antigravity", "haz algo", mode="plan"))
        self.assertEqual([e["type"] for e in events], ["run", "session", "tool", "text", "done"])
        self.assertEqual(events[1]["id"], "11111111-2222-3333-4444-555555555555")
        args = self.received()["args"]
        self.assertEqual(args[-2:], ["-p", "haz algo"])
        self.assertEqual(args[args.index("--mode") + 1], "plan")

    def test_errors(self):
        def last_error(*a, **kw):
            events = list(G.stream(self.tmp.name, *a, **kw))
            self.assertEqual(events[-1], {"type": "done"})
            return events[-2]["text"] if len(events) > 1 and events[-2]["type"] == "error" else ""

        self.assertIn("algo va mal", last_error("claude", "rompe"))
        self.assertIn("Escribe", last_error("claude", "   "))
        self.assertIn("no es válida", last_error("claude", "hola", "../../x"))
        self.assertIn("No conozco", last_error("codex", "hola"))
        self.assertIn("demasiado largo", last_error("antigravity", "a" * 30000))
        with mock.patch.object(G, "_exe", lambda agent: ""):
            self.assertIn("no está instalado", last_error("claude", "hola"))
        with mock.patch.object(G, "_exe", lambda agent: "agy.CMD"), \
                mock.patch.object(G, "build_command", real_build):
            self.assertIn("no es seguro", last_error("antigravity", "hola & calc"))

    def test_stop(self):
        events, runs = [], []

        def work():
            for ev in G.stream(self.tmp.name, "claude", "duerme"):
                events.append(ev)
                if ev["type"] == "run":
                    runs.append(ev["id"])

        t = threading.Thread(target=work)
        t.start()
        for _ in range(100):
            if any(e["type"] == "text" for e in events):
                break
            time.sleep(0.1)
        self.assertEqual(len(G.busy_sessions()), 1)
        busy = list(G.stream(self.tmp.name, "claude", "otra", G.busy_sessions()[0]))
        self.assertIn("ya está respondiendo", busy[0]["text"])
        self.assertTrue(G.stop(runs[0]))
        t.join(15)
        self.assertFalse(t.is_alive())
        self.assertEqual([e["type"] for e in events][-2:], ["stopped", "done"])
        self.assertFalse(G.stop("no-existe"))


class ChatRouteTest(FakeAgents, ServerCase):
    def setUp(self):
        super().setUp()
        self.start_fakes(self.root)

    def test_chat_stream_uses_saved_settings(self):
        self.call("POST", "/api/settings", {"agents": {"claude": {"model": "haiku", "effort": "max"}}})
        status, raw, r = self.call("POST", "/api/chat", {"text": "hola"})
        self.assertEqual(status, 200)
        self.assertIn("ndjson", r.getheader("Content-Type"))
        events = [json.loads(line) for line in raw.splitlines()]
        self.assertEqual([e["type"] for e in events], ["run", "session", "text", "model", "tool", "text", "done"])
        got = self.received()
        self.assertEqual(got["stdin"], "hola")
        args = got["args"]
        self.assertEqual((args[args.index("--model") + 1], args[args.index("--effort") + 1]), ("haiku", "max"))
        self.call("POST", "/api/chat", {"text": "hola", "model": "", "effort": "low"})
        args = self.received()["args"]
        self.assertNotIn("--model", args)
        self.assertEqual(args[args.index("--effort") + 1], "low")

    def test_chat_refusals(self):
        self.assertEqual(self.call("POST", "/api/chat", {"text": ""})[0], 400)
        self.assertEqual(self.call("POST", "/api/chat", {"text": "x", "agent": "codex"})[0], 400)
        self.assertEqual(self.call("POST", "/api/chat", {"text": "x"}, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("GET", "/api/chat")[0], 405)
        self.assertEqual(self.call("POST", "/api/chat/stop", {"run": "nada"})[1], {"stopped": False})
        self.assertEqual(self.call("POST", "/api/open-native", {"agent": "codex"})[0], 400)
        self.assertEqual(self.call("POST", "/api/open-native", {"agent": "claude", "session": "../x"})[0], 400)


if __name__ == "__main__":
    unittest.main()
