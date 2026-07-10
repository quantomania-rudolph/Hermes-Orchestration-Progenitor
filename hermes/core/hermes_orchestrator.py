#!/usr/bin/env python3
"""
Hermes: autonomous orchestrator (NoLlama chat + local RAG + Cursor Composer).

Set CURSOR_API_KEY before runs that delegate to Composer (never commit keys).
Start NoLlama first (install.ps1 / start.ps1). Run ensure_hermes_model.py --check.
"""

from __future__ import annotations

from hermes_secrets import load_local_env

load_local_env()

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from openai import OpenAI

try:
    from cursor_sdk import Agent, CursorAgentError, LocalAgentOptions
except ImportError as exc:
    raise SystemExit(
        "cursor-sdk is required: pip install cursor-sdk openai numpy"
    ) from exc

from hermes_config import (
    BUILD_INDEX_SCRIPT,
    CURSOR_MODEL_DEFAULT,
    HERMES_CHAT_MODEL_DEFAULT,
    HERMES_DIR,
    NOLLAMA_OPENAI_BASE_URL,
    VECTORS_PATH,
    WORKSPACE_ROOT,
)
from hermes_embeddings import embed_query as local_embed_query
from hermes_nollama import resolve_chat_model

# ── Paths & clients ───────────────────────────────────────────────────────────

TOOLS_DIR = HERMES_DIR / "hermes_invented_tools"
TOOLS_DIR.mkdir(exist_ok=True)
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

NOLLAMA_CHAT_URL = os.environ.get("NOLLAMA_OPENAI_BASE_URL", NOLLAMA_OPENAI_BASE_URL)
CHAT_MODEL = os.environ.get("HERMES_CHAT_MODEL", HERMES_CHAT_MODEL_DEFAULT)
CURSOR_MODEL = os.environ.get("HERMES_CURSOR_MODEL", CURSOR_MODEL_DEFAULT)
MAX_TURNS = int(os.environ.get("HERMES_MAX_TURNS", "40"))
TERMINAL_TIMEOUT = int(os.environ.get("HERMES_TERMINAL_TIMEOUT", "120"))
RAG_TOP_K = 3

local_client = OpenAI(
    base_url=NOLLAMA_CHAT_URL,
    api_key=os.environ.get("NOLLAMA_API_KEY", "nollama"),
)

_TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

HERMES_SYSTEM_PROMPT = """You are Hermes, an autonomous software engineering agent for a large multi-root workspace.

Workflow:
1. Use query_local_rag to locate relevant code before editing or running tests.
2. Use run_terminal_test to validate changes (pytest, scripts, compiles).
3. When tests fail due to structural or multi-file issues, use invoke_cursor_composer with code_context and error_log.
4. IMMEDIATELY after invoke_cursor_composer creates or modifies any file, call trigger_codebase_reindex so your RAG memory matches disk.
5. If you need a capability that no tool provides, use create_new_tool (reason → write Python → hot-load), then call the new tool on the same turn cycle when possible.

Rules:
- Prefer minimal, targeted fixes; run tests after substantive edits.
- Never invent file paths; confirm via RAG or terminal listing first.
- Terminal commands run in the workspace root with a timeout; avoid destructive commands unless the user explicitly asked.
- create_new_tool functions must be named exactly like tool_name, return a string, and use only stdlib plus numpy unless already installed.
"""


# ── Vector / RAG helpers ───────────────────────────────────────────────────────


def _load_chunks() -> list[dict[str, Any]]:
    if not VECTORS_PATH.is_file():
        raise FileNotFoundError(
            f"Missing {VECTORS_PATH.name}. Run scripts/setup_index/01_build_index.bat "
            "or trigger_codebase_reindex first."
        )
    raw = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        chunks = raw.get("chunks", [])
    elif isinstance(raw, list):
        chunks = raw
    else:
        raise ValueError("codebase_vectors.json has unexpected structure")
    if not chunks:
        raise ValueError("codebase_vectors.json contains no chunks")
    return chunks


def _embed_query(text: str) -> np.ndarray:
    return local_embed_query(text)


