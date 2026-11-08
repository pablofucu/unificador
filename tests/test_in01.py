import json
import subprocess
import threading
import urllib.request
import urllib.error

import pytest

from unificador.config import config
from unificador.git_service import GitService
from unificador.models import Project
from unificador.server import ThreadedHTTPServer, UnificadorAPIHandler


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def api(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "kanvas.json").write_text(json.dumps({"groups": [], "tasks": []}), encoding="utf-8")
    proj = Project(id="t", name="T", path=str(tmp_path))
    monkeypatch.setattr(config, "get_project", lambda pid: proj if pid == "t" else None)
    from unificador import server
    from unificador.chats import ChatStore
    monkeypatch.setattr(server, "chat_store", ChatStore(tmp_path / "_chats", tmp_path / "_claude"))
    srv = ThreadedHTTPServer(("127.0.0.1", 0), UnificadorAPIHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path
    srv.shutdown()
    srv.server_close()


def call(url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_git_status_commit_and_push_error(api):
    base, path = api
    (path / "a.txt").write_text("x")
    st, body = call(f"{base}/api/git/status?project_id=t")
    assert st == 200 and not json.loads(body)["clean"]
    st, body = call(f"{base}/api/git/commit", {"project_id": "t", "task_id": "IN-01", "title": "Prueba"})
    assert st == 200 and json.loads(body)["success"]
    assert GitService(path).get_status()["clean"]
    st, body = call(f"{base}/api/git/push", {"project_id": "t"})  # sin remoto
    assert st == 500 and not json.loads(body)["success"]


def test_chat_errors_and_prepare(api):
    base, _ = api
    assert call(f"{base}/api/chat/prepare", {"project_id": "zz"})[0] == 404
    assert call(f"{base}/api/chat/prepare", {"project_id": "t", "agent": "nope"})[0] == 400
    st, body = call(f"{base}/api/chat/prepare", {"project_id": "t", "prompt": "hola"})
    assert st == 200 and "hola" in json.loads(body)["injected_prompt"]


def test_chat_stream_sse(api, monkeypatch):
    from unificador import server

    class Fake:
        def stream_execute(self, ctx):
            yield "uno"
            yield "dos"

    monkeypatch.setattr(server, "get_adapter", lambda t: Fake())
    base, _ = api
    st, body = call(f"{base}/api/chat/stream", {"project_id": "t", "prompt": "x"})
    assert st == 200
    assert '"chunk": "uno"' in body and '"chunk": "dos"' in body and "event: done" in body
