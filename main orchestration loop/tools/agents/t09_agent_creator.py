"""T09 — Agent_Creator (Cursor SDK)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents.creator_prompt import CreatorPromptInput, build_creator_prompt
from agents.cursor_sdk import CursorAgentError, CursorSDK
from agents.hermes_local_creator import HermesLocalCreator
from config.loop_config import t09_runtime
from tools.context.t08_scope_boundary_compiler import AuthorizationBlock


@dataclass
class CreatorResult:
    ok: bool
    status: str
    transcript: str
    target_files: list[str]


class AgentCreator:
    def __init__(self, sdk: CursorSDK, local: HermesLocalCreator | None = None) -> None:
        self.sdk = sdk
        self.local = local or HermesLocalCreator()

    def run(
        self,
        *,
        repo_root: Path,
        objective: str,
        step_intent: str,
        auth: AuthorizationBlock,
        interfaces: str,
        rag_context: str,
        target_files: list[str],
    ) -> CreatorResult:
        prompt = build_creator_prompt(
            CreatorPromptInput(
                objective_snippet=objective[:500],
                step_intent=step_intent,
                boundary_block=auth.text,
                interface_snippets=interfaces,
                rag_snippets=rag_context[:6000],
                target_files=target_files,
            )
        )
        result = self.sdk.spawn_and_run(prompt, cwd=repo_root, target_files=target_files)
        ok = result.status not in ("error",)
        return CreatorResult(
            ok=ok,
            status=result.status,
            transcript=result.transcript[-8000:],
            target_files=target_files,
        )

    def run_local(
        self,
        *,
        repo_root: Path,
        wrapped_prompt: str,
        step_intent: str,
        auth: AuthorizationBlock,
        interfaces: str,
        rag_context: str,
        target_files: list[str],
        objective: str,
    ) -> CreatorResult:
        prompt = build_creator_prompt(
            CreatorPromptInput(
                objective_snippet=objective[:500],
                step_intent=step_intent,
                boundary_block=auth.text,
                interface_snippets=interfaces,
                rag_snippets=rag_context[:6000],
                target_files=target_files,
            )
        )
        result = self.local.run(
            repo_root=repo_root,
            wrapped_prompt=wrapped_prompt,
            creator_prompt=prompt,
            target_files=target_files,
        )
        return CreatorResult(
            ok=result.ok,
            status=result.status,
            transcript=result.transcript,
            target_files=result.target_files,
        )

    def run_with_fallback(
        self,
        *,
        repo_root: Path,
        objective: str,
        step_intent: str,
        auth: AuthorizationBlock,
        interfaces: str,
        rag_context: str,
        target_files: list[str],
        wrapped_prompt: str,
        cursor_ok: bool,
    ) -> tuple[CreatorResult | None, str]:
        """Try Cursor (if configured), then Qwen. Returns (result, delegate_label)."""
        mode = t09_runtime()
        if mode not in {"auto", "cursor", "qwen"}:
            mode = "auto"

        if mode in {"auto", "cursor"} and cursor_ok:
            try:
                result = self.run(
                    repo_root=repo_root,
                    objective=objective,
                    step_intent=step_intent,
                    auth=auth,
                    interfaces=interfaces,
                    rag_context=rag_context,
                    target_files=target_files,
                )
                if result.ok:
                    return result, "cursor"
                print(f"[P2] T09 Cursor returned non-ok status: {result.status}")
            except (CursorAgentError, Exception) as exc:
                print(f"[P2] T09 Cursor spawn failed ({exc})")
                if mode == "cursor":
                    raise

        if mode in {"auto", "qwen"}:
            print("[P2] T09 delegating to Hermes/Qwen local writer")
            result = self.run_local(
                repo_root=repo_root,
                wrapped_prompt=wrapped_prompt,
                step_intent=step_intent,
                auth=auth,
                interfaces=interfaces,
                rag_context=rag_context,
                target_files=target_files,
                objective=objective,
            )
            return result, "qwen"

        return None, "none"
