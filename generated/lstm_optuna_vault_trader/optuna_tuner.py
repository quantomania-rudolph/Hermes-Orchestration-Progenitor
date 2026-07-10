"""Optuna hyperparameter search on inner train/val within outer train folds (§8.3).

Search never touches the outer OOS test fold (invariant L4). Each outer fold
uses an 85/15 chronological inner split of ``train_idx`` only. Smoke runs use
``InMemoryStorage``; full runs may persist to ``models/optuna_study.db``.
When Optuna is unavailable, a fixed grid of three hand-picked param sets is
evaluated instead.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

import config
from dataset import FoldScaler, build_sequences
from nn_model import build_model, make_loaders, train_fold
from signals import FEATURE_COLS

logger = logging.getLogger(__name__)

try:
    import optuna
    from optuna.pruners import MedianPruner
    from optuna.storages import InMemoryStorage
    from optuna.trial import TrialState

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    _OPTUNA_AVAILABLE = True
except ImportError:  # pragma: no cover - orchestrator must not fail without optuna
    optuna = None  # type: ignore[assignment]
    MedianPruner = None  # type: ignore[assignment,misc]
    InMemoryStorage = None  # type: ignore[assignment,misc]
    TrialState = None  # type: ignore[assignment,misc]
    _OPTUNA_AVAILABLE = False

_MODELS_DIR = Path(__file__).resolve().parent / "models"
_INNER_VAL_FRAC = 0.15
_MIN_INNER_TRAIN = 8
_MIN_INNER_VAL = 2

SeqBuilder = Callable[..., tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]

__all__ = [
    "FALLBACK_PARAM_SETS",
    "best_params_path",
    "inner_train_val_split",
    "optuna_objective",
    "run_fold_tuning",
    "save_best_params",
]

FALLBACK_PARAM_SETS: list[dict[str, Any]] = [
    {
        "lookback": config.LOOKBACK,
        "hidden_h1": 64,
        "hidden_h2": 0,
        "n_layers": 1,
        "dropout_l1": 0.2,
        "dropout_l2": 0.1,
        "lr": 1e-3,
        "weight_decay": 1e-5,
        "batch_size": 64,
        "epochs": config.EPOCHS,
        "use_skip": True,
        "pfg_mode": "learned",
        "loss": "huber",
        "fold_reset": True,
    },
    {
        "lookback": config.LOOKBACK,
        "hidden_h1": 32,
        "hidden_h2": 32,
        "n_layers": 2,
        "dropout_l1": 0.1,
        "dropout_l2": 0.2,
        "lr": 5e-4,
        "weight_decay": 1e-4,
        "batch_size": 32,
        "epochs": config.EPOCHS,
        "use_skip": True,
        "pfg_mode": "learned",
        "loss": "mse",
        "fold_reset": True,
    },
    {
        "lookback": config.LOOKBACK,
        "hidden_h1": 128,
        "hidden_h2": 0,
        "n_layers": 1,
        "dropout_l1": 0.3,
        "dropout_l2": 0.1,
        "lr": 2e-3,
        "weight_decay": 1e-6,
        "batch_size": 128,
        "epochs": config.EPOCHS,
        "use_skip": False,
        "pfg_mode": "scheduled",
        "loss": "huber",
        "fold_reset": True,
    },
]


def inner_train_val_split(
    train_idx: np.ndarray,
    *,
    val_frac: float = _INNER_VAL_FRAC,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Chronological 85/15 inner split of an outer train index array.

    The last ``val_frac`` fraction becomes validation; earlier rows are inner
    train. Indices must already be time-ordered (as emitted by purged K-fold).
    """
    idx = np.asarray(train_idx, dtype=np.int64)
    if idx.size < _MIN_INNER_TRAIN + _MIN_INNER_VAL:
        raise ValueError(
            f"train_idx too small for inner split: need >= "
            f"{_MIN_INNER_TRAIN + _MIN_INNER_VAL}, got {idx.size}"
        )
    if not (0.0 < val_frac < 1.0):
        raise ValueError(f"val_frac must be in (0, 1), got {val_frac}")

    n_val = max(_MIN_INNER_VAL, int(round(idx.size * val_frac)))
    n_val = min(n_val, idx.size - _MIN_INNER_TRAIN)
    n_train = idx.size - n_val
    if n_train < _MIN_INNER_TRAIN:
        raise ValueError(
            f"inner train too small after split: {n_train} < {_MIN_INNER_TRAIN}"
        )

    inner_train = idx[:n_train]
    inner_val = idx[n_train:]
    return inner_train, inner_val


def optuna_objective(
    trial: Any,
    train_idx: np.ndarray,
    feature_df: pd.DataFrame,
    seq_builder: SeqBuilder,
) -> float:
    """
    Optuna objective: minimize inner validation loss on outer train fold only.

    Hyperparameters are sampled per §7.4. An inner 85/15 train/val split is
    applied within ``train_idx``; the outer test fold is never passed here.
    """
    params = _sample_trial_params(trial)
    return _evaluate_params(params, train_idx, feature_df, seq_builder)


