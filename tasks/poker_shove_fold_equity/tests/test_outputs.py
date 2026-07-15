import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path


WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "poker_ev.py"
    spec = importlib.util.spec_from_file_location("candidate_poker_ev", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "shove_fold.json"
    assert output_path.exists(), "missing outputs/shove_fold.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected


def test_inline_fold_equity_can_make_low_equity_shove_profitable():
    poker_ev = load_candidate_module()
    spot = {
        "spot_id": "inline_fold_equity_bluff",
        "pot": 100.0,
        "risk": 200.0,
        "call": 200.0,
        "equity": 0.10,
        "fold_probability": 0.70,
    }

    assert round(poker_ev.called_ev(100.0, 200.0, 200.0, 0.10), 2) == -150.0
    assert round(poker_ev.shove_ev(100.0, 200.0, 200.0, 0.10, 0.70), 2) == 25.0
    assert round(poker_ev.breakeven_fold_equity(100.0, 200.0, 200.0, 0.10), 6) == 0.6
    assert poker_ev.evaluate_spot(spot) == {
        "spot_id": "inline_fold_equity_bluff",
        "shove_ev": 25.0,
        "breakeven_fold_equity": 0.6,
        "decision": "shove",
    }


def test_inline_positive_called_ev_needs_no_fold_equity():
    poker_ev = load_candidate_module()
    spot = {
        "spot_id": "inline_value_shove",
        "pot": 40.0,
        "risk": 75.0,
        "call": 75.0,
        "equity": 0.70,
        "fold_probability": 0.0,
    }

    assert round(poker_ev.called_ev(40.0, 75.0, 75.0, 0.70), 2) == 58.0
    assert poker_ev.breakeven_fold_equity(40.0, 75.0, 75.0, 0.70) == 0.0
    assert poker_ev.evaluate_spot(spot)["decision"] == "shove"


def test_inline_losing_shove_at_zero_fold_probability_stays_fold():
    poker_ev = load_candidate_module()
    spot = {
        "spot_id": "inline_zero_fold_loser",
        "pot": 100.0,
        "risk": 120.0,
        "call": 120.0,
        "equity": 0.20,
        "fold_probability": 0.0,
    }

    assert round(poker_ev.called_ev(100.0, 120.0, 120.0, 0.20), 2) == -52.0
    assert round(poker_ev.shove_ev(100.0, 120.0, 120.0, 0.20, 0.0), 2) == -52.0
    assert round(poker_ev.breakeven_fold_equity(100.0, 120.0, 120.0, 0.20), 6) == 0.342105
    assert poker_ev.evaluate_spot(spot) == {
        "spot_id": "inline_zero_fold_loser",
        "shove_ev": -52.0,
        "breakeven_fold_equity": 0.342105,
        "decision": "fold",
    }


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
