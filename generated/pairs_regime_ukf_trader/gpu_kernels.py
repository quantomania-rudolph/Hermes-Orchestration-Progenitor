"""Intel Arc / XPU batched linear algebra for pair discovery and regime features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from compute_device import get_torch_device, resolve_compute_device


def pearson_corr_matrix_gpu(frame: pd.DataFrame) -> pd.DataFrame | None:
    """Pearson correlation on Intel XPU when available; else None (caller uses CPU)."""
    if resolve_compute_device().kind != "xpu":
        return None

    import torch

    data = frame.to_numpy(dtype=np.float64).copy()
    if data.size == 0 or data.shape[0] < 2:
        return None

    device = get_torch_device()
    t = torch.as_tensor(data, device=device, dtype=torch.float64)
    t = t - t.mean(dim=0, keepdim=True)
    n = t.shape[0]
    std = t.std(dim=0, unbiased=(n > 1), keepdim=True)
    std = torch.where(std < 1e-12, torch.ones_like(std), std)
    t = t / std
    corr = (t.T @ t) / max(n - 1, 1)
    corr = torch.clamp(corr, -1.0, 1.0)
    out = corr.detach().to("cpu").numpy()
    return pd.DataFrame(out, index=frame.columns, columns=frame.columns)


def batch_cumsum_levels_gpu(returns: pd.DataFrame) -> pd.DataFrame | None:
    """Cumulative sum of return columns on XPU for level-based pair screens."""
    if resolve_compute_device().kind != "xpu":
        return None

    import torch

    device = get_torch_device()
    t = torch.as_tensor(returns.to_numpy(dtype=np.float64).copy(), device=device)
    levels = torch.cumsum(t, dim=0)
    arr = levels.detach().to("cpu").numpy()
    return pd.DataFrame(arr, index=returns.index, columns=returns.columns)
