"""Registro de proyectos."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from unificador import projects as P


class ProjectsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        patcher = mock.patch.dict(os.environ, {"UNIFICADOR_HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_empty_when_missing_or_broken(self):
        self.assertEqual(P.listing(), [])
        self.home.mkdir()
        (self.home / "proyectos.json").write_text("{roto", encoding="utf-8")
        self.assertEqual(P.listing(), [])
        P.register(self.tmp.name)  # se recupera sobre un fichero roto
        self.assertEqual(len(P.listing()), 1)

    def test_register_is_idempotent_and_listing_sorted(self):
        b, a = Path(self.tmp.name) / "beta", Path(self.tmp.name) / "Alfa"
        b.mkdir()
        P.register(b)
        P.register(b)
        P.register(a)  # no existe
        items = P.listing()
        self.assertEqual([i["name"] for i in items], ["Alfa", "beta"])
        self.assertEqual([i["exists"] for i in items], [False, True])
        self.assertTrue(os.path.isabs(items[0]["path"]))
        self.assertRegex(items[1]["id"], r"^[0-9a-f]{10}$")

    def test_find_and_forget(self):
        d = Path(self.tmp.name) / "proy"
        d.mkdir()
        P.register(d)
        pid = P.listing()[0]["id"]
        self.assertEqual(P.find(pid), Path(os.path.abspath(d)))
        self.assertIsNone(P.find("nadie"))
        P.forget(d)
        P.forget(d)
        self.assertEqual(P.listing(), [])
        self.assertIsNone(P.find(pid))


if __name__ == "__main__":
    unittest.main()
