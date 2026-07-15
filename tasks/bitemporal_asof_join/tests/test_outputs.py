from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bitemporal import asof_join


def test_public_report() -> None:
    report = json.loads((Path.cwd() / "outputs" / "bitemporal_report.json").read_text())
    assert report["seed"] == 100
    assert [row["revision_id"] for row in report["matches"]] == ["rA1", "rA2", "rB2", None]


def test_system_cutoff_prevents_future_correction_and_is_order_invariant() -> None:
    facts = [{"id": "x", "event": "2024-01-10T00:00:00Z"}]
    revisions = [
        {"id": "x", "vf": "2024-01-01T00:00:00Z", "vt": None, "sf": "2024-01-02T00:00:00Z", "revision_id": "old", "value": 1},
        {"id": "x", "vf": "2024-01-01T00:00:00Z", "vt": None, "sf": "2024-02-01T00:00:00Z", "revision_id": "new", "value": 2},
    ]
    kwargs = dict(entity_key="id", fact_time="event", valid_from="vf", valid_to="vt", system_from="sf")
    early = asof_join(facts, revisions, as_of_system_time="2024-01-15T00:00:00Z", **kwargs)
    late = asof_join(facts, list(reversed(revisions)), as_of_system_time="2024-03-01T00:00:00Z", **kwargs)
    assert early[0]["revision"]["revision_id"] == "old"
    assert late[0]["revision"]["revision_id"] == "new"


def test_half_open_intervals_timezone_and_missing_match() -> None:
    facts = [{"id": 1, "event": "2024-01-02T01:00:00+01:00"}, {"id": 2, "event": "2024-01-01T00:00:00Z"}]
    revisions = [{"id": 1, "vf": "2024-01-01T00:00:00Z", "vt": "2024-01-02T00:00:00Z", "sf": "2023-12-01T00:00:00Z", "revision_id": "expired"}]
    rows = asof_join(facts, revisions, entity_key="id", fact_time="event", valid_from="vf", valid_to="vt", system_from="sf", as_of_system_time="2024-01-10T00:00:00Z")
    assert rows[0]["revision"] is None
    assert rows[1]["revision"] is None


def test_lexicographic_tie_break_and_no_input_mutation() -> None:
    facts = [{"id": "a", "event": "2024-02-01T00:00:00Z"}]
    revisions = [
        {"id": "a", "vf": "2024-01-01T00:00:00Z", "vt": None, "sf": "2024-01-01T00:00:00Z", "revision_id": "a"},
        {"id": "a", "vf": "2024-01-01T00:00:00Z", "vt": None, "sf": "2024-01-01T00:00:00Z", "revision_id": "b"},
    ]
    original = copy.deepcopy((facts, revisions))
    row = asof_join(facts, revisions, entity_key="id", fact_time="event", valid_from="vf", valid_to="vt", system_from="sf", as_of_system_time="2024-02-01T00:00:00Z")[0]
    assert row["revision"]["revision_id"] == "b"
    assert (facts, revisions) == original


def test_duplicate_revision_keys_rejected() -> None:
    revision = {"id": "a", "vf": "2024-01-01", "vt": None, "sf": "2024-01-01", "revision_id": "r"}
    with pytest.raises(ValueError):
        asof_join([], [revision, dict(revision)], entity_key="id", fact_time="event", valid_from="vf", valid_to="vt", system_from="sf", as_of_system_time="2024-02-01")
