# market_log_latency_summary

## Overview

This task asks the agent to parse market API log records from a JSONL file, calculate summary statistics grouped by minute and sportsbook, and compute the 50th, 95th, and 99th latency percentiles using the nearest-rank method.

The candidate must complete `log_summary.py` and ensure running `run_summary.py` outputs the correct summary JSON file at `outputs/latency_summary.json`.

## Source Grounding & Provenance

- **Source Tasks**: Concept-level adaptation of the Terminal-Bench 2.1 `log-summary-date-ranges` and `regex-log` tasks.
- **Parent Behavior Preserved**:
  - Reading and parsing semi-structured/JSONL log lines.
  - Filtering, cleaning, and validating records to skip invalid JSON, missing keys, or internal system events (like heartbeats).
  - Truncating timestamp timestamps to minute granularity and grouping log statistics by minute and category (sportsbook).
- **Domain Translation Added**:
  - Translates general system log parsing and filtering to sports betting market API monitoring.
  - Calculates nearest-rank percentiles ($p_{50}$, $p_{95}$, $p_{99}$) for latency distributions of successful, non-dropped requests.
  - Computes HTTP status-based error counts and dropped request rates.
- **Verifier Anti-Cheat & Robustness**:
  - The verifier is designed to resist static-output copying. In addition to testing if `latency_summary.json` matches the static expected snapshot, it dynamically imports the candidate's `log_summary` module to call functions on different, non-trivial inputs. It executes unit tests on `nearest_rank_percentile` with unsorted and single-item lists, tests `parse_records` on custom malformed log streams, and verifies `summarize` behaves correctly on empty collections. A hardcoded solution or a simple output copy will fail these dynamic assertions.
- **Promotion Readiness**:
  - All blockers are cleared. The nearest-rank percentile and log aggregation verifier checks have been validated under Python 3.13 and are structurally complete.

## What It Tests

- Parsing JSONL log files with error handling for invalid/incomplete records.
- Correctly ignoring heartbeat entries and invalid inputs.
- Timestamp minute truncation and multi-key grouping.
- Calculation of error count (HTTP status outside 200-299) and drop rate.
- Calculation of nearest-rank percentiles for request latency (excluding dropped requests).
- Formatted JSON output sorted by minute and sportsbook.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No network access, live market feeds, or credentials are required.

## Inputs

`workspace/logs/market_api.jsonl` contains lines of JSON records, heartbeats, or malformed text.

## Required Outputs

Create `workspace/outputs/latency_summary.json` with grouped metrics.

## Verification

`tests/test_outputs.py` imports `log_summary.py` and verifies:
1. `outputs/latency_summary.json` exactly matches `tests/expected.json` for the public fixture.
2. The nearest-rank percentile formula computes correct values for unsorted lists, single-item lists, and empty inputs.
3. Malformed log lines are ignored.
4. Empty input returns an empty summary.
