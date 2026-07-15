import importlib
import json
import os
import sys
from pathlib import Path
from decimal import Decimal

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    try:
        return importlib.import_module("reconcile")
    finally:
        try:
            sys.path.remove(str(WORKSPACE))
        except ValueError:
            pass


def test_public_fixture_output_matches_expected_snapshot():
    output_path = WORKSPACE / "outputs" / "reconciliation_report.json"
    assert output_path.exists(), "missing outputs/reconciliation_report.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)
    assert actual == expected


def test_candidate_exposes_helper_functions_and_behaves_correctly():
    mod = import_candidate_module()

    # Test normalize_correlation_id
    assert mod.normalize_correlation_id(" txn_abc  ") == "abc"
    assert mod.normalize_correlation_id("tx_xyz") == "xyz"
    assert mod.normalize_correlation_id("TXN_123") == "123"
    assert mod.normalize_correlation_id("txn-999") == "999"
    assert mod.normalize_correlation_id("12345") == "12345"

    # Test calculate_expected_fee (banker's rounding half-even)
    assert mod.calculate_expected_fee(Decimal("100.00"), "card") == Decimal("2.80")
    assert mod.calculate_expected_fee(Decimal("1.00"), "card") == Decimal("0.32")
    assert mod.calculate_expected_fee(Decimal("3.00"), "card") == Decimal("0.38")
    assert mod.calculate_expected_fee(Decimal("0.50"), "ach") == Decimal("0.16")
    assert mod.calculate_expected_fee(Decimal("1.50"), "ach") == Decimal("0.16")
    assert mod.calculate_expected_fee(Decimal("600.00"), "ach") == Decimal("5.00")

    # Test parse_iso_to_utc_date
    _, date1 = mod.parse_iso_to_utc_date("2026-06-27T10:00:00-04:00")
    assert date1 == "2026-06-27"
    _, date2 = mod.parse_iso_to_utc_date("2026-06-27T22:00:00-04:00")
    assert date2 == "2026-06-28"
    _, date3 = mod.parse_iso_to_utc_date("2026-06-28T02:00:00Z")
    assert date3 == "2026-06-28"
