"""Conversión de un tablero Kanvas al plan de Unificador."""

import json
import tempfile
import unittest
from pathlib import Path

from unificador import kanvas_import as K
from unificador import plan as P

BOARD = {"kanvas": 1, "title": "Tienda", "groups": [
    {"id": "ES", "name": "Fase 1: Especificación"}, {"id": "IT", "name": "Interfaz"},
    {"id": "VA", "name": "Vacío"}],
    "tasks": [
        {"id": "ES-01", "title": "Escribir la especificación", "state": "done", "group": "ES",
         "notes": [{"at": "2026-01-01T00:00:00Z", "by": "claude", "text": "Escrita y revisada"}]},
        {"id": "IT-01", "title": "Vista del plan", "state": "review", "group": "IT", "desc": "d"},
        {"id": "IT-02", "title": "Chat", "state": "doing", "group": "IT", "deps": ["IT-01", "ES-01"]},
        {"id": "IT-04", "title": "Colores", "state": "todo", "group": "IT", "deps": ["IT-01"]},
        {"id": "IT-05", "title": "Corregir", "state": "proposed", "group": "IT", "deps": ["IT-02"]},
        {"id": "IT-03", "title": "Descartada", "state": "withdrawn", "group": "IT"},
        {"id": "X-1", "title": "Suelta", "state": "todo"},
    ]}


class ImportTest(unittest.TestCase):
    def test_groups_become_branches_and_deps_become_named_phases(self):
        plan = K.convert(BOARD)
        self.assertEqual([b["name"] for b in plan["branches"]], ["Especificación", "Interfaz", "OTROS"])
        it = plan["branches"][1]
        self.assertEqual([p["name"] for p in it["phases"]],
                         ["Vista del plan", "Chat y 1 más", "Corregir"])
        states = {s["id"]: s["state"] for _, _, s in P.iter_steps(plan, archived=True)}
        self.assertEqual(states, {"ES-01": "done", "IT-01": "done", "IT-02": "doing",
                                  "IT-04": "pending", "IT-05": "pending", "X-1": "pending"})
        self.assertEqual(it["next_id"], 6)
        self.assertTrue(plan["branches"][0].get("archived"))
        self.assertEqual(plan["branches"][0]["phases"][0]["steps"][0]["result"], "Escrita y revisada")

    def test_result_is_a_valid_plan_for_the_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "kanvas.json").write_text(json.dumps(BOARD), encoding="utf-8")
            K.import_board(root)
            with self.assertRaises(P.PlanError):
                K.import_board(root)
            K.import_board(root, force=True)
            path = root / P.PLAN_FILE
            P.mutate(path, lambda plan: P.set_state(plan, "it-04", P.DONE, "yo", "ok"))
            P.mutate(path, lambda plan: P.add_step(plan, "IT", "Corregir", "Otro"))
            plan = P.load(path)
            self.assertEqual(P.find_step(plan, "IT-6")[2]["title"], "Otro")
            self.assertIn("Interfaz", P.render_status(plan))
            self.assertNotIn("Especificación", P.render_status(plan))
            self.assertTrue((root / "kanvas.json").is_file())

    def test_bad_input(self):
        with self.assertRaises(P.PlanError):
            K.convert({"groups": []})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.PlanError):
                K.import_board(tmp)

    def test_cycles_and_generic_titles_do_not_break(self):
        plan = K.convert({"tasks": [
            {"id": "A-1", "title": "1", "state": "todo", "group": "A", "deps": ["A-2"]},
            {"id": "A-2", "title": "2", "state": "todo", "group": "A", "deps": ["A-1"]}]})
        for p in plan["branches"][0]["phases"]:
            self.assertFalse(P.GENERIC_PHASE.match(p["name"]))


if __name__ == "__main__":
    unittest.main()
