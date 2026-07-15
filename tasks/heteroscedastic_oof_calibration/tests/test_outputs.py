from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_module():
    path = WORKSPACE / "hetero.py"
    spec = importlib.util.spec_from_file_location("candidate_hetero", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"missing candidate module at {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_public_calibration_output():
    subprocess.run([sys.executable, str(WORKSPACE / "run_calibration.py")], cwd=WORKSPACE, check=True)
    with (WORKSPACE / "outputs" / "calibration.json").open(encoding="utf-8") as fh:
        result = json.load(fh)
    assert set(result) == {"scale", "nll_before", "nll_after", "n_calibration_rows"}
    assert np.isfinite(result["scale"]) and result["scale"] > 0
    assert np.isfinite(result["nll_before"]) and np.isfinite(result["nll_after"])
    assert result["nll_after"] <= result["nll_before"] + 1e-10
    assert result["n_calibration_rows"] == 36


def test_weighted_variance_multiplier_formula_and_validation():
    mod = load_module()
    y = np.array([1.0, 4.0, 10.0])
    mu = np.array([0.0, 0.0, 0.0])
    var = np.array([1.0, 4.0, 25.0])
    w = np.array([1.0, 1.0, 8.0])
    expected = np.average(y * y / var, weights=w)
    assert mod.fit_variance_scale(y, mu, var, sample_weight=w) == pytest.approx(expected)
    assert mod.fit_variance_scale(y, mu, var) == pytest.approx(np.mean(y * y / var))
    with pytest.raises(ValueError):
        mod.fit_variance_scale(y, mu[:-1], var)
    with pytest.raises(ValueError):
        mod.fit_variance_scale(y, mu, var, sample_weight=np.array([1.0, 0.0, 1.0]))
    with pytest.raises(ValueError):
        mod.fit_variance_scale(y, mu, var, eps=0.0)


class Memorizer:
    def fit(self, X, y, sample_weight=None):
        x = np.asarray(X, dtype=float).reshape(len(y), -1)
        self.seen = {tuple(row): float(value) for row, value in zip(x, y)}
        self.fit_weight = None if sample_weight is None else np.asarray(sample_weight).copy()
        return self

    def predict(self, X):
        x = np.asarray(X, dtype=float).reshape(len(X), -1)
        return np.array([self.seen.get(tuple(row), -999.0) for row in x], dtype=float)


def test_oof_is_strictly_out_of_fold_and_weight_slices_are_training_only():
    mod = load_module()
    X = np.arange(18, dtype=float)[:, None]
    y = np.arange(18, dtype=float) + 0.25
    weights = np.arange(1.0, 19.0)
    pred = mod.make_oof_predictions(lambda: Memorizer(), X, y, n_splits=3, sample_weight=weights, random_state=100)
    # A model that memorizes its training rows must miss every validation row.
    assert np.all(pred == -999.0)
    groups = np.repeat(np.arange(6), 3)
    gp = mod.make_oof_predictions(lambda: Memorizer(), X, y, n_splits=3, groups=groups, random_state=7)
    assert np.all(gp == -999.0)
    with pytest.raises(ValueError):
        mod.make_oof_predictions(lambda: Memorizer(), X, y, groups=groups, times=np.arange(18))


def test_time_mode_expands_and_leaves_initial_rows_nan():
    mod = load_module()
    X = np.arange(20, dtype=float)[:, None]
    y = np.sin(X[:, 0])
    times = np.array([20 - i for i in range(20)])  # intentionally unsorted input
    pred = mod.make_oof_predictions(lambda: Memorizer(), X, y, n_splits=4, times=times, random_state=1)
    assert pred.shape == (20,)
    assert np.count_nonzero(~np.isfinite(pred)) >= 4
    assert np.all(np.isfinite(pred[np.isfinite(pred)]))


def test_invalid_oof_shapes_and_fold_count_rejected():
    mod = load_module()
    X = np.arange(8, dtype=float)[:, None]
    y = np.arange(8, dtype=float)
    with pytest.raises(ValueError):
        mod.make_oof_predictions(lambda: Memorizer(), X, y[:-1])
    with pytest.raises(ValueError):
        mod.make_oof_predictions(lambda: Memorizer(), X, y, n_splits=1)
    with pytest.raises(ValueError):
        mod.make_oof_predictions(lambda: Memorizer(), X, y, sample_weight=np.ones(7))
