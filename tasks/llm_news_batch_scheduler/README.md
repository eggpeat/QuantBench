# llm_news_batch_scheduler

## Overview

This task asks the agent to implement a robust, rate-limited batch scheduling data pipeline to score news items using a simulated LLM API. The API has strict rate limits and occasionally raises transient errors.

The candidate must complete `scheduler.py` in the workspace, deduplicating news items by ID, batching them up to a specified size, and calling the fake API while strictly respecting its rate limit (using a sliding window) and retrying transient failures exactly once. The results must preserve the order of the first occurrence of each item and be written to `outputs/news_scores.json`.

## Source Grounding & Provenance

- **Source**: Industry standard patterns for reliable API client design (rate-limiting, sliding window rate limiters, token buckets, idempotency via deduplication, transient fault handling / retries).
- **Task Behavior**:
  - Requires implementing a sliding-window rate limiter or equivalent wait strategy.
  - Requires handling API failures, distinguishing transient errors from permanent errors using an `is_transient` flag.
  - Requires output ordering and deduplication preservation.
- **Verifier Risk**: None. Verifier uses a deterministic virtual/mocked clock to test rate limits instantly and reliably without depending on real-time sleep accuracy.

## What It Tests

- Correct deduplication and batching of structured data.
- Implementation of a rate limiter (sync or async) that blocks before exceeding a specified requests-per-window threshold.
- Transient error retry logic (exactly once, only for transient errors) combined with rate-limit compliance on retry attempts.
- Clean exception propagation for permanent errors or double failures.
- Maintaining original document ordering in the processed output.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No external network access.
- The verifier uses pytest-style tests with plain asserts.

## Inputs

The workspace contains:

- `workspace/news_items.json`: A JSON list of news articles to score, including duplicate records.
- `workspace/scheduler.py`: Starter implementation file containing the `APIError`, `FakeNewsAPI` definition, and the `schedule_batches` and `main` stubs.
- `workspace/run_scheduler.py`: A starter script that imports and executes your `scheduler.py` module.

## Required Outputs

Create `outputs/news_scores.json` under the workspace. The file must contain a JSON array of objects, each containing:

- `id`: The unique news item ID.
- `score`: The API-returned score for the item.

The ordering must match the order of the first occurrence of each unique item in `news_items.json`.

## Verification

The verifier checks:

1. `outputs/news_scores.json` matches the expected snapshot exactly.
2. The scheduler handles duplicate records correctly.
3. The rate limiter respects the rate limit on a large slate of requests.
4. Retries are executed exactly once for transient failures, and rate limits are respected during retries.
5. Permanent errors and exhausted retries correctly propagate to the caller.

Candidates can run the scheduler locally using:
```bash
python run_scheduler.py
```
