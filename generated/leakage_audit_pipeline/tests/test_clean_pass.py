"""Leakage-free synthetic data must pass all detectors and audit scoring."""

from audit_runner import run_audit
from config import (
    DATASET_TAG_CLEAN,
    EMBARGO_BARS,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    TIMESTAMP_COLUMN,
    TRAP_CLASS_CLEAN,
)
from detectors import (
    detect_future_shift,
    detect_index_overlap,
    detect_scaler_leakage,
)
from purged_validator import assert_purge_valid, detect_purge_violations
from synthetic_data import generate_clean_series


def test_clean_series_passes_detectors():
    dataset = generate_clean_series()
    metadata = dataset.metadata
    frame = dataset.df

    features = frame[[col for col in FEATURE_COLUMNS if col in frame.columns]]
    labels = frame[LABEL_COLUMN]
    train_idx = metadata["train_idx"]
    test_idx = metadata["test_idx"]

    assert detect_future_shift(features, labels) == []
    assert detect_scaler_leakage(metadata["train_stats"], metadata["test_stats"]) == []
    assert detect_index_overlap(train_idx, test_idx) == []
    assert detect_purge_violations(
        frame[TIMESTAMP_COLUMN],
        train_idx,
        test_idx,
        embargo_bars=EMBARGO_BARS,
    ) == []


def test_clean_series_passes_purge_gate():
    dataset = generate_clean_series()
    metadata = dataset.metadata

    assert_purge_valid(
        dataset.df[TIMESTAMP_COLUMN],
        metadata["train_idx"],
        metadata["test_idx"],
        embargo_bars=EMBARGO_BARS,
    )


def test_clean_audit_passes():
    result = run_audit(DATASET_TAG_CLEAN)

    assert result.trap_class == TRAP_CLASS_CLEAN
    assert result.has_leakage_expected is False
    assert result.findings == ()
    assert result.passed is True
    assert result.max_severity == 0.0
    assert result.score == 0.0
