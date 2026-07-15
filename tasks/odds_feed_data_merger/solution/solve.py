#!/usr/bin/env python3
"""Reference solution for odds_feed_data_merger."""

import sys
import subprocess
from pathlib import Path

MERGE_ODDS_CODE = """\"\"\"Merge odds feeds into deterministic canonical odds and conflict reports.

This module provides functions to normalize, load, merge, and output odds data
from multiple heterogeneous sources.
\"\"\"

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

MARKET_ALIASES = {
    "moneyline": "moneyline",
    "ml": "moneyline",
    "h2h": "moneyline",
    "spread": "spread",
    "point_spread": "spread",
    "point spread": "spread",
    "total": "total",
    "totals": "total",
    "over_under": "total",
    "over/under": "total",
}

OUTPUT_FIELDS = [
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
]

DETAIL_FIELDS = ["odds", "line", "timestamp", "source_priority", "source_file"]


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def parse_int(value: Any) -> int:
    return int(clean(value))


def parse_line(value: Any) -> int | float | None:
    if value is None:
        return None
    text = clean(value)
    if text == "":
        return None
    number = float(text)
    if number.is_integer():
        return int(number)
    return number


def canonical_market(value: str) -> str:
    key = clean(value).lower()
    if key not in MARKET_ALIASES:
        return clean(value).lower()
    return MARKET_ALIASES[key]


def canonical_name(value: str, aliases: Dict[str, str]) -> str:
    text = clean(value)
    return aliases.get(text, text)


def timestamp_rank(value: str) -> float:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc).timestamp()


def normalize_record(
    raw: Dict[str, Any], source_file: str, row_number: int, aliases: Dict[str, str]
) -> Dict[str, Any]:
    event_id = raw.get("event_id", raw.get("event"))
    home = raw.get("home_team", raw.get("home"))
    away = raw.get("away_team", raw.get("away"))
    market = raw.get("market", raw.get("market_name"))
    book = raw.get("book", raw.get("sportsbook"))
    outcome = raw.get("outcome", raw.get("selection"))
    odds = raw.get("odds", raw.get("american_odds", raw.get("price")))
    line = raw.get("line", raw.get("points"))
    timestamp = raw.get("timestamp", raw.get("as_of", raw.get("observed_at")))

    return {
        "event_id": clean(event_id),
        "home_team": canonical_name(home, aliases),
        "away_team": canonical_name(away, aliases),
        "market": canonical_market(market),
        "book": clean(book),
        "outcome": canonical_name(outcome, aliases),
        "odds": parse_int(odds),
        "line": parse_line(line),
        "timestamp": clean(timestamp),
        "source_priority": parse_int(raw["source_priority"]),
        "source_file": source_file,
        "_row_number": row_number,
    }


def load_records(workspace_path: Path) -> List[Dict[str, Any]]:
    aliases = json.loads((workspace_path / "team_aliases.json").read_text())
    feeds = workspace_path / "feeds"
    records: List[Dict[str, Any]] = []

    json_path = feeds / "json_feed.json"
    payload = json.loads(json_path.read_text())
    for index, raw in enumerate(payload["records"], start=1):
        records.append(normalize_record(raw, json_path.name, index, aliases))

    csv_path = feeds / "csv_feed.csv"
    with csv_path.open(newline="") as handle:
        for index, raw in enumerate(csv.DictReader(handle), start=1):
            records.append(normalize_record(raw, csv_path.name, index, aliases))

    jsonl_path = feeds / "jsonl_feed.jsonl"
    with jsonl_path.open() as handle:
        for index, line in enumerate(handle, start=1):
            if line.strip():
                records.append(normalize_record(json.loads(line), jsonl_path.name, index, aliases))

    return records


def canonical_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return tuple(record[field] for field in ["event_id", "home_team", "away_team", "market", "book", "outcome"])


def exact_duplicate_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return canonical_key(record) + tuple(record[field] for field in DETAIL_FIELDS)


def winner_sort_key(record: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        -record["source_priority"],
        -timestamp_rank(record["timestamp"]),
        record["source_file"],
        record["_row_number"],
    )


def public_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {field: record[field] for field in OUTPUT_FIELDS}


def detail(record: Dict[str, Any]) -> Dict[str, Any]:
    return {field: record[field] for field in DETAIL_FIELDS}


def merge_records(
    records: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    grouped: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    seen_exact: set[Tuple[Any, ...]] = set()

    for record in records:
        duplicate_key = exact_duplicate_key(record)
        if duplicate_key in seen_exact:
            continue
        seen_exact.add(duplicate_key)
        grouped[canonical_key(record)].append(record)

    merged: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []

    for key, group in grouped.items():
        winner = sorted(group, key=winner_sort_key)[0]
        merged.append(public_record(winner))
        for rejected in group:
            if rejected is winner:
                continue
            if (rejected["odds"], rejected["line"]) == (winner["odds"], winner["line"]):
                continue
            conflict = {
                "event_id": key[0],
                "home_team": key[1],
                "away_team": key[2],
                "market": key[3],
                "book": key[4],
                "outcome": key[5],
                "winning": detail(winner),
                "rejected": detail(rejected),
                "reason": "lower_priority_or_older_timestamp",
            }
            conflicts.append(conflict)

    merged.sort(key=lambda item: tuple(item[field] for field in ["event_id", "home_team", "away_team", "market", "book", "outcome"]))
    conflicts.sort(
        key=lambda item: (
            item["event_id"],
            item["home_team"],
            item["away_team"],
            item["market"],
            item["book"],
            item["outcome"],
            item["rejected"]["source_file"],
            item["rejected"]["timestamp"],
            item["rejected"]["source_priority"],
            item["rejected"]["odds"],
            -999999999 if item["rejected"]["line"] is None else item["rejected"]["line"],
        )
    )
    return merged, conflicts


def write_outputs(
    merged: List[Dict[str, Any]], conflicts: List[Dict[str, Any]], workspace_path: Path
) -> None:
    output_dir = workspace_path / "outputs"
    output_dir.mkdir(exist_ok=True)
    (output_dir / "merged_odds.json").write_text(json.dumps(merged, indent=2, sort_keys=True) + "\\n")
    (output_dir / "conflicts.json").write_text(json.dumps(conflicts, indent=2, sort_keys=True) + "\\n")


def main(workspace_path: str | Path | None = None) -> None:
    if workspace_path is None:
        workspace_path = Path.cwd()
    else:
        workspace_path = Path(workspace_path)
    records = load_records(workspace_path)
    merged, conflicts = merge_records(records)
    write_outputs(merged, conflicts, workspace_path)
"""

RUN_MERGE_CODE = """#!/usr/bin/env python3
\"\"\"Run the odds feed data merger.\"\"\"

import sys
from pathlib import Path
from merge_odds import main

if __name__ == "__main__":
    workspace = sys.argv[1] if len(sys.argv) > 1 else None
    main(workspace)
"""


def main(argv: list[str]) -> int:
    workspace = Path(argv[1]) if len(argv) > 1 else Path.cwd()

    # Write reference implementation to merge_odds.py
    merge_odds_path = workspace / "merge_odds.py"
    merge_odds_path.write_text(MERGE_ODDS_CODE)

    # Write run_merge.py
    run_merge_path = workspace / "run_merge.py"
    run_merge_path.write_text(RUN_MERGE_CODE)
    run_merge_path.chmod(0o755)

    # Run the merger via subprocess in the workspace directory
    subprocess.run([sys.executable, "run_merge.py"], cwd=workspace, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
