"""Run leakage audits on synthetic datasets and write JSON/MD reports."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_PKG_ROOT = Path(__file__).resolve().parent
_CONFIG_MODULE = "leakage_audit_pipeline.config"
_DETECTORS_MODULE = "leakage_audit_pipeline.detectors"
_PURGED_MODULE = "leakage_audit_pipeline.purged_validator"
_SYNTHETIC_MODULE = "leakage_audit_pipeline.synthetic_data"


def _ensure_parent_modules(qualified_name: str) -> None:
    """Stub parent packages so dotted spec names resolve under T17 fuzz imports."""
    parts = qualified_name.split(".")
    for i in range(1, len(parts)):
        parent_name = ".".join(parts[:i])
        if parent_name in sys.modules:
            continue
        parent = types.ModuleType(parent_name)
        parent.__path__ = [str(_PKG_ROOT)]
        sys.modules[parent_name] = parent


def _load_sibling_module(qualified_name: str, filename: str):
    """Load sibling module with sys.modules registration (fuzz-safe)."""
    cached = sys.modules.get(qualified_name)
    if cached is not None:
        return cached

    module_path = _PKG_ROOT / filename
    if not module_path.is_file():
        raise ImportError(f"cannot find {filename} at {module_path}")

    _ensure_parent_modules(qualified_name)
    spec = importlib.util.spec_from_file_location(qualified_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename} from {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


_cfg = _load_sibling_module(_CONFIG_MODULE, "config.py")
_det = _load_sibling_module(_DETECTORS_MODULE, "detectors.py")
_purged = _load_sibling_module(_PURGED_MODULE, "purged_validator.py")
_synth = _load_sibling_module(_SYNTHETIC_MODULE, "synthetic_data.py")

ALL_DATASET_TAGS = _cfg.ALL_DATASET_TAGS
AUDIT_REPORT_JSON = _cfg.AUDIT_REPORT_JSON
AUDIT_REPORT_MD = _cfg.AUDIT_REPORT_MD
DATASET_TAG_CLEAN = _cfg.DATASET_TAG_CLEAN
DATASET_TAG_FUTURE_LABEL = _cfg.DATASET_TAG_FUTURE_LABEL
DATASET_TAG_OVERLAP = _cfg.DATASET_TAG_OVERLAP
DATASET_TAG_SCALER = _cfg.DATASET_TAG_SCALER
EMBARGO_BARS = _cfg.EMBARGO_BARS
FEATURE_COLUMNS = _cfg.FEATURE_COLUMNS
LABEL_COLUMN = _cfg.LABEL_COLUMN
REPORT_DIR = _cfg.REPORT_DIR
SMOKE = _cfg.SMOKE
TIMESTAMP_COLUMN = _cfg.TIMESTAMP_COLUMN
TRAP_CLASS_CLEAN = _cfg.TRAP_CLASS_CLEAN
TRAP_CLASS_FUTURE_LABEL = _cfg.TRAP_CLASS_FUTURE_LABEL
TRAP_CLASS_INDEX_OVERLAP = _cfg.TRAP_CLASS_INDEX_OVERLAP
TRAP_CLASS_SCALER_FIT = _cfg.TRAP_CLASS_SCALER_FIT

LeakageFinding = _det.LeakageFinding
SyntheticDataset = _synth.SyntheticDataset
compute_feature_stats = _det.compute_feature_stats
detect_future_shift = _det.detect_future_shift
detect_purge_violations = _purged.detect_purge_violations
detect_scaler_leakage = _det.detect_scaler_leakage
findings_to_dicts = _det.findings_to_dicts
future_label_trap = _synth.future_label_trap
generate_clean_series = _synth.generate_clean_series
overlap_trap = _synth.overlap_trap
scaler_trap = _synth.scaler_trap

__all__ = [
    "AuditResult",
    "aggregate_findings",
    "build_report",
    "main",
    "run_audit",
    "run_audits",
    "score_severity",
    "write_reports",
]

_DATASET_GENERATORS: dict[str, Callable[..., SyntheticDataset]] = {
    DATASET_TAG_CLEAN: generate_clean_series,
    DATASET_TAG_FUTURE_LABEL: future_label_trap,
    DATASET_TAG_SCALER: scaler_trap,
    DATASET_TAG_OVERLAP: overlap_trap,
}

_DETECTORS_RUN = (
    "future_shift",
    "scaler_leakage",
    "index_overlap",
    "purged_validator",
)


@dataclass(frozen=True)
class AuditResult:
    """Single-dataset audit outcome consumed by report builders and pytest."""

    dataset_tag: str
    trap_class: str
    has_leakage_expected: bool
    findings: tuple[LeakageFinding, ...]
    max_severity: float
    mean_severity: float
    score: float
    passed: bool


def _finding_key(finding: LeakageFinding) -> tuple[str, str, str]:
    return (finding.detector, finding.trap_class, finding.message)


def _dedupe_findings(findings: list[LeakageFinding]) -> list[LeakageFinding]:
    best: dict[tuple[str, str, str], LeakageFinding] = {}
    for finding in findings:
        key = _finding_key(finding)
        prior = best.get(key)
        if prior is None or float(finding.severity) > float(prior.severity):
            best[key] = finding
    return list(best.values())


def _resolve_dataset_tags(
    dataset_tags: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if dataset_tags is None:
        return ALL_DATASET_TAGS
    tags = tuple(dataset_tags)
    if not tags:
        raise ValueError("dataset_tags must be non-empty; omit the argument to audit all tags")
    unknown = sorted(set(tags) - set(_DATASET_GENERATORS))
    if unknown:
        known = ", ".join(sorted(_DATASET_GENERATORS))
        raise ValueError(f"unknown dataset_tag(s) {unknown!r}; expected one of: {known}")
    return tags


def _json_safe(value: Any) -> Any:
    """Coerce numpy/pandas scalars to native JSON types."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if value is None or isinstance(value, str):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _json_safe(item())
        except (TypeError, ValueError):
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _json_safe(tolist())
    return str(value)


