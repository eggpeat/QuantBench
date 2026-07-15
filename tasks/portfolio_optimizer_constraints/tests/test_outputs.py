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


def load_candidate():
    path = WORKSPACE / "portfolio.py"
    spec = importlib.util.spec_from_file_location("candidate_portfolio", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_fixture_report_and_unridged_objective():
    subprocess.run([sys.executable, str(WORKSPACE / "run_portfolio.py")], cwd=WORKSPACE, check=True)
    data = json.loads((WORKSPACE / "input.json").read_text(encoding="utf-8"))
    report = json.loads((WORKSPACE / "outputs" / "portfolio_report.json").read_text(encoding="utf-8"))
    mod = load_candidate()
    result = mod.min_variance_portfolio(
        data["covariance"],
        data["expected_returns"],
        target_return=data["target_return"],
        bounds=data["bounds"],
        sector_labels=data["sector_labels"],
        sector_bounds=data["sector_bounds"],
        previous_weights=data["previous_weights"],
        turnover_limit=data["turnover_limit"],
        ridge=data["ridge"],
    )
    cov = (np.asarray(data["covariance"], dtype=float) + np.asarray(data["covariance"], dtype=float).T) / 2
    weights = np.asarray(report["weights"], dtype=float)
    assert report["seed"] == 100
    assert report["status"] == "optimal"
    np.testing.assert_allclose(weights, result.weights, rtol=1e-8, atol=1e-8)
    assert report["objective"] == pytest.approx(float(weights @ cov @ weights), rel=1e-10, abs=1e-12)
    assert report["objective"] != pytest.approx(float(weights @ (cov + data["ridge"] * np.eye(len(weights))) @ weights))
    assert np.sum(weights) == pytest.approx(1.0, abs=2e-6)
    assert np.dot(weights, data["expected_returns"]) == pytest.approx(data["target_return"], abs=2e-6)


def test_default_bounds_sum_and_covariance_symmetrization():
    mod = load_candidate()
    covariance = np.array([[0.20, 0.08, 0.01], [0.02, 0.10, 0.03], [0.04, 0.01, 0.16]], dtype=float)
    before = covariance.copy()
    result = mod.min_variance_portfolio(covariance, ridge=0.25)
    assert result.success
    assert isinstance(result, mod.OptimizationResult)
    assert np.all(result.weights >= -2e-6)
    assert np.all(result.weights <= 1.0 + 2e-6)
    assert np.sum(result.weights) == pytest.approx(1.0, abs=2e-6)
    sym = (before + before.T) / 2
    np.testing.assert_allclose(result.objective, result.weights @ sym @ result.weights, rtol=1e-10, atol=1e-12)
    np.testing.assert_array_equal(covariance, before)


def test_target_return_sector_intervals_and_no_input_mutation():
    mod = load_candidate()
    covariance = np.diag([0.04, 0.06, 0.03, 0.05])
    expected = np.array([0.05, 0.11, 0.09, 0.15])
    labels = ["growth", "growth", "defensive", "defensive"]
    previous = np.array([0.25, 0.25, 0.25, 0.25])
    previous_before = previous.copy()
    result = mod.min_variance_portfolio(
        covariance,
        expected,
        target_return=0.10,
        sector_labels=labels,
        sector_bounds={"growth": (0.30, 0.60), "defensive": (0.40, 0.70)},
        previous_weights=previous,
        turnover_limit=0.80,
    )
    assert result.success
    weights = result.weights
    assert np.dot(expected, weights) == pytest.approx(0.10, abs=2e-6)
    assert 0.30 - 2e-6 <= weights[:2].sum() <= 0.60 + 2e-6
    assert 0.40 - 2e-6 <= weights[2:].sum() <= 0.70 + 2e-6
    assert np.abs(weights - previous).sum() <= 0.80 + 2e-6
    np.testing.assert_array_equal(previous, previous_before)


def test_turnover_constraint_is_enforced():
    mod = load_candidate()
    covariance = np.diag([0.001, 0.10, 0.20])
    previous = np.array([0.0, 1.0, 0.0])
    result = mod.min_variance_portfolio(covariance, previous_weights=previous, turnover_limit=0.20)
    assert result.success, result.message
    assert result.turnover <= 0.20 + 5e-6
    assert np.abs(result.weights - previous).sum() <= 0.20 + 5e-6
    unconstrained = mod.min_variance_portfolio(covariance, previous_weights=previous)
    assert unconstrained.success
    assert unconstrained.turnover > 0.20 + 1e-3


def test_validation_and_explicit_infeasible_schema():
    mod = load_candidate()
    with pytest.raises(ValueError):
        mod.min_variance_portfolio(np.ones((2, 3)))
    with pytest.raises(ValueError):
        mod.min_variance_portfolio(np.eye(2), [0.1, np.nan], target_return=0.1)
    with pytest.raises(ValueError):
        mod.min_variance_portfolio(np.eye(2), bounds=(0.8, 0.2))
    with pytest.raises(ValueError):
        mod.min_variance_portfolio(np.eye(2), previous_weights=[0.5, 0.5], turnover_limit=-1)
    with pytest.raises(ValueError):
        mod.min_variance_portfolio(np.eye(2), target_return=0.1)
    infeasible = mod.min_variance_portfolio(
        np.eye(2), [0.0, 0.1], target_return=0.5, bounds=(0.0, 1.0)
    )
    assert not infeasible.success
    assert infeasible.status == "infeasible"
    assert infeasible.weights is None
    assert infeasible.objective is None
    assert infeasible.variance is None
