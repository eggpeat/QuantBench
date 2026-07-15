Implement a rate-limited batch scheduling data pipeline to score news items via a simulated LLM API with transient retries.

You are building a reliable data pipeline to feed news items to an LLM scoring service. The service has a strict rate limit, charges per request (not per item, so batching is critical), and occasionally experiences transient network or server errors.

Starter files are provided in the workspace:
- `news_items.json`: A list of news articles to process (with some duplicate items to clean up).
- `scheduler.py`: Contains stubs for your implementation and the `FakeNewsAPI` definition.
- `run_scheduler.py`: A wrapper script that imports and executes your `scheduler.main()` function.

### Requirements

1. **Complete the `schedule_batches` function in `scheduler.py`**:
   The function signature is:
   ```python
   def schedule_batches(items, api, max_batch_size, max_requests_per_window, window_seconds):
   ```
   *Note: You can implement this function as either synchronous or asynchronous.*

2. **Core Logic Requirements**:
   - **Deduplication**: Deduplicate news items by their `"id"`. If a duplicate ID is encountered, keep only the first occurrence to preserve output order.
   - **Batching**: Group the deduplicated items into batches. A batch must contain at most `max_batch_size` items.
   - **Rate Limiting**: Do not exceed `max_requests_per_window` requests to the API within any sliding window of `window_seconds`.
     - *Important*: Retries and initial attempts all count as requests and must respect the rate limit.
     - Your rate limiter must block/wait (e.g. using `time.sleep` or `asyncio.sleep`) to prevent rate limit violations. Use `time.time()` or `time.monotonic()` for tracking timestamps.
   - **Error Handling & Retries**:
     - The API may raise an `APIError`.
     - If the error is transient (`api_error.is_transient == True`), you must retry the request exactly once (respecting the rate limit before retrying).
     - If the error is not transient (`is_transient == False`), or if the retry attempt also fails, propagate the exception.
   - **Ordering**: The final list of results must preserve the order of the first occurrence of each item in the input.

3. **API Methods**:
   The API instance supports:
   - Synchronous: `api.score_batch(batch)` -> returns a list of dictionaries with `"id"` and `"score"`.
   - Asynchronous: `await api.score_batch_async(batch)` -> returns the same.

4. **Main Entry Point**:
   Complete `main(workspace_path=None)` in `scheduler.py` to:
   - Load `news_items.json` from the workspace.
   - Initialize `FakeNewsAPI` with the public transient failure settings: `transient_fail_ids={"doc_004", "doc_008"}`.
   - Call `schedule_batches` with:
     - `max_batch_size = 3`
     - `max_requests_per_window = 3`
     - `window_seconds = 0.5`
   - Write the output list of scored items to `outputs/news_scores.json`.

5. **Output Format**:
   `outputs/news_scores.json` must be a JSON array of objects, containing the `"id"` and `"score"` of each unique news item in the correct order:
   ```json
   [
     {
       "id": "doc_001",
       "score": 0.5375
     },
     ...
   ]
   ```

Candidates can run the scheduler locally using:
```bash
python run_scheduler.py
```
