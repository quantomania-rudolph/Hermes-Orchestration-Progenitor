"""Four-state anti-flicker Markov regime model on market features."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

import config as cfg
import numpy as np
import pandas as pd

MIN_REGIME_BARS = int(getattr(cfg, "MIN_REGIME_BARS", 5))
POSTERIOR_EMA_ALPHA = float(getattr(cfg, "REGIME_POSTERIOR_EMA_ALPHA", 0.15))
SWITCH_COMMIT_PROB = float(getattr(cfg, "REGIME_SWITCH_COMMIT_PROB", 0.55))

FEATURE_COLS: tuple[str, ...] = (
    "market_return_5d",
    "realized_vol_20d",
    "corr_median_change_20d",
    "drawdown_5d",
    "eigen_concentration",
)

REGIME_LABELS: tuple[str, ...] = ("BULL", "BEAR", "VOLATILE", "CRASH")
N_STATES = len(REGIME_LABELS)


class RegimeState(IntEnum):
    BULL = 0
    BEAR = 1
    VOLATILE = 2
    CRASH = 3


def _built_in_transition() -> np.ndarray:
    """Default transition matrix penalizing rapid oscillation (heavy diagonal)."""
    return np.array(
        [
            [0.92, 0.03, 0.03, 0.02],
            [0.03, 0.90, 0.05, 0.02],
            [0.03, 0.05, 0.87, 0.05],
            [0.02, 0.03, 0.05, 0.90],
        ],
        dtype=float,
    )


def _built_in_emission_means() -> np.ndarray:
    """Gaussian emission means aligned with ARCHITECTURE detection rules."""
    return np.array(
        [
            [0.015, 0.12, 0.01, -0.005, 0.35],  # BULL
            [-0.010, 0.18, 0.06, -0.020, 0.42],  # BEAR
            [0.000, 0.28, 0.10, -0.030, 0.62],  # VOLATILE
            [-0.070, 0.35, 0.28, -0.080, 0.75],  # CRASH
        ],
        dtype=float,
    )


def _built_in_emission_stds() -> np.ndarray:
    return np.array(
        [
            [0.008, 0.03, 0.02, 0.008, 0.05],
            [0.010, 0.04, 0.03, 0.012, 0.06],
            [0.012, 0.05, 0.04, 0.015, 0.07],
            [0.015, 0.06, 0.05, 0.020, 0.08],
        ],
        dtype=float,
    )


DEFAULT_TRANSITION = np.asarray(
    getattr(cfg, "REGIME_MARKOV_TRANSITION", _built_in_transition()),
    dtype=float,
)
DEFAULT_EMISSION_MEANS = np.asarray(
    getattr(cfg, "REGIME_MARKOV_EMISSION_MEANS", _built_in_emission_means()),
    dtype=float,
)
DEFAULT_EMISSION_STDS = np.asarray(
    getattr(cfg, "REGIME_MARKOV_EMISSION_STDS", _built_in_emission_stds()),
    dtype=float,
)
DEFAULT_START_PROB = np.asarray(
    getattr(cfg, "REGIME_MARKOV_START_PROB", [0.40, 0.25, 0.25, 0.10]),
    dtype=float,
)


def _persist_regime_defaults_to_config() -> None:
    """Register default Markov/HMM parameters on the package config module."""
    defaults: dict[str, Any] = {
        "MIN_REGIME_BARS": 5,
        "REGIME_POSTERIOR_EMA_ALPHA": 0.15,
        "REGIME_SWITCH_COMMIT_PROB": 0.55,
        "REGIME_MARKOV_TRANSITION": _built_in_transition(),
        "REGIME_MARKOV_EMISSION_MEANS": _built_in_emission_means(),
        "REGIME_MARKOV_EMISSION_STDS": _built_in_emission_stds(),
        "REGIME_MARKOV_START_PROB": np.array([0.40, 0.25, 0.25, 0.10]),
    }
    for name, value in defaults.items():
        if not hasattr(cfg, name):
            setattr(cfg, name, value)


_persist_regime_defaults_to_config()


@dataclass
class RegimeModelParams:
    transition: np.ndarray
    means: np.ndarray
    stds: np.ndarray
    start_prob: np.ndarray
    feature_means: np.ndarray | None = None
    feature_stds: np.ndarray | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "transition": self.transition.tolist(),
            "means": self.means.tolist(),
            "stds": self.stds.tolist(),
            "start_prob": self.start_prob.tolist(),
        }


_fitted_model: RegimeModelParams | None = None


def _validate_features(features_df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in FEATURE_COLS if c not in features_df.columns]
    if missing:
        raise ValueError(f"features_df missing columns: {missing}")
    out = features_df[list(FEATURE_COLS)].astype(float).copy()
    if out.empty:
        raise ValueError("features_df is empty")
    return out


def _standardize(obs: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    sigma_safe = np.where(sigma < 1e-8, 1.0, sigma)
    return (obs - mu) / sigma_safe


def _log_gaussian_diag(obs: np.ndarray, means: np.ndarray, stds: np.ndarray) -> np.ndarray:
    """Log emission probability for each state; obs (T,D), returns (T,K)."""
    n_features = obs.shape[1]
    log_det = 2.0 * np.sum(np.log(stds + 1e-12), axis=1)
    diff = obs[:, None, :] - means[None, :, :]
    inv_var = 1.0 / (stds[None, :, :] ** 2 + 1e-12)
    quad = np.sum(diff * diff * inv_var, axis=2)
    log_norm = -0.5 * (n_features * np.log(2.0 * np.pi) + log_det[None, :] + quad)
    return log_norm


def _log_forward_filter(
    log_emissions: np.ndarray,
    transition: np.ndarray,
    start_prob: np.ndarray,
) -> np.ndarray:
    """Forward filtering in log domain; returns posteriors (T, K)."""
    t_steps, n_states = log_emissions.shape
    log_trans = np.log(transition + 1e-300)
    log_start = np.log(start_prob + 1e-300)

    log_alpha = np.zeros((t_steps, n_states), dtype=float)
    log_alpha[0] = log_start + log_emissions[0]

    for t in range(1, t_steps):
        prev = log_alpha[t - 1][:, None] + log_trans
        log_alpha[t] = log_emissions[t] + np.logaddexp.reduce(prev, axis=0)

    posteriors = np.zeros_like(log_alpha)
    for t in range(t_steps):
        row = log_alpha[t]
        row = row - np.logaddexp.reduce(row)
        posteriors[t] = np.exp(row)
    return posteriors


def _forward_filter_torch(
    obs: np.ndarray,
    means: np.ndarray,
    stds: np.ndarray,
    transition: np.ndarray,
    start_prob: np.ndarray,
) -> np.ndarray | None:
    """Optional XPU/CPU torch batch for emission + forward pass."""
    try:
        import torch
        from compute_device import get_torch_device

        device = get_torch_device()
        obs_t = torch.as_tensor(obs, dtype=torch.float64, device=device)
        means_t = torch.as_tensor(means, dtype=torch.float64, device=device)
        stds_t = torch.as_tensor(stds, dtype=torch.float64, device=device)
        trans_t = torch.as_tensor(transition, dtype=torch.float64, device=device)
        start_t = torch.as_tensor(start_prob, dtype=torch.float64, device=device)

        diff = obs_t.unsqueeze(1) - means_t.unsqueeze(0)
        inv_var = 1.0 / (stds_t.unsqueeze(0) ** 2 + 1e-12)
        quad = (diff * diff * inv_var).sum(dim=2)
        log_det = 2.0 * torch.log(stds_t + 1e-12).sum(dim=1)
        n_features = obs_t.shape[1]
        log_norm = -0.5 * (n_features * np.log(2.0 * np.pi) + log_det.unsqueeze(0) + quad)
        log_emissions = log_norm

        t_steps, n_states = log_emissions.shape
        log_trans = torch.log(trans_t + 1e-300)
        log_start = torch.log(start_t + 1e-300)

        log_alpha = torch.zeros((t_steps, n_states), dtype=torch.float64, device=device)
        log_alpha[0] = log_start + log_emissions[0]
        for t in range(1, t_steps):
            prev = log_alpha[t - 1].unsqueeze(1) + log_trans
            log_alpha[t] = log_emissions[t] + torch.logsumexp(prev, dim=0)

        posteriors = torch.zeros_like(log_alpha)
        for t in range(t_steps):
            row = log_alpha[t]
            posteriors[t] = torch.softmax(row, dim=0)
        return posteriors.detach().cpu().numpy()
    except Exception:
        return None


def _online_ema_antiflicker(
    posteriors: np.ndarray,
    *,
    alpha: float = POSTERIOR_EMA_ALPHA,
    min_dwell: int = MIN_REGIME_BARS,
    commit_prob: float = SWITCH_COMMIT_PROB,
) -> tuple[np.ndarray, np.ndarray]:
    """Joint EMA + dwell/commit gate; reset EMA anchor on commit to block bounce-back."""
    n_steps, n_states = posteriors.shape
    smoothed = np.zeros_like(posteriors)
    labels = np.zeros(n_steps, dtype=int)

    smoothed[0] = posteriors[0] / max(posteriors[0].sum(), 1e-12)
    current = int(np.argmax(smoothed[0]))
    labels[0] = current
    dwell = 1

    for t in range(1, n_steps):
        ema = alpha * posteriors[t] + (1.0 - alpha) * smoothed[t - 1]
        ema = ema / max(ema.sum(), 1e-12)

        candidate = int(np.argmax(ema))
        candidate_prob = float(ema[candidate])
        if (
            candidate != current
            and dwell >= min_dwell
            and candidate_prob > commit_prob
        ):
            current = candidate
            dwell = 1
            anchor = np.zeros(n_states, dtype=float)
            anchor[current] = 1.0
            ema = alpha * posteriors[t] + (1.0 - alpha) * anchor
            ema = ema / max(ema.sum(), 1e-12)
        else:
            dwell += 1

        smoothed[t] = ema
        labels[t] = current

    return labels, smoothed


def build_regime_features(
    market_returns: pd.Series,
    *,
    corr_median: pd.Series | None = None,
    eigen_concentration: pd.Series | None = None,
) -> pd.DataFrame:
    """Build per-bar regime feature vector from market return series."""
    ret = market_returns.astype(float)
    idx = ret.index

    market_return_5d = ret.rolling(5, min_periods=1).sum()
    realized_vol_20d = ret.rolling(20, min_periods=5).std()

    if corr_median is not None:
        corr_aligned = corr_median.reindex(idx).astype(float)
        corr_median_change_20d = corr_aligned.diff(20).abs()
    else:
        corr_median_change_20d = pd.Series(0.02, index=idx, dtype=float)

    if eigen_concentration is not None:
        eigen_aligned = eigen_concentration.reindex(idx).astype(float)
    else:
        eigen_aligned = pd.Series(0.40, index=idx, dtype=float)

    cum = (1.0 + ret.fillna(0.0)).cumprod()
    rolling_peak = cum.rolling(5, min_periods=1).max()
    drawdown_5d = cum / rolling_peak - 1.0

    return pd.DataFrame(
        {
            "market_return_5d": market_return_5d,
            "realized_vol_20d": realized_vol_20d,
            "corr_median_change_20d": corr_median_change_20d,
            "drawdown_5d": drawdown_5d,
            "eigen_concentration": eigen_aligned,
        },
        index=idx,
    )


def _estimate_emissions(obs: np.ndarray, transition: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Lightweight EM refinement for diagonal Gaussian emissions from defaults."""
    n_samples = obs.shape[0]
    means = DEFAULT_EMISSION_MEANS.copy()
    stds = DEFAULT_EMISSION_STDS.copy()

    if n_samples < N_STATES * 5:
        return means, stds

    for _ in range(8):
        log_emit = _log_gaussian_diag(obs, means, stds)
        log_start = np.log(DEFAULT_START_PROB + 1e-300)
        log_trans = np.log(transition + 1e-300)

        log_alpha = np.zeros((n_samples, N_STATES))
        log_alpha[0] = log_start + log_emit[0]
        for t in range(1, n_samples):
            prev = log_alpha[t - 1][:, None] + log_trans
            log_alpha[t] = log_emit[t] + np.logaddexp.reduce(prev, axis=0)

        log_beta = np.zeros((n_samples, N_STATES))
        for t in range(n_samples - 2, -1, -1):
            nxt = log_emit[t + 1] + log_beta[t + 1]
            log_beta[t] = np.logaddexp.reduce(log_trans + nxt[None, :], axis=1)

        log_gamma = log_alpha + log_beta
        log_gamma -= np.logaddexp.reduce(log_gamma, axis=1)[:, None]
        resp = np.exp(log_gamma)

        for k in range(N_STATES):
            weight = resp[:, k]
            w_sum = weight.sum()
            if w_sum < 1e-6:
                continue
            est_mean = (weight[:, None] * obs).sum(axis=0) / w_sum
            var = (weight[:, None] * (obs - est_mean) ** 2).sum(axis=0) / w_sum
            est_std = np.sqrt(np.maximum(var, 1e-6))
            means[k] = 0.90 * DEFAULT_EMISSION_MEANS[k] + 0.10 * est_mean
            stds[k] = np.maximum(
                0.85 * DEFAULT_EMISSION_STDS[k] + 0.15 * est_std,
                DEFAULT_EMISSION_STDS[k] * 0.5,
            )

    return means, stds


