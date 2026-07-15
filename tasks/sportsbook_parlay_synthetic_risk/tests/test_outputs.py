import importlib
import json
import os
import sys
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    try:
        return importlib.import_module("parlay_risk")
    finally:
        try:
            sys.path.remove(str(WORKSPACE))
        except ValueError:
            pass


def test_public_fixture_output_matches_expected_snapshot():
    output_path = WORKSPACE / "outputs" / "parlay_risk.json"
    assert output_path.exists(), "missing outputs/parlay_risk.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)
    assert actual == expected


def test_candidate_exposes_american_odds_helpers_for_edge_cases():
    mod = import_candidate_module()

    assert round(mod.american_to_decimal(100), 6) == 2.0
    assert round(mod.american_to_decimal(150), 6) == 2.5
    assert round(mod.american_to_decimal(-200), 6) == 1.5
    assert round(mod.american_to_decimal(-110), 6) == 1.909091


def test_inline_one_leg_degeneracy():
    mod = import_candidate_module()
    ticket = {
        "ticket_id": "test_one_leg",
        "stake": 200.0,
        "legs": [
            {"leg_id": "leg_1", "american_odds": -150, "true_win_prob": 0.60}
        ]
    }
    res = mod.evaluate_ticket(ticket)
    assert res["true_rollover_decimal"] == 1.666667
    assert res["offered_decimal"] == 1.666667
    assert res["short_pay_margin"] == 0.0
    assert res["expected_synthetic_handle"] == 200.0
    assert res["expected_return"] == 200.0
    assert res["hold_on_stake"] == 0.0
    assert res["hold_on_synthetic_handle"] == 0.0


def test_inline_fair_rollover():
    mod = import_candidate_module()
    ticket = {
        "ticket_id": "test_fair_rollover",
        "stake": 150.0,
        "legs": [
            {"leg_id": "leg_1", "american_odds": 100, "true_win_prob": 0.50},
            {"leg_id": "leg_2", "american_odds": -150, "true_win_prob": 0.60},
            {"leg_id": "leg_3", "american_odds": -300, "true_win_prob": 0.75}
        ]
    }
    res = mod.evaluate_ticket(ticket)
    assert res["true_rollover_decimal"] == 4.444444
    assert res["offered_decimal"] == 4.444444
    assert res["short_pay_margin"] == 0.0
    assert res["expected_synthetic_handle"] == 450.0
    assert res["expected_return"] == 150.0
    assert res["hold_on_stake"] == 0.0
    assert res["hold_on_synthetic_handle"] == 0.0


def test_inline_short_pay():
    mod = import_candidate_module()
    ticket = {
        "ticket_id": "test_short_pay",
        "stake": 100.0,
        "legs": [
            {"leg_id": "leg_1", "american_odds": -110, "true_win_prob": 0.50},
            {"leg_id": "leg_2", "american_odds": -110, "true_win_prob": 0.50},
            {"leg_id": "leg_3", "american_odds": -110, "true_win_prob": 0.50}
        ],
        "offered_payout": 600.0
    }
    res = mod.evaluate_ticket(ticket)
    assert res["true_rollover_decimal"] == 6.957926
    assert res["offered_decimal"] == 6.0
    assert res["short_pay_margin"] == 0.137674
    assert res["expected_synthetic_handle"] == 286.570248
    assert res["expected_return"] == 75.0
    assert res["hold_on_stake"] == 0.25
    assert res["hold_on_synthetic_handle"] == 0.087239


def test_inline_edge_compounding():
    mod = import_candidate_module()
    ticket = {
        "ticket_id": "test_edge_compounding",
        "stake": 100.0,
        "legs": [
            {"leg_id": "leg_1", "american_odds": 100, "true_win_prob": 0.55},
            {"leg_id": "leg_2", "american_odds": 100, "true_win_prob": 0.55},
            {"leg_id": "leg_3", "american_odds": 100, "true_win_prob": 0.55}
        ]
    }
    res = mod.evaluate_ticket(ticket)
    assert res["true_rollover_decimal"] == 8.0
    assert res["offered_decimal"] == 8.0
    assert res["short_pay_margin"] == 0.0
    assert res["expected_synthetic_handle"] == 331.0
    assert res["expected_return"] == 133.1
    assert res["hold_on_stake"] == -0.331
    assert res["hold_on_synthetic_handle"] == -0.1
