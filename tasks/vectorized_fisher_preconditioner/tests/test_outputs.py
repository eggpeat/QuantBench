from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_candidate():
    path = WORKSPACE / "fisher.py"
    spec = importlib.util.spec_from_file_location("candidate_fisher", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_cli_fixture_and_no_static_answers():
    subprocess.run([sys.executable, str(WORKSPACE / "run_fisher.py")], cwd=WORKSPACE, check=True)
    report = json.loads((WORKSPACE / "outputs" / "fisher_report.json").read_text(encoding="utf-8"))
    data = json.loads((WORKSPACE / "input.json").read_text(encoding="utf-8"))
    raw = np.asarray(data["raw_grad"], dtype=np.float64)
    fisher = np.asarray(data["fisher_diag"], dtype=np.float64)
    expected = raw / np.maximum(fisher, data["floor"])
    np.testing.assert_allclose(np.asarray(report["values"]), expected, rtol=1e-12, atol=1e-12)
    assert report["seed"] == 100
    assert report["shape"] == list(expected.shape)


def test_diagonal_solve_broadcast_floor_and_no_mutation():
    mod = load_candidate()
    raw = np.array([[2.0, -4.0, 3.0], [1.0, 8.0, -2.0]], dtype=np.float32)
    fisher = np.array([2.0, 0.0, 4.0], dtype=np.float32)
    raw_before = raw.copy()
    fisher_before = fisher.copy()
    actual = mod.precondition_diagonal(raw, fisher, floor=1e-3)
    expected = raw.astype(np.float64) / np.maximum(fisher.astype(np.float64), 1e-3)
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    assert actual.dtype == np.float64
    np.testing.assert_array_equal(raw, raw_before)
    np.testing.assert_array_equal(fisher, fisher_before)


def test_shape_domain_and_floor_validation():
    mod = load_candidate()
    with pytest.raises(ValueError):
        mod.precondition_diagonal(np.ones((2, 3)), np.ones((2, 2)))
    with pytest.raises(ValueError):
        mod.precondition_diagonal(np.ones((2, 3)), np.array([1.0, np.nan, 2.0]))
    with pytest.raises(ValueError):
        mod.precondition_diagonal(np.ones((2, 3)), np.ones(3), floor=0.0)
    with pytest.raises(ValueError):
        mod.precondition_diagonal(np.ones((2, 3)), np.ones(3), floor=np.inf)
    with pytest.raises(ValueError):
        mod.precondition_diagonal(np.array([[1.0, np.inf]]), np.ones((1, 2)))
    with pytest.raises(ValueError):
        mod.precondition_diagonal(np.array(["1.0"], dtype=object), np.ones(1))


def test_large_fixture_is_vectorized_and_finite():
    mod = load_candidate()
    rng = np.random.default_rng(1199)
    raw = rng.normal(size=(500_000, 3))
    fisher = rng.uniform(0.01, 4.0, size=(500_000, 3))
    output = mod.precondition_diagonal(raw, fisher)
    assert output.shape == raw.shape
    assert output.dtype == np.float64
    assert np.isfinite(output).all()

def test_vectorized_speedup_and_rss_against_matrix_solve_reference():
    mod = load_candidate()
    rng = np.random.default_rng(1199)
    raw = rng.normal(size=(500_000, 3))
    fisher = rng.uniform(0.1, 4.0, size=(500_000, 3))
    eye = np.eye(3)

    def candidate():
        return mod.precondition_diagonal(raw, fisher)

    def reference():
        matrices = fisher[:, :, None] * eye[None, :, :]
        return np.linalg.solve(matrices, raw[..., None])[..., 0]

    memory_probe = """
import importlib.util
import json
import resource
import sys
import numpy as np
spec = importlib.util.spec_from_file_location("candidate_fisher_probe", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
rng = np.random.default_rng(1199)
raw = rng.normal(size=(500_000, 3))
fisher = rng.uniform(0.1, 4.0, size=(500_000, 3))
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
output = module.precondition_diagonal(raw, fisher)
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"delta_kib": max(0, after - before), "finite": bool(np.isfinite(output).all())}))
"""
    memory = subprocess.run(
        [sys.executable, "-c", memory_probe, str(WORKSPACE / "fisher.py")],
        check=True,
        text=True,
        capture_output=True,
        timeout=60,
    )
    memory_result = json.loads(memory.stdout)
    assert memory_result["finite"]
    assert memory_result["delta_kib"] <= 128 * 1024

    candidate()
    reference()
    candidate_times = []
    reference_times = []
    for _ in range(5):
        start = time.perf_counter()
        candidate()
        candidate_times.append(time.perf_counter() - start)
        start = time.perf_counter()
        reference()
        reference_times.append(time.perf_counter() - start)
    assert np.median(candidate_times) <= 0.10 * np.median(reference_times)