def run_fold_tuning(
    train_idx: np.ndarray,
    feature_df: pd.DataFrame,
    fold_k: int,
    *,
    seq_builder: SeqBuilder = build_sequences,
    models_dir: Path | str | None = None,
    n_trials: int | None = None,
) -> dict[str, Any]:
    """
    Tune hyperparameters for one purged outer fold's train indices.

    Runs an Optuna study (or fallback grid when Optuna is missing) and writes
    ``best_params_fold_{k}.json``. Only ``train_idx`` is used — never the outer
    OOS test fold.
    """
    train_idx = np.asarray(train_idx, dtype=np.int64)
    if train_idx.size == 0:
        raise ValueError("train_idx is empty")

    out_dir = Path(models_dir) if models_dir is not None else _MODELS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    trials = config.OPTUNA_TRIALS if n_trials is None else n_trials

    if _OPTUNA_AVAILABLE:
        try:
            result = _run_optuna_study(
                train_idx,
                feature_df,
                fold_k,
                seq_builder=seq_builder,
                n_trials=trials,
                models_dir=out_dir,
            )
        except Exception as exc:
            logger.warning("Optuna study failed (%s); using fallback param grid", exc)
            result = _run_fallback_grid(
                train_idx,
                feature_df,
                fold_k,
                seq_builder=seq_builder,
            )
    else:
        logger.warning("optuna not installed; using fallback param grid")
        result = _run_fallback_grid(
            train_idx,
            feature_df,
            fold_k,
            seq_builder=seq_builder,
        )

    params_path = save_best_params(result["best_params"], fold_k, out_dir)
    result["params_path"] = str(params_path)
    return result


def best_params_path(fold_k: int, models_dir: Path | str | None = None) -> Path:
    """Return the canonical path for a fold's best-params JSON artifact."""
    root = Path(models_dir) if models_dir is not None else _MODELS_DIR
    return root / f"best_params_fold_{fold_k}.json"


