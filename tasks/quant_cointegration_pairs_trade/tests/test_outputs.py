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
    module_path = WORKSPACE / "pairs.py"
    spec = importlib.util.spec_from_file_location("candidate_pairs", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected_json():
    # Make sure we run the candidate's run_pairs.py to populate outputs
    subprocess.run(
        [sys.executable, str(WORKSPACE / "run_pairs.py"), str(WORKSPACE)],
        cwd=WORKSPACE,
        check=True,
    )

    output_path = WORKSPACE / "outputs" / "pairs_signals.json"
    assert output_path.exists(), f"missing outputs/pairs_signals.json at {output_path}"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    for key in ["hedge_ratio", "residual_mean", "residual_std", "z_score", "adf_t_stat"]:
        assert math.isclose(actual[key], expected[key], abs_tol=1e-5), f"Mismatch in {key}: actual={actual[key]}, expected={expected[key]}"

    assert actual["cointegrated"] == expected["cointegrated"], f"Mismatch in cointegrated: actual={actual['cointegrated']}, expected={expected['cointegrated']}"
    assert actual["signal"] == expected["signal"], f"Mismatch in signal: actual={actual['signal']}, expected={expected['signal']}"


def test_reject_correlated_non_cointegrated_pair():
    pairs_mod = load_candidate_module()

    # Generate two random walks that are highly correlated but not cointegrated
    # x_t = x_{t-1} + e_x
    # y_t = y_{t-1} + e_y
    # where e_x, e_y are highly correlated: e_y = 0.8 * e_x + noise
    # Both x and y are random walks, so their difference y_t - beta * x_t is also a random walk,
    # thus not cointegrated (residuals have a unit root, adf_t_stat should be close to 0)
    import random
    random.seed(12345)

    n = 250
    x = [100.0]
    y = [120.0]
    for _ in range(n-1):
        ex = random.normalvariate(0, 1)
        ey = 0.8 * ex + random.normalvariate(0, 0.2)
        x.append(x[-1] + ex)
        y.append(y[-1] + ey)

    beta = pairs_mod.fit_hedge_ratio(x, y)
    residuals = [y_val - beta * x_val for x_val, y_val in zip(x, y)]
    t_stat = pairs_mod.adf_t_stat(residuals)

    # Critical value of -2.76 is standard for 5% significance level
    # Since they are not cointegrated, t_stat should be > -2.76 (e.g. -1.2)
    assert t_stat > -2.76, f"Expected ADF t-stat to be greater than -2.76 for non-cointegrated pair, got {t_stat}"

    # Double check via analyze_pair
    rows = [{"date": f"D{i}", "X": x[i], "Y": y[i]} for i in range(n)]
    config = {
        "x_col": "X",
        "y_col": "Y",
        "adf_critical_value": -2.76,
        "z_threshold": 2.0
    }
    res = pairs_mod.analyze_pair(rows, config)
    assert res["cointegrated"] is False, f"Expected cointegrated to be False, got {res['cointegrated']}"


def test_cointegrated_pair_rejection_of_unit_root():
    pairs_mod = load_candidate_module()

    # Generate cointegrated pair:
    # x_t = x_{t-1} + e_x
    # z_t = 0.4 * z_{t-1} + e_z (stationary)
    # y_t = 1.5 * x_t + z_t
    import random
    random.seed(54321)

    n = 250
    x = [50.0]
    for _ in range(n-1):
        x.append(x[-1] + random.normalvariate(0, 1))

    z = [0.0]
    for _ in range(n-1):
        z.append(0.4 * z[-1] + random.normalvariate(0, 0.5))

    y = [1.5 * xv + zv for xv, zv in zip(x, z)]

    beta = pairs_mod.fit_hedge_ratio(x, y)
    residuals = [y_val - beta * x_val for x_val, y_val in zip(x, y)]
    t_stat = pairs_mod.adf_t_stat(residuals)

    # Since they are cointegrated, the residuals are stationary, t_stat should be < -2.76 (very negative)
    assert t_stat < -2.76, f"Expected ADF t-stat to be less than -2.76 for cointegrated pair, got {t_stat}"

    rows = [{"date": f"D{i}", "X": x[i], "Y": y[i]} for i in range(n)]
    config = {
        "x_col": "X",
        "y_col": "Y",
        "adf_critical_value": -2.76,
        "z_threshold": 2.0
    }
    res = pairs_mod.analyze_pair(rows, config)
    assert res["cointegrated"] is True, f"Expected cointegrated to be True, got {res['cointegrated']}"


def test_z_score_signals():
    pairs_mod = load_candidate_module()

    config = {
        "x_col": "X",
        "y_col": "Y",
        "adf_critical_value": -2.76,
        "z_threshold": 2.0
    }

    # 1. SELL signal
    x_sell = [float(i) for i in range(1, 11)]
    y_sell = [xv + ev for xv, ev in zip(x_sell, [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 4.5])]
    rows_sell = [{"date": f"D{i}", "X": x_sell[i], "Y": y_sell[i]} for i in range(10)]
    res_sell = pairs_mod.analyze_pair(rows_sell, config)
    assert res_sell["signal"] == "SELL", f"Expected SELL signal, got {res_sell['signal']} (z-score: {res_sell['z_score']})"

    # 2. BUY signal
    y_buy = [xv + ev for xv, ev in zip(x_sell, [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, -5.0])]
    rows_buy = [{"date": f"D{i}", "X": x_sell[i], "Y": y_buy[i]} for i in range(10)]
    res_buy = pairs_mod.analyze_pair(rows_buy, config)
    assert res_buy["signal"] == "BUY", f"Expected BUY signal, got {res_buy['signal']} (z-score: {res_buy['z_score']})"

    # 3. HOLD signal
    y_hold = [xv + ev for xv, ev in zip(x_sell, [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 1.0])]
    rows_hold = [{"date": f"D{i}", "X": x_sell[i], "Y": y_hold[i]} for i in range(10)]
    res_hold = pairs_mod.analyze_pair(rows_hold, config)
    assert res_hold["signal"] == "HOLD", f"Expected HOLD signal, got {res_hold['signal']} (z-score: {res_hold['z_score']})"


def run_all_tests():
    failures = 0
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
