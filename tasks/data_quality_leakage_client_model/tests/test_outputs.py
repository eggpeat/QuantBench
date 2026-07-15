import importlib.util
import json
import os
import sys
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_candidate_module():
    module_path = WORKSPACE / "quality_model.py"
    spec = importlib.util.spec_from_file_location("candidate_quality_model", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_output_matches_expected():
    output_path = WORKSPACE / "outputs" / "model_audit.json"
    assert output_path.exists(), "missing outputs/model_audit.json"

    with output_path.open("r", encoding="utf-8") as fh:
        actual = json.load(fh)
    with EXPECTED_PATH.open("r", encoding="utf-8") as fh:
        expected = json.load(fh)

    assert actual == expected, f"Output mismatch: {actual} vs expected {expected}"


def test_inline_duplicate_ids():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
        "train_validation_cutoff": "2026-05-01T00:00:00Z",
        "stable_attributes": ["signup_date"]
    }
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "signup_date": "2026-01-01", "target_churn": 0},
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "signup_date": "2026-01-01", "target_churn": 0},
        {"row_id": "r2", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "signup_date": "2026-01-01", "target_churn": 0}
    ]
    res = qm.make_validation_split(rows, schema)
    assert res["duplicate_ids_count"] == 1, f"Expected 1 duplicate, got {res['duplicate_ids_count']}"
    assert res["train_ids"] == ["r2"], f"Expected clean train ID ['r2'], got {res['train_ids']}"


def test_inline_unstable_ids():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
        "train_validation_cutoff": "2026-05-01T00:00:00Z",
        "stable_attributes": ["signup_date"]
    }
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "signup_date": "2026-01-01", "target_churn": 0},
        {"row_id": "r2", "client_id": "c1", "timestamp": "2026-01-02T00:00:00Z", "signup_date": "2026-01-02", "target_churn": 0},
        {"row_id": "r3", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "signup_date": "2026-01-01", "target_churn": 0}
    ]
    res = qm.make_validation_split(rows, schema)
    assert res["unstable_ids_count"] == 1, f"Expected 1 unstable entity ID, got {res['unstable_ids_count']}"
    assert res["train_ids"] == ["r3"], f"Expected train ID ['r3'], got {res['train_ids']}"


def test_inline_future_timestamps():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
        "train_validation_cutoff": "2026-05-01T00:00:00Z",
        "stable_attributes": ["signup_date"]
    }
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-07-01T00:00:00Z", "signup_date": "2026-01-01", "target_churn": 0},
        {"row_id": "r2", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "signup_date": "2026-01-01", "target_churn": 0}
    ]
    res = qm.make_validation_split(rows, schema)
    assert res["future_timestamps_count"] == 1, f"Expected 1 future timestamp, got {res['future_timestamps_count']}"
    assert res["train_ids"] == ["r2"], f"Expected train ID ['r2'], got {res['train_ids']}"


def test_inline_high_missingness():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
    }
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "f1": "", "target_churn": 0},
        {"row_id": "r2", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "f1": None, "target_churn": 1},
        {"row_id": "r3", "client_id": "c3", "timestamp": "2026-01-01T00:00:00Z", "f1": "NaN", "target_churn": 0},
        {"row_id": "r4", "client_id": "c4", "timestamp": "2026-01-01T00:00:00Z", "f1": 12.3, "target_churn": 0},
        {"row_id": "r5", "client_id": "c5", "timestamp": "2026-01-01T00:00:00Z", "f1": 45.6, "target_churn": 0},
        {"row_id": "r6", "client_id": "c6", "timestamp": "2026-01-01T00:00:00Z", "f1": 78.9, "target_churn": 1},
        {"row_id": "r7", "client_id": "c7", "timestamp": "2026-01-01T00:00:00Z", "f1": "null", "target_churn": 1}
    ]
    res = qm.audit_dataset(rows, schema)
    assert "f1" in res["high_missingness"], f"Expected 'f1' in high_missingness, got {res['high_missingness']}"


def test_inline_label_leakage_correlation():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
    }
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "f1": 0.0, "target_churn": 0},
        {"row_id": "r2", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "f1": 1.0, "target_churn": 1},
        {"row_id": "r3", "client_id": "c3", "timestamp": "2026-01-01T00:00:00Z", "f1": 0.0, "target_churn": 0},
        {"row_id": "r4", "client_id": "c4", "timestamp": "2026-01-01T00:00:00Z", "f1": 1.0, "target_churn": 1}
    ]
    res = qm.audit_dataset(rows, schema)
    assert "f1" in res["leakage"], f"Expected 'f1' in leakage due to correlation, got {res['leakage']}"


def test_inline_label_leakage_conditional():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
    }
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "f1": "", "target_churn": 0},
        {"row_id": "r2", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "f1": "dissatisfied", "target_churn": 1},
        {"row_id": "r3", "client_id": "c3", "timestamp": "2026-01-01T00:00:00Z", "f1": "", "target_churn": 0},
        {"row_id": "r4", "client_id": "c4", "timestamp": "2026-01-01T00:00:00Z", "f1": "expensive", "target_churn": 1}
    ]
    res = qm.audit_dataset(rows, schema)
    assert "f1" in res["leakage"], f"Expected 'f1' in leakage due to conditional presence, got {res['leakage']}"


def test_inline_target_contamination():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
    }
    # f1 is client-level sum of transaction_amount
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "transaction_amount": 100, "f1": 250, "target_churn": 0},
        {"row_id": "r2", "client_id": "c1", "timestamp": "2026-01-02T00:00:00Z", "transaction_amount": 150, "f1": 250, "target_churn": 0},
        {"row_id": "r3", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "transaction_amount": 50, "f1": 50, "target_churn": 0}
    ]
    res = qm.audit_dataset(rows, schema)
    assert "f1" in res["target_contamination"], f"Expected 'f1' in target_contamination, got {res['target_contamination']}"


def test_inline_future_lookahead():
    qm = load_candidate_module()
    schema = {
        "primary_key": "row_id",
        "entity_id": "client_id",
        "timestamp": "timestamp",
        "target": "target_churn",
        "cutoff_time": "2026-06-27T00:00:00Z",
    }
    # f1 is next row transaction_amount
    rows = [
        {"row_id": "r1", "client_id": "c1", "timestamp": "2026-01-01T00:00:00Z", "transaction_amount": 100, "f1": 150, "target_churn": 0},
        {"row_id": "r2", "client_id": "c1", "timestamp": "2026-01-02T00:00:00Z", "transaction_amount": 150, "f1": 0, "target_churn": 0},
        {"row_id": "r3", "client_id": "c2", "timestamp": "2026-01-01T00:00:00Z", "transaction_amount": 50, "f1": 0, "target_churn": 0}
    ]
    res = qm.audit_dataset(rows, schema)
    assert "f1" in res["leakage"], f"Expected 'f1' in leakage due to future lookahead, got {res['leakage']}"


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
