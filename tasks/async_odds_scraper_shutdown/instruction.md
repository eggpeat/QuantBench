Implement `async def run_book_tasks(book_tasks, max_concurrent):` in `scraper.py`.

`book_tasks` is a list of zero-argument async callables. Run the callables with at most `max_concurrent` active at a time, return a list of successful results in the same order as the input list, and avoid starting queued work before a concurrency slot is actually available.

If `run_book_tasks` is cancelled, cancel and await any child tasks that have already started so their `finally` cleanup blocks run before cancellation is re-raised. Do not leave pending child tasks behind.
