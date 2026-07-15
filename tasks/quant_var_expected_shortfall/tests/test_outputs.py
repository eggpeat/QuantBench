import importlib.util
import json
import math
import os
import subprocess
import sys
import traceback
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))
EXPECTED_PATH = TASK_DIR / "tests" / "expected.json"


def load_candidate_module():
    module_path = WORKSPACE / "risk_metrics.py"
    spec = importlib.util.spec_from_file_location("candidate_risk_metrics", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected_json():
    # Make sure we run the candidate's run_risk.py to populate outputs
    subprocess.run(
        [sys.executable, str(WORKSPACE / "run_risk.py"), str(WORKSPACE)],
        cwd=WORKSPACE,
        check=True,
    )

    output_path = WORKSPACE / "outputs" / "risk_report.json"
    assert output_path.exists(), f"missing outputs/risk_report.json at {output_path}"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    # Simple dictionary float comparison or direct exact match
    assert actual["portfolio_returns"] == expected["portfolio_returns"]
    assert actual["metrics"] == expected["metrics"]


def test_inline_mixed_gain_loss_returns():
    risk_metrics = load_candidate_module()
    # Simple deterministic returns
    # returns of asset_a: [0.01, -0.02, 0.03, -0.04, 0.05, -0.06, 0.07, -0.08, 0.09, -0.10]
    # corresponding portfolio returns (weight 1.0): [0.01, -0.02, 0.03, -0.04, 0.05, -0.06, 0.07, -0.08, 0.09, -0.10]
    # losses: [-0.01, 0.02, -0.03, 0.04, -0.05, 0.06, -0.07, 0.08, -0.09, 0.10]
    # sorted losses: [-0.09, -0.07, -0.05, -0.03, -0.01, 0.02, 0.04, 0.06, 0.08, 0.10]
    # n = 10.
    # For confidence = 0.90:
    # idx = ceil(0.90 * 10) - 1 = 9 - 1 = 8.
    # index 8 is 0.08.
    # losses >= 0.08: [0.08, 0.10]
    # ES: (0.08 + 0.10)/2 = 0.09

    rows = [{"asset_a": r} for r in [0.01, -0.02, 0.03, -0.04, 0.05, -0.06, 0.07, -0.08, 0.09, -0.10]]
    weights = {"asset_a": 1.0}
    p_returns = risk_metrics.portfolio_returns(rows, weights)
    assert p_returns == [0.01, -0.02, 0.03, -0.04, 0.05, -0.06, 0.07, -0.08, 0.09, -0.10]

    var_val, es_val = risk_metrics.historical_var_es(p_returns, 0.90)
    assert math.isclose(var_val, 0.08, abs_tol=1e-9)
    assert math.isclose(es_val, 0.09, abs_tol=1e-9)

    # For confidence = 0.85:
    # idx = ceil(0.85 * 10) - 1 = 9 - 1 = 8. (Since 0.85 * 10 = 8.5 -> ceil is 9)
    # So VaR is also 0.08, ES is also 0.09.
    var_val_85, es_val_85 = risk_metrics.historical_var_es(p_returns, 0.85)
    assert math.isclose(var_val_85, 0.08, abs_tol=1e-9)
    assert math.isclose(es_val_85, 0.09, abs_tol=1e-9)

    # For confidence = 0.80:
    # idx = ceil(0.80 * 10) - 1 = 8 - 1 = 7.
    # index 7 is 0.06.
    # losses >= 0.06: [0.06, 0.08, 0.10]
    # ES: (0.06 + 0.08 + 0.10)/3 = 0.08
    var_val_80, es_val_80 = risk_metrics.historical_var_es(p_returns, 0.80)
    assert math.isclose(var_val_80, 0.06, abs_tol=1e-9)
    assert math.isclose(es_val_80, 0.08, abs_tol=1e-9)


def test_inline_all_positive_returns():
    risk_metrics = load_candidate_module()
    # If all returns are positive (say, 0.05 for all 5 observations), then losses are all -0.05
    # losses: [-0.05, -0.05, -0.05, -0.05, -0.05]
    # VaR should be -0.05. ES should be -0.05.
    p_returns = [0.05, 0.05, 0.05, 0.05, 0.05]
    var_val, es_val = risk_metrics.historical_var_es(p_returns, 0.95)
    assert math.isclose(var_val, -0.05, abs_tol=1e-9)
    assert math.isclose(es_val, -0.05, abs_tol=1e-9)


def test_inline_malformed_confidence_outside_0_1():
    risk_metrics = load_candidate_module()
    p_returns = [0.01, -0.02, 0.03]
    for conf in [0.0, 1.0, -0.5, 1.5]:
        try:
            risk_metrics.historical_var_es(p_returns, conf)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for confidence level {conf}")


def run_all_tests():
    failures = 0
    # Sort them or iterate in order
    for name in sorted(globals().keys()):
        test_func = globals()[name]
        if not name.startswith("test_") or not callable(test_func):
            continue
        try:
            test_func()
        except Exception:
            failures += 1
            print(f"FAIL {name}", file=sys.stderr)
            traceback.print_exc()
        else:
            print(f"PASS {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
