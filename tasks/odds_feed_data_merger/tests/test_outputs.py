import sys
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))


def load_json(path):
    with path.open() as handle:
        return json.load(handle)


def test_merged_odds_matches_expected_snapshot():
    expected = load_json(ROOT / "expected.json")["merged_odds"]
    actual = load_json(WORKSPACE / "outputs" / "merged_odds.json")
    assert actual == expected


def test_conflicts_match_expected_snapshot():
    expected = load_json(ROOT / "expected.json")["conflicts"]
    actual = load_json(WORKSPACE / "outputs" / "conflicts.json")
    assert actual == expected


def test_output_records_use_required_shapes_only():
    merged = load_json(WORKSPACE / "outputs" / "merged_odds.json")
    conflicts = load_json(WORKSPACE / "outputs" / "conflicts.json")

    merged_keys = {
        "event_id",
        "home_team",
        "away_team",
        "market",
        "book",
        "outcome",
        "odds",
        "line",
        "timestamp",
        "source_priority",
        "source_file",
    }
    conflict_keys = {
        "event_id",
        "home_team",
        "away_team",
        "market",
        "book",
        "outcome",
        "winning",
        "rejected",
        "reason",
    }
    detail_keys = {"odds", "line", "timestamp", "source_priority", "source_file"}

    assert all(set(record) == merged_keys for record in merged)
    assert all(set(conflict) == conflict_keys for conflict in conflicts)
    assert all(set(conflict["winning"]) == detail_keys for conflict in conflicts)
    assert all(set(conflict["rejected"]) == detail_keys for conflict in conflicts)


def test_inline_normalization_and_conflict_edge_case():
    sys.path.insert(0, str(WORKSPACE))
    try:
        from merge_odds import canonical_name, canonical_market, normalize_record, merge_records
    except ImportError as e:
        raise AssertionError(f"Could not import from merge_odds: {e}")

    aliases = {"N.Y. Knicks": "New York Knicks", "BOS": "Boston Celtics", "Knicks": "New York Knicks"}

    # Test canonical_name
    assert canonical_name(" N.Y. Knicks ", aliases) == "New York Knicks"
    assert canonical_name("BOS", aliases) == "Boston Celtics"
    assert canonical_name("Knicks", aliases) == "New York Knicks"

    # Test canonical_market
    assert canonical_market("ML") == "moneyline"
    assert canonical_market("h2h") == "moneyline"
    assert canonical_market("over_under") == "total"

    # Raw row shapes resembling the inputs before normalization
    raw_rows = [
        {
            "event_id": "event_1",
            "home_team": " N.Y. Knicks ",
            "away_team": "BOS",
            "market": "ML",
            "book": "book_a",
            "outcome": "Knicks",
            "odds": -121,
            "line": None,
            "timestamp": "2026-01-01T00:05:00Z",
            "source_priority": 4,
        },
        {
            "event_id": "event_1",
            "home_team": "New York Knicks",
            "away_team": "Boston Celtics",
            "market": "h2h",
            "book": "book_a",
            "outcome": "New York Knicks",
            "odds": -125,
            "line": None,
            "timestamp": "2026-01-01T00:06:00Z",
            "source_priority": 4,
        },
    ]

    norm_rows = [
        normalize_record(raw_rows[0], "b.jsonl", 1, aliases),
        normalize_record(raw_rows[1], "a.csv", 9, aliases),
    ]

    assert norm_rows[0]["home_team"] == "New York Knicks"
    assert norm_rows[0]["away_team"] == "Boston Celtics"
    assert norm_rows[0]["market"] == "moneyline"
    assert norm_rows[0]["outcome"] == "New York Knicks"

    merged, conflicts = merge_records(norm_rows)
    assert len(merged) == 1
    assert len(conflicts) == 1

    winner = merged[0]
    conflict = conflicts[0]

    assert winner["odds"] == -125
    assert conflict["rejected"]["odds"] == -121
    assert (winner["odds"], winner["line"]) != (conflict["rejected"]["odds"], conflict["rejected"]["line"])
