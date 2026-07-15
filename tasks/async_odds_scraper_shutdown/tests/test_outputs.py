import asyncio
import importlib.util
import os
from pathlib import Path


def load_scraper():
    workspace = Path(os.environ.get("TASK_WORKSPACE", "/workspace"))
    module_path = workspace / "scraper.py"
    spec = importlib.util.spec_from_file_location("candidate_scraper", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_successful_run_respects_concurrency_and_preserves_order():
    async def scenario():
        scraper = load_scraper()
        started = [asyncio.Event() for _ in range(4)]
        release = [asyncio.Event() for _ in range(4)]
        active = 0
        max_seen = 0

        def make_book(index):
            async def book():
                nonlocal active, max_seen
                active += 1
                max_seen = max(max_seen, active)
                started[index].set()
                try:
                    await release[index].wait()
                    return f"result-{index}"
                finally:
                    active -= 1
            return book

        runner = asyncio.create_task(
            scraper.run_book_tasks([make_book(i) for i in range(4)], max_concurrent=2)
        )

        await asyncio.wait_for(started[0].wait(), timeout=1.0)
        await asyncio.wait_for(started[1].wait(), timeout=1.0)
        assert not started[2].is_set()
        assert max_seen == 2

        release[1].set()
        await asyncio.wait_for(started[2].wait(), timeout=1.0)
        assert active <= 2
        assert not started[3].is_set()

        release[0].set()
        await asyncio.wait_for(started[3].wait(), timeout=1.0)
        assert active <= 2

        release[3].set()
        release[2].set()
        results = await asyncio.wait_for(runner, timeout=1.0)

        assert results == ["result-0", "result-1", "result-2", "result-3"]
        assert max_seen == 2

    asyncio.run(scenario())


def test_cancellation_cleans_started_tasks_without_starting_queue():
    async def scenario():
        scraper = load_scraper()
        started_events = [asyncio.Event() for _ in range(5)]
        never_release = asyncio.Event()
        started = []
        cleaned = []
        current = asyncio.current_task()
        before = {
            task for task in asyncio.all_tasks()
            if task is not current and not task.done()
        }

        def make_book(index):
            async def book():
                started.append(index)
                started_events[index].set()
                try:
                    await never_release.wait()
                finally:
                    cleaned.append(index)
            return book

        runner = asyncio.create_task(
            scraper.run_book_tasks([make_book(i) for i in range(5)], max_concurrent=2)
        )

        await asyncio.wait_for(started_events[0].wait(), timeout=1.0)
        await asyncio.wait_for(started_events[1].wait(), timeout=1.0)
        assert started == [0, 1]
        assert not started_events[2].is_set()

        runner.cancel()
        try:
            await asyncio.wait_for(runner, timeout=1.0)
            assert False, "run_book_tasks should re-raise cancellation"
        except asyncio.CancelledError:
            pass

        assert sorted(cleaned) == [0, 1]
        assert started == [0, 1]
        await asyncio.sleep(0)
        after = {
            task for task in asyncio.all_tasks()
            if task is not current and not task.done()
        }
        assert after <= before

    asyncio.run(scenario())


def test_no_pending_tasks_leaked_after_success():
    async def scenario():
        scraper = load_scraper()
        current = asyncio.current_task()
        before = {
            task for task in asyncio.all_tasks()
            if task is not current and not task.done()
        }

        async def book(index):
            await asyncio.sleep(0)
            return index * 10

        results = await scraper.run_book_tasks(
            [lambda i=i: book(i) for i in range(6)], max_concurrent=3
        )
        await asyncio.sleep(0)

        after = {
            task for task in asyncio.all_tasks()
            if task is not current and not task.done()
        }
        assert results == [0, 10, 20, 30, 40, 50]
        assert after <= before

    asyncio.run(scenario())


def test_empty_input_returns_empty_list_inline_edge_case():
    async def scenario():
        scraper = load_scraper()
        assert await scraper.run_book_tasks([], max_concurrent=3) == []

    asyncio.run(scenario())