def fit_regime_model(features_df: pd.DataFrame) -> RegimeModelParams:
    """Fit emission parameters in raw feature space; persist module-global model."""
    global _fitted_model

    frame = _validate_features(features_df)
    obs = frame.to_numpy(dtype=float)
    obs = np.nan_to_num(obs, nan=0.0, posinf=0.0, neginf=0.0)

    transition = DEFAULT_TRANSITION.copy()
    means, stds = _estimate_emissions(obs, transition)

    params = RegimeModelParams(
        transition=transition,
        means=means,
        stds=stds,
        start_prob=DEFAULT_START_PROB.copy(),
    )
    _fitted_model = params
    cfg.REGIME_MARKOV_EMISSION_MEANS = means
    cfg.REGIME_MARKOV_EMISSION_STDS = stds
    cfg.REGIME_MARKOV_TRANSITION = transition
    return params


def _resolve_model(model: RegimeModelParams | None) -> RegimeModelParams:
    if model is not None:
        return model
    if _fitted_model is not None:
        return _fitted_model
    return RegimeModelParams(
        transition=DEFAULT_TRANSITION.copy(),
        means=DEFAULT_EMISSION_MEANS.copy(),
        stds=DEFAULT_EMISSION_STDS.copy(),
        start_prob=DEFAULT_START_PROB.copy(),
    )


