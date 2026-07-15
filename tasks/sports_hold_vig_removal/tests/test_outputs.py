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
        return importlib.import_module("no_vig_kelly")
    finally:
        try:
            sys.path.remove(str(WORKSPACE))
        except ValueError:
            pass


def test_public_fixture_output_matches_expected_snapshot():
    output_path = WORKSPACE / "outputs" / "no_vig_kelly.json"
    assert output_path.exists(), "missing outputs/no_vig_kelly.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)
    assert actual == expected


def test_candidate_exposes_american_odds_helpers_for_edge_cases():
    mod = import_candidate_module()

    assert round(mod.american_to_decimal(150), 6) == 2.5
    assert round(mod.implied_probability(150), 6) == 0.4

    assert round(mod.american_to_decimal(-200), 6) == 1.5
    assert round(mod.implied_probability(-200), 6) == 0.666667

    assert round(mod.american_to_decimal(100), 6) == 2.0
    assert round(mod.implied_probability(100), 6) == 0.5


def test_inline_two_way_market_uses_offered_odds_for_kelly():
    mod = import_candidate_module()
    market = {
        "market_id": "inline_plus_money_edge",
        "outcomes": [
            {"name": "Plus side", "american_odds": 200, "model_probability": 0.40},
            {"name": "Minus side", "american_odds": -220, "model_probability": 0.60},
        ],
    }

    result = mod.analyze_market(market, bankroll=500.0, fractional_kelly=0.5, high_hold_threshold=0.2)

    assert result["market_id"] == "inline_plus_money_edge"
    assert result["sum_implied"] == 1.020833
    assert result["overround"] == 0.020833
    assert result["hold"] == 0.020408
    assert result["high_hold"] is False

    plus_side = result["outcomes"][0]
    assert plus_side["decimal_odds"] == 3.0
    assert plus_side["implied_probability"] == 0.333333
    assert plus_side["no_vig_probability"] == 0.326531
    assert plus_side["ev_per_dollar"] == 0.2
    assert plus_side["full_kelly"] == 0.1
    assert plus_side["recommended_stake"] == 25.0
    assert plus_side["recommendation"] == "bet"

    minus_side = result["outcomes"][1]
    assert minus_side["decimal_odds"] == 1.454545
    assert minus_side["implied_probability"] == 0.6875
    assert minus_side["no_vig_probability"] == 0.673469
    assert minus_side["ev_per_dollar"] == -0.127273
    assert minus_side["full_kelly"] == 0.0
    assert minus_side["recommended_stake"] == 0.0
    assert minus_side["recommendation"] == "no_bet"


def test_inline_high_hold_market_forces_no_bet_even_with_positive_edge():
    mod = import_candidate_module()
    market = {
        "market_id": "inline_high_hold_three_way",
        "outcomes": [
            {"name": "Home", "american_odds": 100, "model_probability": 0.70},
            {"name": "Draw", "american_odds": 100, "model_probability": 0.20},
            {"name": "Away", "american_odds": 100, "model_probability": 0.10},
        ],
    }

    result = mod.analyze_market(market, bankroll=1000.0, fractional_kelly=0.25, high_hold_threshold=0.2)

    assert result["sum_implied"] == 1.5
    assert result["overround"] == 0.5
    assert result["hold"] == 0.333333
    assert result["high_hold"] is True
    assert all(outcome["recommendation"] == "no_bet_high_hold" for outcome in result["outcomes"])
    assert all(outcome["recommended_stake"] == 0.0 for outcome in result["outcomes"])
    assert result["outcomes"][0]["ev_per_dollar"] == 0.4
    assert result["outcomes"][0]["full_kelly"] == 0.4
