"""YAML policy validation engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

try:
    from .config import MAX_RULES
except ImportError:  # pragma: no cover - script import when package root is on sys.path
    from config import MAX_RULES

try:
    from .schema import PolicyDocument
except ImportError:  # pragma: no cover - script import when package root is on sys.path
    from schema import PolicyDocument

__all__ = ["PolicyViolation", "ValidationResult", "validate_policy"]


@dataclass
class PolicyViolation:
    code: str
    message: str
    rule_id: str | None = None


@dataclass
class ValidationResult:
    yaml_path: str
    valid: bool
    version: str | None
    rule_count: int
    violations: list[PolicyViolation] = field(default_factory=list)

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["violation_count"] = self.violation_count
        return payload


def _normalize_rule_id(rule_id: object) -> str | None:
    """Normalize a raw rule id the same way Pydantic coerces Rule.id."""
    if rule_id is None or isinstance(rule_id, bool):
        return None
    if isinstance(rule_id, str):
        return rule_id or None
    if isinstance(rule_id, (int, float)):
        return str(rule_id)
    return None


def _duplicate_rule_ids(rule_ids: list[str]) -> list[str]:
    """Return ids that appear more than once, preserving first-seen duplicate order."""
    seen: set[str] = set()
    duplicates: list[str] = []
    for rule_id in rule_ids:
        if rule_id in seen and rule_id not in duplicates:
            duplicates.append(rule_id)
        else:
            seen.add(rule_id)
    return duplicates


def _raw_rule_ids(rules: object) -> list[str]:
    """Collect normalized ids from a raw YAML rules sequence."""
    if not isinstance(rules, list):
        return []

    ids: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_id = _normalize_rule_id(rule.get("id"))
        if rule_id is not None:
            ids.append(rule_id)
    return ids


def _schema_violations(exc: ValidationError) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        message = err.get("msg", "schema validation failed")
        if loc:
            message = f"{loc}: {message}"
        violations.append(PolicyViolation(code="schema_error", message=message))
    return violations


def validate_policy(yaml_path: str | Path) -> ValidationResult:
    """Load and validate a YAML policy file; detect duplicate rule ids."""
    path = Path(yaml_path)
    resolved = str(path.resolve())

    if not path.is_file():
        return ValidationResult(
            yaml_path=resolved,
            valid=False,
            version=None,
            rule_count=0,
            violations=[
                PolicyViolation(code="file_not_found", message=f"Policy file not found: {path}")
            ],
        )

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return ValidationResult(
            yaml_path=resolved,
            valid=False,
            version=None,
            rule_count=0,
            violations=[
                PolicyViolation(code="read_error", message=f"Unable to read policy file: {exc}")
            ],
        )

    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        return ValidationResult(
            yaml_path=resolved,
            valid=False,
            version=None,
            rule_count=0,
            violations=[PolicyViolation(code="yaml_error", message=str(exc))],
        )

    if not isinstance(data, dict):
        return ValidationResult(
            yaml_path=resolved,
            valid=False,
            version=None,
            rule_count=0,
            violations=[
                PolicyViolation(
                    code="schema_error",
                    message="Policy document must be a YAML mapping with version and rules",
                )
            ],
        )

    raw_rules = data.get("rules")
    rule_count = len(raw_rules) if isinstance(raw_rules, list) else 0
    version = data.get("version") if isinstance(data.get("version"), str) else None

    violations: list[PolicyViolation] = []

    for rule_id in _duplicate_rule_ids(_raw_rule_ids(raw_rules)):
        violations.append(
            PolicyViolation(
                code="duplicate_id",
                message=f"Duplicate rule id: {rule_id}",
                rule_id=rule_id,
            )
        )

    if rule_count > MAX_RULES:
        violations.append(
            PolicyViolation(
                code="max_rules_exceeded",
                message=f"Policy has {rule_count} rules; maximum allowed is {MAX_RULES}",
            )
        )

    try:
        document = PolicyDocument.model_validate(data)
    except ValidationError as exc:
        violations.extend(_schema_violations(exc))
        return ValidationResult(
            yaml_path=resolved,
            valid=False,
            version=version,
            rule_count=rule_count,
            violations=violations,
        )

    return ValidationResult(
        yaml_path=resolved,
        valid=len(violations) == 0,
        version=document.version,
        rule_count=len(document.rules),
        violations=violations,
    )
