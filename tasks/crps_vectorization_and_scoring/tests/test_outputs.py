from __future__ import annotations

import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from scipy.special import ndtr

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_candidate():
    path = WORKSPACE / "scoring.py"
    spec = importlib.util.spec_from_file_location("candidate_scoring", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pairwise_reference(samples: np.ndarray, y: np.ndarray) -> np.ndarray:
    # Small independent O(M^2) reference; samples are members x observations.
    return np.mean(np.abs(samples - y[None, :]), axis=0) - 0.5 * np.mean(
        np.abs(samples[:, None, :] - samples[None, :, :]), axis=(0, 1)
    )


def test_public_cli_fixture_and_no_static_answers():
    subprocess.run([sys.executable, str(WORKSPACE / "run_scoring.py")], cwd=WORKSPACE, check=True)
    report = json.loads((WORKSPACE / "outputs" / "scoring_report.json").read_text(encoding="utf-8"))
    data = json.loads((WORKSPACE / "input.json").read_text(encoding="utf-8"))
    mu = np.asarray(data["mu"], dtype=np.float64)
    sigma = np.asarray(data["sigma"], dtype=np.float64)
    y = np.asarray(data["y"], dtype=np.float64)
    w = np.asarray(data["sample_weight"], dtype=np.float64)
    z = (y - mu) / sigma
    gaussian_pointwise = sigma * (z * (2 * ndtr(z) - 1) + 2 * np.exp(-z * z / 2) / np.sqrt(2 * np.pi) - 1 / np.sqrt(np.pi))
    gaussian = float(np.sum(w * gaussian_pointwise) / np.sum(w))
    samples = np.asarray(data["samples"], dtype=np.float64)
    empirical_pointwise = pairwise_reference(samples, y)
    empirical = float(np.sum(w * empirical_pointwise) / np.sum(w))
    assert report["seed"] == 100
    assert math.isclose(report["gaussian_crps"], gaussian, rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(report["empirical_crps"], empirical, rel_tol=1e-12, abs_tol=1e-12)


def test_gaussian_closed_form_broadcast_weight_and_float32():
    mod = load_candidate()
    mu = np.array([0.0, 1.0], dtype=np.float32)
    sigma = np.array([1.0, 2.0], dtype=np.float32)
    y = np.array([0.0, 1.0], dtype=np.float32)
    expected_each = np.array([2 / np.sqrt(2 * np.pi) - 1 / np.sqrt(np.pi), 2 * (2 / np.sqrt(2 * np.pi) - 1 / np.sqrt(np.pi))])
    np.testing.assert_allclose(mod.gaussian_crps(mu, sigma, y), np.mean(expected_each), rtol=1e-7, atol=1e-9)
    np.testing.assert_allclose(mod.gaussian_crps(mu, sigma, y, [1.0, 3.0]), np.average(expected_each, weights=[1.0, 3.0]), rtol=1e-7, atol=1e-9)
    with pytest.raises(ValueError):
        mod.gaussian_crps(0.0, 0.0, 1.0)
    assert math.isfinite(mod.gaussian_crps(0.0, 1e-300, 1.0))


def test_empirical_sorted_formula_orientation_weights_and_no_mutation():
    mod = load_candidate()
    rng = np.random.default_rng(1101)
    members_first = rng.normal(size=(7, 11))
    y = rng.normal(size=11)
    weights = rng.uniform(0.1, 3.0, size=11)
    before = members_first.copy()
    expected = pairwise_reference(members_first, y)
    actual = mod.empirical_crps(members_first, y, weights)
    np.testing.assert_allclose(actual, np.average(expected, weights=weights), rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(members_first, before)
    np.testing.assert_allclose(mod.empirical_crps(members_first.T, y), np.mean(expected), rtol=1e-12, atol=1e-12)


def test_shape_domain_and_weight_validation():
    mod = load_candidate()
    with pytest.raises(ValueError):
        mod.gaussian_crps([0.0, 1.0], [1.0], [0.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        mod.gaussian_crps([0.0], [-1.0], [0.0])
    with pytest.raises(ValueError):
        mod.gaussian_crps([0.0], [np.nan], [0.0])
    with pytest.raises(ValueError):
        mod.gaussian_crps([0.0, 1.0], [1.0, 1.0], [0.0, 1.0], [-1.0, 2.0])
    with pytest.raises(ValueError):
        mod.empirical_crps(np.ones((2, 3)), [0.0, 1.0, 2.0, 3.0], [1.0, 1.0, 1.0, 1.0])
    with pytest.raises(ValueError):
        mod.empirical_crps(np.ones((2, 3)), [0.0, 1.0], [1.0, 1.0, 1.0])
    with pytest.raises(ValueError):
        mod.empirical_crps(np.ones((2, 3)), [0.0, 1.0, 2.0], [0.0, 0.0, 0.0])
    one_distribution = np.array([0.0, 1.0, 2.0])
    one_score = mod.empirical_crps(one_distribution, 1.0)
    expected_one = pairwise_reference(one_distribution[:, None], np.array([1.0]))[0]
    np.testing.assert_allclose(one_score, expected_one, rtol=1e-12, atol=1e-12)
    with pytest.raises(ValueError):
        mod.empirical_crps(one_distribution, [0.0, 1.0])
    with pytest.raises(ValueError):
        mod.empirical_crps(np.ones((3, 3)), [0.0, 1.0, 2.0])
    with pytest.raises(ValueError):
        mod.gaussian_crps(np.array([1.0], dtype=object), [1.0], [1.0])
    with pytest.raises(ValueError):
        mod.empirical_crps(np.ones((2, 3)), [0.0, np.inf, 2.0])


def test_empirical_speedup_against_pairwise_reference():
    mod = load_candidate()
    rng = np.random.default_rng(1102)
    samples = rng.normal(size=(100, 1_000))
    y = rng.normal(size=1_000)
    mod.empirical_crps(samples, y)

    def reference():
        pairwise = np.abs(samples[:, None, :] - samples[None, :, :])
        return np.mean(np.abs(samples - y[None, :]), axis=0) - 0.5 * np.mean(pairwise, axis=(0, 1))

    candidate_times = []
    reference_times = []
    for _ in range(3):
        start = time.perf_counter()
        mod.empirical_crps(samples, y)
        candidate_times.append(time.perf_counter() - start)
        start = time.perf_counter()
        reference()
        reference_times.append(time.perf_counter() - start)
    assert np.median(candidate_times) <= 0.20 * np.median(reference_times)


def test_large_empirical_fixture_is_memory_bounded():
    mod = load_candidate()
    rng = np.random.default_rng(1199)
    samples = rng.normal(size=(100, 100_000)).astype(np.float32)
    y = rng.normal(size=100_000).astype(np.float32)
    score = mod.empirical_crps(samples, y)
    assert np.isfinite(score)
    assert score >= 0.0
