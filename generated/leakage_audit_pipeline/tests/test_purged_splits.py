"""Purged train/test split validation with embargo and overlap detection."""

import numpy as np
import pytest

from config import EMBARGO_BARS, TIMESTAMP_COLUMN, TRAP_CLASS_INDEX_OVERLAP
from purged_validator import assert_purge_valid, detect_purge_violations
from synthetic_data import generate_clean_series, overlap_trap


def test_clean_split_is_purge_valid():
    dataset = generate_clean_series()
    metadata = dataset.metadata

    findings = detect_purge_violations(
        dataset.df[TIMESTAMP_COLUMN],
        metadata["train_idx"],
        metadata["test_idx"],
        embargo_bars=EMBARGO_BARS,
    )

    assert findings == []
    assert_purge_valid(
        dataset.df[TIMESTAMP_COLUMN],
        metadata["train_idx"],
        metadata["test_idx"],
        embargo_bars=EMBARGO_BARS,
    )


def test_overlap_trap_fails_purge_validation():
    dataset = overlap_trap()
    metadata = dataset.metadata

    findings = detect_purge_violations(
        dataset.df[TIMESTAMP_COLUMN],
        metadata["train_idx"],
        metadata["test_idx"],
        embargo_bars=EMBARGO_BARS,
    )

    assert findings, "overlap trap must violate purged split rules"
    assert TRAP_CLASS_INDEX_OVERLAP in {finding.trap_class for finding in findings}
    overlap_findings = [
        finding for finding in findings if finding.detector == "index_overlap"
    ]
    assert overlap_findings, "overlap trap must surface index_overlap findings"
    assert overlap_findings[0].details.get("overlap_count", 0) > 0
    assert any(finding.detector == "purged_validator" for finding in findings)

    with pytest.raises(AssertionError):
        assert_purge_valid(
            dataset.df[TIMESTAMP_COLUMN],
            metadata["train_idx"],
            metadata["test_idx"],
            embargo_bars=EMBARGO_BARS,
        )


def test_insufficient_embargo_is_flagged():
    assert EMBARGO_BARS >= 1, "test requires a positive embargo to shrink"

    dataset = generate_clean_series()
    metadata = dataset.metadata
    train_idx = np.asarray(metadata["train_idx"], dtype=np.int64)
    test_idx = np.asarray(metadata["test_idx"], dtype=np.int64)

    # Shrink embargo by moving test window one bar closer to train.
    test_start = int(test_idx.min())
    shrunk_test_idx = np.arange(test_start - 1, test_start + len(test_idx), dtype=np.int64)

    findings = detect_purge_violations(
        dataset.df[TIMESTAMP_COLUMN],
        train_idx,
        shrunk_test_idx,
        embargo_bars=EMBARGO_BARS,
    )

    assert findings, "insufficient embargo gap must be reported"
    embargo_findings = [
        finding
        for finding in findings
        if finding.detector == "purged_validator"
        and "embargo gap" in finding.message.lower()
    ]
    assert embargo_findings, "purged_validator must report the shrunk embargo gap"
    assert embargo_findings[0].details.get("purge_gap_bars") == EMBARGO_BARS - 1
