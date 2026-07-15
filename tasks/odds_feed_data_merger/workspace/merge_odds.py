"""Merge odds feeds into deterministic canonical odds and conflict reports.

This module provides functions to normalize, load, merge, and output odds data
from multiple heterogeneous sources.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple


def canonical_name(value: str, aliases: Dict[str, str]) -> str:
    """Canonicalize a team name or outcome label using aliases.

    Trailing and leading whitespace should be trimmed. If the trimmed name
    exists in the aliases dictionary, map it to the canonical value;
    otherwise, return the trimmed name as-is.
    """
    raise NotImplementedError("Implement canonical_name")


def canonical_market(value: str) -> str:
    """Canonicalize market names according to canonicalization rules.

    Trim whitespace and convert to lowercase before mapping. The mapping is:
    - 'moneyline', 'ml', 'h2h' -> 'moneyline'
    - 'spread', 'point_spread', 'point spread' -> 'spread'
    - 'total', 'totals', 'over_under', 'over/under' -> 'total'
    Unmapped markets return their trimmed lowercase representation.
    """
    raise NotImplementedError("Implement canonical_market")


def normalize_record(
    raw: Dict[str, Any], source_file: str, row_number: int, aliases: Dict[str, str]
) -> Dict[str, Any]:
    """Normalize a raw record from any feed into a standard dictionary shape.

    The output dictionary must contain the following keys with clean/normalized values:
    - event_id (str)
    - home_team (str)
    - away_team (str)
    - market (str)
    - book (str)
    - outcome (str)
    - odds (int)
    - line (float or int or None)
    - timestamp (str)
    - source_priority (int)
    - source_file (str)
    - _row_number (int)
    """
    raise NotImplementedError("Implement normalize_record")


def load_records(workspace_path: Path) -> List[Dict[str, Any]]:
    """Load all records from json, csv, and jsonl feeds, and normalize them.

    This function reads:
    - feeds/json_feed.json
    - feeds/csv_feed.csv
    - feeds/jsonl_feed.jsonl
    using team_aliases.json for team/outcome mapping.
    """
    raise NotImplementedError("Implement load_records")


def merge_records(
    records: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Merge normalized records, resolving conflicts and identifying winners.

    Returns a tuple of (merged_odds, conflicts), sorted according to the
    specification.
    """
    raise NotImplementedError("Implement merge_records")


def write_outputs(
    merged: List[Dict[str, Any]], conflicts: List[Dict[str, Any]], workspace_path: Path
) -> None:
    """Write the merged odds and conflicts to JSON files in the outputs directory."""
    raise NotImplementedError("Implement write_outputs")


def main(workspace_path: str | Path | None = None) -> None:
    """Main entry point to merge odds data.

    If workspace_path is None, it defaults to the current directory or the
    appropriate fallback.
    """
    raise NotImplementedError("Implement main")
