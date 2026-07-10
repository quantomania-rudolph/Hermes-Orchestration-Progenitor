"""HMAC API-key authentication for the FastAPI todo REST API."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

try:
    from config import API_KEY
except ImportError:  # pragma: no cover - package import when run as module
    from .config import API_KEY

__all__ = ["API_KEY_HEADER", "require_auth", "verify_api_key"]

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _constant_time_equal(provided: str | None, expected: str) -> bool:
    """Compare API keys without leaking length or content via timing."""
    provided_b = (provided or "").encode("utf-8")
    expected_b = expected.encode("utf-8")
    if len(provided_b) != len(expected_b):
        hmac.compare_digest(expected_b, expected_b)
        return False
    return hmac.compare_digest(provided_b, expected_b)


def verify_api_key(api_key: str | None) -> str:
    """Validate the caller token against the configured API_KEY."""
    if not API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key not configured",
        )
    if not _constant_time_equal(api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return API_KEY


async def require_auth(
    api_key: Annotated[str | None, Security(API_KEY_HEADER)],
) -> str:
    """FastAPI dependency that rejects unauthenticated requests."""
    return verify_api_key(api_key)
