"""Hermes local inference — Qwen via NoLlama OpenAI-compatible API."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Type

from openai import OpenAI

HERMES_ROOT = Path(__file__).resolve().parents[2]
if str(HERMES_ROOT) not in sys.path:
    sys.path.insert(0, str(HERMES_ROOT))

from hermes_config import HERMES_CHAT_MODEL_DEFAULT, NOLLAMA_OPENAI_BASE_URL  # noqa: E402
from hermes_nollama import resolve_chat_model  # noqa: E402

from models.schema_contracts.base import SchemaViolation  # noqa: E402


@dataclass
class HermesResponse:
    raw: str
    parsed: Any | None
    tokens_estimated: int


class HermesModel:
    """T26 routes here for HERMES task_class calls."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("NOLLAMA_OPENAI_BASE_URL", NOLLAMA_OPENAI_BASE_URL)
        self.model = os.environ.get("HERMES_CHAT_MODEL", HERMES_CHAT_MODEL_DEFAULT)
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=os.environ.get("NOLLAMA_API_KEY", "nollama"),
        )

    def _resolved_model(self) -> str:
        return resolve_chat_model(self.model, prefer_device="GPU") or self.model

    def call(
        self,
        wrapped_prompt: str,
        *,
        output_schema: Type[Any] | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> HermesResponse:
        if "SYSTEM MACRO-DIRECTIVE" not in wrapped_prompt:
            raise ValueError("Prompt must be T01-wrapped before Hermes call")
        resp = self.client.chat.completions.create(
            model=self._resolved_model(),
            messages=[{"role": "user", "content": wrapped_prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw = (resp.choices[0].message.content or "").strip()
        tokens = getattr(resp.usage, "total_tokens", None) or max(len(raw) // 4, 1)
        parsed = None
        if output_schema is not None:
            try:
                parsed = output_schema.from_raw(raw)
            except (SchemaViolation, json.JSONDecodeError, KeyError, ValueError) as exc:
                raise SchemaViolation(str(exc)) from exc
        return HermesResponse(raw=raw, parsed=parsed, tokens_estimated=int(tokens))
