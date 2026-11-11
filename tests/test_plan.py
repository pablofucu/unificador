"""Formato del plan (unificador.json) y su mini-CLI."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from unificador import plan as P

SAMPLE = {"branches": [{
    "name": "Carrito de compra", "icon": "🛒", "goal": "Comprar desde la web",
    "phases": [
        {"name": "Cimientos", "steps": [{"title": "Modelo del carrito", "desc": "Hecho cuando se guarda"}]},
        {"name": "Pagos", "steps": [{"title": "Pasarela"}, "Recibo por correo"]},
    ]}]}


def run(path, *argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    old = P.sys.stdin
    if stdin is not None:
        P.sys.stdin = io.StringIO(stdin)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            code = P.main(["-f", str(path), *argv])
    finally:
        P.sys.stdin = old
    return code, out.getvalue(), err.getvalue()


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / P.PLAN_FILE

    def tearDown(self):
        self.tmp.cleanup()

    def make(self):
        code, out, err = run(self.path, "plan", stdin=json.dumps(SAMPLE))
        self.assertEqual(code, 0, err)
        return P.load(self.path)

    def test_plan_creates_branch_phases_and_ids(self):
        plan = self.make()
        b = plan["branches"][0]
        self.assertEqual((b["key"], b["name"], b["icon"]), ("CDC", "Carrito de compra", "🛒"))
        self.assertEqual([p["name"] for p in b["phases"]], ["Cimientos", "Pagos"])
        self.assertEqual([s["id"] for _, _, s in P.iter_steps(plan)], ["CDC-1", "CDC-2", "CDC-3"])
        self.assertTrue(all(s["state"] == P.PENDING for _, _, s in P.iter_steps(plan)))

    def test_single_branch_object_is_accepted(self):
        code, _, err = run(self.path, "plan", stdin=json.dumps(SAMPLE["branches"][0]))
        self.assertEqual(code, 0, err)

    def test_generic_phase_names_are_rejected_and_nothing_is_saved(self):
        for bad in ("Fase 1", "fase 2:", "Etapa 3", "1", "Step 2"):
            data = {"branches": [{"name": "X", "phases": [{"name": bad, "steps": ["a"]}]}]}
            code, _, err = run(self.path, "plan", stdin=json.dumps(data))
            self.assertEqual(code, 1, bad)
            self.assertIn("no dice nada", err)
        self.assertFalse(self.path.exists())

    def test_malformed_plans_are_rejected(self):
        cases = ["no es json", "{}", '{"branches": []}',
                 '{"branches": [{"name": "A"}]}',
                 '{"branches": [{"name": "A", "phases": [{"name": "Base", "steps": []}]}]}',
                 '{"branches": [{"name": "A", "phases": [{"name": "Base", "steps": [{"desc": "x"}]}]}]}',
                 '{"branches": [{"phases": [{"name": "Base", "steps": ["a"]}]}]}']
        for raw in cases:
            code, _, err = run(self.path, "plan", stdin=raw)
            self.assertEqual(code, 1, raw)
            self.assertTrue(err.strip())

    def test_duplicate_branch_name_is_rejected(self):
        self.make()
        code, _, err = run(self.path, "plan", stdin=json.dumps(SAMPLE))
        self.assertEqual(code, 1)
        self.assertIn("ya hay una rama", err)

    def test_start_done_note_reopen(self):
        self.make()
        self.assertEqual(run(self.path, "--as", "claude", "start", "cdc-1")[0], 0)
        self.assertEqual(P.find_step(P.load(self.path), "CDC-1")[2]["state"], P.DOING)
        self.assertEqual(run(self.path, "note", "CDC-1", "a medias")[0], 0)
        self.assertEqual(run(self.path, "done", "CDC-1", "-m", "Guarda en disco; 3 pruebas")[0], 0)
        step = P.find_step(P.load(self.path), "CDC-1")[2]
        self.assertEqual((step["state"], step["result"]), (P.DONE, "Guarda en disco; 3 pruebas"))
        self.assertEqual([n["kind"] for n in step["notes"]], ["start", "note", "done"])
        self.assertEqual(step["notes"][0]["by"], "claude")
        self.assertEqual(run(self.path, "reopen", "CDC-1")[0], 0)
        self.assertEqual(P.find_step(P.load(self.path), "CDC-1")[2]["state"], P.PENDING)

    def test_done_needs_a_summary_and_unknown_step_fails(self):
        self.make()
        with self.assertRaises(SystemExit):
            run(self.path, "done", "CDC-1")
        code, _, err = run(self.path, "start", "ZZ-9")
        self.assertEqual(code, 1)
        self.assertIn("CDC-1", err)

    def test_add_step_and_new_phase(self):
        self.make()
        self.assertEqual(run(self.path, "add", "CDC", "Pagos", "Devoluciones")[0], 0)
        self.assertEqual(run(self.path, "add", "carrito de compra", "Pulido", "Animaciones")[0], 0)
        b = P.load(self.path)["branches"][0]
        self.assertEqual([p["name"] for p in b["phases"]], ["Cimientos", "Pagos", "Pulido"])
        self.assertEqual(b["phases"][1]["steps"][-1]["id"], "CDC-4")
        self.assertEqual(b["phases"][2]["steps"][0]["id"], "CDC-5")
        self.assertEqual(run(self.path, "add", "CDC", "Fase 4", "x")[0], 1)

    def test_change_request_shows_in_status_until_done(self):
        self.make()
        run(self.path, "done", "CDC-1", "-m", "ok")
        P.mutate(self.path, lambda plan: P.request_change(plan, "CDC-1", "El total sale mal"))
        _, out, _ = run(self.path, "status")
        self.assertIn("PIDE CAMBIOS", out)
        self.assertIn("El total sale mal", out)
        run(self.path, "done", "CDC-1", "-m", "arreglado")
        _, out, _ = run(self.path, "status")
        self.assertNotIn("PIDE CAMBIOS", out)

    def test_status_shows_progress_and_next(self):
        _, out, _ = run(self.path, "status")
        self.assertIn("vacío", out)
        self.make()
        run(self.path, "done", "CDC-1", "-m", "ok")
        _, out, _ = run(self.path)
        self.assertIn("1/3", out)
        self.assertIn("Siguiente: CDC-2", out)

    def test_archive_and_drop(self):
        self.make()
        self.assertEqual(run(self.path, "archive", "CDC")[0], 1)
        self.assertEqual(run(self.path, "archive", "CDC", "--force")[0], 0)
        self.assertIn("vacío", run(self.path, "status")[1])
        self.assertEqual(run(self.path, "plan", stdin=json.dumps(SAMPLE))[0], 0)  # el nombre queda libre
        self.assertEqual(P.load(self.path)["branches"][1]["key"], "CDC2")
        self.assertEqual(run(self.path, "drop", "CDC2")[0], 0)
        self.assertEqual(len(P.load(self.path)["branches"]), 1)

    def test_colors_do_not_repeat_between_live_branches(self):
        for name in ("Uno mas", "Dos mas", "Tres mas"):
            P.mutate(self.path, lambda plan, n=name: P.add_branches(
                plan, {"name": n, "phases": [{"name": "Base", "steps": ["a"]}]}))
        self.assertEqual([b["color"] for b in P.load(self.path)["branches"]], [0, 1, 2])

    def test_broken_file_gives_clear_error(self):
        self.path.write_text("{roto", encoding="utf-8")
        code, _, err = run(self.path, "status")
        self.assertEqual(code, 1)
        self.assertIn("no es JSON válido", err)


if __name__ == "__main__":
    unittest.main()
