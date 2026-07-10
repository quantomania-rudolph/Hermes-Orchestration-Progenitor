"""Low-level Cursor SDK wrapper (Layer 4)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.cloud_git_sync import prepare_for_cloud_spawn, sync_after_cloud_spawn
from config.loop_config import cursor_runtime

try:
    from cursor_sdk import Agent, CloudAgentOptions, CloudRepository, CursorAgentError, LocalAgentOptions
except ImportError:
    Agent = None  # type: ignore[misc, assignment]
    CloudAgentOptions = None  # type: ignore[misc, assignment]
    CloudRepository = None  # type: ignore[misc, assignment]
    CursorAgentError = Exception  # type: ignore[misc, assignment]
    LocalAgentOptions = None  # type: ignore[misc, assignment]


BRIDGE_WINERROR = "10038"


@dataclass
class CursorSessionResult:
    status: str
    run_id: str
    transcript: str
    write_set: list[str] = field(default_factory=list)
    runtime: str = "local"


class CursorSDK:
    def bridge_available(self) -> bool:
        """Quick probe — local bridge is broken on some Windows builds (WinError 10038)."""
        mode = cursor_runtime()
        if mode == "cloud":
            return bool(self._git_remote_url(Path.cwd()))
        if mode == "auto" and self._git_remote_url(Path.cwd()):
            return True
        if os.environ.get("HERMES_CURSOR_BRIDGE_PROBE", "0").strip().lower() not in {
            "1",
            "true",
            "yes",
        }:
            return mode == "cloud"
        try:
            self._spawn_session("Reply PING", cwd=Path.cwd(), timeout_probe=True)
            return True
        except Exception as exc:
            if BRIDGE_WINERROR in str(exc):
                return False
            return cursor_runtime() == "cloud"

    def _git_remote_url(self, cwd: Path) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=10,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return None

    def _resolve_runtime_mode(self, cwd: Path) -> str:
        mode = cursor_runtime()
        if mode in {"local", "cloud"}:
            return mode
        # auto: prefer local bridge; on Windows WinError 10038 use cloud when git remote exists
        if self._git_remote_url(cwd):
            try:
                self._spawn_session("Reply PING", cwd=cwd, timeout_probe=True)
                return "local"
            except Exception as exc:
                if BRIDGE_WINERROR in str(exc):
                    return "cloud"
        return "local"

    def _agent_options(self, *, cwd: Path, model: str, api_key: str, runtime_mode: str) -> dict[str, Any]:
        opts: dict[str, Any] = {"model": model, "api_key": api_key}
        if runtime_mode == "cloud":
            remote = self._git_remote_url(cwd)
            if not remote:
                raise CursorAgentError(
                    "HERMES_CURSOR_RUNTIME=cloud requires git remote origin "
                    "(init repo + push to GitHub first)",
                    is_retryable=False,
                )
            opts["cloud"] = CloudAgentOptions(
                repos=[CloudRepository(url=remote)],
                skip_reviewer_request=True,
            )
            return opts
        opts["local"] = LocalAgentOptions(cwd=str(cwd))
        return opts

    def _spawn_session(
        self,
        prompt: str,
        *,
        cwd: Path,
        model: str | None = None,
        timeout_probe: bool = False,
        target_files: list[str] | None = None,
    ) -> CursorSessionResult:
        if Agent is None:
            raise CursorAgentError("cursor-sdk not installed")
        api_key = os.environ.get("CURSOR_API_KEY", "").strip()
        if not api_key:
            raise CursorAgentError("CURSOR_API_KEY not set")
        model = model or os.environ.get("HERMES_CURSOR_MODEL", "composer-2.5")
        transcript_parts: list[str] = []
        runtime_mode = self._resolve_runtime_mode(cwd) if not timeout_probe else "local"
        if runtime_mode == "cloud" and not timeout_probe:
            prep = prepare_for_cloud_spawn(cwd)
            if not prep.ok:
                raise CursorAgentError(prep.detail, is_retryable=False)
        opts = self._agent_options(cwd=cwd, model=model, api_key=api_key, runtime_mode=runtime_mode)
        runtime_label = "cloud" if "cloud" in opts else "local"
        try:
            if timeout_probe and runtime_label == "local":
                with Agent.create(**opts):
                    pass
                return CursorSessionResult(
                    status="completed",
                    run_id="probe",
                    transcript="probe-ok",
                    runtime=runtime_label,
                )
            with Agent.create(**opts) as agent:
                run = agent.send(prompt)
                for message in run.messages():
                    if message.type == "assistant":
                        for block in message.message.content:
                            if getattr(block, "type", None) == "text":
                                transcript_parts.append(block.text)
                result = run.wait()
        except (CursorAgentError, OSError, Exception) as exc:
            if BRIDGE_WINERROR in str(exc) and runtime_label == "local" and cursor_runtime() == "auto":
                raise CursorAgentError(
                    f"{exc} — set HERMES_T09_RUNTIME=auto to delegate to Qwen, "
                    "or HERMES_CURSOR_RUNTIME=cloud with git remote",
                    is_retryable=True,
                ) from exc
            raise CursorAgentError(str(exc), is_retryable=True) from exc

        if runtime_label == "cloud" and result.status not in ("error",):
            sync = sync_after_cloud_spawn(cwd, target_files=target_files)
            if not sync.ok:
                raise CursorAgentError(
                    f"cloud agent finished but local sync failed: {sync.detail}",
                    is_retryable=True,
                )

        return CursorSessionResult(
            status=result.status,
            run_id=result.id,
            transcript="\n".join(transcript_parts),
            write_set=list(target_files or []),
            runtime=runtime_label,
        )

    def spawn_and_run(
        self,
        prompt: str,
        *,
        cwd: Path,
        model: str | None = None,
        target_files: list[str] | None = None,
    ) -> CursorSessionResult:
        return self._spawn_session(prompt, cwd=cwd, model=model, target_files=target_files)
