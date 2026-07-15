import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "side_pots.py"
    spec = importlib.util.spec_from_file_location("candidate_side_pots", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "settlements.json"
    assert output_path.exists(), "missing outputs/settlements.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected, f"Expected {expected}, got {actual}"


def test_inline_hidden_hand_3_allin_levels_and_chop_odd_chips():
    side_pots = load_candidate_module()
    hidden_hand = {
        "hand_id": "inline_hidden_001",
        "players": [
            {"seat": 1, "name": "Player A", "bet": 100, "folded": False, "hand_strength": 90},
            {"seat": 2, "name": "Player B", "bet": 150, "folded": False, "hand_strength": 90},
            {"seat": 3, "name": "Player C", "bet": 200, "folded": False, "hand_strength": 80},
            {"seat": 4, "name": "Player D", "bet": 250, "folded": False, "hand_strength": 90},
            {"seat": 5, "name": "Player E", "bet": 300, "folded": False, "hand_strength": 70}
        ]
    }
    res = side_pots.settle_hand(hidden_hand)
    assert res["hand_id"] == "inline_hidden_001"
    assert res["payouts"] == {
        "Player A": 167,
        "Player B": 267,
        "Player C": 0,
        "Player D": 516,
        "Player E": 50
    }
    assert res["conservation"] == {
        "total_bets": 1000,
        "total_payouts": 1000,
        "is_conserved": True
    }


def test_inline_hidden_uncontested_hand():
    side_pots = load_candidate_module()
    uncontested_hand = {
        "hand_id": "inline_hidden_uncontested",
        "players": [
            {"seat": 1, "name": "Player A", "bet": 100, "folded": False, "hand_strength": 10},
            {"seat": 2, "name": "Player B", "bet": 200, "folded": True, "hand_strength": None},
            {"seat": 3, "name": "Player C", "bet": 50, "folded": True, "hand_strength": None}
        ]
    }
    res = side_pots.settle_hand(uncontested_hand)
    assert res["hand_id"] == "inline_hidden_uncontested"
    assert res["payouts"] == {
        "Player A": 250,
        "Player B": 100,
        "Player C": 0
    }
    assert res["conservation"] == {
        "total_bets": 350,
        "total_payouts": 350,
        "is_conserved": True
    }


def test_inline_hidden_three_way_chop():
    side_pots = load_candidate_module()
    three_way_chop_hand = {
        "hand_id": "inline_hidden_three_way_chop",
        "players": [
            {"seat": 2, "name": "Bob", "bet": 100, "folded": False, "hand_strength": 50},
            {"seat": 4, "name": "Dave", "bet": 100, "folded": False, "hand_strength": 50},
            {"seat": 7, "name": "Grace", "bet": 100, "folded": False, "hand_strength": 50},
            {"seat": 1, "name": "Alice", "bet": 101, "folded": True, "hand_strength": None}
        ]
    }
    res = side_pots.settle_hand(three_way_chop_hand)
    assert res["hand_id"] == "inline_hidden_three_way_chop"
    assert res["payouts"] == {
        "Bob": 134,
        "Dave": 133,
        "Grace": 133,
        "Alice": 1
    }
    assert res["conservation"] == {
        "total_bets": 401,
        "total_payouts": 401,
        "is_conserved": True
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
