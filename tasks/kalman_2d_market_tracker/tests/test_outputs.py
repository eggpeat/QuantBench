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
    module_path = WORKSPACE / "kalman2d.py"
    spec = importlib.util.spec_from_file_location("candidate_kalman2d", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "filtered_states.json"
    assert output_path.exists(), "missing outputs/filtered_states.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected


def test_predict_correctness():
    mod = load_candidate_module()

    x = [10.0, 1.0]
    P = [[2.0, 0.5], [0.5, 1.0]]
    F = [[1.0, 1.0], [0.0, 1.0]]
    Q = [[0.1, 0.0], [0.0, 0.1]]

    x_pred, P_pred = mod.predict(x, P, F, Q)

    # Expected: x_pred: [11.0, 1.0], P_pred: [[4.1, 1.5], [1.5, 1.1]]
    assert len(x_pred) == 2
    assert abs(x_pred[0] - 11.0) < 1e-9
    assert abs(x_pred[1] - 1.0) < 1e-9

    assert len(P_pred) == 2 and len(P_pred[0]) == 2 and len(P_pred[1]) == 2
    assert abs(P_pred[0][0] - 4.1) < 1e-9
    assert abs(P_pred[0][1] - 1.5) < 1e-9
    assert abs(P_pred[1][0] - 1.5) < 1e-9
    assert abs(P_pred[1][1] - 1.1) < 1e-9


def test_update_no_anomaly():
    mod = load_candidate_module()

    x_pred = [11.0, 1.0]
    P_pred = [[4.1, 1.5], [1.5, 1.1]]
    z = [11.5]
    H = [[1.0, 0.0]]
    R = [[0.5]]
    anomaly_threshold = 3.0
    inflation_factor = 2.0

    x_opt, P_opt, anomaly, mahalanobis = mod.update(
        x_pred, P_pred, z, H, R, anomaly_threshold, inflation_factor
    )

    assert anomaly is False
    assert abs(mahalanobis - 0.233126202) < 1e-6
    assert abs(x_opt[0] - 11.44565217) < 1e-6
    assert abs(x_opt[1] - 1.16304348) < 1e-6
    assert abs(P_opt[0][0] - 0.44565217) < 1e-6
    assert abs(P_opt[1][1] - 0.61086957) < 1e-6


def test_update_with_anomaly_inflation():
    mod = load_candidate_module()

    x_pred = [11.0, 1.0]
    P_pred = [[4.1, 1.5], [1.5, 1.1]]
    z = [20.0]
    H = [[1.0, 0.0]]
    R = [[0.5]]
    anomaly_threshold = 3.0
    inflation_factor = 2.0

    x_opt, P_opt, anomaly, mahalanobis = mod.update(
        x_pred, P_pred, z, H, R, anomaly_threshold, inflation_factor
    )

    assert anomaly is True
    assert abs(mahalanobis - 4.196271637) < 1e-6
    assert abs(x_opt[0] - 19.48275862) < 1e-6
    assert abs(x_opt[1] - 4.10344828) < 1e-6
    assert abs(P_opt[0][0] - 0.47126437) < 1e-6
    assert abs(P_opt[1][1] - 1.16551724) < 1e-6


def test_invalid_inputs_raise_value_error():
    mod = load_candidate_module()

    # Test negative variance on diagonal in P
    try:
        mod.predict([10.0, 1.0], [[-1.0, 0.0], [0.0, 1.0]], [[1.0, 1.0], [0.0, 1.0]], [[0.1, 0.0], [0.0, 0.1]])
    except ValueError:
        pass
    else:
        assert False, "Negative P diagonal did not raise ValueError"

    # Test negative variance on diagonal in Q
    try:
        mod.predict([10.0, 1.0], [[1.0, 0.0], [0.0, 1.0]], [[1.0, 1.0], [0.0, 1.0]], [[0.1, 0.0], [0.0, -0.1]])
    except ValueError:
        pass
    else:
        assert False, "Negative Q diagonal did not raise ValueError"

    # Test negative variance on diagonal in R
    try:
        mod.update([11.0, 1.0], [[4.1, 1.5], [1.5, 1.1]], [11.5], [[1.0, 0.0]], [[-0.5]], 3.0, 2.0)
    except ValueError:
        pass
    else:
        assert False, "Negative R diagonal did not raise ValueError"

    # Test negative anomaly_threshold
    try:
        mod.update([11.0, 1.0], [[4.1, 1.5], [1.5, 1.1]], [11.5], [[1.0, 0.0]], [[0.5]], -3.0, 2.0)
    except ValueError:
        pass
    else:
        assert False, "Negative anomaly_threshold did not raise ValueError"

    # Test negative inflation_factor
    try:
        mod.update([11.0, 1.0], [[4.1, 1.5], [1.5, 1.1]], [11.5], [[1.0, 0.0]], [[0.5]], 3.0, -2.0)
    except ValueError:
        pass
    else:
        assert False, "Negative inflation_factor did not raise ValueError"


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
