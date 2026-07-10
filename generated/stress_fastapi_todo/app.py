"""FastAPI todo REST API with token auth and SQLite persistence."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel

try:
    from auth import require_auth
    from database import add_todo, delete_todo, init_db, list_todos
    from models import Todo, TodoCreate
except ImportError:  # pragma: no cover - package import when run as module
    from .auth import require_auth
    from .database import add_todo, delete_todo, init_db, list_todos
    from .models import Todo, TodoCreate

__all__ = ["app"]


class TodoDeleteResponse(BaseModel):
    deleted: bool
    id: int


@asynccontextmanager
async def _lifespan(_: FastAPI):
    await asyncio.to_thread(init_db)
    yield


app = FastAPI(
    title="Todo API",
    description="Research/demo FastAPI todo REST API with API-key auth.",
    version="1.0.0",
    lifespan=_lifespan,
)


@app.get("/todos", response_model=list[Todo], tags=["todos"])
async def get_todos(
    _: Annotated[str, Depends(require_auth)],
) -> list[Todo]:
    """List all todos."""
    rows = await asyncio.to_thread(list_todos)
    return [Todo.model_validate(row) for row in rows]


@app.post(
    "/todos",
    response_model=Todo,
    status_code=status.HTTP_201_CREATED,
    tags=["todos"],
)
async def create_todo(
    payload: TodoCreate,
    _: Annotated[str, Depends(require_auth)],
) -> Todo:
    """Create a new todo."""
    try:
        record = await asyncio.to_thread(add_todo, payload.title)
    except ValueError as exc:
        message = str(exc)
        if "todo limit reached" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=message,
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc
    return Todo.model_validate(record)


@app.delete(
    "/todos/{todo_id}",
    response_model=TodoDeleteResponse,
    tags=["todos"],
)
async def remove_todo(
    todo_id: int,
    _: Annotated[str, Depends(require_auth)],
) -> TodoDeleteResponse:
    """Delete a todo by id."""
    deleted = await asyncio.to_thread(delete_todo, todo_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todo not found",
        )
    return TodoDeleteResponse(deleted=True, id=todo_id)
