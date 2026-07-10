"""Smoke tests for synthetic leakage trap datasets."""

from synthetic_data import generate_clean_series, future_label_trap


def test_clean_series_shape():
    ds = generate_clean_series()
    assert len(ds.df) > 0
    assert "label" in ds.df.columns


def test_future_trap_tag():
    ds = future_label_trap()
    assert ds.metadata.get("trap_class") == "future_label"
    assert len(ds.df) > 0
