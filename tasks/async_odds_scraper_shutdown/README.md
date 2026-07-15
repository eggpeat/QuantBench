# async_odds_scraper_shutdown

## Overview

Implement a bounded asyncio scheduler for sportsbook scraping callables. The workspace starts with `scraper.py`; candidates must fill in `run_book_tasks(book_tasks, max_concurrent)`.

## Source Grounding & Provenance

- **Source Task**: Direct/API-parity adaptation from the Terminal-Bench 2.1 `cancel-async-tasks` task.
- **Parent Behavior Preserved**:
  - Executing asynchronous callables with bounded concurrency via `asyncio.Semaphore`.
  - Preserving input sequence ordering in the final output list of results.
  - Handling task cancellation robustly: when the parent task is cancelled, any child tasks that have already started are explicitly cancelled and awaited to allow their `finally` cleanups to run, preventing the leak of pending tasks.
- **Domain Translation Added**:
  - Translates the abstract async task execution pattern into a sports betting book scraper scheduler context (managing async scrape tasks for bookmakers).
- **Verifier Anti-Cheat & Robustness**:
  - The verifier is designed to resist static-output copying by dynamically testing runtime execution state in `asyncio`. It uses `asyncio.Event` synchronization and sleep timing inside dynamically created tasks to assert concurrency limits, verifies result order, intercepts cancellation to check if cleanup blocks run, and audits the active event loop to ensure no tasks are leaked. As a result, static or hardcoded outputs cannot pass the tests.
- **Promotion Readiness**:
  - All blockers are cleared. The async book scraper scheduling interface has been verified to be fully compatible with Python 3.13, and the tests execute correctly.

## What It Tests

- Bounded async concurrency without eager-starting every callable.
- Preserving input order while concurrent tasks finish out of order.
- Correct cancellation behavior: when the parent coroutine is cancelled, already-started children must be cancelled and awaited so `finally` cleanup runs.
- Avoiding leaked pending asyncio tasks after success or cancellation.

## Environment

The task uses Python standard-library `asyncio` only. The Docker image is `python:3.13-slim-bookworm`; no internet, credentials, or external services are required.

## Inputs

- `workspace/scraper.py` contains the starter function signature.
- Tests construct in-memory async book-task callables; there are no network inputs.

## Required Outputs

No output JSON is required from the candidate. The implementation must update `scraper.py` so importing it exposes a working `async def run_book_tasks(book_tasks, max_concurrent)`.

## Verification

`tests/test_outputs.py` imports `scraper.py` from `TASK_WORKSPACE` if set, otherwise `/workspace`, and uses `asyncio.run(...)` with deterministic events. It verifies the concurrency limit, ordered result list, cancellation cleanup when queued tasks exist, and absence of leaked pending tasks.

## Difficulty/Anti-cheat notes

This mirrors the Terminal-Bench `cancel-async-tasks` gotcha: simply cancelling the parent task is not enough if child tasks have been spawned. Implementations must cancel and await started children. Tests include inline edge cases and event-driven scheduling so hard-coded snapshots from `expected.json` are insufficient.
