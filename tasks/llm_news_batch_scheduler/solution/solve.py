#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MODULE_SOURCE = r'''import asyncio
import hashlib
import json
import os
import time
from pathlib import Path


class APIError(Exception):
    """Exception raised by the Fake API for rate limit violations or service issues."""
    def __init__(self, message: str, is_transient: bool = False):
        super().__init__(message)
        self.is_transient = is_transient


class FakeNewsAPI:
    """
    A simulated LLM API for scoring news items.

    This class is provided for you to use. It supports:
    - Synchronous scoring: `score_batch(batch)`
    - Asynchronous scoring: `await score_batch_async(batch)`

    It tracks the virtual or real time to enforce a rate limit window, and
    can simulate transient and permanent errors.
    """
    def __init__(
        self,
        transient_fail_ids: set[str] = None,
        permanent_fail_ids: set[str] = None,
        max_requests_per_window: int = 5,
        window_seconds: float = 1.0,
        clock=None
    ):
        self.transient_fail_ids = transient_fail_ids or set()
        self.permanent_fail_ids = permanent_fail_ids or set()
        self.max_requests_per_window = max_requests_per_window
        self.window_seconds = window_seconds
        self.clock = clock or time.time

        self.request_times = []
        self._rate_window = []
        self.failed_attempts = {}  # item_id -> count of failed attempts
        self.request_log = []      # list of lists of item IDs requested

    def _calculate_score(self, item: dict) -> float:
        item_id = item.get("id", "")
        h = hashlib.sha256(item_id.encode("utf-8")).hexdigest()
        score = int(h[:8], 16) / 0xffffffff
        return round(score, 4)

    def _check_rate_limit(self):
        now = self.clock()
        self.request_times.append(now)
        window_start = now - self.window_seconds
        self._rate_window = [t for t in self._rate_window if t >= window_start]
        self._rate_window.append(now)
        if len(self._rate_window) > self.max_requests_per_window:
            raise APIError("Rate limit exceeded", is_transient=False)

    def _process_batch_logic(self, batch: list[dict]) -> list[dict]:
        self._check_rate_limit()
        self.request_log.append([item["id"] for item in batch])

        # Check for permanent failures
        for item in batch:
            if item.get("id") in self.permanent_fail_ids:
                raise APIError(f"Permanent error processing item {item.get('id')}", is_transient=False)

        # Check for transient failures (fail exactly once on first attempt)
        for item in batch:
            item_id = item.get("id")
            if item_id in self.transient_fail_ids:
                if self.failed_attempts.get(item_id, 0) == 0:
                    self.failed_attempts[item_id] = 1
                    raise APIError(f"Transient error processing item {item_id}", is_transient=True)

        # Score the items
        results = []
        for item in batch:
            results.append({
                "id": item["id"],
                "score": self._calculate_score(item)
            })
        return results

    def score_batch(self, batch: list[dict]) -> list[dict]:
        """
        Synchronously score a batch of news items.
        """
        return self._process_batch_logic(batch)

    async def score_batch_async(self, batch: list[dict]) -> list[dict]:
        """
        Asynchronously score a batch of news items.
        """
        return self._process_batch_logic(batch)


class RateLimiter:
    def __init__(self, max_requests, window_seconds, clock):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clock = clock
        self.requests = []

    async def wait_if_needed(self):
        now = self.clock()
        self.requests = [t for t in self.requests if now - t < self.window_seconds]
        if len(self.requests) >= self.max_requests:
            sleep_time = self.requests[0] + self.window_seconds - now + 1e-9
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            now = self.clock()
            self.requests = [t for t in self.requests if now - t < self.window_seconds]
        self.requests.append(now)


async def schedule_batches(items, api, max_batch_size, max_requests_per_window, window_seconds):
    seen = set()
    deduped = []
    for item in items:
        item_id = item.get("id")
        if item_id and item_id not in seen:
            seen.add(item_id)
            deduped.append(item)

    batches = [deduped[i : i + max_batch_size] for i in range(0, len(deduped), max_batch_size)]

    clock = getattr(api, "clock", time.time)
    limiter = RateLimiter(max_requests_per_window, window_seconds, clock)

    is_async_api = hasattr(api, "score_batch_async") and asyncio.iscoroutinefunction(api.score_batch_async)

    results = []
    for batch in batches:
        attempts = 0
        while True:
            await limiter.wait_if_needed()
            try:
                if is_async_api:
                    batch_res = await api.score_batch_async(batch)
                else:
                    batch_res = api.score_batch(batch)
                results.extend(batch_res)
                break
            except APIError as e:
                if e.is_transient and attempts < 1:
                    attempts += 1
                    continue
                raise e
    return results


def main(workspace_path=None):
    if workspace_path is None:
        workspace_path = Path.cwd()
    else:
        workspace_path = Path(workspace_path)

    input_path = workspace_path / "news_items.json"
    output_dir = workspace_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "news_scores.json"

    with open(input_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    api = FakeNewsAPI(
        transient_fail_ids={"doc_004", "doc_008"},
        max_requests_per_window=3,
        window_seconds=0.5
    )

    import inspect
    if inspect.iscoroutinefunction(schedule_batches):
        results = asyncio.run(schedule_batches(
            items=items,
            api=api,
            max_batch_size=3,
            max_requests_per_window=3,
            window_seconds=0.5
        ))
    else:
        results = schedule_batches(
            items=items,
            api=api,
            max_batch_size=3,
            max_requests_per_window=3,
            window_seconds=0.5
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
'''

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "scheduler.py").write_text(MODULE_SOURCE, encoding="utf-8")

    # Run the scheduler to generate outputs
    sys.path.insert(0, str(workspace))
    import scheduler
    scheduler.main(str(workspace))

if __name__ == "__main__":
    main()
