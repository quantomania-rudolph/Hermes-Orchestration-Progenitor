"""Smoke import test — ensures package loads under DAEDALUS R22."""

def test_smoke_import():
    import config  # noqa: F401
    assert True
