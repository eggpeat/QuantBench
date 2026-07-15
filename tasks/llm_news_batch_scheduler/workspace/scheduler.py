import asyncio
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
        self.request_times = [t for t in self.request_times if t >= window_start]
        if len(self.request_times) > self.max_requests_per_window:
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


def schedule_batches(items, api, max_batch_size, max_requests_per_window, window_seconds):
    """
    Schedule batches of news items to be scored by the API while respecting rate limits.

    Args:
        items (list[dict]): A list of news items (dictionaries).
        api (FakeNewsAPI): The scoring API instance.
        max_batch_size (int): Max number of items allowed in a single API call.
        max_requests_per_window (int): Max requests allowed in a sliding window.
        window_seconds (float): Window size for rate limiting in seconds.

    Returns:
        list[dict] (or Coroutine returning list[dict]):
            A list of scored items, where each item has {"id": ..., "score": ...}.
            Must deduplicate items by ID (keep first occurrence), batch them, respect the rate
            limit (blocking as needed), retry transient errors once, propagate other errors,
            and return results in the order of the first occurrence of each ID.
    """
    # TODO: Implement this function (sync or async)
    pass


def main(workspace_path=None):
    """
    Main entry point. Loads news_items.json, schedules batches, and writes output.
    """
    # TODO: Implement main loading/scheduling/saving logic.
    # It must handle both sync and async implementations of schedule_batches.
    pass
