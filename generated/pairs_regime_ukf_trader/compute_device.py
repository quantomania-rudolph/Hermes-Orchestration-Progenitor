"""Compute device resolution for Intel Core Ultra / Arc XPU acceleration.

Priority: Intel Arc XPU (PyTorch ``torch.xpu``) → CPU fallback.
Controlled via ``HERMES_USE_INTEL_XPU`` (1|0|auto) and ``HERMES_FORCE_CPU``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class ComputeDevice:
    kind: str  # "xpu" | "cpu"
    name: str
    index: int = 0

    @property
    def torch_device(self) -> str:
        if self.kind == "xpu":
            return f"xpu:{self.index}"
        return "cpu"


def _xpu_available() -> tuple[bool, str]:
    try:
        import torch

        if not hasattr(torch, "xpu") or not torch.xpu.is_available():
            return False, ""
        count = int(torch.xpu.device_count())
        if count < 1:
            return False, ""
        name = str(torch.xpu.get_device_name(0))
        return True, name
    except Exception:
        return False, ""


def resolve_compute_device() -> ComputeDevice:
    """Pick Intel Arc XPU when enabled and available, else CPU."""
    if os.getenv("HERMES_FORCE_CPU", "0") == "1":
        return ComputeDevice(kind="cpu", name="cpu")

    mode = os.getenv("HERMES_USE_INTEL_XPU", "auto").strip().lower()
    if mode in {"0", "false", "no", "off", "cpu"}:
        return ComputeDevice(kind="cpu", name="cpu")

    ok, name = _xpu_available()
    if ok and mode in {"1", "true", "yes", "on", "auto"}:
        return ComputeDevice(kind="xpu", name=name or "Intel XPU", index=0)
    return ComputeDevice(kind="cpu", name="cpu")


@lru_cache(maxsize=1)
def get_torch_device() -> Any:
    """Return ``torch.device`` for the resolved backend."""
    import torch

    dev = resolve_compute_device()
    return torch.device(dev.torch_device)


def device_report() -> dict[str, str | bool]:
    """JSON-serializable probe for reports and smoke tests."""
    dev = resolve_compute_device()
    ok, hw_name = _xpu_available()
    return {
        "kind": dev.kind,
        "name": dev.name,
        "torch_device": dev.torch_device,
        "xpu_hardware_present": ok,
        "xpu_hardware_name": hw_name,
        "hermes_use_intel_xpu": os.getenv("HERMES_USE_INTEL_XPU", "auto"),
    }
