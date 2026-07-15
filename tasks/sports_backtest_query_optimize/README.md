# sports_backtest_query_optimize

## Overview

This Quant Bench task asks the agent to optimize a slow, complex SQL query used to backtest a predictive sports model. The workspace contains a SQLite database `backtest.db` populated with historical match results, model predictions, and odds updates. The query in `query.sql` is intentionally inefficient because it lacks indexes and joins three tables using correlated subqueries to fetch the latest odds and predictions before game time.

The candidate must implement `optimize_query.py` to create the appropriate indices, execute the query, and save the result and the query plan under the `outputs/` directory.

## Source Grounding & Provenance

- **Source**: SQLite Query Planner documentation (sqlite.org/queryplanner.html); *Using SQLite* (Jay A. Kreibich), Chapter 5 (designing indexes and analyzing EXPLAIN QUERY PLAN).
- **Task Behavior vs. Source**:
  - The task is aligned with database engine optimization principles. It checks for search vs scan transitions and requires eliminating automatic indices by creating composite/covering indexes for the query.
- **Verifier Risk**: None.

## What It Tests

- Schema indexing strategies for multi-table joins.
- Designing composite indices for range filters and lookup keys.
- Eliminating correlated subquery performance bottlenecks in SQLite.
- Interpreting and verifying query execution plans using `EXPLAIN QUERY PLAN`.
- Writing deterministic JSON output.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No internet access.

## Inputs

The workspace contains:
- `workspace/backtest.db`: SQLite database containing matches, odds, and predictions.
- `workspace/query.sql`: The original inefficient SQL query.
- `workspace/optimize_query.py`: Stub to implement the optimization.
- `workspace/run_query.py`: Helper script to run the candidate's implementation.
- `workspace/build_db.py`: The database generation script.

## Required Outputs

Create the following files in the workspace:
- `outputs/query_result.json`: Exact rows returned by the optimized query.
- `outputs/query_plan.json`: The rows returned by running `EXPLAIN QUERY PLAN` on the optimized query.

## Verification

The verifier checks:
1. Output parity: the resulting JSON output matches the expected snapshot exactly.
2. Query plan efficiency: parsing the query plan and ensuring no table scans or automatic index creation messages are present, and verifying index usage.
3. Inline test: running the candidate's function on a newly constructed, different database with different games, and verifying correct behavior.
