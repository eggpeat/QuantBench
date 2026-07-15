#!/usr/bin/env python3
"""Reference solution for the market API log latency summary task."""

import json
import sys
import math
from pathlib import Path

LOG_SUMMARY_SOURCE = '''"""Log summary parser and analyzer."""
import json
import math
from pathlib import Path

def parse_records(path: Path) -> list:
    """
    Parse JSONL log file at the given path.
    Ignore malformed lines (invalid JSON), heartbeat records, and
    records missing any required fields (timestamp, sportsbook, endpoint, status, latency_ms, dropped).

    Returns a list of parsed valid record dicts.
    """
    required_fields = {"timestamp", "sportsbook", "endpoint", "status", "latency_ms", "dropped"}
    records = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                if "type" in data and data["type"] == "heartbeat":
                    continue
                if not all(field in data for field in required_fields):
                    continue
                records.append(data)
            except json.JSONDecodeError:
                continue
    return records

def nearest_rank_percentile(values: list, percentile: float) -> float | None:
    """
    Calculate the percentile of the values using the nearest-rank method.
    If values list is empty, return None.
    """
    if not values:
        return None
    sorted_val = sorted(values)
    n = max(1, math.ceil((percentile / 100) * len(sorted_val)))
    return sorted_val[n - 1]

def summarize(records: list) -> list:
    """
    Summarize records by grouping them by minute and sportsbook.
    Returns a list of dicts, sorted by minute (ascending) and sportsbook (alphabetically).
    """
    groups = {}
    for r in records:
        ts = r["timestamp"]
        # Format as YYYY-MM-DDTHH:MM:00Z
        minute = ts[:16] + ":00Z"
        sb = r["sportsbook"]
        key = (minute, sb)
        if key not in groups:
            groups[key] = []
        groups[key].append(r)

    summary = []
    for (minute, sportsbook), recs in sorted(groups.items()):
        req_count = len(recs)
        err_count = sum(1 for r in recs if not (200 <= r["status"] < 300))
        drop_count = sum(1 for r in recs if r["dropped"])
        drop_rate = round(drop_count / req_count, 6) if req_count > 0 else 0.0

        non_dropped = [r["latency_ms"] for r in recs if not r["dropped"]]
        p50 = nearest_rank_percentile(non_dropped, 50)
        p95 = nearest_rank_percentile(non_dropped, 95)
        p99 = nearest_rank_percentile(non_dropped, 99)

        summary.append({
            "minute": minute,
            "sportsbook": sportsbook,
            "request_count": req_count,
            "error_count": err_count,
            "dropped_count": drop_count,
            "drop_rate": drop_rate,
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99
        })
    return summary
'''

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")

    # Write solution to log_summary.py
    (workspace / "log_summary.py").write_text(LOG_SUMMARY_SOURCE, encoding="utf-8")

    # Run the summary generation logic (same as run_summary.py)
    sys.path.insert(0, str(workspace))
    try:
        import log_summary
        log_path = workspace / "logs" / "market_api.jsonl"
        output_path = workspace / "outputs" / "latency_summary.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        records = log_summary.parse_records(log_path)
        summary = log_summary.summarize(records)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
            f.write("\n")
    finally:
        if str(workspace) in sys.path:
            sys.path.remove(str(workspace))

if __name__ == "__main__":
    main()
