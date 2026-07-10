"""Pydantic models for the FastAPI todo REST API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TodoBase(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class TodoCreate(TodoBase):
    pass


class Todo(TodoBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class UserCreate(UserBase):
    pass


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
