"""Async sportsbook scraping scheduler starter."""


async def run_book_tasks(book_tasks, max_concurrent):
    """Run zero-argument async callables with bounded concurrency.

    Return successful results in input order. On cancellation, make sure any
    started child work is cancelled and awaited before re-raising.
    """
    raise NotImplementedError("Implement run_book_tasks")
