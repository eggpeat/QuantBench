Read the market API logs from `workspace/logs/market_api.jsonl` and create `workspace/outputs/latency_summary.json`.

Required implementation:

1. Complete `log_summary.py` in the workspace:
   - `parse_records(path)`: Parse JSONL log file at the given path, ignoring malformed records (invalid JSON, missing required fields, or heartbeat records). Returns a list of parsed record dicts.
   - `nearest_rank_percentile(values, percentile)`: Given a list of numeric values and a percentile (0 to 100), return the value corresponding to that percentile using the nearest-rank method:
     - Sort the values in ascending order.
     - Calculate ordinal rank: $n = \lceil \frac{P}{100} \times N \rceil$, where $P$ is the percentile and $N$ is the number of values.
     - Return the value at index $n - 1$.
     - If the list is empty, return `None`.
   - `summarize(records)`: Summarize the records by grouping them by the minute of the timestamp (formatted as `YYYY-MM-DDTHH:MM:00Z`) and the sportsbook.
     - For each group (minute + sportsbook), compute:
       - `request_count`: total count of valid non-heartbeat requests.
       - `error_count`: count of requests where status code is not in 200-299.
       - `dropped_count`: count of requests where `dropped` is true.
       - `drop_rate`: `dropped_count / request_count` (round to 6 decimal places). If request_count is 0, drop_rate is 0.0.
       - `p50_ms`: 50th percentile of `latency_ms` (integer/float) for all non-dropped requests in the group, calculated using the nearest-rank percentile method. If there are no non-dropped requests, return `None`.
       - `p95_ms`: 95th percentile of `latency_ms` for all non-dropped requests in the group. If there are no non-dropped requests, return `None`.
       - `p99_ms`: 99th percentile of `latency_ms` for all non-dropped requests in the group. If there are no non-dropped requests, return `None`.

2. The summary output should be written by running `workspace/run_summary.py` to `workspace/outputs/latency_summary.json`. The output structure must be a list of summary objects sorted by timestamp (ascending) and then by sportsbook alphabetically.

Log record requirements:
- A valid record must be a JSON object containing: `timestamp` (string), `sportsbook` (string), `endpoint` (string), `status` (integer), `latency_ms` (integer or float), `dropped` (boolean).
- If a line is not valid JSON, ignore it.
- If a line contains `type: "heartbeat"`, ignore it (these are internal heartbeat records).
- If a line is missing any of the required fields (`timestamp`, `sportsbook`, `endpoint`, `status`, `latency_ms`, `dropped`), ignore it.
- The ISO timestamp format is `YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DDTHH:MM:SS.fffZ`. Grouping must extract the minute and format it as `YYYY-MM-DDTHH:MM:00Z` (with seconds set to zero).

Output format of `outputs/latency_summary.json`:
A JSON list of objects:
```json
[
  {
    "minute": "2026-06-26T14:32:00Z",
    "sportsbook": "DraftKings",
    "request_count": 4,
    "error_count": 1,
    "dropped_count": 1,
    "drop_rate": 0.25,
    "p50_ms": 15,
    "p95_ms": 80,
    "p99_ms": 80
  }
]
```
