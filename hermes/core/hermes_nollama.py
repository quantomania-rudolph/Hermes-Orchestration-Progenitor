"""NoLlama helpers: model name resolution and health probes."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from hermes_config import (
    HERMES_CHAT_MODEL_DEFAULT,
    NOLLAMA_HEALTH_URL,
    NOLLAMA_OLLAMA_TAGS_URL,
    NOLLAMA_OPENAI_BASE_URL,
)


def _fetch_json(url: str, timeout: float = 8.0) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def normalize_model_key(name: str) -> str:
    """Case-insensitive key for matching NoLlama model ids."""
    base = name.split("@", 1)[0]
    return base.lower().replace("_", "-")


def listed_model_ids() -> list[str]:
    ids: list[str] = []
    openai_models = _fetch_json(f"{NOLLAMA_OPENAI_BASE_URL.rstrip('/')}/models")
    if isinstance(openai_models, dict):
        for entry in openai_models.get("data", []):
            mid = entry.get("id")
            if mid:
                ids.append(str(mid))
    tags = _fetch_json(NOLLAMA_OLLAMA_TAGS_URL)
    if isinstance(tags, dict):
        for entry in tags.get("models", []):
            name = entry.get("name")
            if name:
                ids.append(str(name))
    return ids


def resolve_chat_model(
    requested: str | None = None,
    *,
    prefer_device: str | None = None,
) -> str | None:
    """
    Map HERMES_CHAT_MODEL (e.g. qwen3-14b-int4) to the exact id NoLlama exposes
    (e.g. Qwen3-14B-int4 or Qwen3-14B-int4@GPU).
    """
    target = normalize_model_key(
        requested or os.environ.get("HERMES_CHAT_MODEL", HERMES_CHAT_MODEL_DEFAULT)
    )
    candidates = listed_model_ids()
    if not candidates:
        return None

    scored: list[tuple[int, str]] = []
    for mid in candidates:
        base = mid.split("@", 1)[0]
        device = mid.split("@", 1)[1] if "@" in mid else ""
        key = normalize_model_key(base)
        if key != target and target not in key and key not in target:
            continue
        score = 0
        if key == target:
            score += 100
        if prefer_device and device.upper() == prefer_device.upper():
            score += 50
        if device.upper() == "GPU":
            score += 10
        scored.append((score, base))

    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def nollama_health() -> dict | None:
    data = _fetch_json(NOLLAMA_HEALTH_URL)
    return data if isinstance(data, dict) else None


def is_model_available(requested: str | None = None) -> bool:
    return resolve_chat_model(requested) is not None
