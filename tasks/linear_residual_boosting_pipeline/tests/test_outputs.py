from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.base import clone

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_candidate():
    path = WORKSPACE / "linear_residual.py"
    spec = importlib.util.spec_from_file_location("candidate_linear_residual", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ILoc:
    def __init__(self, frame):
        self.frame = frame

    def __getitem__(self, key):
        rows, column = key
        return self.frame._rows[rows, column]


class NamedFrame:
    def __init__(self, columns, rows):
        self.columns = list(columns)
        self._rows = np.asarray(rows, dtype=object)
        self.iloc = _ILoc(self)

    def __len__(self):
        return len(self._rows)

    def to_numpy(self, dtype=object):
        return np.asarray(self._rows, dtype=dtype)


def test_public_seed_100_fixture_and_reload():
    subprocess.run([sys.executable, str(WORKSPACE / "run_linear_residual.py")], cwd=WORKSPACE, check=True)
    data = json.loads((WORKSPACE / "input.json").read_text(encoding="utf-8"))
    report = json.loads((WORKSPACE / "outputs" / "linear_residual.json").read_text(encoding="utf-8"))
    assert report["seed"] == 100
    assert report["n_rows"] == len(data["y"])
    assert report["trend_active"] is True
    assert len(report["predictions"]) == len(data["y"])
    assert report["max_reload_error"] <= 1e-12
    assert np.isfinite(report["predictions"]).all()


def test_weighted_numeric_trend_categorical_missing_and_named_reorder():
    mod = load_candidate()
    frame = NamedFrame(
        ["x", "category", "noise"],
        [[0.0, "a", 1.0], [1.0, "b", None], [2.0, "a", 0.5], [3.0, "c", 1.5], [4.0, "b", 2.0], [5.0, "a", None]],
    )
    y = np.array([0.5, 2.0, 4.1, 6.0, 8.1, 10.2])
    estimator = mod.LinearResidualRegressor(alpha=0.1, max_depth=3, random_state=100)
    estimator.fit(frame, y, sample_weight=np.array([1.0, 2.0, 1.0, 1.0, 0.5, 1.0]))
    assert estimator.linear_residual_active_
    assert estimator.linear_residual_feature_indices_.tolist() == [0, 2]
    assert np.all(np.isfinite(estimator.predict(frame)))
    reordered = NamedFrame(["noise", "x", "category"], np.asarray(frame._rows)[:, [2, 0, 1]])
    np.testing.assert_allclose(estimator.predict(frame), estimator.predict(reordered), rtol=0, atol=1e-12)
    with pytest.raises(ValueError):
        estimator.predict(NamedFrame(["x", "category"], [[1.0, "a"]]))


def test_positive_weight_train_only_preprocessing_and_residual_tree():
    mod = load_candidate()
    train = np.array([[0.0, "a"], [1.0, "a"], [2.0, "b"], [3.0, "b"], [4.0, "a"]], dtype=object)
    y = np.array([1.0, 3.0, 5.0, 7.0, 9.0])
    test = np.array([[1.5, "a"], [10.0, "z"]], dtype=object)
    baseline = mod.LinearResidualRegressor(alpha=0.2, max_depth=2, random_state=100)
    baseline.fit(train, y, sample_weight=np.ones(5))
    augmented = np.vstack([train, [[1e12, "validation-only"], [-1e12, "validation-only"]]])
    augmented_y = np.concatenate([y, [1e15, -1e15]])
    weighted = mod.LinearResidualRegressor(alpha=0.2, max_depth=2, random_state=100)
    weighted.fit(augmented, augmented_y, sample_weight=np.array([1, 1, 1, 1, 1, 0, 0], dtype=float))
    np.testing.assert_allclose(baseline.predict(test), weighted.predict(test), rtol=0, atol=1e-12)
    weighted_imputation = (
        weighted.linear_residual_impute_values_
        if hasattr(weighted, "linear_residual_impute_values_")
        else weighted.linear_residual_imputation_
    )
    baseline_imputation = (
        baseline.linear_residual_impute_values_
        if hasattr(baseline, "linear_residual_impute_values_")
        else baseline.linear_residual_imputation_
    )
    np.testing.assert_allclose(weighted_imputation, baseline_imputation, rtol=0, atol=1e-12)


def test_clone_constructor_immutability_and_weight_scaling():
    mod = load_candidate()
    params = {"alpha": 0.35, "max_depth": 2, "min_samples_leaf": 2, "random_state": 17, "features": "auto", "fit_intercept": True, "standardize": False}
    estimator = mod.LinearResidualRegressor(**params)
    before = estimator.get_params(deep=False)
    clone_estimator = clone(estimator)
    assert clone_estimator.get_params(deep=False) == before
    X = np.array([[0.0], [1.0], [2.0], [3.0], [4.0]])
    y = np.array([0.1, 1.2, 1.8, 3.2, 4.1])
    w = np.array([1.0, 2.0, 1.0, 3.0, 0.5])
    estimator.fit(X, y, sample_weight=w)
    clone_estimator.fit(X, y, sample_weight=w * 7.0)
    np.testing.assert_allclose(estimator.predict(X), clone_estimator.predict(X), rtol=0, atol=1e-12)
    assert estimator.get_params(deep=False) == before


def test_non_pickle_roundtrip_and_invalid_weights():
    mod = load_candidate()
    X = np.array([[0.0, "a"], [1.0, "b"], [2.0, "a"], [3.0, "b"]], dtype=object)
    y = np.array([0.0, 1.0, 1.9, 3.1])
    estimator = mod.LinearResidualRegressor(alpha=0.05, max_depth=2).fit(X, y)
    path = WORKSPACE / "outputs" / "_linear_model.npz"
    path.parent.mkdir(exist_ok=True)
    try:
        estimator.save_model(path)
        raw = path.read_bytes()
        assert b"pickle" not in raw.lower()
        loaded = mod.LinearResidualRegressor.load_model(path)
        np.testing.assert_allclose(estimator.predict(X), loaded.predict(X), rtol=0, atol=1e-12)
    finally:
        path.unlink(missing_ok=True)
    with pytest.raises(ValueError):
        mod.LinearResidualRegressor().fit(X, y, sample_weight=np.zeros(len(y)))
    with pytest.raises(ValueError):
        mod.LinearResidualRegressor(alpha=-1.0).fit(X, y)
