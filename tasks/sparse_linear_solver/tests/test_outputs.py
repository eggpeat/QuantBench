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
    path = WORKSPACE / "sparse_solver.py"
    spec = importlib.util.spec_from_file_location("candidate_sparse", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tridiag_csr(n, diag, off):
    indptr = np.zeros(n + 1, dtype=np.int64)
    indices = []
    data = []
    for i in range(n):
        row_cols = []
        row_vals = []
        if i > 0:
            row_cols.append(i - 1)
            row_vals.append(off)
        row_cols.append(i)
        row_vals.append(diag)
        if i < n - 1:
            row_cols.append(i + 1)
            row_vals.append(off)
        indices.extend(row_cols)
        data.extend(row_vals)
        indptr[i + 1] = indptr[i] + len(row_cols)
    return indptr, np.array(indices, dtype=np.int64), np.array(data, dtype=float)


def test_public_cli_fixture():
    subprocess.run([sys.executable, str(WORKSPACE / "run_sparse.py")], cwd=WORKSPACE, check=True)
    report = json.loads((WORKSPACE / "outputs" / "sparse_report.json").read_text(encoding="utf-8"))
    assert report["seed"] == 100
    assert report["converged"] is True
    assert report["reason"] == "converged"
    assert report["residual_norm"] < 1e-6


def test_diagonally_dominant_solution():
    mod = load_candidate()
    n = 32
    indptr, indices, data = _tridiag_csr(n, 4.0, -1.0)
    rng = np.random.default_rng(1101)
    b = rng.normal(size=n)
    result = mod.pcg(indptr, indices, data, b)
    assert result.converged
    assert result.reason == "converged"
    expected = np.linalg.solve(np.diag(4.0 * np.ones(n)) + np.diag(-1.0 * np.ones(n - 1), 1) + np.diag(-1.0 * np.ones(n - 1), -1), b)
    np.testing.assert_allclose(result.x, expected, rtol=1e-6, atol=1e-8)


def test_zero_rhs_returns_zero():
    mod = load_candidate()
    n = 10
    indptr, indices, data = _tridiag_csr(n, 2.0, -0.5)
    b = np.zeros(n)
    result = mod.pcg(indptr, indices, data, b)
    assert result.converged
    assert result.iterations == 0
    np.testing.assert_allclose(result.x, 0.0, atol=1e-12)


def test_singular_preconditioner_detected():
    mod = load_candidate()
    n = 4
    indptr = np.array([0, 2, 4, 6, 8], dtype=np.int64)
    indices = np.array([0, 1, 0, 1, 2, 3, 2, 3], dtype=np.int64)
    data = np.array([0.0, 1.0, 1.0, 2.0, 0.0, 1.0, 1.0, 2.0], dtype=float)
    b = np.ones(n)
    result = mod.pcg(indptr, indices, data, b)
    assert result.converged is False
    assert result.reason == "singular_preconditioner"


def test_non_spd_detected():
    mod = load_candidate()
    # Indefinite matrix [[1,2],[2,1]]
    n = 2
    indptr = np.array([0, 2, 4], dtype=np.int64)
    indices = np.array([0, 1, 0, 1], dtype=np.int64)
    data = np.array([1.0, 2.0, 2.0, 1.0], dtype=float)
    b = np.array([1.0, -1.0])
    result = mod.pcg(indptr, indices, data, b, x0=np.zeros(n))
    assert result.converged is False
    assert result.reason == "non_spd"


def test_invalid_input_shapes():
    mod = load_candidate()
    with pytest.raises(ValueError):
        mod.pcg(np.array([0, 1]), np.array([0]), np.array([1.0, 2.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        mod.pcg(np.array([0, 1, 2]), np.array([0, 1]), np.array([1.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        mod.pcg(np.array([0, 1, 2]), np.array([0, 2]), np.array([1.0, 1.0]), np.array([1.0, 1.0]))


def test_large_sparse_performance():
    mod = load_candidate()
    rng = np.random.default_rng(1199)
    n = 250_000
    k = 7
    indptr = np.zeros(n + 1, dtype=np.int64)
    indices = []
    data = []
    for i in range(n):
        cols = [j % n for j in range(i - k // 2, i + k // 2 + 1)]
        vals = rng.uniform(-0.1, 0.1, size=len(cols))
        diag_idx = cols.index(i)
        vals[diag_idx] = 2.0 + np.sum(np.abs(vals))  # make diagonally dominant
        indices.extend(cols)
        data.extend(vals)
        indptr[i + 1] = indptr[i] + len(cols)
    b = rng.normal(size=n)
    import time
    start = time.perf_counter()
    result = mod.pcg(indptr, np.array(indices, dtype=np.int64), np.array(data, dtype=float), b, tol=1e-6)
    elapsed = time.perf_counter() - start
    assert result.converged
    assert elapsed < 30.0
    assert result.residual_norm <= 1e-6 * max(float(np.linalg.norm(b)), 1.0)
