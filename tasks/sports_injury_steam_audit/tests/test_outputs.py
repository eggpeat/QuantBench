import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "injury_audit.py"
    spec = importlib.util.spec_from_file_location("candidate_injury_audit", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "injury_steam_audit.json"
    assert output_path.exists(), "missing outputs/injury_steam_audit.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected


def test_inline_no_edge():
    injury_audit = load_candidate_module()
    game = {
        "event_id": "inline_no_edge",
        "opening_line": -3.0,
        "current_line": -3.0,
        "model_fair_line": -3.0,
        "audit_timestamp": "2026-06-26T15:00:00Z",
        "injury_status": "none",
        "news_timestamp": None,
        "model_relies_on_injury_adjustment": False,
        "line_moves": [
            {"timestamp": "2026-06-26T10:00:00Z", "line": -3.0}
        ]
    }
    result = injury_audit.audit_game(game)
    assert result["classification"] == "no_bet_no_edge"
    assert result["edge_points"] == 0.0


def test_inline_double_count():
    injury_audit = load_candidate_module()
    game = {
        "event_id": "inline_double_count",
        "opening_line": -3.0,
        "current_line": -5.0,
        "model_fair_line": -5.5,
        "audit_timestamp": "2026-06-26T15:00:00Z",
        "injury_status": "confirmed_material",
        "news_timestamp": "2026-06-26T12:00:00Z",
        "model_relies_on_injury_adjustment": True,
        "line_moves": [
            {"timestamp": "2026-06-26T10:00:00Z", "line": -3.0},
            {"timestamp": "2026-06-26T13:00:00Z", "line": -5.0}
        ]
    }
    result = injury_audit.audit_game(game)
    assert result["classification"] == "no_bet_double_count"
    assert result["edge_points"] == -0.5


def test_inline_stale_market():
    injury_audit = load_candidate_module()
    game = {
        "event_id": "inline_stale_market",
        "opening_line": -3.0,
        "current_line": -3.0,
        "model_fair_line": -5.0,
        "audit_timestamp": "2026-06-26T15:00:00Z",
        "injury_status": "confirmed_material",
        "news_timestamp": "2026-06-26T12:00:00Z",
        "model_relies_on_injury_adjustment": True,
        "line_moves": [
            {"timestamp": "2026-06-26T10:00:00Z", "line": -3.0}
        ]
    }
    result = injury_audit.audit_game(game)
    assert result["classification"] == "bet_stale_market"
    assert result["edge_points"] == -2.0


def test_inline_fake_steam():
    injury_audit = load_candidate_module()
    game = {
        "event_id": "inline_fake_steam",
        "opening_line": -3.0,
        "current_line": -3.0,
        "model_fair_line": -3.0,
        "audit_timestamp": "2026-06-26T15:00:00Z",
        "injury_status": "unconfirmed_rumor",
        "news_timestamp": "2026-06-26T12:00:00Z",
        "model_relies_on_injury_adjustment": False,
        "line_moves": [
            {"timestamp": "2026-06-26T10:00:00Z", "line": -3.0},
            {"timestamp": "2026-06-26T11:00:00Z", "line": -4.0},
            {"timestamp": "2026-06-26T13:00:00Z", "line": -3.0}
        ]
    }
    result = injury_audit.audit_game(game)
    assert result["classification"] == "watch_fake_steam"
    assert result["edge_points"] == 0.0


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
