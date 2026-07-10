"""Unscented Kalman Filter for pair log-spread dynamics."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from regime_markov import RegimeState, regime_state_from_label

# Merwe UKF defaults
UKF_ALPHA = 1e-3
UKF_BETA = 2.0
UKF_KAPPA = 0.0

# Observation noise R scales up in stressed regimes (modulator hook).
REGIME_R_SCALE: dict[RegimeState, float] = {
    RegimeState.BULL: 1.0,
    RegimeState.BEAR: 1.0,
    RegimeState.VOLATILE: 2.5,
    RegimeState.CRASH: 4.0,
}

DEFAULT_PROCESS_NOISE = np.diag([1e-5, 1e-6])
DEFAULT_OBSERVATION_NOISE = 1e-4


def _as_process_noise(q: np.ndarray | float | None) -> np.ndarray:
    if q is None:
        return DEFAULT_PROCESS_NOISE.copy()
    if np.isscalar(q):
        return np.eye(2, dtype=float) * float(q)
    mat = np.asarray(q, dtype=float)
    if mat.shape != (2, 2):
        raise ValueError("process_noise must be scalar or 2x2 matrix")
    return mat.copy()


def modulate_observation_noise(
    base_r: float,
    regime_label: str | RegimeState | None = None,
    *,
    regime_row: Mapping[str, Any] | None = None,
    regime_confidence: float | None = None,
) -> float:
    """Scale observation noise R upward in VOLATILE/CRASH regimes."""
    label = regime_label
    confidence = regime_confidence
    if regime_row is not None:
        if label is None:
            label = regime_row.get("regime_label", RegimeState.BULL.name)
        if confidence is None:
            confidence = float(regime_row.get("regime_confidence", 1.0))

    if label is None:
        return float(base_r)

    state = label if isinstance(label, RegimeState) else regime_state_from_label(str(label))
    confidence = float(max(0.0, min(1.0, confidence if confidence is not None else 1.0)))

    base_scale = REGIME_R_SCALE[state]
    volatile_scale = REGIME_R_SCALE[RegimeState.VOLATILE]
    scale = base_scale * confidence + volatile_scale * (1.0 - confidence)
    return float(base_r) * scale


def _state_transition(x: np.ndarray) -> np.ndarray:
    """Constant-velocity model: level += velocity, velocity persists."""
    level, velocity = x
    return np.array([level + velocity, velocity], dtype=float)


def _observation(x: np.ndarray) -> float:
    return float(x[0])


class UKFSpreadFilter:
    """UKF on log-spread state ``[level, velocity]`` with cointegration hedge ratio."""

    def __init__(
        self,
        beta: float,
        *,
        process_noise: np.ndarray | float | None = None,
        observation_noise: float | None = None,
        regime_label: str | RegimeState | None = None,
        regime_confidence: float | None = None,
        regime_row: Mapping[str, Any] | None = None,
        alpha: float = UKF_ALPHA,
        beta_ukf: float = UKF_BETA,
        kappa: float = UKF_KAPPA,
    ) -> None:
        if not np.isfinite(beta):
            raise ValueError("beta must be finite")
        self.beta = float(beta)
        self._Q = _as_process_noise(process_noise)
        self._base_R = float(
            DEFAULT_OBSERVATION_NOISE if observation_noise is None else observation_noise
        )
        self._regime_label: str | RegimeState | None = None
        self._regime_confidence: float | None = None
        self._regime_row: Mapping[str, Any] | None = None
        if regime_row is not None:
            self._regime_row = regime_row
        else:
            self._regime_label = regime_label
            self._regime_confidence = regime_confidence
        self._alpha = float(alpha)
        self._beta_ukf = float(beta_ukf)
        self._kappa = float(kappa)

        self._n = 2
        self._lam = self._alpha**2 * (self._n + self._kappa) - self._n
        denom = self._n + self._lam
        self._Wm = np.full(2 * self._n + 1, 0.5 / denom, dtype=float)
        self._Wc = np.full(2 * self._n + 1, 0.5 / denom, dtype=float)
        self._Wm[0] = self._lam / denom
        self._Wc[0] = self._lam / denom + (1.0 - self._alpha**2 + self._beta_ukf)

        self._x = np.zeros(2, dtype=float)
        self._P = np.diag([1e-2, 1e-4]).astype(float)
        self._initialized = False
        self._spread_z = 0.0
        self._spread_level = float("nan")
        self._velocity = float("nan")

    @property
    def spread_z(self) -> float:
        return float(self._spread_z)

    @property
    def spread_level(self) -> float:
        return float(self._spread_level)

    @property
    def velocity(self) -> float:
        return float(self._velocity)

    def set_regime(
        self,
        regime_label: str | RegimeState | None,
        *,
        regime_confidence: float | None = None,
        regime_row: Mapping[str, Any] | None = None,
    ) -> None:
        if regime_row is not None:
            self._regime_row = regime_row
            self._regime_label = None
            self._regime_confidence = None
            return

        self._regime_row = None
        self._regime_label = regime_label
        self._regime_confidence = regime_confidence

    def _effective_R(self) -> float:
        if self._regime_row is not None:
            return modulate_observation_noise(self._base_R, regime_row=self._regime_row)
        return modulate_observation_noise(
            self._base_R,
            self._regime_label,
            regime_confidence=self._regime_confidence,
        )

    def _sigma_points(self, x: np.ndarray, P: np.ndarray) -> np.ndarray:
        n = self._n
        lam = self._lam
        try:
            chol = np.linalg.cholesky((n + lam) * P)
        except np.linalg.LinAlgError:
            chol = np.linalg.cholesky((n + lam) * (P + np.eye(n) * 1e-9))
        points = [x.copy()]
        for col in range(n):
            delta = chol[:, col]
            points.append(x + delta)
            points.append(x - delta)
        return np.vstack(points)

    def _unscented_mean(self, points: np.ndarray, weights: np.ndarray) -> np.ndarray:
        return np.tensordot(weights, points, axes=(0, 0))

    def _unscented_cov(
        self,
        points: np.ndarray,
        mean: np.ndarray,
        weights: np.ndarray,
        noise: np.ndarray | float,
    ) -> np.ndarray:
        diff = points - mean
        cov = np.einsum("i,ij,ik->jk", weights, diff, diff)
        if np.isscalar(noise):
            return cov + float(noise)
        return cov + np.asarray(noise, dtype=float)

    def _predict(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        sigmas = self._sigma_points(self._x, self._P)
        sigmas_pred = np.array([_state_transition(s) for s in sigmas])
        x_pred = self._unscented_mean(sigmas_pred, self._Wm)
        P_pred = self._unscented_cov(sigmas_pred, x_pred, self._Wc, self._Q)
        return x_pred, P_pred, sigmas_pred

    def _update(self, y: float, x_pred: np.ndarray, P_pred: np.ndarray, sigmas_pred: np.ndarray) -> None:
        obs_pred = np.array([_observation(s) for s in sigmas_pred], dtype=float)
        z_mean = float(np.dot(self._Wm, obs_pred))
        innov_var = float(
            np.dot(self._Wc, (obs_pred - z_mean) ** 2) + self._effective_R()
        )
        innov_var = max(innov_var, 1e-12)
        cross_cov = np.zeros(2, dtype=float)
        for i, sigma in enumerate(sigmas_pred):
            cross_cov += self._Wc[i] * (sigma - x_pred) * (obs_pred[i] - z_mean)

        innovation = float(y) - z_mean
        kalman_gain = cross_cov / innov_var
        self._x = x_pred + kalman_gain * innovation
        self._P = P_pred - np.outer(kalman_gain, kalman_gain) * innov_var
        self._P = 0.5 * (self._P + self._P.T)

        self._spread_z = innovation / np.sqrt(innov_var)
        self._spread_level = float(self._x[0])
        self._velocity = float(self._x[1])

    def update(self, price_a: float, price_b: float) -> None:
        """Ingest prices, predict, and update UKF on log-spread observation."""
        if price_a <= 0.0 or price_b <= 0.0:
            raise ValueError("prices must be positive")

        log_spread = float(np.log(price_a) - self.beta * np.log(price_b))

        if not self._initialized:
            self._x = np.array([log_spread, 0.0], dtype=float)
            self._P = np.diag([1e-2, 1e-4]).astype(float)
            self._spread_level = log_spread
            self._velocity = 0.0
            self._spread_z = 0.0
            self._initialized = True
            return

        x_pred, P_pred, sigmas_pred = self._predict()
        self._update(log_spread, x_pred, P_pred, sigmas_pred)
