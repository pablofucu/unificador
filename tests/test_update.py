"""Actualizaciones: comprobar versión, el ajuste «actualizar solo» y la puesta al día de los proyectos."""

import os
from pathlib import Path
from unittest import mock

import pytest

from unificador import __version__
from unificador import projects as R
from unificador import rules
from unificador import update as U


def test_status_pip_compares_tags_with_installed_version():
    with mock.patch.object(U, "kind", return_value="pip"):
        U._save_state({"kind": "pip", "latest": "99.0.0"})
        assert U.status()["available"] is True
        U._save_state({"latest": __version__})
        assert U.status()["available"] is False
        U._save_state({"latest": "no-es-version"})
        assert U.status()["available"] is False


def test_check_once_a_day_and_records_errors(monkeypatch):
    monkeypatch.delenv("UNIFICADOR_NO_UPDATE_CHECK")
    calls = []
    def fake_tag():
        calls.append(1)
        return "99.1.0"
    with mock.patch.object(U, "kind", return_value="pip"), mock.patch.object(U, "latest_tag", fake_tag):
        st = U.check()
        assert (st["latest"], st["available"], st["error"]) == ("99.1.0", True, "")
        U.check()  # ya se miró hoy: no vuelve a salir
        assert len(calls) == 1
        U.check(force=True)
        assert len(calls) == 2
    with mock.patch.object(U, "kind", return_value="pip"), \
            mock.patch.object(U, "latest_tag", side_effect=OSError("sin red")):
        assert U.check(force=True)["error"] == "sin red"


def test_check_git_counts_commits_behind(monkeypatch):
    monkeypatch.delenv("UNIFICADOR_NO_UPDATE_CHECK")
    answers = {"fetch": "", "rev-list": "3"}
    with mock.patch.object(U, "kind", return_value="git"), \
            mock.patch.object(U, "_git", lambda *a, **k: answers.get(a[0])):
        st = U.check(force=True)
    assert (st["kind"], st["behind"], st["available"]) == ("git", 3, True)


def test_no_network_when_disabled():
    with mock.patch.object(U, "latest_tag", side_effect=AssertionError("no debía salir")):
        U.check(force=True)


def test_auto_setting_persists():
    assert U.status()["auto"] is False
    assert U.set_auto(True)["auto"] is True
    assert U.load_state()["auto"] is True
    assert U.set_auto(False)["auto"] is False


def test_apply_git_refuses_when_pull_fails():
    with mock.patch.object(U, "kind", return_value="git"), \
            mock.patch.object(U, "_git", lambda *a, **k: None if a[0] == "pull" else "abc1234"):
        with pytest.raises(U.UpdateError):
            U.apply()


def test_apply_git_reports_new_commit():
    heads = iter(["aaa1111", "bbb2222"])
    def fake(*a, **k):
        return next(heads) if a[0] == "rev-parse" else ""
    with mock.patch.object(U, "kind", return_value="git"), mock.patch.object(U, "_git", fake):
        assert U.apply() == "Actualizado de aaa1111 a bbb2222."
    assert U.load_state()["applied"] == "Actualizado de aaa1111 a bbb2222."


def test_refresh_all_updates_only_projects_using_unificador(tmp_path):
    used, other = tmp_path / "usado", tmp_path / "otro"
    used.mkdir(); other.mkdir()
    rules.install(used)
    (used / ".unificador" / "uni.py").write_text("# copia vieja\n", encoding="utf-8")
    R.register(other)
    changed = U.refresh_all()
    assert list(changed) == [str(used)]
    assert "copia vieja" not in (used / ".unificador" / "uni.py").read_text(encoding="utf-8")
    assert not (other / ".unificador").exists()
    assert U.refresh_all() == {}  # repetirlo no cambia nada
