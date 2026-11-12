"""Formato del plan (unificador.json) y su mini-CLI."""

import io
import json
import tempfile
import time
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

    def test_branch_in_one_command_without_json(self):
        code, out, err = run(self.path, "branch", "Web de recetas", "--icon", "🍲", "--goal", "Ver recetas",
                             "--phase", "Cimientos", "Página principal", "Ficha :: Hecha cuando se ve una receta",
                             "--phase", "Pulido", "Buscador")
        self.assertEqual(code, 0, err)
        self.assertIn("start WDR-1", out)  # dice qué escribir después
        b = P.load(self.path)["branches"][0]
        self.assertEqual((b["icon"], b["goal"], [p["name"] for p in b["phases"]]), ("🍲", "Ver recetas", ["Cimientos", "Pulido"]))
        self.assertEqual(b["phases"][0]["steps"][1]["desc"], "Hecha cuando se ve una receta")
        self.assertIn("done WDR-1 -m", run(self.path, "start", "WDR-1")[1])
        self.assertIn("start WDR-2", run(self.path, "done", "WDR-1", "-m", "ok")[1])
        for argv in (["branch", "Sin fases"], ["branch", "Fase vacía", "--phase", "Cimientos"]):
            code, _, err = run(self.path, *argv)
            self.assertEqual(code, 1)
            self.assertIn('--phase "Nombre de fase"', err)
        code, _, err = run(self.path, "plan", stdin="")
        self.assertEqual(code, 1)
        self.assertIn("uni.py branch", err)

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
        self.assertEqual(run(self.path, "note", "CDC-1", "firmado al final", "--as", "gemini")[0], 0)
        self.assertEqual(P.find_step(P.load(self.path), "CDC-1")[2]["notes"][-1]["by"], "gemini")
        self.assertEqual(run(self.path, "done", "CDC-1", "-m", "Guarda en disco; 3 pruebas")[0], 0)
        step = P.find_step(P.load(self.path), "CDC-1")[2]
        self.assertEqual((step["state"], step["result"]), (P.DONE, "Guarda en disco; 3 pruebas"))
        self.assertEqual([n["kind"] for n in step["notes"]], ["start", "note", "note", "done"])
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

    # ── Fases con parada suave ──

    def phase(self, i):
        return P.load(self.path)["branches"][0]["phases"][i]

    def test_finishing_a_phase_waits_for_review(self):
        self.make()
        code, out, _ = run(self.path, "done", "CDC-1", "-m", "ok")
        self.assertEqual(code, 0)
        self.assertIn("FASE TERMINADA: «Cimientos»", out)
        self.assertIn("uni.py approve CDC", out)
        self.assertIn('revise CDC -m', out)
        self.assertEqual(self.phase(0)["review"]["state"], P.WAITING)
        self.assertIn("esperando tu revisión", run(self.path, "status")[1])
        # sin candado: se puede empezar la fase siguiente, con aviso
        code, out, _ = run(self.path, "start", "CDC-2")
        self.assertEqual(code, 0)
        self.assertIn("Aviso", out)
        code, out, _ = run(self.path, "approve", "CDC", "-m", "Me gusta")
        self.assertEqual(code, 0, out)
        self.assertIn("aprobada", out)
        review = self.phase(0)["review"]
        self.assertEqual((review["state"], review["text"], review["by"], review["seen"]),
                         (P.APPROVED, "Me gusta", "persona", True))
        self.assertNotIn("Aviso", run(self.path, "start", "CDC-2")[1])
        # la última fase también para
        run(self.path, "done", "CDC-2", "-m", "ok")
        self.assertNotIn("FASE TERMINADA", run(self.path, "status")[1])
        out = run(self.path, "done", "CDC-3", "-m", "ok")[1]
        self.assertIn("última fase", out)

    def test_revise_and_reopen_clear_review(self):
        self.make()
        run(self.path, "done", "CDC-1", "-m", "ok")
        with self.assertRaises(SystemExit):  # -m es obligatorio
            run(self.path, "revise", "CDC")
        code, out, _ = run(self.path, "revise", "CDC", "Cimientos", "-m", "Falta validar")
        self.assertEqual(code, 0)
        self.assertIn("reopen", out)
        self.assertEqual(self.phase(0)["review"]["state"], P.CHANGES)
        self.assertEqual(P.find_step(P.load(self.path), "CDC-1")[2]["state"], P.DONE)  # no reabre sola
        _, out, _ = run(self.path, "status")
        self.assertIn("PIDE CAMBIOS", out)
        self.assertIn("Falta validar", out)
        self.assertIn("pidió cambios", run(self.path, "start", "CDC-2")[1])  # aviso
        run(self.path, "reopen", "CDC-1")
        self.assertEqual(self.phase(0)["review"]["state"], P.CHANGES)  # se queda lo que pidió
        run(self.path, "done", "CDC-1", "-m", "validado")
        self.assertEqual(self.phase(0)["review"]["state"], P.WAITING)
        run(self.path, "approve", "CDC")
        P.mutate(self.path, lambda plan: P.request_change(plan, "CDC-1", "Otra cosa"))
        self.assertNotIn("review", self.phase(0))
        run(self.path, "done", "CDC-1", "-m", "ok")
        run(self.path, "approve", "CDC")
        run(self.path, "reopen", "CDC-1")
        self.assertNotIn("review", self.phase(0))
        run(self.path, "done", "CDC-1", "-m", "ok")
        run(self.path, "add", "CDC", "Cimientos", "Uno más")  # paso nuevo: deja de esperar
        self.assertNotIn("review", self.phase(0))

    def test_approve_without_waiting_phase_explains(self):
        self.make()
        code, _, err = run(self.path, "approve", "CDC")
        self.assertEqual(code, 1)
        self.assertIn('approve CDC "Nombre de la fase"', err)
        self.assertEqual(run(self.path, "approve", "CDC", "Pagos")[0], 0)
        self.assertEqual(run(self.path, "approve", "CDC", "Inventada")[0], 1)

    def test_nonstop_branch_does_not_stop(self):
        self.make()
        self.assertEqual(run(self.path, "nonstop", "CDC", "on")[0], 0)
        out = run(self.path, "done", "CDC-1", "-m", "ok")[1]
        self.assertNotIn("FASE TERMINADA", out)
        self.assertIn("start CDC-2", out)
        self.assertNotIn("review", self.phase(0))
        self.assertTrue(P.load(self.path)["branches"][0]["nonstop"])
        self.assertEqual(run(self.path, "nonstop", "CDC", "off")[0], 0)
        self.assertNotIn("nonstop", P.load(self.path)["branches"][0])
        self.assertEqual(run(self.path, "nonstop", "CDC", "quizá")[0], 1)

    def test_review_phase_from_web_shows_in_inbox_and_wait(self):
        self.make()
        run(self.path, "done", "CDC-1", "-m", "ok")
        P.mutate(self.path, lambda plan: P.review_phase(plan, "CDC", None, "approved", seen=False))
        code, out, _ = run(self.path, "inbox")
        self.assertEqual(code, 0)
        self.assertIn("APROBADA", out)
        self.assertIn("start CDC-2", out)
        self.assertEqual(run(self.path, "inbox")[1], "")  # ya vista
        with self.assertRaises(P.PlanError):
            P.review_phase(P.load(self.path), "CDC", "Cimientos", "changes")  # sin texto

    # ── Preguntas y propuestas ──

    def test_ask_and_answer_in_chat(self):
        self.make()
        code, out, _ = run(self.path, "ask", "¿Qué color?", "--step", "cdc-1", "--option", "Azul | más limpio",
                             "--option", "Verde | más contraste", "--recommend", "1")
        self.assertEqual(code, 0)
        self.assertIn("P-1", out)
        self.assertIn("answer P-1 N", out)
        ask = P.load(self.path)["asks"][0]
        self.assertEqual((ask["kind"], ask["step"], ask["branch"], [o["label"] for o in ask["options"]], ask["answer"]),
                         (P.QUESTION, "CDC-1", "CDC", ["Azul", "Verde"], None))
        self.assertIn("PREGUNTAS SIN RESPONDER", run(self.path, "status")[1])
        self.assertIn("¿Qué color?", run(self.path, "show", "CDC-1")[1])
        self.assertEqual(run(self.path, "answer", "P-1", "3")[0], 1)
        self.assertEqual(run(self.path, "answer", "P-1")[0], 1)
        code, out, _ = run(self.path, "answer", "p-1", "2", "-m", "más clarito")
        self.assertEqual(code, 0)
        self.assertIn("Verde", out)
        answer = P.load(self.path)["asks"][0]["answer"]
        self.assertEqual((answer["option"], answer["text"], answer["seen"]), (2, "más clarito", True))
        run(self.path, "answer", "P-1", "1")  # se puede volver a contestar
        self.assertEqual(P.load(self.path)["asks"][0]["answer"]["option"], 1)
        self.assertNotIn("PREGUNTAS SIN RESPONDER", run(self.path, "status")[1])
        self.assertEqual(run(self.path, "inbox")[1], "")  # contestada en el chat: nada nuevo
        # libre y en una rama
        self.assertEqual(run(self.path, "ask", "¿Algo más?", "--branch", "Carrito de compra")[0], 0)
        self.assertEqual(run(self.path, "answer", "P-2", "1")[0], 1)  # no tiene opciones
        self.assertEqual(run(self.path, "answer", "P-2", "-m", "nada")[0], 0)
        self.assertEqual(run(self.path, "ask", "X", "--option", "Solo una | x", "--recommend", "1")[0], 1)
        self.assertEqual(run(self.path, "ask", "X", "--step", "ZZ-1")[0], 1)

    def html(self, name, size=100):
        f = Path(self.tmp.name) / name
        f.write_text("<p>" + "x" * size + "</p>", encoding="utf-8")
        return str(f)

    def test_propose_copies_html_and_validates(self):
        self.make()
        a, b = self.html("a.html"), self.html("b.htm")
        code, out, err = run(self.path, "propose", "Portada", "--branch", "CDC", "--option", "Clara | fondo blanco", a,
                             "--option", "Oscura | fondo negro", b, "--recommend", "2")
        self.assertEqual(code, 0, err)
        self.assertIn("enséñale", out)
        ask = P.load(self.path)["asks"][0]
        self.assertEqual(ask["kind"], P.PROPOSAL)
        self.assertEqual([o["file"] for o in ask["options"]],
                         [".unificador/propuestas/P-1/1.html", ".unificador/propuestas/P-1/2.html"])
        self.assertTrue((Path(self.tmp.name) / ask["options"][1]["file"]).is_file())
        self.assertIn(str(Path(self.tmp.name).resolve() / ".unificador"), out)
        txt = Path(self.tmp.name) / "c.txt"
        txt.write_text("x", encoding="utf-8")
        big = self.html("big.html", P.MAX_PROPOSAL + 1)
        for opts in ([["Una", a]], [["A", a], ["B", str(txt)]], [["A", a], ["B", "falta.html"]], [["A", a], ["B", big]]):
            argv = [x for o in opts for x in ("--option", *o)]
            code, _, err = run(self.path, "propose", "Mal", *argv)
            self.assertEqual(code, 1, opts)
            self.assertTrue(err.strip())
        self.assertEqual(len(P.load(self.path)["asks"]), 1)
        # la web contesta; inbox lo cuenta una vez
        P.mutate(self.path, lambda plan: P.answer_ask(plan, "P-1", 2, "con logo"))
        out = run(self.path, "inbox")[1]
        self.assertIn("Oscura", out)
        self.assertIn("con logo", out)
        self.assertEqual(run(self.path, "inbox")[1], "")
        # drop borra preguntas y ficheros
        run(self.path, "drop", "CDC")
        self.assertEqual(P.load(self.path)["asks"], [])
        self.assertFalse((Path(self.tmp.name) / ".unificador" / "propuestas" / "P-1").exists())

    def test_wait_gets_answer_from_another_thread(self):
        import threading
        self.make()
        run(self.path, "ask", "¿Seguimos?", "--option", "Sí | sigo", "--option", "No | paro", "--recommend", "1")
        old = P.POLL
        P.POLL = 0.05
        try:
            def web():
                time.sleep(0.3)
                P.mutate(self.path, lambda plan: P.answer_ask(plan, "P-1", 1))
            t = threading.Thread(target=web)
            t.start()
            start = time.time()
            code, out, _ = run(self.path, "wait", "P-1", "--seconds", "10")
            t.join()
        finally:
            P.POLL = old
        self.assertEqual(code, 0)
        self.assertLess(time.time() - start, 5)
        self.assertIn("«Sí»", out)
        self.assertTrue(P.load(self.path)["asks"][0]["answer"]["seen"])

    def test_wait_times_out_and_ask_wait(self):
        self.make()
        run(self.path, "ask", "¿Seguimos?")
        start = time.time()
        code, out, _ = run(self.path, "wait", "--seconds", "1")
        self.assertEqual(code, 0)
        self.assertIn("Sin respuesta todavía", out)
        self.assertLess(time.time() - start, 4)
        code, out, _ = run(self.path, "ask", "¿Otra?", "--wait", "1")
        self.assertEqual(code, 0)
        self.assertIn("Sin respuesta todavía", out)
        self.assertEqual(run(self.path, "wait", "P-9", "--seconds", "1")[0], 1)
        P.mutate(self.path, lambda plan: plan.update(asks=[]))
        self.assertIn("Nada pendiente", run(self.path, "wait", "--seconds", "5")[1])

    def test_inbox_is_silent_and_never_fails(self):
        self.assertEqual(run(self.path, "inbox"), (0, "", ""))  # sin plan
        self.make()
        self.assertEqual(run(self.path, "inbox"), (0, "", ""))
        self.path.write_text("{roto", encoding="utf-8")
        self.assertEqual(run(self.path, "inbox"), (0, "", ""))

    def test_inbox_lists_pending_change_requests_without_marking(self):
        self.make()
        P.mutate(self.path, lambda plan: P.request_change(plan, "CDC-2", "Más grande"))
        for _ in range(2):
            out = run(self.path, "inbox")[1]
            self.assertIn("CDC-2", out)
            self.assertIn("Más grande", out)

    def test_old_plan_without_new_fields_loads(self):
        old = {"version": 1, "title": "Viejo", "branches": [{
            "key": "V", "name": "Vieja", "goal": "", "icon": "", "color": 0, "next_id": 3,
            "phases": [{"name": "Base", "icon": "", "steps": [
                {"id": "V-1", "title": "a", "desc": "", "state": "done", "notes": []},
                {"id": "V-2", "title": "b", "desc": "", "state": "pending", "notes": []}]}]}]}
        self.path.write_text(json.dumps(old), encoding="utf-8")
        self.assertEqual(run(self.path, "status")[0], 0)
        self.assertEqual(run(self.path, "inbox"), (0, "", ""))
        self.assertIn("FASE TERMINADA", run(self.path, "done", "V-2", "-m", "ok")[1])
        self.assertEqual(run(self.path, "ask", "¿Y ahora?")[0], 0)
        plan = P.load(self.path)
        self.assertEqual((plan["version"], plan["asks"][0]["id"]), (1, "P-1"))


