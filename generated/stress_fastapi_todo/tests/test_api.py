"""Pytest API smoke tests for the FastAPI todo REST API."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

_TEST_API_KEY = "test-api-key"
_MODULE_NAMES = ("app", "auth", "config", "database", "models")

os.environ.setdefault("HERMES_TODO_SMOKE", "1")
os.environ.setdefault("API_KEY", _TEST_API_KEY)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Fresh sqlite DB and TestClient with lifespan startup."""
    monkeypatch.setenv("API_KEY", _TEST_API_KEY)
    monkeypatch.setenv("HERMES_TODO_SMOKE", "1")

    for name in _MODULE_NAMES:
        sys.modules.pop(name, None)

    import config

    db_path = tmp_path / "todos.db"
    monkeypatch.setattr(config, "SQLITE_PATH", db_path)

    import app as app_module
    import database as database_module

    monkeypatch.setattr(database_module, "SQLITE_PATH", db_path)
    database_module.init_db()

    with TestClient(app_module.app) as test_client:
        yield test_client


def _auth_headers() -> dict[str, str]:
    return {"X-API-Key": _TEST_API_KEY}


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-API-Key": "wrong-key"}],
    ids=["missing_key", "invalid_key"],
)
def test_auth_reject(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/todos", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_create_todo(client: TestClient) -> None:
    response = client.post(
        "/todos",
        headers=_auth_headers(),
        json={"title": "Buy milk"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["title"] == "Buy milk"


def test_list_todos(client: TestClient) -> None:
    create = client.post(
        "/todos",
        headers=_auth_headers(),
        json={"title": "Walk dog"},
    )
    assert create.status_code == 201

    response = client.get("/todos", headers=_auth_headers())
    assert response.status_code == 200
    todos = response.json()
    assert len(todos) == 1
    assert todos[0]["id"] == 1
    assert todos[0]["title"] == "Walk dog"


def test_delete_todo(client: TestClient) -> None:
    created = client.post(
        "/todos",
        headers=_auth_headers(),
        json={"title": "Remove me"},
    )
    assert created.status_code == 201
    todo_id = created.json()["id"]

    response = client.delete(f"/todos/{todo_id}", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": todo_id}

    listing = client.get("/todos", headers=_auth_headers())
    assert listing.status_code == 200
    assert listing.json() == []
