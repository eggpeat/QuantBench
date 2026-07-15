import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def load_candidate():
    path = WORKSPACE / "selector.py"
    spec = importlib.util.spec_from_file_location("candidate_selector", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def naive(R, r, k, ridge):
    selected = []
    remaining = list(range(len(r)))
    for _ in range(k):
        scores = []
        for j in remaining:
            if selected:
                S = np.asarray(selected)
                inv = np.linalg.inv(R[np.ix_(S, S)] + ridge * np.eye(len(S)))
                c = R[j, S]
                den = R[j, j] + ridge - c @ inv @ c
                num = r[j] - c @ inv @ r[S]
            else:
                den, num = R[j, j] + ridge, r[j]
            scores.append(num * num / max(den, np.finfo(float).eps))
        pos = int(np.argmax(np.asarray(scores)))
        selected.append(remaining.pop(pos))
    return selected


def test_public_cli_output():
    subprocess.run([sys.executable, str(WORKSPACE / "selector.py")], cwd=WORKSPACE, check=True)
    output = json.loads((WORKSPACE / "outputs" / "selection.json").read_text())
    with np.load(WORKSPACE / "selector_input.npz") as data:
        expected = naive(data["correlation"], data["target_correlation"], 5, 1e-8)
    assert output == {"selected_indices": expected}


def test_incremental_update_matches_full_inverse_reference():
    rng = np.random.default_rng(1101)
    for p in (3, 7, 15):
        A = rng.normal(size=(p, p)); R = A @ A.T
        R /= np.sqrt(np.outer(np.diag(R), np.diag(R)))
        r = rng.normal(size=p)
        got = load_candidate().greedy_select(R, r, min(5, p), ridge=1e-5)
        assert got == naive(R, r, min(5, p), 1e-5)


def test_ties_use_original_index_order_and_k_zero():
    m = load_candidate()
    R = np.eye(6); r = np.ones(6)
    assert m.greedy_select(R, r, 4) == [0, 1, 2, 3]
    assert m.greedy_select(R, r, 0) == []


def test_near_collinear_ridge_stays_finite_and_distinct():
    m = load_candidate()
    R = np.full((5, 5), 0.999999, dtype=float); np.fill_diagonal(R, 1.0)
    r = np.array([0.7, 0.7, 0.69, -0.2, 0.1])
    result = m.greedy_select(R, r, 4, ridge=1e-6)
    assert len(result) == 4 and len(set(result)) == 4
    assert all(0 <= j < 5 for j in result)


def test_input_validation():
    m = load_candidate(); R = np.eye(3); r = np.ones(3)
    for args in [(np.ones((2, 3)), r, 1, 1e-8), (R, np.ones(2), 1, 1e-8), (R, r, 4, 1e-8), (R, r, 1, -1), (R, np.array([np.nan, 1, 1]), 1, 1e-8)]:
        with np.testing.assert_raises(ValueError): m.greedy_select(*args[:3], ridge=args[3])


def test_incremental_update_beats_repeated_full_inverse():
    rng = np.random.default_rng(1102); p, k = 450, 18
    A = rng.normal(size=(p, p)); R = A @ A.T; R /= np.sqrt(np.outer(np.diag(R), np.diag(R)))
    r = rng.normal(size=p)
    m = load_candidate()
    m.greedy_select(R, r, 2, ridge=1e-5)  # warm-up
    t0 = time.perf_counter(); m.greedy_select(R, r, k, ridge=1e-5); fast = time.perf_counter() - t0
    t0 = time.perf_counter(); naive(R, r, k, 1e-5); slow = time.perf_counter() - t0
    assert fast < slow * 0.75, (fast, slow)
