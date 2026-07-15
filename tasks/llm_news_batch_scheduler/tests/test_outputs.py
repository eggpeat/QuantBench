import asyncio
import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    import scheduler
    importlib.reload(scheduler)
    return scheduler


class VirtualClock:
    def __init__(self, start_time=1000.0):
        self.current_time = start_time
        self.original_asyncio_sleep = asyncio.sleep

    def time(self):
        return self.current_time

    def sleep(self, seconds):
        if seconds > 0:
            self.current_time += seconds

    async def sleep_async(self, seconds):
        if seconds > 0:
            self.current_time += seconds
        # Yield to let tasks run/schedule on the loop
        await self.original_asyncio_sleep(0)


def run_schedule_batches(mod, items, api, max_batch_size, max_requests_per_window, window_seconds):
    import inspect
    if inspect.iscoroutinefunction(mod.schedule_batches):
        return asyncio.run(mod.schedule_batches(
            items, api, max_batch_size, max_requests_per_window, window_seconds
        ))
    else:
        return mod.schedule_batches(
            items, api, max_batch_size, max_requests_per_window, window_seconds
        )


def test_public_fixture_output_matches_expected_snapshot():
    output_path = WORKSPACE / "outputs" / "news_scores.json"
    assert output_path.exists(), "missing outputs/news_scores.json"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)
    assert actual == expected


def test_deduplication_and_batching():
    mod = import_candidate_module()

    items = [
        {"id": "doc_1"}, {"id": "doc_2"}, {"id": "doc_1"},
        {"id": "doc_3"}, {"id": "doc_2"}, {"id": "doc_4"}
    ]

    # We want max_batch_size = 2, so after deduping [doc_1, doc_2, doc_3, doc_4],
    # it should make exactly 2 batches of size 2.
    api = mod.FakeNewsAPI(max_requests_per_window=10, window_seconds=1.0)

    res = run_schedule_batches(mod, items, api, max_batch_size=2, max_requests_per_window=10, window_seconds=1.0)

    # Check return value has unique elements
    assert len(res) == 4
    assert [r["id"] for r in res] == ["doc_1", "doc_2", "doc_3", "doc_4"]

    # Check that API received exactly 2 requests (since total 4 unique items and max_batch_size 2)
    assert len(api.request_log) == 2
    assert api.request_log[0] == ["doc_1", "doc_2"]
    assert api.request_log[1] == ["doc_3", "doc_4"]


def test_rate_limiting_compliance():
    clock = VirtualClock()

    with patch('time.time', side_effect=clock.time), \
         patch('time.monotonic', side_effect=clock.time), \
         patch('time.sleep', side_effect=clock.sleep), \
         patch('asyncio.sleep', side_effect=clock.sleep_async):

        mod = import_candidate_module()

        items = [{"id": f"doc_{i}"} for i in range(10)]
        api = mod.FakeNewsAPI(
            max_requests_per_window=2,
            window_seconds=5.0,
            clock=clock.time
        )

        # Keep a persistent list of all request timestamps
        all_req_times = []
        orig_check_rate_limit = api._check_rate_limit
        def patched_check_rate_limit():
            all_req_times.append(api.clock())
            orig_check_rate_limit()
        api._check_rate_limit = patched_check_rate_limit

        res = run_schedule_batches(mod, items, api, max_batch_size=1, max_requests_per_window=2, window_seconds=5.0)

        # Check all results returned
        assert len(res) == 10

        # Check that API received exactly 10 requests using api.request_log and persistent timestamps list
        assert len(api.request_log) == 10
        assert len(all_req_times) == 10

        for i in range(2, len(all_req_times)):
            diff = all_req_times[i] - all_req_times[i-2]
            assert diff >= 5.0, f"Rate limit violated! Req {i} at {all_req_times[i]} and Req {i-2} at {all_req_times[i-2]} (diff {diff} < 5.0s)"

def test_transient_failure_retry_and_rate_limit():
    clock = VirtualClock()

    with patch('time.time', side_effect=clock.time), \
         patch('time.monotonic', side_effect=clock.time), \
         patch('time.sleep', side_effect=clock.sleep), \
         patch('asyncio.sleep', side_effect=clock.sleep_async):

        mod = import_candidate_module()

        items = [{"id": "doc_0"}, {"id": "doc_1"}, {"id": "doc_2"}]
        api = mod.FakeNewsAPI(
            transient_fail_ids={"doc_1"},
            max_requests_per_window=2,
            window_seconds=3.0,
            clock=clock.time
        )

        # Keep a persistent list of all request timestamps
        all_req_times = []
        orig_check_rate_limit = api._check_rate_limit
        def patched_check_rate_limit():
            all_req_times.append(api.clock())
            orig_check_rate_limit()
        api._check_rate_limit = patched_check_rate_limit

        res = run_schedule_batches(mod, items, api, max_batch_size=1, max_requests_per_window=2, window_seconds=3.0)

        assert len(res) == 3
        assert [r["id"] for r in res] == ["doc_0", "doc_1", "doc_2"]

        # api.request_log should have doc_1 twice (once for fail, once for retry)
        assert api.request_log == [["doc_0"], ["doc_1"], ["doc_1"], ["doc_2"]]
        assert len(api.request_log) == 4
        assert len(all_req_times) == 4

        # Check rate limit on requests
        for i in range(2, len(all_req_times)):
            diff = all_req_times[i] - all_req_times[i-2]
            assert diff >= 3.0, f"Rate limit violated! Req {i} at {all_req_times[i]} and Req {i-2} at {all_req_times[i-2]} (diff {diff} < 3.0s)"

def test_permanent_failure_propagation():
    mod = import_candidate_module()

    items = [{"id": "doc_0"}, {"id": "doc_1"}, {"id": "doc_2"}]
    api = mod.FakeNewsAPI(
        permanent_fail_ids={"doc_1"},
        max_requests_per_window=10,
        window_seconds=1.0
    )

    try:
        run_schedule_batches(mod, items, api, max_batch_size=1, max_requests_per_window=10, window_seconds=1.0)
    except mod.APIError as exc:
        assert not exc.is_transient
    else:
        raise AssertionError("expected permanent APIError")


def test_ordering_preserved():
    mod = import_candidate_module()

    items = [
        {"id": "doc_C"},
        {"id": "doc_A"},
        {"id": "doc_B"},
        {"id": "doc_A"},
        {"id": "doc_C"}
    ]

    api = mod.FakeNewsAPI(max_requests_per_window=10, window_seconds=1.0)
    res = run_schedule_batches(mod, items, api, max_batch_size=1, max_requests_per_window=10, window_seconds=1.0)

    assert [r["id"] for r in res] == ["doc_C", "doc_A", "doc_B"]
