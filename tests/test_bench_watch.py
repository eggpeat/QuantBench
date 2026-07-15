from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bench_watch", ROOT / "scripts" / "bench_watch.py")
assert SPEC is not None and SPEC.loader is not None
bench_watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench_watch)


class BenchWatchTests(unittest.TestCase):
    def test_latest_unsuperseded_rows_remove_old_head(self) -> None:
        rows = [
            {"result_id": "r1", "task_id": "alpha", "status": "REJECT"},
            {
                "result_id": "r2",
                "task_id": "alpha",
                "status": "PASS",
                "supersedes_result_id": "r1",
            },
            {"result_id": "r3", "task_id": "beta", "status": "TIME_LIMIT"},
        ]
        visible = bench_watch.latest_unsuperseded_rows(rows)
        self.assertEqual([row["result_id"] for row in visible], ["r2", "r3"])
        self.assertEqual(bench_watch.latest_task_rows(rows)["alpha"]["status"], "PASS")

    def test_status_summary_overrides_historical_retry_rows(self) -> None:
        rows = [
            {"task_id": "alpha", "status": "INFRA_BLOCKED"},
            {"task_id": "alpha", "status": "PASS"},
        ]
        status = {
            "summary": {
                "by_status": {
                    "PASS": 1,
                    "REJECT": 0,
                    "TIME_LIMIT": 0,
                    "INFRA_BLOCKED": 0,
                }
            }
        }
        self.assertEqual(
            bench_watch._snapshot_counts(status, rows),
            {"PASS": 1, "REJECT": 0, "TIME_LIMIT": 0, "INFRA_BLOCKED": 0},
        )
        self.assertEqual(bench_watch._snapshot_rows(status, rows), [rows[-1]])

    def test_malformed_partial_status_and_results_are_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            run.mkdir()
            (run / "status.json").write_text('{"run_state": "running"', encoding="utf-8")
            (run / "results.jsonl").write_bytes(
                b'{"result_id":"r1","task_id":"alpha","status":"PASS"}\n'
                b'{"result_id":"r2","task_id":"beta","status":"REJ'
            )
            self.assertIsNone(bench_watch.load_status_snapshot(run / "status.json"))
            self.assertEqual(
                bench_watch.load_results_jsonl(run / "results.jsonl"),
                [{"result_id": "r1", "task_id": "alpha", "status": "PASS"}],
            )
            watcher = bench_watch.BenchWatch("run", tmp)
            watcher.refresh()
            self.assertIsNone(watcher.status)
            self.assertEqual(len(watcher.rows), 1)

    def test_missing_run_is_a_clean_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = bench_watch.main(["missing", "--artifact-root", tmp, "--once"])
        self.assertEqual(code, 1)
        self.assertIn("not found", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_once_rendering_is_plain_and_contains_progress_and_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "sample"
            run.mkdir()
            (run / "status.json").write_text(
                json.dumps(
                    {
                        "run_state": "running",
                        "total_trials": 2,
                        "completed_trials": 1,
                        "running_trials": 1,
                        "pending_trials": 0,
                        "effective_concurrency": 2,
                        "tasks": ["alpha", "beta"],
                        "started_at": "2026-07-12T10:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            (run / "results.jsonl").write_text(
                json.dumps(
                    {
                        "result_id": "r1",
                        "task_id": "alpha",
                        "agent": "test-agent",
                        "status": "PASS",

                        "failure_code": "NONE",
                        "agent_elapsed_sec": 1.25,
                        "verifier_elapsed_sec": 0.75,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = bench_watch.main(["sample", "--artifact-root", tmp, "--once"])
        rendered = output.getvalue()
        self.assertEqual(code, 0)
        self.assertNotIn("\033", rendered)
        self.assertIn("Progress: 1/1/0/2", rendered)
        self.assertIn("PASS=1", rendered)
        self.assertIn("alpha", rendered)
        self.assertIn("beta", rendered)
        self.assertIn("PENDING", rendered)
        self.assertIn("00:00:02", rendered)

    def test_multiple_runs_render_one_expanded_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for run_id, state, result in (
                ("sol", "running", "PASS"),
                ("terra", "paused", "REJECT"),
            ):
                run = root / run_id
                run.mkdir()
                (run / "status.json").write_text(
                    json.dumps(
                        {
                            "run_state": state,
                            "total_trials": 2,
                            "completed_trials": 1,
                            "running_trials": 0,
                            "pending_trials": 1,
                            "effective_concurrency": 2,
                            "tasks": [f"{run_id}-task"],
                            "summary": {
                                "by_status": {
                                    "PASS": int(result == "PASS"),
                                    "REJECT": int(result == "REJECT"),
                                }
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                (run / "results.jsonl").write_text(
                    json.dumps(
                        {
                            "result_id": f"{run_id}-1",
                            "task_id": f"{run_id}-task",
                            "agent": run_id,
                            "status": result,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = bench_watch.main(["sol", "terra", "--artifact-root", tmp, "--once", "--no-color"])
        rendered = output.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("Quant Bench dashboard: 2 runs", rendered)
        self.assertIn("Overall progress: 2/0/2/4", rendered)
        self.assertIn("Active workers: 0    Configured concurrency: 4", rendered)
        self.assertIn("Overall results: PASS=1  REJECT=1", rendered)
        self.assertIn("Quant Bench run: sol", rendered)
        self.assertIn("Quant Bench run: terra", rendered)

    def test_interactive_refresh_erases_prior_scrollback(self) -> None:
        class TTYBuffer(io.StringIO):
            def isatty(self) -> bool:
                return True

        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "sample"
            run.mkdir()
            (run / "status.json").write_text(
                json.dumps(
                    {
                        "run_state": "running",
                        "total_trials": 1,
                        "completed_trials": 0,
                        "running_trials": 1,
                        "pending_trials": 0,
                    }
                ),
                encoding="utf-8",
            )
            output = TTYBuffer()
            with contextlib.redirect_stdout(output), mock.patch.object(
                bench_watch.time, "sleep", side_effect=KeyboardInterrupt
            ):
                code = bench_watch.main(["sample", "--artifact-root", tmp])
        self.assertEqual(code, 0)
        self.assertTrue(output.getvalue().startswith("\033[3J\033[2J\033[H"))

    def test_run_id_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            bench_watch.resolve_run_dir("../outside", "/tmp")


if __name__ == "__main__":
    unittest.main()
