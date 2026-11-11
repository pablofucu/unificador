"""Conversaciones de Antigravity: se leen de una copia de mentira de sus bases de datos."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from unificador import agy_sessions as A
from unificador import sessions as S

CID = "11111111-2222-3333-4444-555555555555"
OTHER = "99999999-2222-3333-4444-555555555555"


def varint(n):
    out = b""
    while True:
        out += bytes([(n & 0x7F) | (0x80 if n > 0x7F else 0)])
        n >>= 7
        if not n:
            return out


def field(num, value):
    if isinstance(value, int):
        return varint(num << 3) + varint(value)
    if isinstance(value, str):
        value = value.encode("utf-8")
    return varint(num << 3 | 2) + varint(len(value)) + value


def user_step(text):
    return field(1, 14) + field(19, field(2, text))


def agent_step(text="", tools=()):
    body = field(1, text) if text else b""
    for name, args in tools:
        body += field(7, field(1, "id") + field(2, name) + field(3, json.dumps(args)))
    return field(1, 15) + field(20, body)


def stamp(seconds):
    return field(1, field(1, seconds) + field(2, 5))


class AgySessionsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name) / "agy"
        self.project = Path(tmp.name) / "Mi Proyecto"
        (self.base / "conversations").mkdir(parents=True)
        self.project.mkdir()
        uri = "file:///" + self.project.resolve().as_posix().lstrip("/").replace(" ", "%20")
        db = sqlite3.connect(self.base / "conversation_summaries.db")
        db.execute("create table conversation_summaries (conversation_id text, title text, preview text, "
                   "step_count integer, last_modified_time text, workspace_uris text)")
        db.executemany("insert into conversation_summaries values (?,?,?,?,?,?)", [
            (CID, "", "[SISTEMA: CONTEXTO…", 5, "2026-11-08 18:43:22.8889869+00:00", json.dumps([uri])),
            (OTHER, "De otro sitio", "x", 2, "2026-11-09 10:00:00+00:00", '["file:///C:/otro/sitio"]'),
        ])
        db.commit()
        db.close()
        db = sqlite3.connect(self.base / "conversations" / f"{CID}.db")
        db.execute("create table steps (idx integer primary key, step_type integer, status integer, "
                   "metadata blob, step_payload blob)")
        steps = [
            (14, user_step("[SISTEMA: relleno]\n" + A.OLD_MARKER + "\nArregla el menú")),
            (15, agent_step("Voy a mirar.", [("read_file", {"Path": "C:/x/menu.js"})])),
            (132, field(1, 132) + field(140, field(1, "resultado"))),
            (15, agent_step("", [("run_command", {"CommandLine": "npm test", "toolSummary": "Pasa las pruebas"})])),
            (15, agent_step("Hecho.")),
            (14, user_step("Gracias")),
        ]
        db.executemany("insert into steps values (?,?,3,?,?)",
                       [(i, kind, stamp(1794000000 + i), payload) for i, (kind, payload) in enumerate(steps)])
        db.commit()
        db.close()

    def test_list_only_this_project(self):
        got = A.list_sessions(self.project, self.base)
        self.assertEqual([s["id"] for s in got], [CID])
        self.assertEqual(got[0], {"id": CID, "agent": "antigravity", "title": "Arregla el menú",
                                  "updated": "2026-11-08T18:43:22+00:00", "messages": 5, "origin": "antigravity"})

    def test_read_turns(self):
        turns = A.read_session(self.project, CID, self.base)["turns"]
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user"])
        self.assertEqual(turns[0]["text"], "Arregla el menú")
        self.assertEqual(turns[1]["text"], "Voy a mirar.\n\nHecho.")
        self.assertEqual(turns[1]["tools"], ["Lee C:/x/menu.js", "Ejecuta Pasa las pruebas"])
        self.assertTrue(turns[1]["at"].startswith("2026-"))
        self.assertEqual(turns[2]["text"], "Gracias")

    def test_refusals_and_missing(self):
        for bad in ("../x", "", OTHER, "aaaaaaaa-0000"):
            with self.assertRaises(S.SessionError):
                A.read_session(self.project, bad, self.base)
        nowhere = self.base / "no-existe"
        self.assertEqual(A.list_sessions(self.project, nowhere), [])
        self.assertEqual(A.latest_mtime(self.project, nowhere), 0.0)
        self.assertGreater(A.latest_mtime(self.project, self.base), 0)

    def test_garbage_does_not_break(self):
        self.assertEqual(A.fields(b"\xff\xff\xff"), [])
        self.assertEqual(A.get_text(b"\x0a\x05ab", 1), "")
        self.assertEqual(A._iso("ayer"), "")
        self.assertEqual(A._iso("2026-11-08 20:43:22.5+02:00"), "2026-11-08T18:43:22+00:00")


if __name__ == "__main__":
    unittest.main()
