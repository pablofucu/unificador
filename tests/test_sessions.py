"""Lectura de las sesiones nativas de Claude Code."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from unificador import sessions as S

SID = "11111111-2222-3333-4444-555555555555"


def user(text, **extra):
    return {"type": "user", "message": {"role": "user", "content": text},
            "timestamp": "2026-11-11T10:00:00Z", "entrypoint": "claude-desktop", **extra}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)},
            "timestamp": "2026-11-11T10:00:05Z"}


TEXT = lambda t: {"type": "text", "text": t}
TOOL = lambda n, **i: {"type": "tool_use", "name": n, "input": i}


class SessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "projects"
        self.project = Path(self.tmp.name) / "Mi proyecto"
        self.project.mkdir()
        self.dir = S.project_dir(self.project, self.base)
        self.dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, sid, entries, raw_tail=""):
        p = self.dir / f"{sid}.jsonl"
        p.write_text("\n".join(json.dumps(e, separators=(",", ":")) for e in entries) + "\n" + raw_tail,
                     encoding="utf-8")
        return p

    def test_project_dir_encodes_every_odd_character(self):
        name = S.project_dir(r"C:\Users\ana\Mis cosas\app_1", self.base).name
        self.assertTrue(name.endswith("C--Users-ana-Mis-cosas-app-1"), name)

    def test_turns_skip_noise_and_merge_assistant_chunks(self):
        p = self.write(SID, [
            {"type": "attachment", "attachment": {"type": "hook_success"}},
            user("Hola, arregla el total"),
            assistant(TEXT("Voy a mirarlo.")),
            assistant(TOOL("Bash", command="pytest -q")),
            user([{"type": "tool_result", "content": "ok"}]),
            assistant(TEXT("Arreglado.")),
            user("<system-reminder>ruido</system-reminder>"),
            user("resumen automático", isCompactSummary=True),
            user("de un ayudante", isSidechain=True),
            user("meta", isMeta=True),
            user([{"type": "text", "text": "Gracias"}]),
        ], raw_tail='{"type":"user","message":{"content":"a med')
        turns = S.read_turns(p)
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user"])
        self.assertEqual(turns[1]["text"], "Voy a mirarlo.\n\nArreglado.")
        self.assertEqual(turns[1]["tools"], ["Ejecuta pytest -q"])
        self.assertEqual(turns[2]["text"], "Gracias")

    def test_list_uses_custom_title_then_first_message_and_sorts_by_date(self):
        a = self.write(SID, [user("Primera petición muy " + "larga " * 30), assistant(TEXT("ok"))])
        b = self.write("22222222-0000-0000-0000-000000000000", [
            user("hola"), {"type": "custom-title", "customTitle": "Carrito"},
            {"type": "custom-title", "customTitle": "Carrito y pagos"}])
        self.write("33333333-0000-0000-0000-000000000000", [{"type": "attachment"}])  # sin mensajes
        os.utime(a, (1000, 1000))
        os.utime(b, (2000, 2000))
        got = S.list_sessions(self.project, self.base)
        self.assertEqual([s["title"] for s in got][0], "Carrito y pagos")
        self.assertEqual(len(got), 2)
        self.assertLessEqual(len(got[1]["title"]), S.TITLE_MAX)
        self.assertEqual(got[1]["origin"], "app")
        self.assertEqual(got[0]["messages"], 1)

    def test_summary_cache_notices_changes(self):
        p = self.write(SID, [user("uno")])
        self.assertEqual(S.summarize(p)["messages"], 1)
        self.write(SID, [user("uno"), assistant(TEXT("a")), user("dos y algo más")])
        self.assertEqual(S.summarize(p)["messages"], 2)

    def test_read_session_and_bad_ids(self):
        self.write(SID, [user("hola")])
        got = S.read_session(self.project, SID, self.base)
        self.assertEqual((got["id"], got["turns"][0]["text"]), (SID, "hola"))
        for bad in ("../../secreto", "", "x" * 10, SID + "/.."):
            with self.assertRaises(S.SessionError):
                S.read_session(self.project, bad, self.base)
        with self.assertRaises(S.SessionError):
            S.read_session(self.project, "99999999-0000-0000-0000-000000000000", self.base)

    def test_missing_project_folder_is_empty(self):
        self.assertEqual(S.list_sessions(Path(self.tmp.name) / "otro", self.base), [])
        self.assertEqual(S.latest_mtime(Path(self.tmp.name) / "otro", self.base), 0.0)

    def test_tool_descriptions(self):
        self.assertEqual(S.describe_tool("Read", {"file_path": "a.py"}), "Lee a.py")
        self.assertEqual(S.describe_tool("mcp__x__show_widget", None), "show widget")


if __name__ == "__main__":
    unittest.main()
