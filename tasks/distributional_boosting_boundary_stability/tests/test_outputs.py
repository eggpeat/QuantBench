from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.special import digamma, expit

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))
MIN_EXPONENT = float(np.log(np.float32(1e-32)))
MAX_EXPONENT = float(np.log(np.finfo("float32").max) - 1.0)


def load_module():
    path = WORKSPACE / "negative_binomial.py"
    spec = importlib.util.spec_from_file_location("candidate_negative_binomial", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"missing candidate module at {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_public_boundary_output_is_finite():
    subprocess.run([sys.executable, str(WORKSPACE / "run_negative_binomial.py")], cwd=WORKSPACE, check=True)
    with (WORKSPACE / "outputs" / "gradients.json").open(encoding="utf-8") as fh:
        out = json.load(fh)
    assert set(out) == {"gradient", "hessian", "finite"}
    assert out["finite"] is True
    grad, hess = np.asarray(out["gradient"], dtype=np.float32), np.asarray(out["hessian"], dtype=np.float32)
    assert grad.shape == (6, 2) and hess.shape == (6, 2)
    assert np.all(np.isfinite(grad)) and np.all(hess == 1.0)


def test_corrected_fisher_and_raw_score_reference():
    mod = load_module()
    y = np.array([0.0, 1.0, 5.0, 12.0])
    log_n = np.array([-1.0, 0.0, 2.0, 4.0])
    logit = np.array([-2.0, 0.5, 1.5, -3.0])
    grad, hess = mod.gradient_and_hessian(y, log_n, logit)
    assert grad.dtype == np.float32 and hess.dtype == np.float32
    n, p = np.exp(log_n), expit(logit)
    fisher = np.column_stack([n * p / (p + 1.0), n * (1.0 - p)])
    raw = np.column_stack([
        -n * (digamma(y + n) - digamma(n) + np.log(p)),
        p * y - n * (1.0 - p),
    ])
    expected = raw / fisher
    np.testing.assert_allclose(grad, expected.astype(np.float32), rtol=2e-6, atol=2e-6)
    np.testing.assert_array_equal(hess, np.ones((4, 2), dtype=np.float32))


def test_both_clipping_corners_and_floor_stay_finite():
    mod = load_module()
    y = np.array([0.0, 1.0, 100000.0, 0.0])
    log_n = np.array([MIN_EXPONENT, MAX_EXPONENT, MAX_EXPONENT, MAX_EXPONENT])
    logit = np.array([MIN_EXPONENT, MIN_EXPONENT, MAX_EXPONENT, MAX_EXPONENT])
    grad, hess = mod.gradient_and_hessian(y, log_n, logit)
    assert grad.shape == (4, 2) and hess.shape == (4, 2)
    assert np.all(np.isfinite(grad)) and np.all(np.isfinite(hess))
    assert np.max(np.abs(grad)) < np.finfo(np.float32).max


def test_domain_errors_and_unsupported_standard_gradient():
    mod = load_module()
    z = np.ones(3)
    with pytest.raises(ValueError):
        mod.gradient_and_hessian(np.array([0.0, -1.0, 2.0]), z, z)
    with pytest.raises(ValueError):
        mod.gradient_and_hessian(np.array([0.2, 1.0, 2.0]), z, z)
    with pytest.raises(ValueError):
        mod.gradient_and_hessian(z[:-1], z, z)
    with pytest.raises(ValueError):
        mod.gradient_and_hessian(z, z, np.array([np.nan, 1.0, 2.0]))
    with pytest.raises(NotImplementedError):
        mod.gradient_and_hessian(z, z, z, natural_gradient=False)


def test_finite_difference_score_direction_matches_raw_gradient():
    mod = load_module()
    y = np.array([3.0])
    log_n = np.array([0.7])
    logit = np.array([-0.4])
    grad_nat, _ = mod.gradient_and_hessian(y, log_n, logit)
    n, p = np.exp(log_n[0]), expit(logit[0])
    fisher = np.array([n * p / (p + 1.0), n * (1.0 - p)])
    raw = grad_nat[0].astype(float) * fisher
    # d(-log pmf)/d(log_n,logit_p), with the scipy NB pmf definition.
    from scipy.stats import nbinom
    def score(a, b):
        nn, pp = np.exp(a), expit(b)
        return float(-nbinom.logpmf(y[0], nn, pp))
    h = 1e-5
    numerical = np.array([(score(log_n[0] + h, logit[0]) - score(log_n[0] - h, logit[0])) / (2*h),
                          (score(log_n[0], logit[0] + h) - score(log_n[0], logit[0] - h)) / (2*h)])
    np.testing.assert_allclose(raw, numerical, rtol=2e-4, atol=2e-5)
