from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def run(events: Path, output: Path, check: bool = True):
    return subprocess.run([sys.executable, str(Path.cwd() / "materialize.py"), "--events", str(events), "--output", str(output)], check=check, capture_output=True, text=True)


def current(output: Path):
    generation_id = (output / "CURRENT").read_text().strip()
    generation = output / ".generations" / generation_id
    return generation_id, generation, json.loads((generation / "state.json").read_text())


def rows(generation: Path, day: str):
    return [json.loads(line) for line in (generation / "partitions" / f"{day}.jsonl").read_text().splitlines()]


def test_initial_generation_state_and_last_value(tmp_path: Path) -> None:
    source = Path.cwd() / "events.jsonl"
    output = tmp_path / "features"
    run(source, output)
    _, generation, state = current(output)
    assert set(state) == {"version", "last_event_offset", "input_prefix_sha256", "event_ids", "dirty_start_date", "completed_at"}
    raw = source.read_bytes()
    assert state["version"] == 1 and state["last_event_offset"] == len(raw)
    assert state["input_prefix_sha256"] == hashlib.sha256(raw).hexdigest()
    assert state["event_ids"] == ["e001", "e002", "e003"] and state["dirty_start_date"] is None
    assert {row["entity_id"]: row["value_last"] for row in rows(generation, "2024-01-02")} == {"alpha": 2.5, "beta": 5.0}


def test_append_late_event_recomputes_and_hardlinks_unchanged(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text((Path.cwd() / "events.jsonl").read_text())
    output = tmp_path / "features"
    run(events, output)
    first_id, first, _ = current(output)
    first_inode = (first / "partitions" / "2024-01-01.jsonl").stat().st_ino
    with events.open("a") as handle:
        handle.write('{"event_id":"e004","entity_id":"alpha","event_time":"2024-01-02T11:00:00Z","value":7.0}\n')
    run(events, output)
    second_id, second, state = current(output)
    assert second_id != first_id
    assert (second / "partitions" / "2024-01-01.jsonl").stat().st_ino == first_inode
    assert {row["entity_id"]: row["value_last"] for row in rows(second, "2024-01-02")}["alpha"] == 7.0
    assert state["event_ids"][-1] == "e004"


def test_prefix_mutation_is_rejected_and_current_unchanged(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text((Path.cwd() / "events.jsonl").read_text())
    output = tmp_path / "features"
    run(events, output)
    before = (output / "CURRENT").read_text()
    events.write_text(events.read_text().replace('"value":1.0', '"value":9.0'))
    result = run(events, output, check=False)
    assert result.returncode != 0
    assert (output / "CURRENT").read_text() == before


def test_duplicate_ids_deduplicate_but_conflicts_reject(tmp_path: Path) -> None:
    line = '{"event_id":"x","entity_id":"a","event_time":"2024-01-01T00:00:00Z","value":1}\n'
    events = tmp_path / "events.jsonl"
    events.write_text(line + line)
    output = tmp_path / "features"
    run(events, output)
    assert current(output)[2]["event_ids"] == ["x"]
    conflict = tmp_path / "conflict.jsonl"
    conflict.write_text(line + line.replace('"value":1', '"value":2'))
    assert run(conflict, tmp_path / "bad", check=False).returncode != 0


def test_tie_breaks_by_event_id_and_cleans_old_unreferenced_next_run(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text('{"event_id":"a","entity_id":"e","event_time":"2024-01-01T00:00:00Z","value":1}\n{"event_id":"z","entity_id":"e","event_time":"2024-01-01T00:00:00Z","value":2}\n')
    output = tmp_path / "features"
    run(events, output)
    first_id, first, _ = current(output)
    assert rows(first, "2024-01-01")[0]["value_last"] == 2
    run(events, output)
    second_id, _, _ = current(output)
    assert second_id != first_id
    run(events, output)
    assert not (output / ".generations" / first_id).exists()
    assert (output / ".generations" / second_id).exists()
