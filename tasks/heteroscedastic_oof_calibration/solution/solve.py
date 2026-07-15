#!/usr/bin/env python3
"""General oracle for heteroscedastic OOF calibration."""
from __future__ import annotations

from pathlib import Path

SOURCE = r'''"""Leakage-safe out-of-fold predictions and Gaussian variance calibration."""
from __future__ import annotations

from typing import Any, Callable
import math
import numpy as np


def _rows(X: Any, idx: np.ndarray) -> Any:
    if hasattr(X, "iloc"):
        return X.iloc[idx]
    return np.asarray(X)[idx]


def _groups_folds(groups: np.ndarray, n_splits: int, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    try:
        unique, inverse = np.unique(groups, return_inverse=True)
    except Exception as exc:
        raise ValueError("groups must be a one-dimensional comparable array") from exc
    if unique.size < n_splits:
        raise ValueError("n_splits cannot exceed the number of groups")
    rng = np.random.default_rng(seed)
    group_order = rng.permutation(unique.size)
    folds = np.array_split(group_order, n_splits)
    all_idx = np.arange(groups.size)
    out = []
    for fold_groups in folds:
        mask = np.isin(inverse, fold_groups)
        val = all_idx[mask]
        train = all_idx[~mask]
        if train.size == 0 or val.size == 0:
            raise ValueError("every group fold needs training and validation rows")
        out.append((train, val))
    return out


def _time_folds(times: Any, n_splits: int) -> tuple[list[tuple[np.ndarray, np.ndarray]], np.ndarray]:
    try:
        order = np.argsort(np.asarray(times), kind="mergesort")
    except Exception as exc:
        raise ValueError("times must be stably sortable") from exc
    n = order.size
    test_size = n // (n_splits + 1)
    if test_size < 1:
        raise ValueError("not enough rows for expanding-window folds")
    initial = n - test_size * n_splits
    folds = []
    for j in range(n_splits):
        start = initial + j * test_size
        stop = start + test_size
        train = order[:start]
        val = order[start:stop]
        if train.size == 0 or val.size == 0:
            raise ValueError("every time fold needs training and validation rows")
        folds.append((train, val))
    return folds, order


def _ordinary_folds(n: int, n_splits: int, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(seed)
    chunks = np.array_split(rng.permutation(n), n_splits)
    folds = []
    all_idx = np.arange(n)
    for val in chunks:
        train = np.setdiff1d(all_idx, val, assume_unique=False)
        if train.size == 0 or val.size == 0:
            raise ValueError("every fold needs training and validation rows")
        folds.append((train, val))
    return folds


def make_oof_predictions(estimator_factory: Callable[[], Any], X: Any, y: Any, *, n_splits: int = 5,
                         groups: Any = None, times: Any = None, sample_weight: Any = None,
                         random_state: int = 0) -> np.ndarray:
    """Fit fresh models on folds and return predictions in original row order."""
    if groups is not None and times is not None:
        raise ValueError("groups and times are mutually exclusive")
    try:
        n = len(X)
    except Exception as exc:
        raise ValueError("X must be row-indexable") from exc
    yy = np.asarray(y, dtype=float)
    if yy.ndim != 1 or yy.size != n:
        raise ValueError("y must be one-dimensional with len(X) entries")
    if not np.all(np.isfinite(yy)):
        raise ValueError("y must be finite")
    if isinstance(n_splits, bool) or int(n_splits) != n_splits or n_splits < 2:
        raise ValueError("n_splits must be an integer >= 2")
    n_splits = int(n_splits)
    ww = None
    if sample_weight is not None:
        ww = np.asarray(sample_weight, dtype=float)
        if ww.ndim != 1 or ww.size != n or not np.all(np.isfinite(ww)) or np.any(ww <= 0):
            raise ValueError("sample_weight must be finite, one-dimensional, and positive")
    gg = None
    if groups is not None:
        gg = np.asarray(groups)
        if gg.ndim != 1 or gg.size != n:
            raise ValueError("groups must be one-dimensional with len(X) entries")
        if np.issubdtype(gg.dtype, np.number) and not np.all(np.isfinite(gg)):
            raise ValueError("groups must not contain non-finite values")
        folds = _groups_folds(gg, n_splits, int(random_state))
    elif times is not None:
        tt = np.asarray(times)
        if tt.ndim != 1 or tt.size != n:
            raise ValueError("times must be one-dimensional with len(X) entries")
        if np.issubdtype(tt.dtype, np.number) and not np.all(np.isfinite(tt)):
            raise ValueError("times must be finite")
        folds, _ = _time_folds(tt, n_splits)
    else:
        if n_splits > n:
            raise ValueError("n_splits cannot exceed the number of rows")
        folds = _ordinary_folds(n, n_splits, int(random_state))
    pred = np.full(n, np.nan, dtype=float)
    for train, val in folds:
        try:
            model = estimator_factory()
            if model is None or not callable(getattr(model, "fit", None)) or not callable(getattr(model, "predict", None)):
                raise ValueError("estimator_factory must return an estimator with fit and predict")
            kwargs = {} if ww is None else {"sample_weight": ww[train]}
            model.fit(_rows(X, train), yy[train], **kwargs)
            out = np.asarray(model.predict(_rows(X, val)), dtype=float)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("fold estimator failed during fit or predict") from exc
        if out.ndim != 1 or out.size != val.size or not np.all(np.isfinite(out)):
            raise ValueError("estimator predictions must be finite one-dimensional values")
        pred[val] = out
    return pred


def fit_variance_scale(y: Any, mu: Any, var_raw: Any, *, sample_weight: Any = None, eps: float = 1e-12) -> float:
    """Return the closed-form multiplicative variance calibration scale."""
    if not np.isfinite(eps) or eps <= 0:
        raise ValueError("eps must be finite and positive")
    yy = np.asarray(y, dtype=float)
    mm = np.asarray(mu, dtype=float)
    vv = np.asarray(var_raw, dtype=float)
    if yy.ndim != 1 or mm.ndim != 1 or vv.ndim != 1 or not (yy.size == mm.size == vv.size):
        raise ValueError("y, mu, and var_raw must be matching one-dimensional arrays")
    if yy.size == 0 or not (np.all(np.isfinite(yy)) and np.all(np.isfinite(mm)) and np.all(np.isfinite(vv))):
        raise ValueError("calibration arrays must be nonempty and finite")
    denom = np.maximum(vv, float(eps))
    ratio = (yy - mm) ** 2 / denom
    if sample_weight is None:
        scale = float(np.mean(ratio))
    else:
        ww = np.asarray(sample_weight, dtype=float)
        if ww.ndim != 1 or ww.size != yy.size or not np.all(np.isfinite(ww)) or np.any(ww <= 0):
            raise ValueError("sample_weight must be finite, matching, and positive")
        total = float(np.sum(ww))
        if not np.isfinite(total) or total <= 0:
            raise ValueError("sample_weight must have positive finite total")
        scale = float(np.sum(ww * ratio) / total)
    if not np.isfinite(scale):
        raise ValueError("calibration scale is not finite")
    return float(max(scale, float(eps)))
'''


def main() -> None:
    path = Path("hetero.py")
    path.write_text(SOURCE, encoding="utf-8")
    runner = Path("run_calibration.py")
    if runner.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(runner)], check=True)


if __name__ == "__main__":
    main()
