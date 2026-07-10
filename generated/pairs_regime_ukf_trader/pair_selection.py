"""Pair discovery via correlation, cointegration, and copula tail dependence."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import config as cfg
import numpy as np
import pandas as pd
from scipy import stats

ROLLING_WINDOW = getattr(cfg, "PAIR_ROLLING_WINDOW", 60)
MIN_OVERLAP_BARS = getattr(cfg, "PAIR_MIN_OVERLAP_BARS", 100)
MIN_ABS_CORR = getattr(cfg, "PAIR_MIN_ABS_CORR", 0.65)
MAX_COINT_P = getattr(cfg, "PAIR_MAX_COINT_P", 0.05)
SCORE_W_CORR = getattr(cfg, "PAIR_SCORE_W_CORR", 0.4)
SCORE_W_COINT = getattr(cfg, "PAIR_SCORE_W_COINT", 0.35)
SCORE_W_TAIL = getattr(cfg, "PAIR_SCORE_W_TAIL", 0.25)
MAX_PAIRS = getattr(cfg, "MAX_PAIRS", 20)
TAIL_QUANTILE = getattr(cfg, "PAIR_TAIL_QUANTILE", 0.95)


@dataclass(frozen=True)
class PairCandidate:
    symbol_a: str
    symbol_b: str
    corr: float
    coint_p: float
    tail_dep: float
    score: float


def rolling_pearson_matrix(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    """Pearson correlation matrix over the trailing *window* rows."""
    if returns.empty:
        raise ValueError("returns frame is empty")
    win = min(max(int(window), 2), len(returns))
    tail = returns.iloc[-win:]
    try:
        from gpu_kernels import pearson_corr_matrix_gpu

        gpu_corr = pearson_corr_matrix_gpu(tail)
        if gpu_corr is not None:
            return gpu_corr
    except Exception:
        pass
    return tail.corr(method="pearson")


def rolling_spearman_matrix(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    """Spearman correlation matrix over the trailing *window* rows."""
    if returns.empty:
        raise ValueError("returns frame is empty")
    win = min(max(int(window), 2), len(returns))
    tail = returns.iloc[-win:]
    return tail.corr(method="spearman")


def engle_granger_cointegration(
    y: np.ndarray | pd.Series,
    x: np.ndarray | pd.Series,
) -> tuple[float, float]:
    """Engle-Granger two-step cointegration test returning (pvalue, beta)."""
    y_arr = np.asarray(y, dtype=float).ravel()
    x_arr = np.asarray(x, dtype=float).ravel()
    mask = np.isfinite(y_arr) & np.isfinite(x_arr)
    y_arr = y_arr[mask]
    x_arr = x_arr[mask]
    if len(y_arr) < 20:
        return 1.0, float("nan")

    design = np.column_stack([np.ones(len(x_arr)), x_arr])
    coef, _, _, _ = np.linalg.lstsq(design, y_arr, rcond=None)
    beta = float(coef[1])
    residuals = y_arr - design @ coef

    try:
        from statsmodels.tsa.stattools import coint

        pvalue = float(coint(y_arr, x_arr, trend="c")[1])
        return pvalue, beta
    except Exception:
        pass

    try:
        from statsmodels.tsa.stattools import adfuller

        pvalue = float(adfuller(residuals, maxlag=0, regression="c", autolag=None)[1])
        return pvalue, beta
    except Exception:
        pass

    return float(_adf_pvalue(residuals)), beta


def gaussian_copula_tail_dependence(
    u: np.ndarray | pd.Series,
    v: np.ndarray | pd.Series,
    *,
    q: float | None = None,
) -> float:
    """Empirical upper-tail dependence on Gaussian copula pseudo-observations."""
    u_arr = np.asarray(u, dtype=float).ravel()
    v_arr = np.asarray(v, dtype=float).ravel()
    mask = np.isfinite(u_arr) & np.isfinite(v_arr)
    u_arr = u_arr[mask]
    v_arr = v_arr[mask]
    if len(u_arr) < 10:
        return 0.0

    threshold = q if q is not None else TAIL_QUANTILE
    threshold = float(np.clip(threshold, 0.5, 0.999))
    upper = (u_arr >= threshold) & (v_arr >= threshold)
    n_exceed = int(np.sum(u_arr >= threshold))
    if n_exceed == 0:
        return 0.0
    return float(np.sum(upper) / n_exceed)


def clayton_copula_theta(
    u: np.ndarray | pd.Series,
    v: np.ndarray | pd.Series,
) -> float:
    """Clayton copula shape parameter estimated via Kendall's tau."""
    u_arr = np.asarray(u, dtype=float).ravel()
    v_arr = np.asarray(v, dtype=float).ravel()
    mask = np.isfinite(u_arr) & np.isfinite(v_arr)
    u_arr = u_arr[mask]
    v_arr = v_arr[mask]
    if len(u_arr) < 10:
        return 0.0

    tau, _ = stats.kendalltau(u_arr, v_arr)
    if not np.isfinite(tau) or tau <= 0.0:
        return 0.0
    return float(max(2.0 * tau / (1.0 - tau), 0.0))


