"""Held-out API probes (DAEDALUS R23). Matched by pytest -k heldout."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_TODO_SMOKE", "1")
os.environ.setdefault("API_KEY", "test-api-key")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("API_KEY", "test-api-key")
    for name in ("app", "auth", "config", "database", "models"):
        sys.modules.pop(name, None)
    import config
    import database as database_module

    db_path = tmp_path / "todos.db"
    monkeypatch.setattr(config, "SQLITE_PATH", db_path)
    monkeypatch.setattr(database_module, "SQLITE_PATH", db_path)
    database_module.init_db()
    import app as app_module

    return TestClient(app_module.app)


def test_heldout_list_todos_requires_auth(client: TestClient) -> None:
    response = client.get("/todos")
    assert response.status_code == 401
