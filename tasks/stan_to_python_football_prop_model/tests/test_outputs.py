import importlib
import json
import os
import sys
from pathlib import Path
import math

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    try:
        return importlib.import_module("football_prop_model")
    finally:
        try:
            sys.path.remove(str(WORKSPACE))
        except ValueError:
            pass


def test_public_fixture_output_matches_expected_snapshot():
    # Invoke candidate module or wrapper to generate outputs in the verifier process
    import runpy
    import os
    import sys

    # Make sure output directory exists
    (WORKSPACE / "outputs").mkdir(exist_ok=True)
    for stale_output in (WORKSPACE / "outputs").glob("*.json"):
        stale_output.unlink()

    old_cwd = os.getcwd()
    old_argv = sys.argv
    try:
        os.chdir(str(WORKSPACE))
        sys.argv = [str(WORKSPACE / "run_model.py"), str(WORKSPACE)]
        runpy.run_path(str(WORKSPACE / "run_model.py"), run_name="__main__")
    except SystemExit:
        # Candidate-controlled wrappers must not be able to terminate the verifier.
        pass
    except Exception:
        # Fallback to direct call in case run_model.py is missing or fails
        try:
            sys.path.insert(0, str(WORKSPACE))
            import football_prop_model
            importlib.reload(football_prop_model)
            football_prop_model.analyze_props(
                str(WORKSPACE / "data" / "passing_tds.csv"),
                str(WORKSPACE / "data" / "prop_bets.csv")
            )
        except Exception:
            pass
        finally:
            try:
                sys.path.remove(str(WORKSPACE))
            except ValueError:
                pass
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)

    output_path = WORKSPACE / "outputs" / "prop_opinions.json"
    assert output_path.exists(), "missing outputs/prop_opinions.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)

    # Check coefficients
    for k in expected["coefficients"]:
        assert abs(actual["coefficients"][k] - expected["coefficients"][k]) < 1e-5, f"coefficient {k} mismatch"

    # Check opinions length
    assert len(actual["prop_opinions"]) == len(expected["prop_opinions"])

    # Check each opinion detail
    for act, exp in zip(actual["prop_opinions"], expected["prop_opinions"]):
        assert act["prop_id"] == exp["prop_id"]
        assert act["passer"] == exp["passer"]
        assert act["opponent"] == exp["opponent"]
        assert abs(act["line"] - exp["line"]) < 1e-7
        assert abs(act["lambda"] - exp["lambda"]) < 1e-5
        assert abs(act["model_prob_over"] - exp["model_prob_over"]) < 1e-5
        assert abs(act["model_prob_under"] - exp["model_prob_under"]) < 1e-5
        assert abs(act["market_be_over"] - exp["market_be_over"]) < 1e-5
        assert abs(act["market_be_under"] - exp["market_be_under"]) < 1e-5
        assert act["fair_odds_over"] == exp["fair_odds_over"]
        assert act["fair_odds_under"] == exp["fair_odds_under"]
        assert abs(act["edge_over"] - exp["edge_over"]) < 1e-5
        assert abs(act["edge_under"] - exp["edge_under"]) < 1e-5
        assert act["opinion"] == exp["opinion"]


def test_candidate_predict_lambda():
    mod = import_candidate_module()
    coeffs = {
        "intercept": -1.0,
        "passer_rating": 0.5,
        "opp_defense_rating": 0.3,
        "is_home": 0.2
    }
    row = {
        "passer_rating": 2.0,
        "opp_defense_rating": 0.5,
        "is_home": 1
    }
    expected_lambda = math.exp(0.35)
    actual_lambda = mod.predict_lambda(coeffs, row)
    assert abs(actual_lambda - expected_lambda) < 1e-7


def test_candidate_poisson_tail():
    mod = import_candidate_module()
    assert abs(mod.poisson_tail(1.5, 1.5) - 0.44217459962892547) < 1e-6
    assert abs(mod.poisson_tail(2.0, 0.5) - 0.8646647167633873) < 1e-6
    assert abs(mod.poisson_tail(0.8, 2.5) - 0.04742259607149024) < 1e-6


def test_candidate_fit_poisson_model_inline():
    mod = import_candidate_module()
    inline_rows = [
        {"passer_rating": 2.0, "opp_defense_rating": 0.5, "is_home": 1, "passing_tds": 2},
        {"passer_rating": 1.5, "opp_defense_rating": 0.0, "is_home": 0, "passing_tds": 1},
        {"passer_rating": 2.5, "opp_defense_rating": -0.2, "is_home": 1, "passing_tds": 3},
        {"passer_rating": 1.0, "opp_defense_rating": 0.8, "is_home": 0, "passing_tds": 1},
        {"passer_rating": 1.8, "opp_defense_rating": 0.3, "is_home": 1, "passing_tds": 2}
    ]
    coeffs = mod.fit_poisson_model(inline_rows)
    expected_coeffs = {
        "intercept": -0.641668600613308,
        "passer_rating": 0.5126589270555963,
        "opp_defense_rating": -0.02114804632513065,
        "is_home": 0.40412938223870076
    }
    for k in expected_coeffs:
        assert abs(coeffs[k] - expected_coeffs[k]) < 1e-5, f"inline coefficient {k} mismatch"
