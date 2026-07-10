"""Intel Arc / XPU device probe tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[1]
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

os.environ.setdefault("HERMES_RESEARCH_SMOKE", "1")


def test_device_report_structure():
    from compute_device import device_report

    rep = device_report()
    assert "kind" in rep
    assert rep["kind"] in {"cpu", "xpu"}
    assert "torch_device" in rep


def test_intel_xpu_when_enabled():
    os.environ["HERMES_USE_INTEL_XPU"] = "1"
    os.environ.pop("HERMES_FORCE_CPU", None)

    from compute_device import resolve_compute_device, _xpu_available

    ok, _ = _xpu_available()
    dev = resolve_compute_device()
    if ok:
        assert dev.kind == "xpu"
        assert dev.torch_device.startswith("xpu")
    else:
        assert dev.kind == "cpu"
