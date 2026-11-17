"""Las pruebas nunca tocan la lista de proyectos de la persona (``~/.unificador``).

Cada prueba recibe su propia carpeta en ``UNIFICADOR_HOME``; los ``uni.py`` lanzados como subproceso la heredan, y ninguna
mira en GitHub si hay versión nueva.
Las pruebas que ponen su propio ``UNIFICADOR_HOME`` siguen mandando sobre esta.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("UNIFICADOR_HOME", str(tmp_path_factory.mktemp("uni-home")))
    monkeypatch.setenv("UNIFICADOR_NO_UPDATE_CHECK", "1")  # nunca salir a GitHub
