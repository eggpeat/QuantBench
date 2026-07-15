from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.special import log_ndtr

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_module(path: Path = WORKSPACE / "temporal_ep.py", name: str = "candidate_temporal_ep"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_public_seed_fixture_report_and_exact_keys():
    subprocess.run([sys.executable, str(WORKSPACE / "run_temporal.py")], cwd=WORKSPACE, check=True)
    report = json.loads((WORKSPACE / "outputs" / "temporal_report.json").read_text(encoding="utf-8"))
    data = json.loads((WORKSPACE / "input.json").read_text(encoding="utf-8"))
    mod = load_module()
    expected = mod.fit_temporal_states(
        data["times"], data["outcomes"], data["weights"], likelihood=data["likelihood"],
        process_var=data["process_var"], initial_mean=data["initial_mean"],
        initial_var=data["initial_var"], quadrature_order=data["quadrature_order"],
    )
    assert report["seed"] == 100
    assert set(report) == {"seed", "times", "filtered_mean", "filtered_var", "smoothed_mean", "smoothed_var", "log_likelihood"}
    for key, value in expected.items():
        np.testing.assert_allclose(np.asarray(report[key]), value, rtol=2e-13, atol=2e-13)


def test_likelihood_families_have_finite_weighted_state_and_partition():
    mod = load_module()
    cases = {
        "probit": np.array([-1.0, 1.0, -1.0]),
        "logit": np.array([-1.0, 1.0, -1.0]),
        "poisson": np.array([0.0, 3.0, 1.0]),
        "skellam": np.array([-2.0, 1.0, 0.0]),
    }
    for family, y in cases.items():
        out = mod.fit_temporal_states([0.0, 0.5, 1.5], y, [0.5, 2.0, 1.25], likelihood=family, process_var=0.2, quadrature_order=28)
        assert set(out) == {"times", "filtered_mean", "filtered_var", "smoothed_mean", "smoothed_var", "log_likelihood"}
        for key, value in out.items():
            assert np.all(np.isfinite(value)), (family, key, value)
        assert np.all(out["filtered_var"] > 0) and np.all(out["smoothed_var"] > 0)


def test_weight_power_changes_posterior_and_unit_weight_is_invariant():
    mod = load_module()
    args = dict(likelihood="logit", process_var=0.15, initial_mean=0.0, initial_var=1.0, quadrature_order=36)
    one = mod.fit_temporal_states([0.0, 1.0], [1.0, -1.0], [1.0, 1.0], **args)
    weighted = mod.fit_temporal_states([0.0, 1.0], [1.0, -1.0], [7.0, 1.0], **args)
    assert not np.allclose(one["filtered_mean"], weighted["filtered_mean"])
    assert not np.allclose(one["log_likelihood"], weighted["log_likelihood"])
    np.testing.assert_allclose(one["filtered_var"], mod.fit_temporal_states([0.0, 1.0], [1.0, -1.0], [1.0, 1.0], **args)["filtered_var"])


def test_stable_sort_and_duplicate_updates_match_sorted_input():
    mod = load_module()
    args = dict(likelihood="probit", process_var=0.4, initial_mean=-0.3, initial_var=0.7, quadrature_order=24)
    unsorted = mod.fit_temporal_states([2.0, 1.0, 1.0, 0.0], [1.0, -1.0, 1.0, -1.0], [1.5, 0.8, 2.2, 0.6], **args)
    # Equal-time events remain in input order in this explicit stable ordering.
    sorted_result = mod.fit_temporal_states([0.0, 1.0, 1.0, 2.0], [-1.0, -1.0, 1.0, 1.0], [0.6, 0.8, 2.2, 1.5], **args)
    for key in unsorted:
        np.testing.assert_allclose(unsorted[key], sorted_result[key], rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(unsorted["times"], np.array([0.0, 1.0, 2.0]))


def test_smoothing_uses_future_information_and_reduces_variance():
    mod = load_module()
    out = mod.fit_temporal_states(
        [0.0, 1.0, 2.0], [-1.0, 1.0, 1.0], [1.0, 5.0, 5.0],
        likelihood="logit", process_var=0.8, initial_var=2.0, quadrature_order=32,
    )
    assert np.all(out["smoothed_var"] <= out["filtered_var"] + 1e-12)
    assert abs(float(out["smoothed_mean"][0] - out["filtered_mean"][0])) > 1e-5


def test_independent_normalized_gh_one_observation_reference():
    mod = load_module()
    order = 40
    out = mod.fit_temporal_states([0.0], [1.0], [2.0], likelihood="logit", process_var=0.5, initial_var=1.3, quadrature_order=order)
    nodes, qw = np.polynomial.hermite.hermgauss(order)
    x = np.sqrt(2 * 1.3) * nodes
    log_terms = np.log(qw / np.sqrt(np.pi)) + 2.0 * (-np.logaddexp(0.0, -x))
    p = np.exp(log_terms - np.logaddexp.reduce(log_terms))
    mean = np.dot(p, x)
    var = np.dot(p, (x - mean) ** 2)
    np.testing.assert_allclose(out["filtered_mean"][0], mean, rtol=1e-11, atol=1e-12)
    np.testing.assert_allclose(out["filtered_var"][0], var, rtol=1e-11, atol=1e-12)


def test_domain_and_parameter_validation():
    mod = load_module()
    base = dict(likelihood="logit", process_var=0.2)
    with pytest.raises(ValueError):
        mod.fit_temporal_states([0.0], [0.0], [1.0], **base)
    with pytest.raises(ValueError):
        mod.fit_temporal_states([0.0], [1.0], [0.0], **base)
    with pytest.raises(ValueError):
        mod.fit_temporal_states([0.0], [1.0], [1.0], likelihood="unknown", process_var=0.2)
    with pytest.raises(ValueError):
        mod.fit_temporal_states([0.0, np.nan], [1.0, -1.0], [1.0, 1.0], **base)
    with pytest.raises(ValueError):
        mod.fit_temporal_states([0.0], [1.0], [1.0], likelihood="poisson", process_var=0.2, quadrature_order=0)
    with pytest.raises(ValueError):
        mod.fit_temporal_states([0.0], [1.2], [1.0], likelihood="poisson", process_var=0.2)
    with pytest.raises(ValueError):
        mod.fit_temporal_states([0.0], [0.2], [1.0], likelihood="skellam", process_var=0.2)


def test_named_unweighted_mutant_is_rejected():
    mutant = load_module(TASK_DIR / "tests" / "mutants" / "unweighted_updates" / "solve.py", "unweighted_mutant")
    args = dict(likelihood="logit", process_var=0.3, initial_mean=0.0, initial_var=1.0, quadrature_order=28)
    weighted = load_module().fit_temporal_states([0.0, 1.0], [1.0, -1.0], [9.0, 0.2], **args)
    candidate = mutant.fit_temporal_states([0.0, 1.0], [1.0, -1.0], [9.0, 0.2], **args)
    assert not np.allclose(candidate["filtered_mean"], weighted["filtered_mean"], rtol=1e-8, atol=1e-8)
    assert not np.allclose(candidate["log_likelihood"], weighted["log_likelihood"], rtol=1e-8, atol=1e-8)
