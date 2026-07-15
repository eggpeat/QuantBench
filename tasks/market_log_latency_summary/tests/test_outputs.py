import importlib
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", Path(__file__).parents[1] / "workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    try:
        return importlib.import_module("log_summary")
    finally:
        try:
            sys.path.remove(str(WORKSPACE))
        except ValueError:
            pass


def test_public_fixture_output_matches_expected_snapshot():
    output_path = WORKSPACE / "outputs" / "latency_summary.json"
    assert output_path.exists(), "missing outputs/latency_summary.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)
    assert actual == expected


def test_percentile_rank_on_unsorted_values():
    mod = import_candidate_module()
    # Test nearest_rank_percentile handles unsorted inputs correctly
    unsorted_vals = [90, 10, 50, 30, 70, 20, 80, 40, 60, 100]
    # N = 10
    # p50: ceil(0.5 * 10) = 5 -> index 4 of sorted [10, 20, 30, ... 100] is 50
    assert mod.nearest_rank_percentile(unsorted_vals, 50) == 50
    # p95: ceil(0.95 * 10) = 10 -> index 9 is 100
    assert mod.nearest_rank_percentile(unsorted_vals, 95) == 100
    # p99: ceil(0.99 * 10) = 10 -> index 9 is 100
    assert mod.nearest_rank_percentile(unsorted_vals, 99) == 100
    # p25: ceil(0.25 * 10) = 3 -> index 2 is 30
    assert mod.nearest_rank_percentile(unsorted_vals, 25) == 30

    # Test nearest_rank_percentile handles empty inputs
    assert mod.nearest_rank_percentile([], 50) is None
    assert mod.nearest_rank_percentile([], 95) is None

    # Test nearest_rank_percentile handles single-item inputs
    assert mod.nearest_rank_percentile([42], 50) == 42
    assert mod.nearest_rank_percentile([42], 95) == 42


def test_malformed_lines_ignored():
    mod = import_candidate_module()
    # Write a temporary log file with malformed and valid records
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".jsonl", delete=False) as tmp:
        tmp.write("invalid_json_here\n")
        tmp.write('{"timestamp": "2026-06-26T14:32:05Z", "sportsbook": "DraftKings", "endpoint": "/v1/odds", "status": 200, "latency_ms": 12, "dropped": false}\n')
        tmp.write('{"type": "heartbeat", "timestamp": "2026-06-26T14:32:45Z"}\n')
        tmp.write('{"timestamp": "2026-06-26T14:32:50Z", "sportsbook": "DraftKings", "endpoint": "/v1/odds", "status": 200}\n')
        tmp_name = tmp.name

    try:
        records = mod.parse_records(Path(tmp_name))
        assert len(records) == 1
        assert records[0]["timestamp"] == "2026-06-26T14:32:05Z"
        assert records[0]["sportsbook"] == "DraftKings"
    finally:
        try:
            os.remove(tmp_name)
        except Exception:
            pass


def test_empty_valid_records_returns_empty_summary():
    mod = import_candidate_module()
    # Empty records list should yield empty summary
    assert mod.summarize([]) == []


def run_all_tests():
    failures = 0
    # Use list(globals().items()) to prevent mutation error
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
