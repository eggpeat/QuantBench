import importlib.util
import json
import os
import sys
import traceback
import math
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "market_filter.py"
    spec = importlib.util.spec_from_file_location("candidate_market_filter", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "filtered_market.json"
    assert output_path.exists(), "missing outputs/filtered_market.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected


def test_accepted_update_hand_computable():
    # Mean=10.0, Var=2.0, Measurement=12.0, process_var=0.5, measurement_var=1.5, outlier_z=3.0
    # Predict: pred_mean = 10.0, pred_var = 2.0 + 0.5 = 2.5
    # Innovation var: S = 2.5 + 1.5 = 4.0 (std_innovation = 2.0)
    # Threshold: 3.0 * 2.0 = 6.0
    # Diff: |12.0 - 10.0| = 2.0 <= 6.0 -> accepted
    # Kalman gain: K = 2.5 / 4.0 = 0.625
    # Updated mean: 10.0 + 0.625 * 2.0 = 11.25
    # Updated var: (1.0 - 0.625) * 2.5 = 0.375 * 2.5 = 0.9375
    mod = load_candidate_module()
    mean, var, accepted = mod.kalman_step(10.0, 2.0, 12.0, 0.5, 1.5, 3.0)
    assert accepted is True
    assert abs(mean - 11.25) < 1e-9
    assert abs(var - 0.9375) < 1e-9


def test_outlier_rejection_preserves_predicted():
    # Mean=10.0, Var=2.0, Measurement=20.0, process_var=0.5, measurement_var=1.5, outlier_z=3.0
    # Predict: pred_mean = 10.0, pred_var = 2.0 + 0.5 = 2.5
    # Innovation var: S = 2.5 + 1.5 = 4.0 (std_innovation = 2.0)
    # Threshold: 3.0 * 2.0 = 6.0
    # Diff: |20.0 - 10.0| = 10.0 > 6.0 -> rejected
    # Output: pred_mean=10.0, pred_var=2.5
    mod = load_candidate_module()
    mean, var, accepted = mod.kalman_step(10.0, 2.0, 20.0, 0.5, 1.5, 3.0)
    assert accepted is False
    assert abs(mean - 10.0) < 1e-9
    assert abs(var - 2.5) < 1e-9


def test_invalid_negative_variance_raises_value_error():
    mod = load_candidate_module()
    try:
        mod.kalman_step(10.0, -1.0, 12.0, 0.5, 1.5, 3.0)
    except ValueError:
        pass
    else:
        assert False, "Negative variance did not raise ValueError"

    try:
        mod.kalman_step(10.0, 2.0, 12.0, -0.5, 1.5, 3.0)
    except ValueError:
        pass
    else:
        assert False, "Negative process variance did not raise ValueError"

    try:
        mod.kalman_step(10.0, 2.0, 12.0, 0.5, -1.5, 3.0)
    except ValueError:
        pass
    else:
        assert False, "Negative measurement variance did not raise ValueError"

    try:
        mod.kalman_step(10.0, 2.0, 12.0, 0.5, 1.5, -3.0)
    except ValueError:
        pass
    else:
        assert False, "Negative outlier_z did not raise ValueError"


def run_all_tests():
    failures = 0
    for name, test_func in globals().items():
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