def score_severity(findings: list[LeakageFinding]) -> dict[str, float]:
    """Aggregate severity metrics for a finding list."""
    if not findings:
        return {"max": 0.0, "mean": 0.0, "score": 0.0}
    severities = [float(f.severity) for f in findings]
    max_severity = max(severities)
    mean_severity = sum(severities) / len(severities)
    score = float(min(1.0, max_severity + 0.05 * max(0, len(findings) - 1)))
    return {
        "max": max_severity,
        "mean": mean_severity,
        "score": score,
    }


def _resolve_generator(dataset_tag: str) -> Callable[..., SyntheticDataset]:
    if dataset_tag not in _DATASET_GENERATORS:
        known = ", ".join(sorted(_DATASET_GENERATORS))
        raise ValueError(f"unknown dataset_tag {dataset_tag!r}; expected one of: {known}")
    return _DATASET_GENERATORS[dataset_tag]


def _split_stats(
    dataset: SyntheticDataset,
    train_idx: list[int] | tuple[int, ...],
    test_idx: list[int] | tuple[int, ...],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    metadata = dataset.metadata
    if metadata.get("features_scaled"):
        return (
            compute_feature_stats(dataset.df, train_idx),
            compute_feature_stats(dataset.df, test_idx),
        )
    return metadata.get("train_stats", {}), metadata.get("test_stats", {})


def _audit_passed(
    trap_class: str,
    findings: list[LeakageFinding],
) -> bool:
    if trap_class == TRAP_CLASS_CLEAN:
        return len(findings) == 0
    detected = {finding.trap_class for finding in findings}
    return trap_class in detected


def run_audit(dataset_tag: str) -> AuditResult:
    """Run all leakage detectors on one synthetic dataset tag."""
    generator = _resolve_generator(dataset_tag)
    dataset = generator()
    metadata = dataset.metadata
    frame = dataset.df

    train_idx = metadata["train_idx"]
    test_idx = metadata["test_idx"]
    trap_class = str(metadata.get("trap_class", TRAP_CLASS_CLEAN))
    has_leakage_expected = bool(metadata.get("has_leakage", trap_class != TRAP_CLASS_CLEAN))

    feature_columns = [col for col in FEATURE_COLUMNS if col in frame.columns]
    features = frame[feature_columns]
    labels = frame[LABEL_COLUMN]
    timestamps = frame[TIMESTAMP_COLUMN]

    train_stats, test_stats = _split_stats(dataset, train_idx, test_idx)

    findings = _dedupe_findings(
        [
            *detect_future_shift(features, labels),
            *detect_scaler_leakage(train_stats, test_stats),
            *detect_purge_violations(
                timestamps,
                train_idx,
                test_idx,
                embargo_bars=EMBARGO_BARS,
            ),
        ]
    )

    severity = score_severity(findings)
    return AuditResult(
        dataset_tag=dataset_tag,
        trap_class=trap_class,
        has_leakage_expected=has_leakage_expected,
        findings=tuple(findings),
        max_severity=severity["max"],
        mean_severity=severity["mean"],
        score=severity["score"],
        passed=_audit_passed(trap_class, findings),
    )


def run_audits(dataset_tags: tuple[str, ...] | list[str] | None = None) -> list[AuditResult]:
    """Run audits for each requested dataset tag (default: all configured tags)."""
    return [run_audit(tag) for tag in _resolve_dataset_tags(dataset_tags)]


def aggregate_findings(results: list[AuditResult]) -> dict[str, Any]:
    """Roll up per-dataset audit results into a summary block."""
    all_findings = [finding for result in results for finding in result.findings]
    severity = score_severity(list(all_findings))
    return {
        "datasets_audited": len(results),
        "total_findings": len(all_findings),
        "max_severity": severity["max"],
        "mean_severity": severity["mean"],
        "score": severity["score"],
        "all_passed": all(result.passed for result in results),
        "trap_classes_detected": sorted({finding.trap_class for finding in all_findings}),
    }


def _audit_result_to_dict(result: AuditResult) -> dict[str, Any]:
    return {
        "dataset_tag": result.dataset_tag,
        "trap_class": result.trap_class,
        "has_leakage_expected": result.has_leakage_expected,
        "finding_count": len(result.findings),
        "findings": findings_to_dicts(list(result.findings)),
        "severity": {
            "max": result.max_severity,
            "mean": result.mean_severity,
            "score": result.score,
        },
        "passed": result.passed,
        "detectors": list(_DETECTORS_RUN),
    }


def build_report(dataset_tags: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
    """Assemble the full leakage audit report payload."""
    tags = _resolve_dataset_tags(dataset_tags)
    results = run_audits(tags)
    return {
        "smoke": SMOKE,
        "dataset_tags": list(tags),
        "audits": [_audit_result_to_dict(result) for result in results],
        "summary": aggregate_findings(results),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Data Leakage Audit Report",
        "",
        "## Summary",
        "",
        f"- Smoke mode: `{report['smoke']}`",
        f"- Dataset tags: `{', '.join(report.get('dataset_tags', []))}`",
        f"- Datasets audited: **{summary['datasets_audited']}**",
        f"- Trap classes detected: **{', '.join(summary.get('trap_classes_detected', [])) or 'none'}**",
        f"- Total findings: **{summary['total_findings']}**",
        f"- Max severity: **{summary['max_severity']:.4f}**",
        f"- Mean severity: **{summary['mean_severity']:.4f}**",
        f"- Aggregate score: **{summary['score']:.4f}**",
        f"- All passed: **{summary['all_passed']}**",
        "",
        "## Per-dataset results",
        "",
        "| Dataset | Trap class | Findings | Max severity | Passed |",
        "|---------|------------|----------|--------------|--------|",
    ]

    for audit in report["audits"]:
        severity = audit["severity"]
        lines.append(
            f"| {audit['dataset_tag']} | {audit['trap_class']} | "
            f"{audit['finding_count']} | {severity['max']:.4f} | {audit['passed']} |"
        )

    lines.extend(["", "## Findings detail", ""])
    for audit in report["audits"]:
        lines.append(f"### {audit['dataset_tag']} (`{audit['trap_class']}`)")
        lines.append("")
        if not audit["findings"]:
            lines.append("_No leakage findings._")
            lines.append("")
            continue
        for finding in audit["findings"]:
            lines.append(
                f"- **{finding['detector']}** ({finding['trap_class']}): "
                f"severity={finding['severity']:.4f} — {finding['message']}"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def write_reports(
    *,
    dataset_tags: tuple[str, ...] | list[str] | None = None,
    report_dir: Path | str | None = None,
    json_path: Path | str | None = None,
    md_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run audits and write ``leakage_audit.json`` and ``leakage_audit.md``."""
    report = build_report(dataset_tags)
    out_dir = Path(report_dir) if report_dir is not None else REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    json_out = Path(json_path) if json_path is not None else out_dir / AUDIT_REPORT_JSON.name
    md_out = Path(md_path) if md_path is not None else out_dir / AUDIT_REPORT_MD.name

    json_out.write_text(
        json.dumps(_json_safe(report), indent=2, sort_keys=False),
        encoding="utf-8",
    )
    md_out.write_text(_render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run leakage audits and write report artifacts."""
    parser = argparse.ArgumentParser(description="Run data leakage audits on synthetic datasets.")
    parser.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=None,
        help=f"Dataset tag to audit (repeatable). Default: all ({', '.join(ALL_DATASET_TAGS)})",
    )
    parser.add_argument(
        "--report-dir",
        default=None,
        help=f"Directory for leakage_audit.json and leakage_audit.md (default: {REPORT_DIR})",
    )
    args = parser.parse_args(argv)
    write_reports(dataset_tags=args.tags, report_dir=args.report_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
