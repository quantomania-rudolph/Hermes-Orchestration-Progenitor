"""Pydantic schema for YAML policy documents."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Rule(BaseModel):
    id: str = Field(min_length=1)
    severity: Severity
    description: str | None = None


class PolicyDocument(BaseModel):
    version: str = Field(min_length=1)
    rules: list[Rule]
