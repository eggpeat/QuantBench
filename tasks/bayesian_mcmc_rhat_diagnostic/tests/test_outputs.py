import importlib.util
import json
import math
import os
import subprocess
import sys
from pathlib import Path


TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = TASK_DIR / "tests" / "expected.json"


def load_diagnostics_module():
    module_path = WORKSPACE / "diagnostics.py"
    spec = importlib.util.spec_from_file_location("candidate_diagnostics", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected_json(tmp_path):
    subprocess.run(
        [sys.executable, str(WORKSPACE / "run_diagnostics.py")],
        cwd=WORKSPACE,
        check=True,
    )
    with EXPECTED_PATH.open("r", encoding="utf-8") as handle:
        expected = json.load(handle)
    with (WORKSPACE / "outputs" / "rhat.json").open("r", encoding="utf-8") as handle:
        actual = json.load(handle)
    assert actual == expected
    assert set(actual["theta"]) == {
        "rhat", "ess_bulk", "ess_tail", "n_chains", "draws_per_chain"
    }


def test_rank_normalized_split_rhat_and_ess_are_finite():
    diagnostics = load_diagnostics_module()
    result = diagnostics.compute_rhat(
        {
            "stable": [
                [-1.0, 0.0, -1.0, 0.0],
                [-1.0, 0.0, -1.0, 0.0],
            ],
            "drifting": [
                [-1.0, 0.0, 1.0, 2.0],
                [3.0, 4.0, 5.0, 6.0],
            ],
        }
    )
    assert result["stable"]["rhat"] == 1.0
    assert result["stable"]["ess_bulk"] == 8.0
    assert result["stable"]["ess_tail"] == 8.0
    assert result["drifting"]["rhat"] > 1.0
    assert 1.0 <= result["drifting"]["ess_bulk"] <= 8.0


def test_constant_identical_chains_are_well_defined():
    diagnostics = load_diagnostics_module()
    result = diagnostics.compute_rhat({"constant": [[2.0] * 4, [2.0] * 4]})
    assert result["constant"]["rhat"] == 1.0
    assert result["constant"]["ess_bulk"] == 8.0


def test_folded_rhat_detects_scale_mismatch_and_ess_tracks_autocorrelation():
    diagnostics = load_diagnostics_module()
    narrow = [-1.0, 1.0] * 50
    wide = [-10.0, 10.0] * 50
    scale_result = diagnostics.compute_rhat({"scale": [narrow, wide]})["scale"]
    assert scale_result["rhat"] > 1.01

    iid_a = [((i * 37) % 101) / 101.0 for i in range(200)]
    iid_b = [((i * 53 + 7) % 103) / 103.0 for i in range(200)]
    correlated = []
    for phase in (0.0, 0.25):
        chain = []
        state = phase
        for i in range(200):
            innovation = (((i * 29 + int(phase * 100)) % 97) / 97.0) - 0.5
            state = 0.95 * state + innovation
            chain.append(state)
        correlated.append(chain)
    result = diagnostics.compute_rhat({"iid": [iid_a, iid_b], "ar": correlated})
    assert result["ar"]["ess_bulk"] < result["iid"]["ess_bulk"]
    assert result["ar"]["ess_bulk"] < 0.5 * 400


def test_compute_rhat_rejects_malformed_chains():
    diagnostics = load_diagnostics_module()
    malformed_inputs = [
        {"one_chain": [[1.0, 2.0, 3.0, 4.0]]},
        {"too_few": [[1.0, 2.0], [1.0, 2.0]]},
        {"ragged": [[1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0]]},
        {"non_numeric": [[1.0, "bad", 3.0, 4.0], [1.0, 2.0, 3.0, 4.0]]},
        {"non_finite": [[1.0, 2.0, 3.0, math.inf], [1.0, 2.0, 3.0, 4.0]]},
    ]
    for chains in malformed_inputs:
        try:
            diagnostics.compute_rhat(chains)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {chains!r}")
