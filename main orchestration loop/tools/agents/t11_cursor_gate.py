"""T11 — Cursor SDK Availability Gate."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum

from agents.cloud_git_sync import git_remote_url, is_git_repo
from config.loop_config import CURSOR_MODEL, CURSOR_SDK_VERSION_PIN, cursor_runtime


class CursorStatus(str, Enum):
    CURSOR_OK = "CURSOR_OK"
    CURSOR_UNAVAILABLE = "CURSOR_UNAVAILABLE"


@dataclass
class CursorGateResult:
    status: CursorStatus
    reason_code: str | None = None
    detail: str = ""


class CursorAvailabilityGate:
    def run(self, *, budget_ok: bool = True, skip: bool = False) -> CursorGateResult:
        if skip or os.environ.get("HERMES_SKIP_CURSOR", "").strip() in {"1", "true", "yes"}:
            return CursorGateResult(
                CursorStatus.CURSOR_UNAVAILABLE,
                "SKIP_CURSOR",
                "HERMES_SKIP_CURSOR set — Cursor tools deferred",
            )
        api_key = os.environ.get("CURSOR_API_KEY", "").strip()
        if not api_key:
            return CursorGateResult(
                CursorStatus.CURSOR_UNAVAILABLE,
                "AUTH_EXPIRED",
                "CURSOR_API_KEY not set",
            )
        if not budget_ok:
            return CursorGateResult(
                CursorStatus.CURSOR_UNAVAILABLE,
                "RATE_LIMITED",
                "Session budget floor not met",
            )
        try:
            import cursor_sdk  # noqa: F401
        except ImportError:
            return CursorGateResult(
                CursorStatus.CURSOR_UNAVAILABLE,
                "VERSION_DRIFT",
                f"cursor-sdk not installed ({CURSOR_SDK_VERSION_PIN})",
            )
        try:
            req = urllib.request.Request("https://api.cursor.com", method="HEAD")
            urllib.request.urlopen(req, timeout=5)
        except (urllib.error.URLError, TimeoutError):
            return CursorGateResult(
                CursorStatus.CURSOR_UNAVAILABLE,
                "NETWORK_DOWN",
                "Cursor endpoint unreachable",
            )
        mode = cursor_runtime()
        if mode == "cloud":
            from config.loop_config import HERMES_ROOT

            if not is_git_repo(HERMES_ROOT) or not git_remote_url(HERMES_ROOT):
                return CursorGateResult(
                    CursorStatus.CURSOR_UNAVAILABLE,
                    "VERSION_DRIFT",
                    "HERMES_CURSOR_RUNTIME=cloud requires git repo with origin remote",
                )
            return CursorGateResult(
                CursorStatus.CURSOR_OK,
                detail=f"Cursor cloud gate passed (model pin: {CURSOR_MODEL})",
            )

        if mode == "auto":
            from config.loop_config import HERMES_ROOT

            if git_remote_url(HERMES_ROOT):
                return CursorGateResult(
                    CursorStatus.CURSOR_OK,
                    detail=f"Cursor auto gate passed — cloud fallback available (model: {CURSOR_MODEL})",
                )

        if os.environ.get("HERMES_CURSOR_BRIDGE_PROBE", "0").strip().lower() in {"1", "true", "yes"}:
            try:
                from cursor_sdk import Agent, LocalAgentOptions

                with Agent.create(
                    api_key=api_key,
                    local=LocalAgentOptions(cwd=os.getcwd()),
                ):
                    pass
            except (OSError, Exception) as exc:
                return CursorGateResult(
                    CursorStatus.CURSOR_UNAVAILABLE,
                    "DIRTY_SESSION",
                    f"Cursor bridge probe failed: {exc}",
                )
        return CursorGateResult(
            CursorStatus.CURSOR_OK,
            detail=f"Cursor gate passed (model pin: {CURSOR_MODEL})",
        )