def save_best_params(
    params: dict[str, Any],
    fold_k: int,
    models_dir: Path | str | None = None,
) -> Path:
    """Persist best hyperparameters for fold ``fold_k``."""
    path = best_params_path(fold_k, models_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fold": fold_k,
        "best_params": _json_safe(params),
        "smoke": config.SMOKE,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _run_optuna_study(
    train_idx: np.ndarray,
    feature_df: pd.DataFrame,
    fold_k: int,
    *,
    seq_builder: SeqBuilder,
    n_trials: int,
    models_dir: Path,
) -> dict[str, Any]:
    assert optuna is not None
    assert MedianPruner is not None
    assert InMemoryStorage is not None

    if config.SMOKE:
        storage: Any = InMemoryStorage()
    else:
        db_path = models_dir / "optuna_study.db"
        storage = f"sqlite:///{db_path.as_posix()}"

    study = optuna.create_study(
        study_name=f"lstm_fold_{fold_k}",
        direction="minimize",
        storage=storage,
        load_if_exists=not config.SMOKE,
        pruner=MedianPruner(n_startup_trials=max(2, n_trials // 5)),
    )

    def _objective(trial: Any) -> float:
        return optuna_objective(trial, train_idx, feature_df, seq_builder)

    study.optimize(
        _objective,
        n_trials=n_trials,
        show_progress_bar=False,
        catch=(Exception,),
    )

    complete = [
        t
        for t in study.trials
        if TrialState is not None and t.state == TrialState.COMPLETE
    ]
    if not complete or not np.isfinite(study.best_value):
        raise RuntimeError(
            f"no successful Optuna trials for fold {fold_k} "
            f"(complete={len(complete)}, best={study.best_value})"
        )

    best_params = _finalize_sampled_params(dict(study.best_params))

    return {
        "fold": fold_k,
        "best_params": best_params,
        "best_val_loss": float(study.best_value),
        "n_trials": len(study.trials),
        "method": "optuna",
    }


def _run_fallback_grid(
    train_idx: np.ndarray,
    feature_df: pd.DataFrame,
    fold_k: int,
    *,
    seq_builder: SeqBuilder,
) -> dict[str, Any]:
    best_loss = float("inf")
    best_params: dict[str, Any] | None = None

    for params in FALLBACK_PARAM_SETS:
        loss = _evaluate_params(params, train_idx, feature_df, seq_builder)
        if loss < best_loss:
            best_loss = loss
            best_params = dict(params)

    if best_params is None:
        best_params = dict(FALLBACK_PARAM_SETS[0])
        best_loss = float("inf")

    return {
        "fold": fold_k,
        "best_params": best_params,
        "best_val_loss": best_loss,
        "n_trials": len(FALLBACK_PARAM_SETS),
        "method": "fallback_grid",
    }


def _sample_trial_params(trial: Any) -> dict[str, Any]:
    lookback = trial.suggest_int("lookback", 30, 90, step=15)
    hidden_h1 = trial.suggest_int("hidden_h1", 32, 128, step=32)
    hidden_h2 = trial.suggest_int("hidden_h2", 0, 64, step=32)
    n_layers = trial.suggest_categorical("n_layers", [1, 2])

    if hidden_h2 == 0:
        n_layers = 1
    elif n_layers == 1:
        hidden_h2 = 0

    epoch_lo = max(3, min(10, config.EPOCHS))
    epochs = trial.suggest_int("epochs", epoch_lo, config.EPOCHS)

    params = {
        "lookback": lookback,
        "hidden_h1": hidden_h1,
        "hidden_h2": hidden_h2,
        "n_layers": n_layers,
        "dropout_l1": trial.suggest_float("dropout_l1", 0.0, 0.5),
        "dropout_l2": trial.suggest_float("dropout_l2", 0.0, 0.4),
        "lr": trial.suggest_float("lr", 1e-4, 5e-3, log=True),
        "weight_decay": trial.suggest_float("weight_decay", 1e-6, 1e-3, log=True),
        "batch_size": trial.suggest_int("batch_size", 32, 128, step=32),
        "epochs": epochs,
        "use_skip": trial.suggest_categorical("use_skip", [True, False]),
        "pfg_mode": trial.suggest_categorical("pfg_mode", ["learned", "scheduled"]),
        "loss": trial.suggest_categorical("loss", ["mse", "huber", "bce"]),
        "fold_reset": True,
    }
    return _finalize_sampled_params(params)


def _finalize_sampled_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    n_layers = int(out.get("n_layers", 1))
    hidden_h2 = int(out.get("hidden_h2", 0))
    if hidden_h2 < 1:
        out["n_layers"] = 1
        out["hidden_h2"] = 0
    elif n_layers == 1:
        out["hidden_h2"] = 0
    out["fold_reset"] = True
    out["epochs"] = int(min(int(out.get("epochs", config.EPOCHS)), config.EPOCHS))
    return out


def _evaluate_params(
    params: dict[str, Any],
    train_idx: np.ndarray,
    feature_df: pd.DataFrame,
    seq_builder: SeqBuilder,
) -> float:
    params = _finalize_sampled_params(params)
    lookback = int(params["lookback"])

    try:
        X, y_reg, _, ts = seq_builder(
            feature_df,
            lookback=lookback,
            feature_cols=FEATURE_COLS,
        )
    except ValueError as exc:
        logger.debug("sequence build failed for lookback=%s: %s", lookback, exc)
        return float("inf")

    aligned = _bar_indices_to_seq_indices(
        train_idx,
        lookback=lookback,
        n_sequences=int(ts.shape[0]),
    )
    if aligned.size < _MIN_INNER_TRAIN + _MIN_INNER_VAL:
        return float("inf")

    try:
        inner_train, inner_val = inner_train_val_split(aligned)
    except ValueError:
        return float("inf")

    X_train = X[inner_train]
    y_train = y_reg[inner_train]
    X_val = X[inner_val]
    y_val = y_reg[inner_val]

    scaler = FoldScaler()
    X_train = scaler.fit_transform(X_train, feature_cols=FEATURE_COLS)
    X_val = scaler.transform(X_val)

    batch_size = int(min(int(params["batch_size"]), len(inner_train)))
    batch_size = max(1, batch_size)

    train_loader, val_loader = make_loaders(
        X_train,
        y_train,
        X_val,
        y_val,
        batch_size=batch_size,
    )

    model_kwargs = {
        k: params[k]
        for k in (
            "hidden_h1",
            "hidden_h2",
            "n_layers",
            "dropout_l1",
            "dropout_l2",
            "use_skip",
            "pfg_mode",
            "fold_reset",
        )
        if k in params
    }
    try:
        model = build_model(X.shape[-1], **model_kwargs)
        metrics = train_fold(
            model,
            train_loader,
            val_loader,
            epochs=int(params["epochs"]),
            lr=float(params["lr"]),
            weight_decay=float(params["weight_decay"]),
            loss=params["loss"],
        )
        val_loss = float(metrics["val_loss"])
    except (RuntimeError, ValueError, TypeError) as exc:
        logger.debug("param evaluation failed: %s", exc)
        return float("inf")

    if not np.isfinite(val_loss):
        return float("inf")
    return val_loss


def _bar_indices_to_seq_indices(
    bar_idx: np.ndarray,
    *,
    lookback: int,
    n_sequences: int,
) -> np.ndarray:
    """
    Map purged-K-fold bar indices onto sequence rows for a trial lookback.

    ``purged_kfold`` emits feature-frame row indices; ``build_sequences`` row
    ``k`` ends at bar ``k + lookback - 1``. Bars before ``lookback - 1`` have
    no valid window and are dropped.
    """
    bars = np.asarray(bar_idx, dtype=np.int64)
    seq = bars - (lookback - 1)
    valid = (seq >= 0) & (seq < n_sequences)
    if not np.any(valid):
        return np.array([], dtype=np.int64)
    return np.sort(np.unique(seq[valid]))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value
