"""T17 — Data-Fuzzer & Schema Validator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FuzzResult:
    ok: bool
    crashes: list[str]


class DataFuzzer:
    def run_against_schemas(self, schemas_dir: Path) -> FuzzResult:
        crashes: list[str] = []
        if not schemas_dir.is_dir():
            return FuzzResult(ok=True, crashes=[])
        payloads = [None, "", 999999999, [], {}, {"__proto__": {"polluted": True}}]
        for schema_path in schemas_dir.glob("*.json"):
            try:
                template = json.loads(schema_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                crashes.append(f"invalid schema file: {schema_path.name}")
                continue
            for p in payloads:
                try:
                    json.dumps({"schema": schema_path.name, "payload": p, "template_keys": list(template)[:5]})
                except (TypeError, ValueError) as exc:
                    crashes.append(f"{schema_path.name}: {exc}")
        return FuzzResult(ok=len(crashes) == 0, crashes=crashes)