def rank_pairs(
    universe_returns: pd.DataFrame,
    *,
    window: int | None = None,
    max_pairs: int | None = None,
) -> list[PairCandidate]:
    """Rank cointegrated pair candidates by composite correlation/coint/tail score."""
    if universe_returns.empty or len(universe_returns) < MIN_OVERLAP_BARS:
        return []

    win = window if window is not None else ROLLING_WINDOW
    symbols = list(universe_returns.columns)
    cap = max_pairs if max_pairs is not None else MAX_PAIRS

    candidates: list[PairCandidate] = []
    for sym_a, sym_b in combinations(symbols, 2):
        pair = universe_returns[[sym_a, sym_b]].dropna()
        if len(pair) < MIN_OVERLAP_BARS:
            continue

        tail = pair.iloc[-min(max(int(win), 2), len(pair)) :]
        levels = _cumsum_levels(tail)
        corr_mat = rolling_pearson_matrix(levels, len(levels))
        corr = float(corr_mat.loc[sym_a, sym_b])
        if not np.isfinite(corr) or abs(corr) <= MIN_ABS_CORR:
            continue

        y_levels = pair[sym_a].cumsum().to_numpy()
        x_levels = pair[sym_b].cumsum().to_numpy()
        coint_p, _beta = engle_granger_cointegration(y_levels, x_levels)
        if not np.isfinite(coint_p) or coint_p >= MAX_COINT_P:
            continue

        u, v = _pseudo_observations(
            pair[sym_a].to_numpy(),
            pair[sym_b].to_numpy(),
        )
        gauss_tail = gaussian_copula_tail_dependence(u, v)
        clayton_theta = clayton_copula_theta(u, v)
        clayton_tail = 2.0 ** (-1.0 / clayton_theta) if clayton_theta > 0.0 else 0.0
        tail_dep = 0.5 * gauss_tail + 0.5 * clayton_tail

        score = (
            SCORE_W_CORR * abs(corr)
            + SCORE_W_COINT * (1.0 - coint_p)
            + SCORE_W_TAIL * tail_dep
        )
        candidates.append(
            PairCandidate(
                symbol_a=sym_a,
                symbol_b=sym_b,
                corr=corr,
                coint_p=coint_p,
                tail_dep=tail_dep,
                score=score,
            )
        )

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[: max(cap, 0)]


def _cumsum_levels(returns: pd.DataFrame) -> pd.DataFrame:
    try:
        from gpu_kernels import batch_cumsum_levels_gpu

        levels_gpu = batch_cumsum_levels_gpu(returns)
        if levels_gpu is not None:
            return levels_gpu
    except Exception:
        pass
    return returns.cumsum()


def _pseudo_observations(
    a: np.ndarray,
    b: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(a)
    rank_a = pd.Series(a).rank(method="average").to_numpy()
    rank_b = pd.Series(b).rank(method="average").to_numpy()
    denom = n + 1
    return rank_a / denom, rank_b / denom


def _adf_pvalue(residuals: np.ndarray) -> float:
    """Augmented Dickey-Fuller p-value on cointegration residuals (with intercept)."""
    y = np.asarray(residuals, dtype=float).ravel()
    if len(y) < 25:
        return 1.0

    dy = np.diff(y)
    y_lag = y[:-1]
    if len(dy) < 10:
        return 1.0

    design = np.column_stack([np.ones(len(y_lag)), y_lag])
    coef, _, _, _ = np.linalg.lstsq(design, dy, rcond=None)
    gamma = float(coef[1])
    resid = dy - design @ coef
    n = len(dy)
    k = design.shape[1]
    sigma2 = float(np.dot(resid, resid) / max(n - k, 1))
    xtx_inv = np.linalg.pinv(design.T @ design)
    se_gamma = float(np.sqrt(max(sigma2 * xtx_inv[1, 1], 1e-12)))
    if se_gamma <= 0.0:
        return 1.0

    t_stat = gamma / se_gamma
    return float(_mac_kinnon_pvalue(t_stat, n))


def _mac_kinnon_pvalue(t_stat: float, n: int) -> float:
    """Approximate ADF p-value using MacKinnon response surface (constant, no trend)."""
    ln_n = np.log(max(n, 20))
    crit = {
        0.10: -2.5671 - 1.438 / ln_n - 4.48 / ln_n**2,
        0.05: -2.8621 - 2.738 / ln_n - 6.438 / ln_n**2,
        0.01: -3.4336 - 5.999 / ln_n - 29.938 / ln_n**2,
    }
    if t_stat <= crit[0.01]:
        return 0.01
    if t_stat <= crit[0.05]:
        return 0.05
    if t_stat <= crit[0.10]:
        return 0.10
    return 0.99
