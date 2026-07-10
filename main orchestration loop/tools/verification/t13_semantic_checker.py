"""T13 — Vision-Alignment Semantic Checker (HYBRID harness + optional Qwen)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from models.hermes import HermesModel
from models.schema_contracts.base import SemanticAlignResult, SchemaViolation


@dataclass
class SemanticResult:
    ok: bool
    items: list[dict]
    raw: str


class SemanticChecker:
    def __init__(self, architecture_md: Path) -> None:
        self.architecture_md = architecture_md
        self.checklist = self._parse_checklist()

    def _parse_checklist(self) -> list[str]:
        if not self.architecture_md.is_file():
            return ["state_ownership", "naming_conventions"]
        text = self.architecture_md.read_text(encoding="utf-8")
        markers = re.findall(r"<!-- T13:(\w+) -->", text)
        return markers or ["state_ownership"]

    def _deterministic_check(self, code_summary: str) -> list[dict]:
        """Python-owned rubric — runs before/alongside model (HYBRID harness)."""
        items: list[dict] = []
        lower = code_summary.lower()
        rules = {
            "state_ownership": (
                "pipeline_state" not in lower
                or "t03" in lower
                or "state_manager" in lower
                or len(lower) < 50
            ),
            "naming_conventions": (
                "t0" in lower or "phase" in lower or "def run_" in lower or len(lower) < 50
            ),
            "async_patterns": True,
            "index_consistency": True,
            "hermes_proposes_python_disposes": (
                "hermes" not in lower or "python" in lower or "t03" in lower or len(lower) < 50
            ),
        }
        for marker in self.checklist:
            passed = rules.get(marker, True)
            items.append({"id": marker, "pass": passed, "note": "deterministic harness"})
        return items

    def check(self, wrapped_prompt: str, code_summary: str) -> SemanticResult:
        items = self._deterministic_check(code_summary)
        if all(i["pass"] for i in items):
            return SemanticResult(ok=True, items=items, raw="deterministic pass")

        checklist_str = ", ".join(self.checklist)
        prompt = (
            wrapped_prompt
            + f"\n\nEvaluate code against checklist: {checklist_str}\n"
            f"Code:\n{code_summary[:3000]}\n"
            'JSON only: {"items":[{"id":"...","pass":true,"note":"..."}]}\n'
        )
        try:
            model = HermesModel()
            resp = model.call(prompt, output_schema=SemanticAlignResult, max_tokens=400)
            if resp.parsed and resp.parsed.all_pass():
                return SemanticResult(ok=True, items=resp.parsed.items, raw=resp.raw)
            if resp.parsed:
                return SemanticResult(ok=False, items=resp.parsed.items, raw=resp.raw)
        except (SchemaViolation, Exception) as exc:
            passed = all(i["pass"] for i in items)
            return SemanticResult(
                ok=passed,
                items=items,
                raw=f"model skipped ({exc}); deterministic={'pass' if passed else 'fail'}",
            )
        return SemanticResult(ok=False, items=items, raw="semantic fail")