def _chunk_matrix(chunks: list[dict[str, Any]]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    vectors: list[np.ndarray] = []
    valid: list[dict[str, Any]] = []
    for entry in chunks:
        raw_vec = entry.get("vector")
        if not raw_vec:
            continue
        vec = np.asarray(raw_vec, dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        if norm <= 0:
            continue
        vectors.append(vec / norm)
        valid.append(entry)
    if not vectors:
        raise ValueError("no valid vectors in index")
    return np.vstack(vectors), valid


def query_local_rag(search_query: str) -> str:
    try:
        if not search_query.strip():
            return "RAG error: search_query must be non-empty."
        query_vec = _embed_query(search_query)
        chunks = _load_chunks()
        matrix, valid = _chunk_matrix(chunks)
        scores = matrix @ query_vec
        top_idx = np.argpartition(-scores, min(RAG_TOP_K, len(scores) - 1))[:RAG_TOP_K]
        top_idx = top_idx[np.argsort(-scores[top_idx])]

        lines = ["=== LOCAL RAG CONTEXT (top %d) ===" % RAG_TOP_K]
        for rank, idx in enumerate(top_idx, start=1):
            entry = valid[int(idx)]
            sim = float(scores[int(idx)])
            lines.append(
                f"\n[{rank}] similarity={sim:.4f} file={entry.get('file')} lines={entry.get('lines')}\n"
                f"```\n{entry.get('text', '')}\n```"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"RAG error: {exc}"


# ── Terminal & index tools ────────────────────────────────────────────────────


def run_terminal_test(command: str) -> str:
    try:
        if not command.strip():
            return "Terminal error: command must be non-empty."
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TERMINAL_TIMEOUT,
            cwd=str(WORKSPACE_ROOT),
            env=os.environ.copy(),
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if result.returncode == 0:
            return stdout if stdout.strip() else "(success, no stdout)"
        return (
            f"EXIT_CODE={result.returncode}\n"
            f"--- STDOUT ---\n{stdout}\n"
            f"--- STDERR ---\n{stderr}"
        )
    except subprocess.TimeoutExpired:
        return f"Terminal error: command exceeded {TERMINAL_TIMEOUT}s timeout."
    except Exception as exc:
        return f"Terminal error: {exc}"


def trigger_codebase_reindex() -> str:
    try:
        if not BUILD_INDEX_SCRIPT.is_file():
            return f"Reindex error: missing {BUILD_INDEX_SCRIPT.name}"
        proc = subprocess.run(
            [sys.executable, str(BUILD_INDEX_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=3600,
            cwd=str(HERMES_DIR),
            env=os.environ.copy(),
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return f"Reindex failed (exit {proc.returncode}):\n{combined[-8000:]}"
        return f"Reindex completed successfully.\n{combined[-4000:]}"
    except subprocess.TimeoutExpired:
        return "Reindex error: scripts/setup_index/build_index.py exceeded 3600s."
    except Exception as exc:
        return f"Reindex error: {exc}"


def invoke_cursor_composer(code_context: str, error_log: str) -> str:
    api_key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not api_key:
        return (
            "Cursor SDK error: set CURSOR_API_KEY in the environment "
            "(Dashboard → Integrations)."
        )

    prompt = (
        "Hermes delegated a multi-file repair. Apply minimal, correct patches.\n\n"
        "## Code context\n"
        f"{code_context}\n\n"
        "## Error / test output\n"
        f"{error_log}\n\n"
        "Fix root causes, keep style consistent, and ensure tests would pass."
    )

    try:
        with Agent.create(
            model=CURSOR_MODEL,
            api_key=api_key,
            local=LocalAgentOptions(cwd=str(WORKSPACE_ROOT)),
        ) as agent:
            run = agent.send(prompt)
            transcript_parts: list[str] = []
            for message in run.messages():
                if message.type == "assistant":
                    for block in message.message.content:
                        if getattr(block, "type", None) == "text":
                            transcript_parts.append(block.text)
            result = run.wait()

        if result.status == "error":
            return (
                f"Composer run finished with status=error run_id={result.id}\n"
                + "\n".join(transcript_parts)[-12000:]
            )
        body = "\n".join(transcript_parts).strip()
        return (
            f"Composer run status={result.status} run_id={result.id}\n"
            f"{body[-12000:] if body else '(no assistant text)'}\n\n"
            "ACTION REQUIRED: call trigger_codebase_reindex now so RAG stays current."
        )
    except CursorAgentError as exc:
        return (
            f"Cursor SDK startup failed: {exc.message} "
            f"(retryable={exc.is_retryable})"
        )
    except Exception as exc:
        return f"Cursor SDK error: {exc}"


# ── Dynamic tool registry ─────────────────────────────────────────────────────


class DynamicToolRegistry:
    def __init__(self) -> None:
        self.schemas: list[dict[str, Any]] = []
        self.functions: dict[str, Callable[..., str]] = {}
        self._load_builtins()

    def _register(self, schema: dict[str, Any], func: Callable[..., str]) -> None:
        name = schema["name"]
        if name in self.functions:
            raise ValueError(f"duplicate tool name: {name}")
        envelope = {"type": "function", "function": schema}
        self.schemas.append(envelope)
        self.functions[name] = func

    def _load_builtins(self) -> None:
        self._register(
            {
                "name": "query_local_rag",
                "description": "Semantic search over codebase_vectors.json; returns top matching code blocks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "search_query": {
                            "type": "string",
                            "description": "Natural language or symbol-focused search query.",
                        }
                    },
                    "required": ["search_query"],
                },
            },
            query_local_rag,
        )
        self._register(
            {
                "name": "run_terminal_test",
                "description": "Run a shell command in the workspace directory; returns stdout or stderr.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Command to execute (e.g. pytest tests/).",
                        }
                    },
                    "required": ["command"],
                },
            },
            run_terminal_test,
        )
        self._register(
            {
                "name": "invoke_cursor_composer",
                "description": (
                    "Delegate complex multi-file refactors to Cursor Composer 2.5 via cursor-sdk."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code_context": {
                            "type": "string",
                            "description": "Relevant files/snippets and intent.",
                        },
                        "error_log": {
                            "type": "string",
                            "description": "Failing test output or stack traces.",
                        },
                    },
                    "required": ["code_context", "error_log"],
                },
            },
            invoke_cursor_composer,
        )
        self._register(
            {
                "name": "trigger_codebase_reindex",
                "description": (
                    "Run scripts/setup_index/build_index.py to refresh codebase_vectors.json "
                    "after code changes (especially after Composer edits)."
                ),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
            lambda: trigger_codebase_reindex(),
        )
        self._register(
            {
                "name": "create_new_tool",
                "description": (
                    "Three-step meta-tool: write a new Python tool file, hot-load it, "
                    "append OpenAI schema, then invoke on subsequent turns."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "snake_case function name (must match def in python_code).",
                        },
                        "tool_description": {
                            "type": "string",
                            "description": "What the tool does for the model.",
                        },
                        "python_code": {
                            "type": "string",
                            "description": (
                                "Full Python module source defining def tool_name(...): "
                                "that returns str."
                            ),
                        },
                        "argument_schema": {
                            "type": "object",
                            "description": "OpenAI parameters.properties and .required lists.",
                            "properties": {
                                "properties": {"type": "object"},
                                "required": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["properties", "required"],
                        },
                    },
                    "required": [
                        "tool_name",
                        "tool_description",
                        "python_code",
                        "argument_schema",
                    ],
                },
            },
            lambda **kwargs: self.handle_tool_creation(**kwargs),
        )
        self._reload_invented_tools()

    def _reload_invented_tools(self) -> None:
        for py_file in sorted(TOOLS_DIR.glob("*.py")):
            meta_path = py_file.with_suffix(".json")
            if not meta_path.is_file():
                continue
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                func = self._load_module_function(py_file, meta["name"])
                if meta["name"] not in self.functions:
                    self._register(meta["schema"], func)
            except Exception as exc:
                print(f"[warn] skip invented tool {py_file.name}: {exc}", file=sys.stderr)

    @staticmethod
    def _load_module_function(py_file: Path, tool_name: str) -> Callable[..., str]:
        spec = importlib.util.spec_from_file_location(f"hermes_tool_{tool_name}", py_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load spec for {py_file}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        func = getattr(module, tool_name, None)
        if not callable(func):
            raise AttributeError(f"{tool_name} not callable in {py_file}")
        return func

    def handle_tool_creation(
        self,
        tool_name: str,
        tool_description: str,
        python_code: str,
        argument_schema: dict[str, Any],
    ) -> str:
        try:
            if not _TOOL_NAME_RE.match(tool_name):
                return (
                    "Tool forge error: tool_name must be snake_case "
                    "[a-z][a-z0-9_], max 64 chars."
                )
            if tool_name in self.functions:
                return f"Tool forge error: '{tool_name}' already registered."

            props = argument_schema.get("properties")
            required = argument_schema.get("required")
            if not isinstance(props, dict) or not isinstance(required, list):
                return "Tool forge error: argument_schema needs properties and required."

            file_path = TOOLS_DIR / f"{tool_name}.py"
            file_path.write_text(python_code, encoding="utf-8")

            func = self._load_module_function(file_path, tool_name)
            schema = {
                "name": tool_name,
                "description": tool_description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            }
            meta_path = file_path.with_suffix(".json")
            meta_path.write_text(
                json.dumps({"name": tool_name, "schema": schema}, indent=2),
                encoding="utf-8",
            )
            self._register(schema, func)
            return (
                f"Success: tool '{tool_name}' written to {file_path.name}, "
                "hot-loaded, and registered. Invoke it on your next tool call."
            )
        except Exception as exc:
            return f"Tool forge error for '{tool_name}': {exc}"

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        func = self.functions.get(name)
        if func is None:
            return f"Execution error: unknown tool '{name}'."
        try:
            result = func(**args)
            return result if isinstance(result, str) else str(result)
        except TypeError as exc:
            return f"Execution error: bad arguments for '{name}': {exc}"
        except Exception as exc:
            return f"Execution error in '{name}': {exc}"


# ── Orchestration loop ────────────────────────────────────────────────────────


def run_hermes_loop(
    initial_goal: str,
    *,
    interactive: bool = False,
    max_turns: int = MAX_TURNS,
) -> int:
    registry = DynamicToolRegistry()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": HERMES_SYSTEM_PROMPT},
        {"role": "user", "content": initial_goal},
    ]

    chat_model = resolve_chat_model(CHAT_MODEL, prefer_device="GPU") or CHAT_MODEL

    print("Hermes orchestrator online.")
    print(f"  chat:  {chat_model} @ {NOLLAMA_CHAT_URL}")
    print(f"  embed: local sentence-transformers (BAAI/bge-m3)")
    print(f"  hermes:    {HERMES_DIR}")
    print(f"  workspace: {WORKSPACE_ROOT}")
    print(f"  tools: {len(registry.schemas)}")

    turn = 0
    while turn < max_turns:
        turn += 1
        print(f"\n--- turn {turn}/{max_turns} ---")

        while True:
            try:
                response = local_client.chat.completions.create(
                    model=chat_model,
                    messages=messages,
                    tools=registry.schemas,
                    temperature=0.1,
                )
            except Exception as exc:
                print(f"[fatal] LLM request failed: {exc}", file=sys.stderr)
                return 1

            msg = response.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                break

            forged_tool = False
            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    output = f"Execution error: invalid JSON arguments: {exc}"
                else:
                    print(f"[tool] {name}({json.dumps(args)[:200]})")
                    output = registry.dispatch(name, args)

                if name == "create_new_tool" and output.startswith("Success"):
                    forged_tool = True

                preview = output[:500] + ("..." if len(output) > 500 else "")
                print(f"[result] {preview}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": name,
                        "content": output,
                    }
                )

            if forged_tool:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your new tool is hot-loaded and appears in the tool list. "
                            "Call it immediately to finish the step you invented it for."
                        ),
                    }
                )
                continue

            break

        if not tool_calls:
            content = msg.content or "(empty response)"
            print(f"\n[HERMES]\n{content}")
            if interactive:
                ans = input("\nEnter to continue, or 'exit': ").strip().lower()
                if ans == "exit":
                    return 0
                messages.append(
                    {
                        "role": "user",
                        "content": "Continue working on the original goal.",
                    }
                )
                continue
            return 0

    print(f"[stop] reached max turns ({max_turns})", file=sys.stderr)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes autonomous orchestrator.")
    parser.add_argument(
        "task",
        nargs="?",
        default="",
        help="High-level goal for Hermes (otherwise read from stdin).",
    )
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="After a final assistant message, prompt before continuing.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=MAX_TURNS,
        help=f"Maximum LLM turns (default {MAX_TURNS}).",
    )
    args = parser.parse_args()

    task = args.task.strip()
    if not task:
        print("Enter task (end with Ctrl-D / Ctrl-Z):", file=sys.stderr)
        task = sys.stdin.read().strip()
    if not task:
        print("No task provided.", file=sys.stderr)
        return 1

    return run_hermes_loop(task, interactive=args.interactive, max_turns=args.max_turns)


if __name__ == "__main__":
    raise SystemExit(main())