class DecisionCardTest(unittest.TestCase):
    """Ficha estándar de decisiones, HTML listo para incrustar y revisión de cumplimiento."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.path = self.dir / P.PLAN_FILE
        self.assertEqual(run(self.path, "plan", stdin=json.dumps(SAMPLE))[0], 0)

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, *argv):
        return run(self.path, "ask", "¿Cuál?", *argv)

    def write(self, name, text):
        f = self.dir / name
        f.write_text(text, encoding="utf-8")
        return str(f)

    def propose(self, *files, extra=()):
        argv = []
        for i, f in enumerate(files, 1):
            argv += ["--option", f"Op{i} | cambia {i}", f]
        return run(self.path, "propose", "Mira", "--recommend", "1", *extra, *argv)

    # ── ficha ──

    def test_valid_card_is_saved_with_desc_and_recommend(self):
        code, out, err = self.ask("--option", "Azul | más limpio", "--option", "Verde | más contraste",
                                  "--recommend", "2", "-d", "Contexto **breve**")
        self.assertEqual(code, 0, err)
        ask = P.load(self.path)["asks"][0]
        self.assertEqual([(o["label"], o["desc"]) for o in ask["options"]],
                         [("Azul", "más limpio"), ("Verde", "más contraste")])
        self.assertEqual((ask["recommend"], ask["text"]), (2, "Contexto **breve**"))
        self.assertIn("más contraste", out)
        self.assertIn("[recomendada]", out)
        status = run(self.path, "status")[1]
        self.assertIn("más limpio", status)
        self.assertIn("2) Verde  [recomendada]", status)

    def test_recommend_zero_means_no_preference(self):
        code, out, _ = self.ask("--option", "A | uno", "--option", "B | dos", "--recommend", "0")
        self.assertEqual(code, 0)
        self.assertEqual(P.load(self.path)["asks"][0]["recommend"], 0)
        self.assertNotIn("[recomendada]", out)

    def test_card_rejections_say_what_is_missing(self):
        cases = [
            (("--option", "A", "--option", "B | dos", "--recommend", "1"), "opción 1"),
            (("--option", "A | uno", "--option", "B | dos"), "--recommend"),
            (("--option", "A | uno", "--option", "B | dos", "--recommend", "3"), "1 a 2"),
            (("--option", "A | uno", "--option", "B | dos", "--recommend", "-1"), "1 a 2"),
            (("--option", "A | " + "x" * 161, "--option", "B | dos", "--recommend", "1"), "160"),
            (("--option", "A | uno", "--recommend", "1"), "al menos dos"),
            (("--option", "A | uno", "--option", "B | dos", "--recommend", "1", "-d", "y" * 801), "800"),
        ]
        for argv, needle in cases:
            code, _, err = self.ask(*argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(needle, err)
            self.assertIn("--option", err)  # trae un ejemplo
        self.assertEqual(P.load(self.path)["asks"], [])

    def test_free_answer_needs_no_recommend(self):
        self.assertEqual(self.ask()[0], 0)
        self.assertIsNone(P.load(self.path)["asks"][0]["recommend"])

    def test_old_ask_without_desc_loads_and_shows(self):
        P.mutate(self.path, lambda plan: plan.setdefault("asks", []).append(
            {"id": "P-1", "kind": "question", "title": "Vieja", "text": "", "step": None, "branch": None,
             "options": [{"label": "Sí"}, {"label": "No"}], "answer": None, "by": "ia", "created": "x"}))
        code, out, _ = run(self.path, "status")
        self.assertEqual(code, 0)
        self.assertIn("1) Sí", out)
        self.assertEqual(run(self.path, "answer", "P-1", "1")[0], 0)

    def test_propose_requires_card(self):
        a, b = self.write("a.html", "<p>a</p>"), self.write("b.html", "<p>b</p>")
        code, _, err = run(self.path, "propose", "X", "--option", "A", a, "--option", "B | dos", b)
        self.assertEqual((code, "falta qué implica" in err, "--recommend" in err), (1, True, True))
        code, out, _ = self.propose(a, b)
        self.assertEqual(code, 0)
        ask = P.load(self.path)["asks"][0]
        self.assertEqual((ask["recommend"], ask["options"][0]["desc"]), (1, "cambia 1"))

    # ── HTML ──

    def copy_of(self, n=1):
        return (self.dir / ".unificador/propuestas/P-1" / f"{n}.html").read_text(encoding="utf-8")

    def test_fragment_is_wrapped_and_original_untouched(self):
        a, b = self.write("a.html", "<h1>Hola</h1>"), self.write("b.html", "<p>b</p>")
        self.assertEqual(self.propose(a, b)[0], 0)
        out = self.copy_of()
        for needle in ("<!doctype html>", 'charset="utf-8"', 'name="viewport"', "width=device-width,initial-scale=1",
                       "system-ui", "margin:0", "padding:16px", "box-sizing:border-box", "<h1>Hola</h1>"):
            self.assertIn(needle, out)
        self.assertEqual(Path(a).read_text(encoding="utf-8"), "<h1>Hola</h1>")

    def test_document_without_viewport_gets_it(self):
        doc = "<!doctype html><html><head><title>t</title></head><body>x</body></html>"
        a, b = self.write("a.html", doc), self.write("b.html", "<html><body>sin head</body></html>")
        self.assertEqual(self.propose(a, b)[0], 0)
        self.assertIn('name="viewport"', self.copy_of(1))
        self.assertEqual(self.copy_of(1).count("<html"), 1)
        self.assertIn('name="viewport"', self.copy_of(2))
        self.assertEqual(self.copy_of(2).count("<html"), 1)
        self.assertEqual(Path(a).read_text(encoding="utf-8"), doc)

    def test_document_with_viewport_is_copied_as_is(self):
        doc = '<html><head><meta name="viewport" content="width=500"></head><body>x</body></html>'
        a, b = self.write("a.html", doc), self.write("b.html", "<p>b</p>")
        self.assertEqual(self.propose(a, b)[0], 0)
        self.assertEqual(self.copy_of(1), doc)

    def test_external_resources_are_rejected_with_file_and_line(self):
        cases = {
            "script": '<p>a</p>\n<script src="https://cdn.x/a.js"></script>',
            "img": '<p>a</p>\n<p>b</p>\n<img src="//cdn.x/a.png">',
            "link": '<html><head>\n<link rel="stylesheet" href="http://x/a.css"></head><body></body></html>',
            "style": '<style>\n.a{background:url("https://x/a.png")}</style><p>a</p>',
            "import": '<style>\n@import "https://x/a.css";</style><p>a</p>',
            "importurl": '<style>\n@import url(//x/a.css);</style><p>a</p>',
            "inline": '<p>a</p>\n<div style="background:url(http://x/a.png)">b</div>',
        }
        ok = self.write("ok.html", "<p>ok</p>")
        for name, html in cases.items():
            f = self.write(f"{name}.html", html)
            code, _, err = self.propose(ok, f)
            self.assertEqual(code, 1, name)
            self.assertIn(f"{name}.html, línea 2" if name not in ("img",) else f"{name}.html, línea 3", err, name)
        self.assertEqual(P.load(self.path)["asks"], [])

    def test_external_link_anchor_and_data_urls_are_fine(self):
        html = ('<a href="https://example.com">fuera</a><img src="data:image/png;base64,AAAA">'
                '<div style="background:url(data:image/svg+xml;base64,AAAA)">x</div>')
        a, b = self.write("a.html", html), self.write("b.html", "<p>b</p>")
        self.assertEqual(self.propose(a, b)[0], 0)

    # ── check ──

    def audit_of(self, plan):
        return [(i["level"], i["ref"]) for i in P.audit(plan)]

    def test_audit_rules(self):
        plan = P.load(self.path)
        got = P.audit(plan)
        self.assertTrue(all(set(i) == {"level", "ref", "text"} for i in got))
        self.assertIn(("aviso", "CDC-1"), self.audit_of(plan))  # sin cat
        for _, _, s in P.iter_steps(plan):
            s["cat"] = "codigo"
        self.assertEqual(self.audit_of(plan), [])
        # hecho sin cómo se comprobó
        step = plan["branches"][0]["phases"][0]["steps"][0]
        step["state"], step["result"] = "done", "listo"
        self.assertEqual(self.audit_of(plan), [("aviso", "CDC-1")])
        step["result"] = "Guardado el carrito; lo he comprobado con la prueba de guardar"
        self.assertEqual(self.audit_of(plan), [])
        step["result"] = "Hecho el carrito de la compra y guardado en el fichero"  # largo pero no dice cómo
        self.assertEqual(self.audit_of(plan), [("aviso", "CDC-1")])
        step["result"] = "ok, test pasa"  # corto
        self.assertEqual(self.audit_of(plan), [("aviso", "CDC-1")])
        step["state"] = "pending"
        # fase genérica
        plan["branches"][0]["phases"][1]["name"] = "Fase 2"
        self.assertEqual(self.audit_of(plan), [("aviso", "CDC/Fase 2")])
        plan["branches"][0]["phases"][1]["name"] = "Pagos"
        # dependencia a fase inexistente
        plan["branches"][0]["phases"][1]["after"] = [{"branch": "CDC", "phase": "Cimientos"}]
        self.assertEqual(self.audit_of(plan), [])
        plan["branches"][0]["phases"][1]["after"] = [{"branch": "CDC", "phase": "Nada"}]
        self.assertEqual(self.audit_of(plan), [("error", "CDC/Pagos")])
        plan["branches"][0]["phases"][1]["after"] = [{"branch": "XX", "phase": "Cimientos"}]
        self.assertEqual(self.audit_of(plan), [("error", "CDC/Pagos")])
        del plan["branches"][0]["phases"][1]["after"]
        # pregunta abierta con opciones sin desc / sin recommend
        plan["asks"] = [{"id": "P-1", "kind": "question", "title": "Q", "options": [{"label": "A"}, {"label": "B"}],
                         "answer": None}]
        self.assertEqual(self.audit_of(plan), [("error", "P-1")])
        plan["asks"][0]["options"] = [{"label": "A", "desc": "a"}, {"label": "B", "desc": "b"}]
        self.assertEqual(self.audit_of(plan), [("error", "P-1")])  # sin recommend
        plan["asks"][0]["recommend"] = 0
        self.assertEqual(self.audit_of(plan), [])
        plan["asks"][0].update(recommend=None, answer={"option": 1})  # contestada: ya no cuenta
        self.assertEqual(self.audit_of(plan), [])
        # sin opciones (respuesta libre): bien
        plan["asks"] = [{"id": "P-2", "kind": "question", "title": "Q", "options": [], "answer": None}]
        self.assertEqual(self.audit_of(plan), [])

    def test_audit_missing_proposal_file(self):
        a, b = self.write("a.html", "<p>a</p>"), self.write("b.html", "<p>b</p>")
        self.assertEqual(self.propose(a, b)[0], 0)
        plan = P.load(self.path)
        for _, _, s in P.iter_steps(plan):
            s["cat"] = "codigo"
        self.assertEqual(P.audit(plan, self.dir), [])
        (self.dir / ".unificador/propuestas/P-1/2.html").unlink()
        self.assertEqual([(i["level"], i["ref"]) for i in P.audit(plan, self.dir)], [("error", "P-1")])

    def test_check_command_exit_codes_and_status_footer(self):
        code, out, _ = run(self.path, "check")
        self.assertEqual(code, 0)  # solo avisos (pasos sin categoría)
        self.assertIn("AVISOS", out)
        self.assertRegex(run(self.path, "status")[1], r"Avisos: \d+  \(python \.unificador/uni\.py check\)")
        P.mutate(self.path, lambda plan: plan.setdefault("asks", []).append(
            {"id": "P-1", "kind": "question", "title": "Q", "options": [{"label": "A"}, {"label": "B"}],
             "answer": None}))
        code, out, _ = run(self.path, "check")
        self.assertEqual(code, 1)
        self.assertIn("ERRORES", out)
        self.assertLess(out.index("ERRORES"), out.index("AVISOS"))

        def clean(plan):
            plan["asks"] = []
            for _, _, s in P.iter_steps(plan):
                s["cat"] = "codigo"
        P.mutate(self.path, clean)
        self.assertEqual(run(self.path, "check"), (0, "Todo en orden.\n", ""))
        self.assertNotIn("Avisos:", run(self.path, "status")[1])


if __name__ == "__main__":
    unittest.main()
