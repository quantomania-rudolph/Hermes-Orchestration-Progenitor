"""Pydantic schema for transaction CSV rows."""

from __future__ import annotations

import math
from datetime import datetime

from pydantic import BaseModel, field_validator

_NULL_ID_TOKENS = frozenset({"", "null", "none", "nan"})


class TransactionRow(BaseModel):
    id: int
    amount: float
    category: str
    timestamp: datetime

    @field_validator("id", mode="before")
    @classmethod
    def id_must_not_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("id must not be null")
        if isinstance(value, float) and math.isnan(value):
            raise ValueError("id must not be null")
        if isinstance(value, str) and value.strip().lower() in _NULL_ID_TOKENS:
            raise ValueError("id must not be null")
        return value

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, value: float) -> float:
        if not math.isfinite(value) or value <= 0:
            raise ValueError("amount must be greater than 0")
        return value
