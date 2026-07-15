import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "hand_parser.py"
    spec = importlib.util.spec_from_file_location("candidate_hand_parser", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "parsed_hands.json"
    assert output_path.exists(), "missing outputs/parsed_hands.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert len(actual) == len(expected), f"Length mismatch: got {len(actual)}, expected {len(expected)}"
    for idx, (act, exp) in enumerate(zip(actual, expected)):
        assert act["hand_id"] == exp["hand_id"], f"Hand ID mismatch at index {idx}"
        assert act["valid"] == exp["valid"], f"Validity mismatch for hand {act['hand_id']}: got {act['valid']}, expected {exp['valid']}"
        if exp["valid"]:
            assert act["total_pot"] == exp["total_pot"], f"Pot mismatch for hand {act['hand_id']}"
            assert len(act["actions"]) == len(exp["actions"]), f"Action count mismatch for hand {act['hand_id']}"
            for a_idx, (a_act, a_exp) in enumerate(zip(act["actions"], exp["actions"])):
                assert a_act["player_name"] == a_exp["player_name"], f"Action player mismatch in hand {act['hand_id']} action {a_idx}"
                assert a_act["action_type"] == a_exp["action_type"], f"Action type mismatch in hand {act['hand_id']} action {a_idx}"
                assert float(a_act["amount"]) == float(a_exp["amount"]), f"Action amount mismatch in hand {act['hand_id']} action {a_idx}"
                assert float(a_act["to_amount"]) == float(a_exp["to_amount"]), f"Action to_amount mismatch in hand {act['hand_id']} action {a_idx}"
        else:
            assert len(act["errors"]) > 0, f"Expected validation errors for hand {act['hand_id']}"


def test_inline_all_in():
    hand_parser = load_candidate_module()
    text = """PokerStars Hand #999999001: Hold'em No Limit ($1.00/$2.00 USD) - 2026/06/27 12:00:00 ET
Table 'Test' 9-max Seat #1 is the button
Seat 1: PlayerA ($10.00 in chips)
Seat 2: PlayerB ($100.00 in chips)
PlayerA: posts small blind $1.00
PlayerB: posts big blind $2.00
*** HOLE CARDS ***
PlayerB: raises $18.00 to $20.00
PlayerA: calls $9.00 and is all-in
*** SUMMARY ***
Total pot $20.00 | Rake $0.00
Seat 1: PlayerA collected ($20.00)
"""
    res = hand_parser.parse_hands(text)
    assert len(res) == 1
    assert res[0]["valid"] is True, f"Expected hand to be valid, got errors: {res[0].get('errors')}"
    actions = res[0]["actions"]
    assert len(actions) == 2
    # PlayerB raises
    assert actions[0]["player_name"] == "PlayerB"
    assert actions[0]["action_type"] == "raise"
    assert actions[0]["amount"] == 18.0
    assert actions[0]["to_amount"] == 20.0
    # PlayerA calls all-in
    assert actions[1]["player_name"] == "PlayerA"
    assert actions[1]["action_type"] == "call"
    assert actions[1]["amount"] == 9.0
    assert actions[1]["to_amount"] == 10.0


def test_inline_player_names_as_verbs():
    hand_parser = load_candidate_module()
    text = """PokerStars Hand #999999002: Hold'em No Limit ($1.00/$2.00 USD) - 2026/06/27 12:00:00 ET
Table 'Test' 9-max Seat #1 is the button
Seat 1: checks ($100.00 in chips)
Seat 2: bets ($100.00 in chips)
checks: posts small blind $1.00
bets: posts big blind $2.00
*** HOLE CARDS ***
checks: calls $1.00
bets: checks
*** SUMMARY ***
Total pot $4.00 | Rake $0.00
"""
    res = hand_parser.parse_hands(text)
    assert len(res) == 1
    assert res[0]["valid"] is True
    actions = res[0]["actions"]
    assert len(actions) == 2
    assert actions[0]["player_name"] == "checks"
    assert actions[0]["action_type"] == "call"
    assert actions[1]["player_name"] == "bets"
    assert actions[1]["action_type"] == "check"


def test_inline_chat_messages_containing_verbs():
    hand_parser = load_candidate_module()
    text = """PokerStars Hand #999999003: Hold'em No Limit ($1.00/$2.00 USD) - 2026/06/27 12:00:00 ET
Table 'Test' 9-max Seat #1 is the button
Seat 1: PlayerA ($100.00 in chips)
Seat 2: PlayerB ($100.00 in chips)
PlayerA: posts small blind $1.00
PlayerB: posts big blind $2.00
*** HOLE CARDS ***
PlayerA: "I folds right now"
PlayerA: calls $1.00
PlayerB: "checks"
PlayerB: checks
*** SUMMARY ***
Total pot $4.00 | Rake $0.00
"""
    res = hand_parser.parse_hands(text)
    assert len(res) == 1
    assert res[0]["valid"] is True
    actions = res[0]["actions"]
    assert len(actions) == 2
    assert actions[0]["player_name"] == "PlayerA"
    assert actions[0]["action_type"] == "call"
    assert actions[1]["player_name"] == "PlayerB"
    assert actions[1]["action_type"] == "check"


def test_inline_insufficient_stack_raise():
    hand_parser = load_candidate_module()
    text = """PokerStars Hand #999999004: Hold'em No Limit ($1.00/$2.00 USD) - 2026/06/27 12:00:00 ET
Table 'Test' 9-max Seat #1 is the button
Seat 1: PlayerA ($10.00 in chips)
Seat 2: PlayerB ($100.00 in chips)
PlayerA: posts small blind $1.00
PlayerB: posts big blind $2.00
*** HOLE CARDS ***
PlayerA: raises $14.00 to $15.00
PlayerB: folds
*** SUMMARY ***
Total pot $3.00 | Rake $0.00
"""
    res = hand_parser.parse_hands(text)
    assert len(res) == 1
    assert res[0]["valid"] is False
    assert any("stack" in err.lower() for err in res[0]["errors"])


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
