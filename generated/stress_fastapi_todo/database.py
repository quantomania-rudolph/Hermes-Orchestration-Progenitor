"""SQLite persistence for todos (no ORM)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Generator

try:
    from config import MAX_ITEMS, SQLITE_PATH
except ImportError:  # pragma: no cover - package import when run as module
    from .config import MAX_ITEMS, SQLITE_PATH

__all__ = [
    "get_connection",
    "init_db",
    "list_todos",
    "add_todo",
    "delete_todo",
]


def _ensure_db_parent() -> None:
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Open a sqlite3 connection with row dict access; commit on success."""
    _ensure_db_parent()
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the todos table if it does not exist."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL
            )
            """
        )


def list_todos() -> list[dict[str, Any]]:
    """Return all todos ordered by id."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title FROM todos ORDER BY id ASC"
        ).fetchall()
    return [{"id": int(row["id"]), "title": row["title"]} for row in rows]


def add_todo(title: str) -> dict[str, Any]:
    """Insert a todo and return the persisted record."""
    normalized = title.strip()
    if not normalized:
        raise ValueError("title must not be empty")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO todos (title)
            SELECT ? WHERE (SELECT COUNT(*) FROM todos) < ?
            """,
            (normalized, MAX_ITEMS),
        )
        if cur.rowcount == 0:
            raise ValueError(f"todo limit reached ({MAX_ITEMS})")
        row = conn.execute(
            "SELECT id, title FROM todos WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("insert succeeded but row not found")
    return {"id": int(row["id"]), "title": row["title"]}


def delete_todo(todo_id: int) -> bool:
    """Delete a todo by id; return True when a row was removed."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    return cur.rowcount > 0
