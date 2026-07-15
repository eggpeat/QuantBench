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
    path = WORKSPACE / "conformal.py"
    assert path.exists(), "candidate must provide conformal.py"
    spec = importlib.util.spec_from_file_location("candidate_conformal", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_cli_and_public_fixture():
    subprocess.run([sys.executable, str(WORKSPACE / "run_task.py"), str(WORKSPACE)], cwd=WORKSPACE, check=True)
    out = json.loads((WORKSPACE / "outputs" / "conformal.json").read_text())
    fixture = json.loads((WORKSPACE / "fixture.json").read_text())
    if "splits" in out:
        split = out["splits"]["ordinary"]
        intervals = out["intervals"]
    else:
        split = out
        intervals = out
    assert {"train_indices", "calibration_indices"} <= set(split)
    assert {"lower", "upper"} <= set(intervals)
    assert "quantile" in out
    assert len(split["train_indices"]) + len(split["calibration_indices"]) == 24
    rank = min(int(np.ceil((len(fixture["scores"]) + 1) * (1 - fixture["alpha"]))), len(fixture["scores"]))
    assert out["quantile"] == sorted(fixture["scores"])[rank - 1]
    assert len(intervals["lower"]) == len(intervals["upper"]) == 8


def test_unweighted_and_weighted_finite_sample_ranks():
    c = load_module()
    scores = np.array([4.0, 1.0, 3.0, 2.0])
    assert c.conformal_quantile(scores, 0.25) == 4.0
    assert c.conformal_quantile(scores, 0.25, np.ones(4)) == 4.0
    assert c.conformal_quantile([1.0, 2.0, 3.0], 0.5, [10.0, 1.0, 1.0]) == 1.0


def test_split_modes_are_reproducible_and_respect_boundaries():
    c = load_module()
    tr1, ca1 = c.calibration_split(10, calibration_fraction=.3, random_state=7)
    tr2, ca2 = c.calibration_split(10, calibration_fraction=.3, random_state=7)
    np.testing.assert_array_equal(tr1, tr2)
    np.testing.assert_array_equal(ca1, ca2)
    assert len(ca1) == 3 and set(tr1).isdisjoint(ca1)

    groups = np.array(["a", "b", "a", "c", "b", "c", "d", "d", "e", "e"])
    tr, ca = c.calibration_split(10, groups=groups, calibration_fraction=.3, random_state=3)
    assert len(ca) >= 3
    assert set(groups[ca]).isdisjoint(set(groups[tr]))
    times = np.array([2, 1, 1, 3, 0])
    tr, ca = c.calibration_split(5, times=times, calibration_fraction=.4)
    np.testing.assert_array_equal(tr, [4, 1, 2])
    np.testing.assert_array_equal(ca, [0, 3])


def test_intervals_floor_broadcast_and_validation():
    c = load_module()
    lo, hi = c.normalized_intervals([0, 1], [0, -2], .5, scale_floor=2)
    np.testing.assert_allclose(lo, [-1, 0])
    np.testing.assert_allclose(hi, [1, 2])
    with pytest.raises(ValueError): c.conformal_quantile([], .1)
    with pytest.raises(ValueError): c.conformal_quantile([1, np.nan], .1)
    with pytest.raises(ValueError): c.conformal_quantile([1, 2], 0)
    with pytest.raises(ValueError): c.conformal_quantile([1, 2], .1, [1, -1])
    with pytest.raises(ValueError): c.calibration_split(4, groups=[0, 1], calibration_fraction=.2)
    with pytest.raises(ValueError): c.calibration_split(4, groups=[0, 1, 0, 1], times=[0, 1, 2, 3])
    with pytest.raises(ValueError): c.normalized_intervals([0], [1], -1)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
