"""Load local secrets from .env.local (never commit that file)."""

from __future__ import annotations

import os
from pathlib import Path

from hermes_config import HERMES_DIR

LOCAL_ENV_PATH = HERMES_DIR / ".env.local"
EXAMPLE_ENV_PATH = HERMES_DIR / ".env.example"


def load_local_env(*, override: bool = False) -> bool:
    """Parse .env.local and set os.environ. Returns True if file was loaded."""
    if not LOCAL_ENV_PATH.is_file():
        return False
    for raw in LOCAL_ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ or not os.environ.get(key, "").strip():
            os.environ[key] = value
    return True


def cursor_key_configured() -> bool:
    load_local_env()
    return bool(os.environ.get("CURSOR_API_KEY", "").strip())
