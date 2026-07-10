"""Shared types and helpers for HERMES tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Phase(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"


class ToolError(Exception):
    """Deterministic tool failure."""


class ContractViolation(ToolError):
    """T29 phase contract not met."""


class SystemHalt(ToolError):
    """Terminal halt — routed to T30."""


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any]
    message: str = ""
