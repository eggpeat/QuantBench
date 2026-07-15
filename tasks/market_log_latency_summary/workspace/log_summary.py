from pathlib import Path

def parse_records(path: Path) -> list:
    """
    Parse JSONL log file at the given path.
    Ignore malformed lines (invalid JSON), heartbeat records, and
    records missing any required fields (timestamp, sportsbook, endpoint, status, latency_ms, dropped).

    Returns a list of parsed valid record dicts.
    """
    raise NotImplementedError("parse_records not implemented")

def nearest_rank_percentile(values: list, percentile: float) -> float | None:
    """
    Calculate the percentile of the values using the nearest-rank method.
    If values list is empty, return None.
    """
    raise NotImplementedError("nearest_rank_percentile not implemented")

def summarize(records: list) -> list:
    """
    Summarize records by grouping them by minute and sportsbook.
    Returns a list of dicts, sorted by minute (ascending) and sportsbook (alphabetically).
    """
    raise NotImplementedError("summarize not implemented")
