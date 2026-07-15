import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "ctr_shrinkage.py"
    spec = importlib.util.spec_from_file_location("candidate_ctr_shrinkage", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "ctr_report.json"
    assert output_path.exists(), "missing outputs/ctr_report.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected


def test_inline_shrinkage_low_vs_high_volume():
    ctr_shrinkage = load_candidate_module()

    # Prior settings (strength K = 100)
    alpha0 = 2.67271
    beta0 = 97.32729

    ad_low = {"ad_id": "ad_low", "impressions": 2, "clicks": 2}
    ad_high = {"ad_id": "ad_high", "impressions": 10000, "clicks": 500}

    res_low = ctr_shrinkage.posterior_summary(ad_low, alpha0, beta0)
    res_high = ctr_shrinkage.posterior_summary(ad_high, alpha0, beta0)

    # 2/2 ad is shrunk below the high-sample performer (approx 4.58% vs 4.98%)
    assert res_low["posterior_mean"] < res_high["posterior_mean"]
    assert res_low["posterior_mean"] == 0.045811
    assert res_high["posterior_mean"] == 0.04977


def test_inline_zero_impression_handled():
    ctr_shrinkage = load_candidate_module()

    alpha0 = 2.67271
    beta0 = 97.32729

    ad_zero = {"ad_id": "ad_zero", "impressions": 0, "clicks": 0}
    res = ctr_shrinkage.posterior_summary(ad_zero, alpha0, beta0)

    # Shrunk back to the global prior mean (0.026727)
    expected_prior_mean = round(alpha0 / (alpha0 + beta0), 6)
    assert res["posterior_mean"] == expected_prior_mean
    assert res["posterior_mean"] == 0.026727


def test_inline_negative_values_raise_value_error():
    ctr_shrinkage = load_candidate_module()

    alpha0 = 2.67271
    beta0 = 97.32729

    # Negative impressions
    try:
        ctr_shrinkage.posterior_summary({"ad_id": "err", "impressions": -10, "clicks": 2}, alpha0, beta0)
    except ValueError:
        pass
    else:
        assert False, "Negative impressions did not raise ValueError"

    # Negative clicks
    try:
        ctr_shrinkage.posterior_summary({"ad_id": "err", "impressions": 10, "clicks": -2}, alpha0, beta0)
    except ValueError:
        pass
    else:
        assert False, "Negative clicks did not raise ValueError"

    # Clicks exceeding impressions
    try:
        ctr_shrinkage.posterior_summary({"ad_id": "err", "impressions": 10, "clicks": 15}, alpha0, beta0)
    except ValueError:
        pass
    else:
        assert False, "Clicks > impressions did not raise ValueError"


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
