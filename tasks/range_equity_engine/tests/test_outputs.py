import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")

def load_candidate_module():
    module_path = WORKSPACE / "range_equity.py"
    spec = importlib.util.spec_from_file_location("candidate_range_equity", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "equity.json"
    assert output_path.exists(), "missing outputs/equity.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    actual_dict = {s["scenario_id"]: s for s in actual.get("scenarios", [])}
    expected_dict = {s["scenario_id"]: s for s in expected.get("scenarios", [])}

    for sid, exp_data in expected_dict.items():
        assert sid in actual_dict, f"Scenario {sid} missing in output"
        act_data = actual_dict[sid]
        for key in ["p1_equity", "p2_equity", "tie_probability"]:
            assert abs(act_data[key] - exp_data[key]) <= 1e-4, \
                f"Mismatch for {sid} {key}: expected {exp_data[key]}, got {act_data[key]}"

def test_inline_card_parsing():
    range_equity = load_candidate_module()
    card1 = range_equity.parse_card("Ah")
    card2 = range_equity.parse_card("2d")
    assert card1 is not None
    assert card2 is not None

def test_inline_hand_evaluation_comparisons():
    range_equity = load_candidate_module()

    rf = ["Ah", "Kh", "Qh", "Jh", "Th", "2c", "3d"]
    fh = ["Ac", "Ad", "As", "Kc", "Kd", "7s", "2h"]
    fl = ["Ah", "Qh", "Th", "7h", "2h", "2c", "3d"]
    st = ["As", "Kd", "Qc", "Js", "Td", "2c", "3d"]
    hc = ["Ah", "Kd", "Qc", "7s", "5d", "3c", "2s"]

    score_rf = range_equity.evaluate_hand(rf)
    score_fh = range_equity.evaluate_hand(fh)
    score_fl = range_equity.evaluate_hand(fl)
    score_st = range_equity.evaluate_hand(st)
    score_hc = range_equity.evaluate_hand(hc)

    assert score_rf > score_fh, "Royal flush should beat full house"
    assert score_fh > score_fl, "Full house should beat flush"
    assert score_fl > score_st, "Flush should beat straight"
    assert score_st > score_hc, "Straight should beat high card"

def test_inline_tie_handling():
    range_equity = load_candidate_module()
    p1 = ["AhKd"]
    p2 = ["AsKc"]
    board = ["Qd", "Jd", "Th", "5c", "2s"]
    p1_eq, p2_eq, tie_prob = range_equity.calculate_equity(p1, p2, board)
    assert abs(p1_eq - 0.5) < 1e-4
    assert abs(p2_eq - 0.5) < 1e-4
    assert abs(tie_prob - 1.0) < 1e-4

def run_all_tests():
    failures = 0
    tests = [
        test_public_output_matches_expected,
        test_inline_card_parsing,
        test_inline_hand_evaluation_comparisons,
        test_inline_tie_handling
    ]
    for test in tests:
        try:
            print(f"Running {test.__name__}...")
            test()
            print(f"{test.__name__} passed.")
        except Exception as e:
            print(f"{test.__name__} FAILED:")
            traceback.print_exc()
            failures += 1
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(run_all_tests())
