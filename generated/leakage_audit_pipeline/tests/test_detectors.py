"""Each planted leakage trap must produce non-empty detector findings."""

from config import (
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    TRAP_CLASS_FUTURE_LABEL,
    TRAP_CLASS_INDEX_OVERLAP,
    TRAP_CLASS_SCALER_FIT,
)
from detectors import (
    compute_feature_stats,
    detect_future_shift,
    detect_index_overlap,
    detect_scaler_leakage,
)
from synthetic_data import future_label_trap, overlap_trap, scaler_trap


def _trap_classes(findings):
    return {finding.trap_class for finding in findings}


def _scaled_split_stats(dataset, train_idx, test_idx):
    """Match audit_runner._split_stats when features_scaled=True."""
    if dataset.metadata.get("features_scaled"):
        return (
            compute_feature_stats(dataset.df, train_idx),
            compute_feature_stats(dataset.df, test_idx),
        )
    return dataset.metadata["train_stats"], dataset.metadata["test_stats"]


def test_future_label_trap_detected():
    dataset = future_label_trap()
    features = dataset.df[[col for col in FEATURE_COLUMNS if col in dataset.df.columns]]
    labels = dataset.df[LABEL_COLUMN]

    findings = detect_future_shift(features, labels)

    assert findings, "future label trap must trigger detect_future_shift"
    assert TRAP_CLASS_FUTURE_LABEL in _trap_classes(findings)
    assert any(finding.detector == "future_shift" for finding in findings)
    assert all(finding.severity > 0.0 for finding in findings)


def test_scaler_trap_detected():
    dataset = scaler_trap()
    train_idx = dataset.metadata["train_idx"]
    test_idx = dataset.metadata["test_idx"]

    # Negative control: raw split stats must not false-trigger before global scaling.
    assert detect_scaler_leakage(
        dataset.metadata["train_stats"],
        dataset.metadata["test_stats"],
    ) == []

    train_stats, test_stats = _scaled_split_stats(dataset, train_idx, test_idx)
    findings = detect_scaler_leakage(train_stats, test_stats)

    assert findings, "scaler trap must trigger detect_scaler_leakage"
    assert TRAP_CLASS_SCALER_FIT in _trap_classes(findings)
    assert any(finding.detector == "scaler_leakage" for finding in findings)
    assert all(finding.severity > 0.0 for finding in findings)


def test_overlap_trap_detected():
    dataset = overlap_trap()
    train_idx = dataset.metadata["train_idx"]
    test_idx = dataset.metadata["test_idx"]

    findings = detect_index_overlap(train_idx, test_idx)

    assert findings, "overlap trap must trigger detect_index_overlap"
    assert TRAP_CLASS_INDEX_OVERLAP in _trap_classes(findings)
    assert any(finding.detector == "index_overlap" for finding in findings)
    assert all(finding.severity > 0.0 for finding in findings)
    overlap_finding = next(
        finding for finding in findings if finding.detector == "index_overlap"
    )
    assert overlap_finding.details.get("overlap_count", 0) > 0