def filter_regime(
    features_df: pd.DataFrame,
    *,
    model: RegimeModelParams | None = None,
) -> pd.DataFrame:
    """Filter regime labels with anti-flicker posterior smoothing."""
    frame = _validate_features(features_df)
    params = _resolve_model(model)

    obs = frame.to_numpy(dtype=float)
    obs = np.nan_to_num(obs, nan=0.0, posinf=0.0, neginf=0.0)
    if params.feature_means is not None and params.feature_stds is not None:
        obs = _standardize(obs, params.feature_means, params.feature_stds)

    posteriors = _forward_filter_torch(
        obs, params.means, params.stds, params.transition, params.start_prob
    )
    if posteriors is None:
        log_emit = _log_gaussian_diag(obs, params.means, params.stds)
        posteriors = _log_forward_filter(log_emit, params.transition, params.start_prob)

    state_idx, smoothed = _online_ema_antiflicker(
        posteriors,
        alpha=POSTERIOR_EMA_ALPHA,
        min_dwell=MIN_REGIME_BARS,
        commit_prob=SWITCH_COMMIT_PROB,
    )

    regime_label = pd.Series(
        [REGIME_LABELS[i] for i in state_idx],
        index=frame.index,
        name="regime_label",
    )
    prob_cols = {f"regime_prob_{label}": smoothed[:, k] for k, label in enumerate(REGIME_LABELS)}
    regime_probs = pd.DataFrame(prob_cols, index=frame.index)
    regime_confidence = pd.Series(
        smoothed[np.arange(len(smoothed)), state_idx],
        index=frame.index,
        name="regime_confidence",
    )

    return pd.concat([regime_label, regime_probs, regime_confidence], axis=1)


def regime_state_from_label(label: str) -> RegimeState:
    try:
        return RegimeState[label.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown regime label: {label}") from exc
