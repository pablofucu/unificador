import json
import threading
import urllib.error
import urllib.request

import pytest

from unificador.config import config
from unificador.models import Project
from unificador.server import ThreadedHTTPServer, UnificadorAPIHandler

BOARD = {
    "groups": [{"id": "DA", "name": "Datos"}, {"id": "DI", "name": "Diseño"}, {"id": "VA", "name": "Vacía"}],
    "tasks": [
        {"id": "DA-01", "title": "Modelo", "state": "done", "group": "DA"},
        {"id": "DA-02", "title": "Guardar", "state": "review", "group": "DA", "deps": ["DA-01"],
         "notes": [{"text": "Primera"}, {"text": "Listo para revisar"}]},
        {"id": "DA-03", "title": "Copia", "state": "todo", "group": "DA", "deps": ["DA-02"]},
        {"id": "DA-04", "title": "Importar", "state": "doing", "group": "DA", "deps": ["DA-01"]},
        {"id": "DI-01", "title": "Paleta", "state": "proposed", "group": "DI"},
    ],
}


@pytest.fixture
def api(tmp_path, monkeypatch):
    (tmp_path / "kanvas.json").write_text(json.dumps(BOARD), encoding="utf-8")
    proj = Project(id="t", name="T", path=str(tmp_path))
    monkeypatch.setattr(config, "get_project", lambda pid: proj if pid == "t" else None)
    srv = ThreadedHTTPServer(("127.0.0.1", 0), UnificadorAPIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def get(url):
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_itinerary_structure(api):
    st, data = get(f"{api}/api/projects/t/itinerary")
    assert st == 200
    assert [r["name"] for r in data["ramas"]] == ["Datos", "Diseño"]  # sin ramas vacías
    datos = data["ramas"][0]
    assert [f["name"] for f in datos["fases"]] == ["Fase 1", "Fase 2", "Fase 3"]
    assert [[s["id"] for s in f["steps"]] for f in datos["fases"]] == [["DA-01"], ["DA-02", "DA-04"], ["DA-03"]]
    assert [f["state"] for f in datos["fases"]] == ["hecho", "toca", "pend"]


def test_itinerary_states_and_counts(api):
    _, data = get(f"{api}/api/projects/t/itinerary")
    steps = {s["id"]: s for r in data["ramas"] for f in r["fases"] for s in f["steps"]}
    assert {k: v["state"] for k, v in steps.items()} == {
        "DA-01": "hecho", "DA-02": "toca", "DA-03": "pend", "DA-04": "run", "DI-01": "pend"}
    assert steps["DA-03"]["blocked"] and not steps["DI-01"]["blocked"]
    assert steps["DA-02"]["last_note"] == "Listo para revisar"
    assert data["counts"] == {"total": 5, "hecho": 1, "run": 1, "toca": 1}
    assert data["join"]["state"] == "pend"


def test_itinerary_unknown_project(api):
    assert get(f"{api}/api/projects/zz/itinerary")[0] == 404


def test_frontend_is_served(api):
    with urllib.request.urlopen(f"{api}/") as r:
        assert r.status == 200 and b"<title>Unificador" in r.read()
    assert get(f"{api}/../unificador/server.py")[0] == 404


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


@pytest.fixture
def created(tmp_path, monkeypatch):
    store = {}
    monkeypatch.setattr(config, "get_project", lambda pid: store.get(pid))
    monkeypatch.setattr(config, "add_project", lambda p: store.__setitem__(p.id, p))
    srv = ThreadedHTTPServer(("127.0.0.1", 0), UnificadorAPIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path, store
    srv.shutdown()
    srv.server_close()


def test_create_project_creates_folder_and_slug(created):
    base, tmp, store = created
    st, data = post(f"{base}/api/projects", {"name": "  Mi Álbum de fotos ", "path": str(tmp / "album")})
    assert st == 201 and data["project"]["id"] == "mi_album_de_fotos"
    assert data["project"]["name"] == "Mi Álbum de fotos"
    assert (tmp / "album").is_dir() and "mi_album_de_fotos" in store


def test_create_project_validation(created):
    base, tmp, _ = created
    assert post(f"{base}/api/projects", {"name": "   "})[0] == 400
    assert post(f"{base}/api/projects", {"name": "A", "path": str(tmp / "a")})[0] == 201
    assert post(f"{base}/api/projects", {"name": "A", "path": str(tmp / "b")})[0] == 409
    (tmp / "f").write_text("x")
    assert post(f"{base}/api/projects", {"name": "C", "path": str(tmp / "f")})[0] == 400


class StubAdapter:
    def stream_execute(self, context):
        yield "Hola "
        yield "mundo"


class BoomAdapter:
    def stream_execute(self, context):
        yield "a medias"
        raise RuntimeError("fallo simulado")


def stream(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return r.status, r.read().decode()


def test_chat_stream_sse(api, monkeypatch):
    monkeypatch.setattr("unificador.server.get_adapter", lambda a: StubAdapter())
    st, raw = stream(f"{api}/api/chat/stream", {"project_id": "t", "prompt": "hola", "agent": "codex"})
    assert st == 200
    assert 'data: {"chunk": "Hola "}' in raw and 'data: {"chunk": "mundo"}' in raw
    assert raw.rstrip().endswith("event: done\ndata: {}")


def test_chat_stream_error_event(api, monkeypatch):
    monkeypatch.setattr("unificador.server.get_adapter", lambda a: BoomAdapter())
    _, raw = stream(f"{api}/api/chat/stream", {"project_id": "t", "prompt": "hola", "agent": "codex"})
    assert "event: error" in raw and "fallo simulado" in raw


def test_chat_stream_bad_requests(api):
    assert post(f"{api}/api/chat/stream", {"project_id": "zz", "prompt": "x"})[0] == 404
    assert post(f"{api}/api/chat/stream", {"project_id": "t", "prompt": "x", "agent": "nope"})[0] == 400


@pytest.fixture
def review_api(tmp_path, monkeypatch):
    """Proyecto con copia del script de Kanvas, para probar aceptar/devolver."""
    import shutil
    from pathlib import Path
    script_dir = tmp_path / ".agents" / "skills" / "kanvas"
    script_dir.mkdir(parents=True)
    shutil.copy(Path(__file__).resolve().parent.parent / ".agents/skills/kanvas/kanvas.py", script_dir / "kanvas.py")
    board = {"kanvas": 1, "title": "T", "groups": [{"id": "DA", "name": "Datos"}], "tasks": [
        {"id": "DA-01", "title": "Modelo", "state": "review", "group": "DA", "at": "2026-01-01T00:00:00Z", "by": "agent"},
        {"id": "DA-02", "title": "Otro", "state": "review", "group": "DA", "at": "2026-01-01T00:00:00Z", "by": "agent"},
        {"id": "DA-03", "title": "Nuevo", "state": "todo", "group": "DA", "at": "2026-01-01T00:00:00Z", "by": "agent"}]}
    (tmp_path / "kanvas.json").write_text(json.dumps(board), encoding="utf-8")
    proj = Project(id="t", name="T", path=str(tmp_path))
    monkeypatch.setattr(config, "get_project", lambda pid: proj if pid == "t" else None)
    srv = ThreadedHTTPServer(("127.0.0.1", 0), UnificadorAPIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    srv.shutdown()
    srv.server_close()


def board_state(tmp, tid):
    t = next(t for t in json.loads((tmp / "kanvas.json").read_text(encoding="utf-8"))["tasks"] if t["id"] == tid)
    return t


def test_accept_marks_done_with_note(review_api):
    base, tmp = review_api
    st, data = post(f"{base}/api/projects/t/tasks/DA-01/accept", {})
    assert st == 200 and data["board_state"] == "done"
    t = board_state(tmp, "DA-01")
    assert t["state"] == "done" and t["notes"][-1]["by"] == "usuario"
    assert get(f"{base}/api/projects/t/itinerary")[1]["counts"]["hecho"] == 1


def test_send_back_needs_comment_and_reopens(review_api):
    base, tmp = review_api
    assert post(f"{base}/api/projects/t/tasks/DA-02/send-back", {"comment": "  "})[0] == 400
    assert board_state(tmp, "DA-02")["state"] == "review"
    st, data = post(f"{base}/api/projects/t/tasks/DA-02/send-back", {"comment": "Falta el botón"})
    assert st == 200 and data["board_state"] == "doing"
    assert board_state(tmp, "DA-02")["notes"][-1]["text"] == "Falta el botón"


def test_review_errors(review_api):
    base, _ = review_api
    assert post(f"{base}/api/projects/t/tasks/DA-03/accept", {})[0] == 409  # no está en revisión
    assert post(f"{base}/api/projects/t/tasks/XX-99/accept", {})[0] == 404
    assert post(f"{base}/api/projects/zz/tasks/DA-01/accept", {})[0] == 404


@pytest.fixture
def git_api(tmp_path, monkeypatch):
    import subprocess
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@t.t")
    run("config", "user.name", "T")
    (tmp_path / "a.txt").write_text("1")
    run("add", ".")
    run("commit", "-qm", "base")
    proj = Project(id="g", name="G", path=str(tmp_path))
    monkeypatch.setattr(config, "get_project", lambda pid: proj if pid == "g" else None)
    srv = ThreadedHTTPServer(("127.0.0.1", 0), UnificadorAPIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path, run
    srv.shutdown()
    srv.server_close()


def test_git_status_keeps_full_filenames(git_api):
    base, tmp, _ = git_api
    (tmp / "a.txt").write_text("2")       # modificado: el estado empieza por espacio
    (tmp / "nuevo.txt").write_text("x")   # sin seguimiento
    st, data = get(f"{base}/api/git/status?project_id=g")
    assert st == 200 and data["is_repo"] and not data["clean"]
    assert {f["file"]: f["status"] for f in data["files"]} == {"a.txt": "M", "nuevo.txt": "??"}
    assert data["has_remote"] is False and data["ahead"] == 0


def test_git_commit_message_has_phase_and_id(git_api):
    import subprocess
    base, tmp, _ = git_api
    (tmp / "b.txt").write_text("x")
    st, data = post(f"{base}/api/git/commit", {"project_id": "g", "task_id": "DA-01", "title": "Guardar", "phase": "Datos"})
    assert st == 200 and data["success"]
    msg = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=tmp, capture_output=True, text=True).stdout.strip()
    assert msg == "[Datos] DA-01: Guardar"
    assert get(f"{base}/api/git/status?project_id=g")[1]["clean"]


def test_git_errors(git_api, tmp_path):
    base, _, _ = git_api
    assert get(f"{base}/api/git/status?project_id=zz")[0] == 404
    assert post(f"{base}/api/git/push", {"project_id": "g"})[0] == 500  # sin remoto


def test_status_lists_adapters(api):
    st, data = get(f"{api}/api/status")
    assert st == 200 and data["status"] == "online"
    assert {"claude_code", "codex"} <= set(data["adapters"])
    assert all("installed" in a for a in data["adapters"].values())


def test_invalid_json_and_unknown_routes(api):
    req = urllib.request.Request(f"{api}/api/projects", data=b"{no json", headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 400
    assert get(f"{api}/api/nada")[0] == 404
    assert post(f"{api}/api/nada", {})[0] == 404


def test_projects_list_counts_run_and_toca(api, monkeypatch):
    proj = config.get_project("t")
    monkeypatch.setattr(config, "get_projects", lambda: [proj])
    _, data = get(f"{api}/api/projects")
    p = data["projects"][0]
    assert (p["total_tasks"], p["run"], p["toca"]) == (5, 1, 1)
