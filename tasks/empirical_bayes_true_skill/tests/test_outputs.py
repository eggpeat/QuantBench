import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "eb_skill.py"
    spec = importlib.util.spec_from_file_location("candidate_eb_skill", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "skill_rankings.json"
    assert output_path.exists(), "missing outputs/skill_rankings.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected


def test_inline_shrinkage_low_vs_high_volume():
    eb_skill = load_candidate_module()

    # Fitted prior settings for the dataset
    alpha0 = 3.099177
    beta0 = 5.578519

    p_low = {"player_id": "player_low", "successes": 2, "attempts": 2}
    p_high = {"player_id": "player_high", "successes": 700, "attempts": 1000}

    res_low = eb_skill.posterior_summary(p_low, alpha0, beta0)
    res_high = eb_skill.posterior_summary(p_high, alpha0, beta0)

    # The 2/2 player must shrink below the strong 700/1000 performer
    assert res_low["posterior_mean"] < res_high["posterior_mean"]
    assert res_low["posterior_mean"] == 0.477554
    assert res_high["posterior_mean"] == 0.69705


def test_inline_zero_attempts_handled():
    eb_skill = load_candidate_module()

    alpha0 = 3.099177
    beta0 = 5.578519

    p_zero = {"player_id": "player_zero", "successes": 0, "attempts": 0}
    res = eb_skill.posterior_summary(p_zero, alpha0, beta0)

    # Should resolve raw rate to 0.0 and posterior mean to the prior mean
    assert res["raw_rate"] == 0.0
    expected_prior_mean = round(alpha0 / (alpha0 + beta0), 6)
    assert res["posterior_mean"] == expected_prior_mean
    assert res["posterior_mean"] == 0.357143


def test_inline_negative_values_raise_value_error():
    eb_skill = load_candidate_module()

    alpha0 = 3.099177
    beta0 = 5.578519

    # Negative attempts
    try:
        eb_skill.posterior_summary({"player_id": "err", "successes": 2, "attempts": -10}, alpha0, beta0)
    except ValueError:
        pass
    else:
        assert False, "Negative attempts did not raise ValueError"

    # Negative successes
    try:
        eb_skill.posterior_summary({"player_id": "err", "successes": -2, "attempts": 10}, alpha0, beta0)
    except ValueError:
        pass
    else:
        assert False, "Negative successes did not raise ValueError"

    # Successes exceeding attempts
    try:
        eb_skill.posterior_summary({"player_id": "err", "successes": 15, "attempts": 10}, alpha0, beta0)
    except ValueError:
        pass
    else:
        assert False, "Successes > attempts did not raise ValueError"


def test_inline_method_of_moments_fitting():
    eb_skill = load_candidate_module()

    # Normal MoM case: two players with >= 10 attempts
    rows = [
        {"player_id": "p1", "successes": 3, "attempts": 10},
        {"player_id": "p2", "successes": 4, "attempts": 10}
    ]
    alpha, beta = eb_skill.fit_beta_prior(rows)
    assert abs(alpha - 15.575) < 1e-4
    assert abs(beta - 28.925) < 1e-4

    # Zero-variance fallback case
    rows_zero_var = [
        {"player_id": "p1", "successes": 3, "attempts": 10},
        {"player_id": "p2", "successes": 3, "attempts": 10}
    ]
    alpha, beta = eb_skill.fit_beta_prior(rows_zero_var)
    assert abs(alpha - 3.0) < 1e-4
    assert abs(beta - 7.0) < 1e-4


def run_all_tests():
    failures = 0
    for name, test_func in list(globals().items()):
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
