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
    path = WORKSPACE / "knockoffs.py"
    assert path.exists(), "candidate must provide knockoffs.py"
    spec = importlib.util.spec_from_file_location("candidate_knockoffs", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cli_and_public_fixture():
    subprocess.run([sys.executable, str(WORKSPACE / "run_task.py"), str(WORKSPACE)], cwd=WORKSPACE, check=True)
    out = json.loads((WORKSPACE / "outputs" / "knockoffs.json").read_text())
    assert set(out) == {"selected_indices", "selection_frequency", "draw_thresholds", "group_selected"}
    assert len(out["selection_frequency"]) == 8
    assert len(out["draw_thresholds"]) == 10
    assert all(0 <= v <= 1 for v in out["selection_frequency"])
    # This small fixture has too few discoveries for Knockoff+ at q=.1.
    assert out["selected_indices"] == []
    assert all(np.isinf(v) for v in out["draw_thresholds"])
    assert (0 in out["selected_indices"]) == (1 in out["selected_indices"])


def test_reproducibility_and_constant_columns():
    k = load_module()
    rng = np.random.default_rng(100)
    X = rng.normal(size=(160, 6))
    X[:, 5] = 3.0
    y = 2.0 * X[:, 0] - 1.5 * X[:, 1] + rng.normal(size=160)
    a = k.select_fdr(X, y, q=.15, n_draws=5, random_state=99)
    b = k.select_fdr(X, y, q=.15, n_draws=5, random_state=99)
    assert a.selected_indices == b.selected_indices
    np.testing.assert_array_equal(a.selection_frequency, b.selection_frequency)
    np.testing.assert_array_equal(a.draw_thresholds, b.draw_thresholds)
    assert np.isfinite(a.selection_frequency).all()
    assert a.selection_frequency[5] == 0


def test_grouped_selection_and_null_control():
    k = load_module()
    rng = np.random.default_rng(1101)
    X = rng.normal(size=(220, 10))
    y = 2.5 * X[:, 0] - 2.2 * X[:, 1] + rng.normal(size=220)
    groups = ["a", "a", "b", "c", "d", "e", "f", "g", "h", "i"]
    result = k.select_fdr(X, y, q=.2, n_draws=8, random_state=4, feature_groups=groups)
    assert result.selected_indices == sorted(result.selected_indices)
    assert (0 in result.selected_indices) == (1 in result.selected_indices)
    assert all(label in groups for label in result.group_selected)
    null = k.select_fdr(rng.normal(size=(220, 10)), rng.normal(size=220), q=.1, n_draws=8, random_state=5)
    assert len(null.selected_indices) <= 4


def test_invalid_inputs():
    k = load_module()
    with pytest.raises(ValueError): k.select_fdr([[1, 2]], [1], q=.1)
    with pytest.raises(ValueError): k.select_fdr(np.ones((5, 2)), np.ones(4))
    with pytest.raises(ValueError): k.select_fdr(np.ones((5, 2)), np.ones(5), q=1)
    with pytest.raises(ValueError): k.select_fdr(np.ones((5, 2)), np.ones(5), n_draws=0)
    with pytest.raises(ValueError): k.select_fdr(np.ones((5, 2)), np.ones(5), feature_groups=[0])
    with pytest.raises(ValueError): k.select_fdr(np.array([[1, np.nan], [2, 3]]), [0, 1])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
