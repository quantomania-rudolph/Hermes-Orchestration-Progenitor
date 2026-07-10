"""Hermes/Qwen local code writer — T09 fallback when Cursor local bridge is unavailable."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from models.hermes import HermesModel
from models.schema_contracts.base import SchemaViolation, _extract_json_block
from tools.common import ToolError


@dataclass
class LocalCreatorResult:
    ok: bool
    status: str
    transcript: str
    target_files: list[str]
    delegate: str = "qwen"


class HermesLocalCreator:
    """Writes target_files using local Qwen when Cursor SDK bridge cannot spawn."""

    def run(
        self,
        *,
        repo_root: Path,
        wrapped_prompt: str,
        creator_prompt: str,
        target_files: list[str],
    ) -> LocalCreatorResult:
        if "SYSTEM MACRO-DIRECTIVE" not in wrapped_prompt:
            raise ToolError("HermesLocalCreator requires T01-wrapped prompt")

        prompt = (
            f"{wrapped_prompt}\n\n"
            f"{creator_prompt}\n\n"
            "DELEGATION MODE: You are Hermes delegating implementation to local Qwen.\n"
            "Return ONLY valid JSON (no markdown fences):\n"
            '{"files":[{"path":"relative/path.py","content":"full file source"}]}\n'
            f"Required paths exactly: {json.dumps(target_files)}\n"
            "Rules: complete runnable Python, no placeholders, no tests unless listed in targets.\n"
        )

        model = HermesModel()
        try:
            resp = model.call(prompt, max_tokens=6000, temperature=0.15)
        except Exception as exc:
            return LocalCreatorResult(
                ok=False,
                status="error",
                transcript=str(exc),
                target_files=target_files,
            )

        written: list[str] = []
        errors: list[str] = []
        try:
            data = _extract_json_block(resp.raw)
            files = data.get("files", [])
            if not isinstance(files, list):
                raise SchemaViolation("files must be a list")
            by_path = {str(item.get("path", "")).replace("\\", "/"): item.get("content", "") for item in files}
            for rel in target_files:
                norm = rel.replace("\\", "/")
                content = by_path.get(norm)
                if content is None:
                    errors.append(f"missing path in model JSON: {norm}")
                    continue
                dest = repo_root / norm
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(str(content).strip() + "\n", encoding="utf-8")
                written.append(norm)
        except (SchemaViolation, json.JSONDecodeError, KeyError, ValueError) as exc:
            # Fallback: extract fenced python blocks keyed by filename in comment
            blocks = self._extract_code_blocks(resp.raw)
            for rel in target_files:
                norm = rel.replace("\\", "/")
                if norm in blocks:
                    dest = repo_root / norm
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(blocks[norm].strip() + "\n", encoding="utf-8")
                    written.append(norm)
            if not written:
                errors.append(f"parse failed: {exc}")

        ok = len(written) == len(target_files) and not errors
        return LocalCreatorResult(
            ok=ok,
            status="completed" if ok else "error",
            transcript=resp.raw[-8000:],
            target_files=written or target_files,
            delegate="qwen",
        )

    @staticmethod
    def _extract_code_blocks(text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        pattern = re.compile(
            r"```(?:python)?\s*#\s*file:\s*([^\n]+)\n(.*?)```",
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            path = match.group(1).strip().replace("\\", "/")
            out[path] = match.group(2)
        return out
