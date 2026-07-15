#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

IMPLEMENTATION = r'''"""Bitemporal as-of join."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


def _instant(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid {field}") from exc
    else:
        raise ValueError(f"invalid {field}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def asof_join(facts, revisions, *, entity_key, fact_time, valid_from, valid_to, system_from, as_of_system_time):
    if not all(isinstance(name, str) and name for name in (entity_key, fact_time, valid_from, valid_to, system_from)):
        raise ValueError("field names must be nonempty strings")
    cutoff = _instant(as_of_system_time, "as_of_system_time")
    prepared = []
    duplicate_keys = set()
    for position, revision in enumerate(revisions):
        if not isinstance(revision, dict) or entity_key not in revision or valid_from not in revision or system_from not in revision:
            raise ValueError("invalid revision")
        start = _instant(revision[valid_from], valid_from)
        end = None if revision.get(valid_to) is None else _instant(revision[valid_to], valid_to)
        known = _instant(revision[system_from], system_from)
        if end is not None and end <= start:
            raise ValueError("valid_to must follow valid_from")
        revision_id = revision.get("revision_id")
        key = (revision[entity_key], start, end, known, revision_id)
        if key in duplicate_keys:
            raise ValueError("duplicate revision key")
        duplicate_keys.add(key)
        prepared.append((revision, start, end, known, revision_id, position))
    result = []
    for fact in facts:
        if not isinstance(fact, dict) or entity_key not in fact or fact_time not in fact:
            raise ValueError("invalid fact")
        when = _instant(fact[fact_time], fact_time)
        candidates = []
        for revision, start, end, known, revision_id, position in prepared:
            if revision[entity_key] == fact[entity_key] and start <= when and (end is None or when < end) and known <= cutoff:
                candidates.append((known, start, str(revision_id), position, revision))
        chosen = max(candidates, key=lambda item: item[:3])[-1] if candidates else None
        row = dict(fact)
        row["revision"] = dict(chosen) if chosen is not None else None
        result.append(row)
    return result
'''


def main() -> int:
    workspace = Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve()
    (workspace / "bitemporal.py").write_text(IMPLEMENTATION, encoding="utf-8")
    os.chdir(workspace)
    sys.path.insert(0, str(workspace))
    from run_bitemporal import main as run
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
