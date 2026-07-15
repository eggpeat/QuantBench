#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

IMPLEMENTATION = r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

STATE_KEYS = {"version", "last_event_offset", "input_prefix_sha256", "event_ids", "dirty_start_date", "completed_at"}


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("event_time must be a string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("invalid event_time") from exc
    if parsed.tzinfo is None:
        raise ValueError("event_time must include a timezone")
    return parsed.astimezone(timezone.utc)


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _current(output):
    pointer = output / "CURRENT"
    if not pointer.is_file():
        return None, None
    generation_id = pointer.read_text(encoding="utf-8").strip()
    generation = output / ".generations" / generation_id
    state_path = generation / "state.json"
    if not generation_id or not state_path.is_file():
        raise ValueError("invalid CURRENT generation")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if set(state) != STATE_KEYS or state.get("version") != 1:
        raise ValueError("invalid prior state")
    return generation, state


def _cleanup_unreferenced(generations, keep):
    if not generations.is_dir():
        return
    for child in generations.iterdir():
        if child.is_dir() and child != keep:
            shutil.rmtree(child)


def _load_events(raw):
    if raw and not raw.endswith(b"\n"):
        raise ValueError("events file must end at a complete newline")
    by_id = {}
    for number, line in enumerate(raw.splitlines(), 1):
        try:
            row = json.loads(line)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid JSONL row {number}") from exc
        if not isinstance(row, dict) or set(row) != {"event_id", "entity_id", "event_time", "value"}:
            raise ValueError(f"invalid event row {number}")
        if not isinstance(row["event_id"], str) or not row["event_id"] or not isinstance(row["entity_id"], str) or not row["entity_id"]:
            raise ValueError(f"invalid event row {number}")
        when = _instant(row["event_time"])
        if not isinstance(row["value"], (int, float)) or isinstance(row["value"], bool):
            raise ValueError(f"invalid event row {number}")
        normalized = dict(row)
        normalized["_when"] = when
        old = by_id.get(row["event_id"])
        if old is not None:
            comparable_old = {k: v for k, v in old.items() if k != "_when"}
            comparable_new = {k: v for k, v in normalized.items() if k != "_when"}
            if comparable_old != comparable_new:
                raise ValueError("conflicting duplicate event_id")
            continue
        by_id[row["event_id"]] = normalized
    return by_id


def _partition_bytes(events):
    dates = sorted({event["_when"].date().isoformat() for event in events.values()})
    entities = sorted({event["entity_id"] for event in events.values()})
    output = {}
    for day in dates:
        cutoff = datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp() + 86400
        rows = []
        for entity in entities:
            eligible = [event for event in events.values() if event["entity_id"] == entity and event["_when"].timestamp() < cutoff]
            if not eligible:
                continue
            chosen = max(eligible, key=lambda event: (event["_when"], event["event_id"]))
            rows.append({"date": day, "entity_id": entity, "event_id": chosen["event_id"], "event_time": chosen["event_time"], "value_last": chosen["value"]})
        text = "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
        output[day] = text.encode("utf-8")
    return output


def materialize(events_path, output_path):
    events_path = Path(events_path).resolve()
    output = Path(output_path).resolve()
    raw = events_path.read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    generations = output / ".generations"
    generations.mkdir(exist_ok=True)
    prior_generation, prior_state = _current(output)
    _cleanup_unreferenced(generations, prior_generation)
    if prior_state is not None:
        offset = prior_state["last_event_offset"]
        if not isinstance(offset, int) or offset < 0 or offset > len(raw):
            raise ValueError("invalid prior input offset")
        digest = hashlib.sha256(raw[:offset]).hexdigest()
        if digest != prior_state["input_prefix_sha256"]:
            raise ValueError("consumed input prefix changed")
    events = _load_events(raw)
    partition_data = _partition_bytes(events)
    generation_id = uuid.uuid4().hex
    staging = generations / ("." + generation_id + ".tmp")
    final = generations / generation_id
    staging.mkdir()
    partitions = staging / "partitions"
    partitions.mkdir()
    prior_partitions = prior_generation / "partitions" if prior_generation else None
    for day, payload in partition_data.items():
        destination = partitions / f"{day}.jsonl"
        old = prior_partitions / destination.name if prior_partitions else None
        if old is not None and old.is_file() and old.read_bytes() == payload:
            os.link(old, destination)
        else:
            destination.write_bytes(payload)
        with destination.open("rb") as handle:
            os.fsync(handle.fileno())
    _fsync_dir(partitions)
    state = {
        "version": 1,
        "last_event_offset": len(raw),
        "input_prefix_sha256": hashlib.sha256(raw).hexdigest(),
        "event_ids": sorted(events),
        "dirty_start_date": None,
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    state_path = staging / "state.json"
    state_path.write_text(json.dumps(state, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with state_path.open("rb") as handle:
        os.fsync(handle.fileno())
    _fsync_dir(staging)
    os.replace(staging, final)
    _fsync_dir(generations)
    fd, pointer_tmp = tempfile.mkstemp(prefix=".CURRENT.", dir=output)
    try:
        os.write(fd, (generation_id + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(pointer_tmp, output / "CURRENT")
    _fsync_dir(output)
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    materialize(args.events, args.output)


if __name__ == "__main__":
    main()
'''


def main() -> int:
    workspace = Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve()
    path = workspace / "materialize.py"
    path.write_text(IMPLEMENTATION, encoding="utf-8")
    path.chmod(0o755)
    os.chdir(workspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
