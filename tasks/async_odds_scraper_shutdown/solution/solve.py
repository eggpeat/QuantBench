#!/usr/bin/env python3
"""Reference solution for async_odds_scraper_shutdown."""

from __future__ import annotations

from pathlib import Path
import sys

IMPLEMENTATION = '''"""Async sportsbook scraping scheduler."""

import asyncio


async def run_book_tasks(book_tasks, max_concurrent):
    """Run zero-argument async callables with bounded concurrency.

    Results are returned in input order. If this coroutine is cancelled or one
    worker fails, any started worker tasks are cancelled and awaited so child
    coroutine ``finally`` blocks have a chance to run before the exception is
    re-raised.
    """
    if max_concurrent < 1:
        raise ValueError("max_concurrent must be at least 1")

    total = len(book_tasks)
    if total == 0:
        return []

    results = [None] * total
    next_index = 0
    semaphore = asyncio.Semaphore(max_concurrent)

    async def worker():
        nonlocal next_index
        while True:
            index = next_index
            if index >= total:
                return
            next_index += 1
            async with semaphore:
                results[index] = await book_tasks[index]()

    workers = [
        asyncio.create_task(worker())
        for _ in range(min(max_concurrent, total))
    ]

    try:
        await asyncio.gather(*workers)
    except BaseException:
        for task in workers:
            if not task.done():
                task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        raise

    return results
'''


def main() -> None:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "scraper.py").write_text(IMPLEMENTATION, encoding="utf-8")


if __name__ == "__main__":
    main()
