# sqlite_wal_odds_recovery

## Overview

This Quant Bench task asks the agent to implement a custom write-ahead log (WAL) recovery engine in SQLite to recover a crashed database of sports betting odds updates. The workspace contains a SQLite database `odds.db` and a transaction log file `odds_transactions.jsonl` (which is formatted as JSON Lines representing sequential database transactions).

Due to a crash, the transaction log file `odds_transactions.jsonl` is truncated/corrupted at the end (missing a `COMMIT` record). The recovery engine must read the WAL, validate each transaction's integrity (sequence ordering, parent-hash linkage, and custom cryptographic SHA-256 payload checksum), skip transactions already checkpointed/applied in the database, replay valid unapplied transactions into SQLite, and rollback/discard any corrupted or incomplete transactions.

The candidate must complete the `recover.py` module exposing `recover_database(workspace)` and run it to produce `outputs/recovered_ticks.json`.

## Source Grounding & Provenance

- **Source**: Standard database recovery and transaction-integrity patterns (e.g. Write-Ahead Logging in SQLite, block/transaction hashing, and checksum verification).
- **Task Behavior**:
  - Validates a chain of transactions where each transaction's start block points to the previous transaction's hash.
  - Verifies operations payload hash using SHA-256.
  - Resolves already-checkpointed transaction IDs by querying the SQLite database.
  - Commits clean state transaction-by-transaction and rolls back any partial transactions upon detecting the first sign of log corruption/truncation.
- **Verifier Risk**: None.

## What It Tests

- Parsing line-by-line structured JSON logs with interleaved transaction markers (`START`, `OP`, `COMMIT`).
- Correct implementation of sequential integrity rules (contiguous `tx_id` increments, matching parent transaction hash linkage).
- Cryptographic verification: computing SHA-256 hash digests of transaction payloads and comparing against the log's `COMMIT` hash.
- Proper database transaction management in Python's standard `sqlite3` library (skip already-applied records, insert new ticks log, upsert latest market odds, insert checkpoint hashes, and handle errors/rollbacks).
- Deterministic output generation describing the final recovery state.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No external libraries or network access.
- The verifier uses pytest-style tests with plain asserts.

## Inputs

The workspace contains:

- `workspace/odds.db`: SQLite database representing the state of the system at the crash checkpoint.
- `workspace/odds_transactions.jsonl`: Line-by-line JSONL file representing transaction records to recover.
- `workspace/recover.py`: Stub module.
- `workspace/run_recovery.py`: Script to execute the recovery.

## Required Outputs

Create `outputs/recovered_ticks.json` under the workspace containing:

- `status`: `"recovered"`
- `initial_tx_id`: Last applied transaction ID before recovery (100).
- `final_tx_id`: Last applied transaction ID after recovery (104).
- `applied_transactions`: List of newly applied transaction IDs `[101, 102, 103, 104]`.
- `ticks_inserted`: Total number of new ticks inserted into `ticks_log` (6).
- `corruption_encountered`: `true` (since the WAL ends with a truncated/incomplete transaction).
- `database_state`:
  - `total_ticks`: Total rows in `ticks_log` after recovery (21).
  - `live_odds`: List of current live odds ordered by `market_id` ASC, `outcome` ASC, `sportsbook` ASC.

## Verification

The verifier checks that:
1. `outputs/recovered_ticks.json` matches `tests/expected.json`.
2. The candidate exposes `recover_database`.
3. Running on a recovered DB returns correct up-to-date states.
4. Custom tests with valid transactions (no corruption), gaps in sequence, invalid hashes, and invalid parent links are correctly handled (stopping recovery at the point of corruption).

Candidates can run recovery locally using:
```bash
python run_recovery.py
```
