from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import unittest.mock
import os
import shutil
import tempfile
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "scripts" / "quant_bench_runner.py"
SPEC = importlib.util.spec_from_file_location("quant_bench_runner", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


class QuantBenchRunnerTests(unittest.TestCase):
    def test_agent_metadata_parses_backend_thinking_and_harness(self) -> None:
        agent = runner.parse_agent(
            "sol=openai-codex/gpt-5.6-sol:max,backend=openai-codex,thinking=max,harness=OMP"
        )

        self.assertEqual(agent.name, "sol")
        self.assertEqual(agent.model, "openai-codex/gpt-5.6-sol:max")
        self.assertEqual(agent.backend_provider, "openai-codex")
        self.assertEqual(agent.thinking, "max")
        self.assertEqual(agent.harness, "OMP")
        self.assertEqual(agent.omp_model, "openai-codex/gpt-5.6-sol")
        self.assertEqual(agent.omp_thinking, "max")

    def test_agent_thinking_defaults_to_max(self) -> None:
        agent = runner.parse_agent("spark=openai-codex/gpt-5.3-codex-spark,backend=openai-codex,harness=OMP")

        self.assertEqual(agent.thinking, "max")

    def test_public_stage_contains_only_instruction_and_workspace(self) -> None:
        task = runner.task_spec("market_log_latency_summary")
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_dir = Path(temp_dir) / "attempt"
            runner.copy_public_task_view(task, attempt_dir)

            self.assertTrue((attempt_dir / "instruction.md").is_file())
            self.assertTrue((attempt_dir / "workspace" / "log_summary.py").is_file())
            self.assertFalse((attempt_dir / "tests").exists())
            self.assertFalse((attempt_dir / "solution").exists())
            self.assertFalse((attempt_dir / "task.toml").exists())
            self.assertFalse((attempt_dir / "environment").exists())


    def test_task_spec_records_promotion_metadata(self) -> None:
        promoted = runner.task_spec("sports_hold_vig_removal")

        self.assertEqual(promoted.promotion_status, "promoted")
        self.assertEqual(promoted.source_status, "source_backed")

    def test_promoted_tasks_do_not_require_diagnostic_flag(self) -> None:
        promoted = runner.task_spec("sports_hold_vig_removal")
        runner.validate_promoted_tasks([promoted], allow_unpromoted=False)

    def test_oracle_host_verifier_passes_and_records_bio_fields(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("oracle", "reference-solution", "local", "none", "REFERENCE")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.run_attempt(
                run_id="unit",
                task=task,
                agent=agent,
                output_root=Path(temp_dir),
                verifier_backend="host",
                agent_execution="host",
                tools="",
                auth_gateway_url=None,
                timeout_scale=1.0,
                oracle=True,
                dry_run=False,
            )

            self.assertTrue(result.passed, result.reason)
            self.assertEqual(result.name, "oracle")
            self.assertEqual(result.agent, "oracle")
            self.assertEqual(result.status, "PASS")
            self.assertEqual(result.backend_provider, "local")
            self.assertEqual(result.thinking, "none")
            self.assertEqual(result.harness, "REFERENCE")
            self.assertIn("PASS", result.verifier_stdout)
            attempt_dir = Path(result.attempt_dir)
            self.assertTrue((attempt_dir / "workspace" / "outputs" / "no_vig_kelly.json").is_file())
            self.assertFalse((attempt_dir / "workspace" / "tests").exists())

    def test_dry_run_records_distinct_unscored_status(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("dry", "model", "provider", "none", "OMP")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.run_attempt(
                run_id="unit",
                task=task,
                agent=agent,
                output_root=Path(temp_dir),
                verifier_backend="host",
                agent_execution="host",
                tools="",
                auth_gateway_url=None,
                timeout_scale=1.0,
                oracle=False,
                dry_run=True,
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(result.reason, "dry run skipped")
        summary = runner.summarize([result])
        self.assertEqual(summary["scored"], 0)
        self.assertIsNone(summary["pass_rate"])

    def test_summary_separates_budgeted_and_semantic_pass_rates(self) -> None:
        def row(status: str, passed: bool) -> runner.AttemptResult:
            return runner.AttemptResult(
                ts="2026-06-27T00:00:00Z",
                run_id="unit",
                task_id="sports_hold_vig_removal",
                agent="unit-agent",
                name="unit-agent",
                model="model",
                backend_provider="provider",
                thinking="none",
                harness="OMP",
                agent_execution="host",
                verifier_backend="host",
                passed=passed,
                reason=status.lower(),
                status=status,
                attempt_dir="/tmp/attempt",
                agent_returncode=0,
                verifier_returncode=0,
                agent_timeout=status == "TIME_LIMIT",
                verifier_timeout=False,
                agent_elapsed_sec=1.0,
                verifier_elapsed_sec=0.1,
                agent_stdout="",
                agent_stderr="",
                verifier_stdout="",
                verifier_stderr="",
                agent_cmd=[],
                verifier_cmd=[],
                attempt_count=1,
                max_retries=0,
                runtime_metrics=None,
            )

        summary = runner.summarize(
            [
                row("PASS", True),
                row("REJECT", False),
                row("TIME_LIMIT", False),
                row("INFRA_BLOCKED", False),
                row("DRY_RUN", False),
            ]
        )

        self.assertEqual(summary["scored"], 4)
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["pass_rate"], 0.25)
        self.assertEqual(summary["budgeted_pass_rate"], 0.25)
        self.assertEqual(summary["semantic_scored"], 2)
        self.assertEqual(summary["semantic_pass_rate"], 0.5)
        self.assertEqual(summary["time_limited"], 1)
        self.assertEqual(summary["infra_blocked"], 1)
        self.assertEqual(summary["rejected"], 1)
        self.assertEqual(summary["by_agent"]["unit-agent"]["semantic_pass_rate"], 0.5)

    def test_no_op_runs_verifier_and_rejects_unsolved_workspace(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("no-op", "no-agent", "local", "none", "NOOP")
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.run_attempt(
                run_id="unit",
                task=task,
                agent=agent,
                output_root=Path(temp_dir),
                verifier_backend="host",
                agent_execution="host",
                tools="",
                auth_gateway_url=None,
                timeout_scale=1.0,
                oracle=False,
                dry_run=False,
                no_op=True,
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "REJECT")
        self.assertEqual(result.reason, "verifier failed")
        self.assertEqual(result.agent_execution, "no-op")
        self.assertIn("no-op: agent skipped", result.agent_stdout)


    def test_bwrap_sandbox_root_stays_outside_visible_workspace(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("unit", "test-provider/model-a", "test-provider", "off", "OMP")
        orig_run_omp_cmd = runner.run_omp_cmd
        cmd_calls = []

        def mock_run_omp_cmd(cmd: list[str], *, cwd: Path, timeout: int, capture_dir: Path, env: dict[str, str] | None = None) -> runner.CommandResult:
            cmd_calls.append(cmd)
            return runner.CommandResult(0, False, 0.1, "stdout", "stderr", cmd)

        try:
            runner.run_omp_cmd = mock_run_omp_cmd
            with tempfile.TemporaryDirectory() as temp_dir:
                attempt_dir = Path(temp_dir) / "attempt"
                attempt_dir.mkdir()
                runner.run_omp_agent(
                    agent,
                    task,
                    attempt_dir,
                    execution="bwrap",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                )
            self.assertEqual(len(cmd_calls), 1)
            cmd = cmd_calls[0]
            workspace = Path(cmd[cmd.index("--workspace") + 1])
            sandbox_root = Path(cmd[cmd.index("--sandbox-root") + 1])
            self.assertEqual(workspace, attempt_dir)
            with self.assertRaises(ValueError):
                sandbox_root.relative_to(attempt_dir)
        finally:
            runner.run_omp_cmd = orig_run_omp_cmd

    def test_omp_command_max_time(self) -> None:
        agent = runner.AgentSpec("unit", "test-provider/model-a", "test-provider", "off", "OMP")
        cmd_with_time = runner.omp_command(agent, "Hello", tools="", max_time=120)
        self.assertIn("--max-time", cmd_with_time)
        self.assertEqual(cmd_with_time[cmd_with_time.index("--max-time") + 1], "120")

        cmd_without_time = runner.omp_command(agent, "Hello", tools="")
        self.assertNotIn("--max-time", cmd_without_time)

    def test_run_omp_agent_includes_scaled_timeout(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("unit", "test-provider/model-a", "test-provider", "off", "OMP")
        orig_run_omp_cmd = runner.run_omp_cmd
        cmd_calls = []
        timeouts = []

        def mock_run_omp_cmd(cmd: list[str], *, cwd: Path, timeout: int | None, capture_dir: Path, env: dict[str, str] | None = None) -> runner.CommandResult:
            cmd_calls.append(cmd)
            timeouts.append(timeout)
            return runner.CommandResult(0, False, 0.1, "stdout", "stderr", cmd)

        try:
            runner.run_omp_cmd = mock_run_omp_cmd
            with tempfile.TemporaryDirectory() as temp_dir:
                attempt_dir = Path(temp_dir) / "attempt"
                attempt_dir.mkdir()
                runner.run_omp_agent(
                    agent,
                    task,
                    attempt_dir,
                    execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                )
                runner.run_omp_agent(
                    agent,
                    task,
                    attempt_dir,
                    execution="bwrap",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=2.0,
                )

            self.assertEqual(len(cmd_calls), 2)

            expected_timeout_1 = max(1, runner.math.ceil(task.agent_timeout_sec * 1.0))
            host_cmd = cmd_calls[0]
            self.assertEqual(timeouts[0], expected_timeout_1)
            self.assertIn("--max-time", host_cmd)
            self.assertEqual(host_cmd[host_cmd.index("--max-time") + 1], str(expected_timeout_1))

            expected_timeout_2 = max(1, runner.math.ceil(task.agent_timeout_sec * 2.0))
            bwrap_cmd = cmd_calls[1]
            self.assertEqual(timeouts[1], expected_timeout_2 + 45)
            omp_index = bwrap_cmd.index("omp")
            omp_subcmd = bwrap_cmd[omp_index:]
            self.assertIn("--max-time", omp_subcmd)
            self.assertEqual(omp_subcmd[omp_subcmd.index("--max-time") + 1], str(expected_timeout_2))
        finally:
            runner.run_omp_cmd = orig_run_omp_cmd

    def test_run_omp_agent_omits_max_time_when_agent_timeout_unset(self) -> None:
        import dataclasses

        task = dataclasses.replace(runner.task_spec("sports_hold_vig_removal"), agent_timeout_sec=None)
        agent = runner.AgentSpec("unit", "test-provider/model-a", "test-provider", "off", "OMP")
        orig_run_omp_cmd = runner.run_omp_cmd
        cmd_calls = []
        timeouts = []

        def mock_run_omp_cmd(cmd: list[str], *, cwd: Path, timeout: int | None, capture_dir: Path, env: dict[str, str] | None = None) -> runner.CommandResult:
            cmd_calls.append(cmd)
            timeouts.append(timeout)
            return runner.CommandResult(0, False, 0.1, "stdout", "stderr", cmd)

        try:
            runner.run_omp_cmd = mock_run_omp_cmd
            with tempfile.TemporaryDirectory() as temp_dir:
                attempt_dir = Path(temp_dir) / "attempt"
                attempt_dir.mkdir()
                runner.run_omp_agent(
                    agent,
                    task,
                    attempt_dir,
                    execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                )

            self.assertEqual(len(cmd_calls), 1)
            self.assertIsNone(timeouts[0])
            self.assertNotIn("--max-time", cmd_calls[0])
        finally:
            runner.run_omp_cmd = orig_run_omp_cmd

    def test_run_omp_cmd_streams_jsonl_and_bounds_in_memory_output(self) -> None:
        event = {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": "final answer",
                "usage": {"input": 10, "output": 2, "totalTokens": 12},
                "stopReason": "stop",
            },
        }
        script = (
            "import json,sys;"
            "print('x'*1000000);"
            f"print(json.dumps({event!r}));"
            "print('e'*10000,file=sys.stderr)"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir)
            result = runner.run_omp_cmd(
                [sys.executable, "-c", script],
                cwd=capture_dir,
                timeout=30,
                capture_dir=capture_dir,
            )
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "final answer")
            self.assertTrue(result.message_end)
            self.assertLessEqual(len(result.stderr), 4000)
            self.assertGreater((capture_dir / "agent-stdout.jsonl").stat().st_size, 1_000_000)
            self.assertGreater((capture_dir / "agent-stderr.log").stat().st_size, 10_000)
            self.assertEqual(result.capture["usage"]["total_tokens"], 12)

    def test_run_omp_cmd_timeout_invokes_cleanup(self) -> None:
        cleanup_calls: list[bool] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir)
            result = runner.run_omp_cmd(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                cwd=capture_dir,
                timeout=0.01,
                capture_dir=capture_dir,
                timeout_cleanup=lambda: cleanup_calls.append(True),
            )
        self.assertTrue(result.timeout)
        self.assertEqual(result.failure_code, runner.FailureCode.AGENT_TIMEOUT)
        self.assertEqual(cleanup_calls, [True])

    def test_force_remove_docker_container_uses_cidfile(self) -> None:
        import unittest.mock
        with tempfile.TemporaryDirectory() as temp_dir:
            cidfile = Path(temp_dir) / "agent.cid"
            cidfile.write_text("abc123\n", encoding="utf-8")
            with unittest.mock.patch.object(runner.subprocess, "run") as run:
                runner._force_remove_docker_container("/usr/bin/docker", cidfile)
        self.assertEqual(run.call_args.args[0], ["/usr/bin/docker", "rm", "-f", "abc123"])
        self.assertIs(run.call_args.kwargs["stdout"], runner.subprocess.DEVNULL)
        self.assertIs(run.call_args.kwargs["stderr"], runner.subprocess.DEVNULL)

    def test_run_cmd_timeout_defaults_to_verifier_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = runner.run_cmd(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                cwd=Path(temp_dir),
                timeout=0.01,
            )
        self.assertTrue(result.timeout)
        self.assertEqual(result.failure_code, runner.FailureCode.VERIFIER_TIMEOUT)

    def test_oracle_timeout_is_reclassified_to_agent_phase(self) -> None:
        import unittest.mock
        task = runner.task_spec("sports_hold_vig_removal")
        timed_out = runner.CommandResult(
            124, True, 1.0, "", "", [], runner.FailureCode.VERIFIER_TIMEOUT
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_dir = Path(temp_dir)
            runner.copy_public_task_view(task, attempt_dir)
            with unittest.mock.patch.object(runner, "run_cmd", return_value=timed_out):
                result = runner.run_oracle_solution(task, attempt_dir)
        self.assertEqual(result.failure_code, runner.FailureCode.AGENT_TIMEOUT)

    def test_docker_verifier_reports_missing_docker_cleanly(self) -> None:
        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = ""
            task = runner.task_spec("sports_hold_vig_removal")
            with tempfile.TemporaryDirectory() as temp_dir:
                attempt_dir = Path(temp_dir) / "attempt"
                runner.copy_public_task_view(task, attempt_dir)
                result = runner.run_docker_verifier(task, attempt_dir)
            self.assertEqual(result.returncode, 127)
            self.assertIn("docker executable not found", result.stderr)
        finally:
            os.environ["PATH"] = old_path

    def test_host_verifier_uses_scrubbed_environment(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        original_run_cmd = runner.run_cmd
        captured: dict[str, object] = {}

        def fake_run_cmd(cmd: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> runner.CommandResult:
            captured["env"] = env
            captured["cwd"] = cwd
            return runner.CommandResult(0, False, 0.1, "PASS", "", cmd)

        runner.run_cmd = fake_run_cmd
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                attempt_dir = Path(temp_dir) / "attempt"
                runner.copy_public_task_view(task, attempt_dir)
                runner.run_host_verifier(task, attempt_dir)
        finally:
            runner.run_cmd = original_run_cmd

        env = captured["env"]
        self.assertIsInstance(env, dict)
        assert isinstance(env, dict)
        self.assertEqual(env["PATH"], "/usr/bin:/bin")
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertIn("TASK_SCRIPT_TIMEOUT_SEC", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("OMP_AUTH_TOKEN", env)

    def test_list_agent_candidates(self) -> None:
        mock_resolver_called = []

        def mock_thinking_resolver(model: str) -> str:
            mock_resolver_called.append(model)
            return "mocked-thinking-level"

        rows = runner.get_agent_candidates(thinking_resolver=mock_thinking_resolver)

        # Ensure our mock resolver was called for every candidate
        self.assertEqual(len(mock_resolver_called), len(runner.QUANT_BENCH_AGENT_CANDIDATES))

        # Ensure the candidate slate names are unique
        names = [row["name"] for row in rows]
        self.assertEqual(len(names), len(set(names)))

        # Ensure rows include OMP harness, backend, and thinking fields
        for row in rows:
            self.assertIn("name", row)
            self.assertIn("model", row)
            self.assertEqual(row["harness"], "OMP")
            self.assertEqual(row["thinking"], "mocked-thinking-level")
            self.assertIn("backend_provider", row)

    def test_manifest_candidate_listing_preserves_frozen_thinking(self) -> None:
        manifest_text = """
schema_version = "1.0"

[agent_sets]
official = ["gpt-5-6-luna", "gpt-5-6-terra"]

[[agents]]
name = "gpt-5-6-luna"
model = "openai-codex/gpt-5.6-luna"
backend_provider = "openai-codex"
thinking = "xhigh"
harness = "OMP"

[[agents]]
name = "gpt-5-6-terra"
model = "openai-codex/gpt-5.6-terra"
backend_provider = "openai-codex"
thinking = "xhigh"
harness = "OMP"
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.toml"
            manifest_path.write_text(manifest_text, encoding="utf-8")
            output = io.StringIO()
            with unittest.mock.patch.object(runner, "highest_known_thinking", return_value="max"), contextlib.redirect_stdout(output):
                code = runner.main(["--manifest", str(manifest_path), "--list-agent-candidates"])
        self.assertEqual(code, 0)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual({row["name"] for row in rows}, {"gpt-5-6-luna", "gpt-5-6-terra"})
        self.assertTrue(all(row["thinking"] == "xhigh" for row in rows))
        self.assertTrue(all(row["current_highest_thinking"] == "max" for row in rows))

    def test_default_tasks_do_not_require_image(self) -> None:
        tasks = [runner.task_spec(task_id) for task_id in runner.DEFAULT_TASKS]

        self.assertEqual(len(tasks), 24)
        self.assertTrue(all(task.requires_image is False for task in tasks))

    def test_list_agent_candidates_text_compatible(self) -> None:
        mock_resolver_called = []

        def mock_thinking_resolver(model: str) -> str:
            mock_resolver_called.append(model)
            return "mocked-thinking-level"

        rows = runner.get_agent_candidates(thinking_resolver=mock_thinking_resolver, slate="text-compatible")

        expected_count = len(runner.QUANT_BENCH_AGENT_CANDIDATES)
        self.assertEqual(expected_count, 4)
        self.assertEqual(len(mock_resolver_called), expected_count)

        names = [row["name"] for row in rows]
        self.assertEqual(
            set(names),
            {"gpt-5-6-sol", "gpt-5-6-luna", "gpt-5-6-terra", "swe-1-7-devin"},
        )

        # Ensure rows include OMP harness, backend, and thinking fields
        for row in rows:
            self.assertIn("name", row)
            self.assertIn("model", row)
            self.assertEqual(row["harness"], "OMP")
            self.assertEqual(row["thinking"], "mocked-thinking-level")
            self.assertIn("backend_provider", row)

    def test_highest_known_thinking_rejects_neighboring_selector_metadata(self) -> None:
        class Completed:
            def __init__(self, stdout: str) -> None:
                self.returncode = 0
                self.stdout = stdout
                self.stderr = ""

        calls: list[list[str]] = []

        def fake_run(cmd, **_kwargs):
            calls.append(cmd)
            if cmd[:3] == ["omp", "models", "--json"]:
                return Completed('{"models":[]}')
            return Completed('{"models":[{"selector":"provider/model","thinking":["high"]}]}')

        original_run = runner.subprocess.run
        original_cache = runner._OMP_MODELS_CACHE
        runner.subprocess.run = fake_run
        runner._OMP_MODELS_CACHE = None
        try:
            with self.assertRaisesRegex(RuntimeError, "exact selector"):
                runner.highest_known_thinking("provider/model-fast")
        finally:
            runner.subprocess.run = original_run
            runner._OMP_MODELS_CACHE = original_cache

        self.assertEqual(calls[1][:3], ["omp", "models", "find"])

    def test_parse_agent_name_resolution(self) -> None:
        agent = runner.parse_agent("gpt-5-6-sol")
        self.assertEqual(agent.name, "gpt-5-6-sol")
        self.assertEqual(agent.model, "openai-codex/gpt-5.6-sol")
        self.assertEqual(agent.backend_provider, "openai-codex")

        agent = runner.parse_agent("swe-1-7-devin")
        self.assertEqual(agent.name, "swe-1-7-devin")
        self.assertEqual(agent.model, "devin/swe-1-7")
        self.assertEqual(agent.backend_provider, "devin")

        agent = runner.parse_agent("my-name=gpt-5-6-terra,backend=custom,thinking=low")
        self.assertEqual(agent.name, "my-name")
        self.assertEqual(agent.model, "openai-codex/gpt-5.6-terra")
        self.assertEqual(agent.backend_provider, "custom")
        self.assertEqual(agent.thinking, "low")

        agent = runner.parse_agent("my-model")
        self.assertEqual(agent.name, "my-model")
        self.assertEqual(agent.model, "my-model")
        self.assertEqual(agent.backend_provider, "unknown")

    def test_public_candidate_list_is_completed_only(self) -> None:
        self.assertEqual(runner.QUANT_BENCH_TEXT_ONLY_HOLDOUTS, ())
        self.assertEqual(
            {candidate[0] for candidate in runner.QUANT_BENCH_AGENT_CANDIDATES},
            {"gpt-5-6-sol", "gpt-5-6-luna", "gpt-5-6-terra", "swe-1-7-devin"},
        )

    def test_timeout_scale_default(self) -> None:
        args = runner.parse_args([])
        self.assertEqual(args.timeout_scale, runner.DEFAULT_TIMEOUT_SCALE)
        self.assertEqual(args.agent_execution, "docker")
    def test_max_retries_cli_parsing(self) -> None:
        args = runner.parse_args([])
        self.assertEqual(args.max_retries, 3)

        # Specifying max_retries should be parsed correctly
        args = runner.parse_args(["--max-retries", "5"])
        self.assertEqual(args.max_retries, 5)

    def test_attempts_cli_parsing(self) -> None:
        args = runner.parse_args([])
        self.assertEqual(args.attempts, 5)

        # Specifying attempts should be parsed correctly
        args = runner.parse_args(["--attempts", "3"])
        self.assertEqual(args.attempts, 3)
        self.assertEqual(args.attempt_start, 1)
        continuation = runner.parse_args(["--attempts", "4", "--attempt-start", "2"])
        self.assertEqual(continuation.attempts, 4)
        self.assertEqual(continuation.attempt_start, 2)

    def test_attempts_validation(self) -> None:
        import sys
        from io import StringIO
        orig_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            exit_code = runner.main(["--attempts", "0", "--agent", "oracle", "--task", "sports_hold_vig_removal"])
            self.assertEqual(exit_code, 2)
            self.assertIn("--attempts must be at least 1", sys.stderr.getvalue())
        finally:
            sys.stderr = orig_stderr

        orig_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            exit_code = runner.main([
                "--attempts", "1", "--attempt-start", "0", "--agent", "oracle",
                "--task", "sports_hold_vig_removal",
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("--attempt-start must be at least 1", sys.stderr.getvalue())
        finally:
            sys.stderr = orig_stderr

    def test_concurrency_cli_parsing(self) -> None:
        args = runner.parse_args([])
        self.assertEqual(args.concurrency, 64)
        self.assertEqual(args.progress_interval_sec, runner.DEFAULT_PROGRESS_INTERVAL_SEC)

        # Specifying concurrency and heartbeat interval should be parsed correctly
        args = runner.parse_args(["--concurrency", "8", "--progress-interval-sec", "15"])
        self.assertEqual(args.concurrency, 8)
        self.assertEqual(args.progress_interval_sec, 15)

    def test_effective_concurrency_defaults_and_validation(self) -> None:
        args = runner.parse_args([])
        self.assertEqual(args.local_memory_budget_mb, 10000)
        self.assertEqual(args.trial_memory_reserve_mb, 10000)
        self.assertFalse(args.disable_memory_concurrency_cap)

        eff = runner.get_effective_concurrency(args)
        self.assertEqual(eff, 1)

        args_c4 = runner.parse_args(["--concurrency", "4"])
        self.assertEqual(runner.get_effective_concurrency(args_c4), 1)

        args_disabled = runner.parse_args(["--disable-memory-concurrency-cap"])
        self.assertTrue(args_disabled.disable_memory_concurrency_cap)
        self.assertEqual(runner.get_effective_concurrency(args_disabled), 64)

        args_disabled_c12 = runner.parse_args(["--disable-memory-concurrency-cap", "--concurrency", "12"])
        self.assertEqual(runner.get_effective_concurrency(args_disabled_c12), 12)

        args_custom = runner.parse_args(["--local-memory-budget-mb", "5000", "--trial-memory-reserve-mb", "2000"])
        self.assertEqual(args_custom.local_memory_budget_mb, 5000)
        self.assertEqual(args_custom.trial_memory_reserve_mb, 2000)
        self.assertEqual(runner.get_effective_concurrency(args_custom), 2)

    def test_memory_concurrency_validation(self) -> None:
        import sys
        from io import StringIO
        orig_stderr = sys.stderr
        try:
            sys.stderr = StringIO()
            exit_code = runner.main([
                "--local-memory-budget-mb", "0",
                "--agent", "oracle",
                "--task", "sports_hold_vig_removal"
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("--local-memory-budget-mb must be positive", sys.stderr.getvalue())

            sys.stderr = StringIO()
            exit_code = runner.main([
                "--trial-memory-reserve-mb", "-5",
                "--agent", "oracle",
                "--task", "sports_hold_vig_removal"
            ])
            self.assertEqual(exit_code, 2)
            self.assertIn("--trial-memory-reserve-mb must be positive", sys.stderr.getvalue())
        finally:
            sys.stderr = orig_stderr

    def test_concurrency_validation(self) -> None:
        import sys
        from io import StringIO
        orig_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            exit_code = runner.main(["--concurrency", "0", "--agent", "oracle", "--task", "sports_hold_vig_removal"])
            self.assertEqual(exit_code, 2)
            self.assertIn("--concurrency must be at least 1", sys.stderr.getvalue())

            sys.stderr = StringIO()
            exit_code = runner.main(["--progress-interval-sec", "-1", "--agent", "oracle", "--task", "sports_hold_vig_removal"])
            self.assertEqual(exit_code, 2)
            self.assertIn("--progress-interval-sec must be non-negative", sys.stderr.getvalue())
        finally:
            sys.stderr = orig_stderr
    def test_default_does_not_retry_on_agent_timeout(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("test-agent", "model", "provider", "none", "OMP")

        agent_calls = 0
        def mock_run_omp_agent(*args, **kwargs) -> runner.CommandResult:
            nonlocal agent_calls
            agent_calls += 1
            return runner.CommandResult(1, True, 0.1, "timeout", "stderr", [])

        orig_run_omp_agent = runner.run_omp_agent
        runner.run_omp_agent = mock_run_omp_agent
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit-test",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                )
                self.assertEqual(agent_calls, 1)
                self.assertEqual(result.attempt_count, 1)
                self.assertEqual(result.max_retries, 3)
                self.assertFalse(result.passed)
                self.assertEqual(result.reason, "agent timeout")
                self.assertEqual(result.status, "TIME_LIMIT")
        finally:
            runner.run_omp_agent = orig_run_omp_agent

    def test_agent_nonzero_at_declared_budget_is_time_limit(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("test-agent", "model", "provider", "none", "OMP")

        agent_calls = 0
        def mock_run_omp_agent(*args, **kwargs) -> runner.CommandResult:
            nonlocal agent_calls
            agent_calls += 1
            return runner.CommandResult(
                1,
                False,
                task.agent_timeout_sec,
                "",
                "session reached max time",
                [],
            )

        orig_run_omp_agent = runner.run_omp_agent
        runner.run_omp_agent = mock_run_omp_agent
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit-test",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=2,
                )
                self.assertEqual(agent_calls, 1)
                self.assertEqual(result.attempt_count, 1)
                self.assertTrue(result.agent_timeout)
                self.assertEqual(result.reason, "agent timeout")
                self.assertEqual(result.status, "TIME_LIMIT")
                self.assertEqual(result.failure_code, runner.FailureCode.AGENT_TIMEOUT.value)
        finally:
            runner.run_omp_agent = orig_run_omp_agent

    def test_retry_on_agent_nonzero_exit(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("test-agent", "model", "provider", "none", "OMP")

        agent_calls = 0
        def mock_run_omp_agent(*args, **kwargs) -> runner.CommandResult:
            nonlocal agent_calls
            agent_calls += 1
            return runner.CommandResult(1, False, 0.1, "", "nonzero exit", [])

        orig_run_omp_agent = runner.run_omp_agent
        runner.run_omp_agent = mock_run_omp_agent
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit-test",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=2,
                )
                # max_retries = 2, so 3 attempts total (1 initial + 2 retries)
                self.assertEqual(agent_calls, 3)
                self.assertEqual(result.attempt_count, 3)
                self.assertEqual(result.max_retries, 2)
                self.assertFalse(result.passed)
                self.assertEqual(result.reason, "agent nonzero exit")
                self.assertEqual(result.status, "INFRA_BLOCKED")
        finally:
            runner.run_omp_agent = orig_run_omp_agent

    def test_no_retry_on_verifier_timeout(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("test-agent", "model", "provider", "none", "OMP")

        agent_calls = 0
        verifier_calls = 0
        def mock_run_omp_agent(*args, **kwargs) -> runner.CommandResult:
            nonlocal agent_calls
            agent_calls += 1
            return runner.CommandResult(0, False, 0.1, "agent ok", "", [])

        def mock_run_verifier(*args, **kwargs) -> runner.CommandResult:
            nonlocal verifier_calls
            verifier_calls += 1
            return runner.CommandResult(1, True, 0.1, "", "verifier timeout", [])

        orig_run_omp_agent = runner.run_omp_agent
        orig_run_verifier = runner.run_verifier
        runner.run_omp_agent = mock_run_omp_agent
        runner.run_verifier = mock_run_verifier
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit-test",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=2,
                )
                # A verifier timeout is a time-budget, right-censored outcome;
                # retrying with the same budget just repeats the censoring.
                self.assertEqual(agent_calls, 1)
                self.assertEqual(verifier_calls, 1)
                self.assertEqual(result.attempt_count, 1)
                self.assertEqual(result.max_retries, 2)
                self.assertFalse(result.passed)
                self.assertEqual(result.reason, "verifier timeout")
                self.assertEqual(result.status, "TIME_LIMIT")
        finally:
            runner.run_omp_agent = orig_run_omp_agent
            runner.run_verifier = orig_run_verifier

    def test_no_retry_on_semantic_verifier_failure(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("test-agent", "model", "provider", "none", "OMP")

        agent_calls = 0
        verifier_calls = 0
        def mock_run_omp_agent(*args, **kwargs) -> runner.CommandResult:
            nonlocal agent_calls
            agent_calls += 1
            return runner.CommandResult(0, False, 0.1, "agent ok", "", [])

        def mock_run_verifier(*args, **kwargs) -> runner.CommandResult:
            nonlocal verifier_calls
            verifier_calls += 1
            return runner.CommandResult(1, False, 0.1, "", "assertion failed", [])

        orig_run_omp_agent = runner.run_omp_agent
        orig_run_verifier = runner.run_verifier
        runner.run_omp_agent = mock_run_omp_agent
        runner.run_verifier = mock_run_verifier
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit-test",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=3,
                )
                # Semantic failure should NOT be retried.
                self.assertEqual(agent_calls, 1)
                self.assertEqual(verifier_calls, 1)
                self.assertEqual(result.attempt_count, 1)
                self.assertEqual(result.max_retries, 3)
                self.assertFalse(result.passed)
                self.assertEqual(result.reason, "verifier failed")
                self.assertEqual(result.status, "REJECT")
        finally:
            runner.run_omp_agent = orig_run_omp_agent
            runner.run_verifier = orig_run_verifier

    def test_no_retry_on_success(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("test-agent", "model", "provider", "none", "OMP")

        agent_calls = 0
        verifier_calls = 0
        def mock_run_omp_agent(*args, **kwargs) -> runner.CommandResult:
            nonlocal agent_calls
            agent_calls += 1
            return runner.CommandResult(0, False, 0.1, "agent ok", "", [])

        def mock_run_verifier(*args, **kwargs) -> runner.CommandResult:
            nonlocal verifier_calls
            verifier_calls += 1
            return runner.CommandResult(0, False, 0.1, "tests passed", "", [])

        orig_run_omp_agent = runner.run_omp_agent
        orig_run_verifier = runner.run_verifier
        runner.run_omp_agent = mock_run_omp_agent
        runner.run_verifier = mock_run_verifier
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit-test",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=3,
                )
                self.assertEqual(agent_calls, 1)
                self.assertEqual(verifier_calls, 1)
                self.assertEqual(result.attempt_count, 1)
                self.assertEqual(result.max_retries, 3)
                self.assertTrue(result.passed)
                self.assertEqual(result.reason, "passed hidden verifier")
                self.assertEqual(result.status, "PASS")
        finally:
            runner.run_omp_agent = orig_run_omp_agent
            runner.run_verifier = orig_run_verifier

    def test_docker_image_tag_is_stable_sha256(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        tag1 = runner.docker_image_tag(task)
        tag2 = runner.docker_image_tag(task)
        self.assertEqual(tag1, tag2)
        prefix, sep, digest = tag1.rpartition(":")
        self.assertEqual(sep, ":")
        self.assertEqual(len(digest), 16)
        int(digest, 16)

    def test_docker_image_tag_includes_environment_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "task"
            environment = root / "environment"
            environment.mkdir(parents=True)
            dockerfile = environment / "Dockerfile"
            dockerfile.write_text("FROM python:3.13-slim-bookworm\n", encoding="utf-8")
            requirements = environment / "requirements.txt"
            requirements.write_text("alpha\n", encoding="utf-8")
            task = runner.TaskSpec(
                task_id="unit_task",
                root=root,
                instruction_path=root / "instruction.md",
                workspace_path=root / "workspace",
                tests_path=root / "tests",
                dockerfile_path=dockerfile,
                solution_path=root / "solution" / "solve.py",
                agent_timeout_sec=1,
                verifier_timeout_sec=1,
                build_timeout_sec=1,
            )
            first = runner.docker_image_tag(task)
            requirements.write_text("beta\n", encoding="utf-8")
            self.assertNotEqual(first, runner.docker_image_tag(task))

    def test_docker_verifier_command_construction(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        orig_which = shutil.which
        orig_run_cmd = runner.run_cmd
        cmd_calls = []

        def mock_run_cmd(cmd: list[str], *, cwd: Path, timeout: int | None, env: dict[str, str] | None = None) -> runner.CommandResult:
            cmd_calls.append(cmd)
            return runner.CommandResult(0, False, 0.1, "sha256:immutable", "", cmd)

        try:
            shutil.which = lambda name: "/usr/bin/docker" if name == "docker" else None
            runner.run_cmd = mock_run_cmd
            with tempfile.TemporaryDirectory() as temp_dir:
                attempt_dir = Path(temp_dir) / "attempt"
                runner.copy_public_task_view(task, attempt_dir)
                result = runner.run_docker_verifier(task, attempt_dir)
                self.assertEqual(result.returncode, 0)
            self.assertEqual(len(cmd_calls), 4)
            run_cmd_args = cmd_calls[-1]
            self.assertEqual(run_cmd_args[0:2], ["/usr/bin/docker", "run"])
            self.assertIn("--network", run_cmd_args)
            self.assertEqual(run_cmd_args[run_cmd_args.index("--network") + 1], "none")
            self.assertIn("--read-only", run_cmd_args)
            self.assertIn("--tmpfs", run_cmd_args)
            self.assertTrue(any("/tmp:" in arg for arg in run_cmd_args))
            self.assertIn("--user", run_cmd_args)
            self.assertEqual(run_cmd_args[run_cmd_args.index("--user") + 1], f"{os.getuid()}:{os.getgid()}")
            self.assertIn("--security-opt", run_cmd_args)
            self.assertEqual(run_cmd_args[run_cmd_args.index("--security-opt") + 1], "no-new-privileges")
            self.assertIn("--cap-drop", run_cmd_args)
            self.assertEqual(run_cmd_args[run_cmd_args.index("--cap-drop") + 1], "ALL")
            self.assertIn("python -m pytest -q /tests", run_cmd_args[-1])
            self.assertTrue(any(arg.endswith(":/tests:ro") for arg in run_cmd_args))
            self.assertNotIn("test_outputs.py", run_cmd_args)
        finally:
            shutil.which = orig_which
            runner.run_cmd = orig_run_cmd
    def test_result_reason_classifies_missing_docker_as_infra(self) -> None:
        agent_result = runner.CommandResult(0, False, 0.1, "", "", [])
        verifier_result = runner.CommandResult(127, False, 0.0, "", "docker executable not found", [])

        self.assertEqual(
            runner.result_reason(agent_result, verifier_result),
            (False, "verifier infrastructure unavailable"),
        )

    def test_result_reason_classifies_docker_build_failure_as_infra(self) -> None:
        agent_result = runner.CommandResult(0, False, 0.1, "", "", [])
        verifier_result = runner.CommandResult(1, False, 0.0, "", "build failed", ["/usr/bin/docker", "build"])

        passed, reason = runner.result_reason(agent_result, verifier_result)
        self.assertFalse(passed)
        self.assertEqual(reason, "verifier build failed")
        self.assertEqual(runner.result_status(passed, reason), "INFRA_BLOCKED")

    def test_result_reason_classifies_docker_build_timeout_as_infra(self) -> None:
        agent_result = runner.CommandResult(0, False, 0.1, "", "", [])
        verifier_result = runner.CommandResult(1, True, 0.0, "", "timeout", ["/usr/bin/docker", "build"])

        passed, reason = runner.result_reason(agent_result, verifier_result)
        self.assertFalse(passed)
        self.assertEqual(reason, "verifier build timeout")
        self.assertEqual(runner.result_status(passed, reason), "INFRA_BLOCKED")

    def test_result_status_classifies_process_timeouts_as_time_limit(self) -> None:
        self.assertEqual(runner.result_status(False, "agent timeout"), "TIME_LIMIT")
        self.assertEqual(runner.result_status(False, "verifier timeout"), "TIME_LIMIT")
        self.assertEqual(runner.result_status(False, "agent nonzero exit"), "INFRA_BLOCKED")
        self.assertEqual(runner.result_status(False, "verifier build timeout"), "INFRA_BLOCKED")
        self.assertEqual(runner.result_status(False, "verifier build failed"), "INFRA_BLOCKED")
        self.assertEqual(runner.result_status(False, "verifier infrastructure unavailable"), "INFRA_BLOCKED")
        self.assertEqual(runner.result_status(False, "verifier failed"), "REJECT")
        self.assertEqual(runner.result_status(True, "passed hidden verifier"), "PASS")

    def test_omp_agent_metrics_extracted_successfully(self) -> None:
        import json
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("unit", "test-provider/model-a", "test-provider", "off", "OMP")

        orig_run_cmd = runner.run_cmd
        orig_run_omp_cmd = runner.run_omp_cmd

        omp_events = [
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": "Final correct solution text",
                    "usage": {
                        "input": 120,
                        "output": 60,
                        "totalTokens": 180,
                        "cacheRead": 30,
                    },
                    "ttft": 250,
                    "duration": 750,
                    "stopReason": "stop"
                }
            }
        ]
        agent_stdout = "\n".join(json.dumps(e) for e in omp_events) + "\n"

        def mock_run_cmd(cmd: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> runner.CommandResult:
            if "test_outputs.py" in str(cmd) or "hidden_pytest_style_runner" in str(cmd):
                return runner.CommandResult(0, False, 0.1, "PASS: all tests passed", "", cmd)
            return runner.CommandResult(0, False, 0.5, agent_stdout, "", cmd)

        try:
            runner.run_cmd = mock_run_cmd
            runner.run_omp_cmd = lambda cmd, *, cwd, timeout, capture_dir, env=None: mock_run_cmd(
                cmd, cwd=cwd, timeout=timeout, env=env
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=0,
                )

                self.assertEqual(result.agent_stdout, "Final correct solution text")
                self.assertEqual(result.agent_returncode, 0)
                self.assertIsNotNone(result.runtime_metrics)
                metrics = result.runtime_metrics

                self.assertEqual(metrics["latency"]["ttft_ms"], 250)
                self.assertEqual(metrics["latency"]["generation_ms"], 500)
                self.assertEqual(metrics["latency"]["provider_ms"], 750)

                self.assertEqual(metrics["tokens"]["input"], 150)
                self.assertEqual(metrics["tokens"]["output"], 60)
                self.assertEqual(metrics["tokens"]["total"], 210)

                self.assertEqual(metrics["throughput"]["output_tok_s"], 80.0)
                self.assertEqual(metrics["throughput"]["wall_output_tok_s"], 120.0)
                self.assertEqual(metrics["throughput"]["total_tok_s"], 420.0)
                self.assertEqual(result.status, "PASS")
        finally:
            runner.run_cmd = orig_run_cmd
            runner.run_omp_cmd = orig_run_omp_cmd

    def test_omp_agent_provider_error_fails_attempt(self) -> None:
        import json
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("unit", "test-provider/model-a", "test-provider", "off", "OMP")

        orig_run_cmd = runner.run_cmd
        orig_run_omp_cmd = runner.run_omp_cmd

        omp_events = [
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "stopReason": "error",
                    "errorMessage": "Safety block triggered"
                }
            }
        ]
        agent_stdout = "\n".join(json.dumps(e) for e in omp_events) + "\n"

        cmd_calls = []

        def mock_run_cmd(cmd: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> runner.CommandResult:
            cmd_calls.append(cmd)
            return runner.CommandResult(0, False, 0.5, agent_stdout, "", cmd)

        try:
            runner.run_cmd = mock_run_cmd
            runner.run_omp_cmd = lambda cmd, *, cwd, timeout, capture_dir, env=None: mock_run_cmd(
                cmd, cwd=cwd, timeout=timeout, env=env
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=0,
                )

                self.assertFalse(result.passed)
                self.assertEqual(result.agent_returncode, 1)
                self.assertEqual(result.status, "INFRA_BLOCKED")
                self.assertEqual(result.reason, "agent nonzero exit")
                self.assertIn("Safety block triggered", result.agent_stderr)

                self.assertTrue(len(cmd_calls) > 0)
                for cmd in cmd_calls:
                    cmd_str = str(cmd)
                    self.assertNotIn("test_outputs.py", cmd_str)
                    self.assertNotIn("hidden_pytest_style_runner", cmd_str)
        finally:
            runner.run_cmd = orig_run_cmd
            runner.run_omp_cmd = orig_run_omp_cmd

    def test_retry_metric_aggregation(self) -> None:
        import json
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("unit-retry", "test-provider/model-a", "test-provider", "off", "OMP")

        orig_run_cmd = runner.run_cmd
        orig_run_omp_cmd = runner.run_omp_cmd

        omp_events_attempt1 = [
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": "Failed first attempt",
                    "usage": {
                        "input": 100,
                        "output": 50,
                        "totalTokens": 150,
                        "cacheRead": 20,
                    },
                    "ttft": 200,
                    "duration": 500,
                    "stopReason": "error"
                }
            }
        ]
        agent_stdout_1 = "\n".join(json.dumps(e) for e in omp_events_attempt1) + "\n"

        omp_events_attempt2 = [
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": "Passed second attempt",
                    "usage": {
                        "input": 200,
                        "output": 100,
                        "totalTokens": 300,
                        "cacheRead": 40,
                    },
                    "ttft": 300,
                    "duration": 1000,
                    "stopReason": "stop"
                }
            }
        ]
        agent_stdout_2 = "\n".join(json.dumps(e) for e in omp_events_attempt2) + "\n"

        cmd_calls = []

        def mock_run_cmd(cmd: list[str], *, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> runner.CommandResult:
            cmd_calls.append(cmd)
            # If it's a verifier run
            if "test_outputs.py" in str(cmd) or "hidden_pytest_style_runner" in str(cmd):
                return runner.CommandResult(0, False, 0.1, "PASS: verifier passed", "", cmd)
            # First agent run fails with nonzero exit
            if len(cmd_calls) == 1:
                return runner.CommandResult(1, False, 0.5, agent_stdout_1, "nonzero exit mock", cmd)
            # Second agent run succeeds
            return runner.CommandResult(0, False, 0.5, agent_stdout_2, "", cmd)

        try:
            runner.run_cmd = mock_run_cmd
            runner.run_omp_cmd = lambda cmd, *, cwd, timeout, capture_dir, env=None: mock_run_cmd(
                cmd, cwd=cwd, timeout=timeout, env=env
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                result = runner.run_attempt(
                    run_id="unit-retry-test",
                    task=task,
                    agent=agent,
                    output_root=Path(temp_dir),
                    verifier_backend="host",
                    agent_execution="host",
                    tools="",
                    auth_gateway_url=None,
                    timeout_scale=1.0,
                    oracle=False,
                    dry_run=False,
                    max_retries=1,
                )

                # Check final attempt outcome
                self.assertEqual(result.agent_stdout, "Passed second attempt")
                self.assertEqual(result.agent_returncode, 0)
                self.assertEqual(result.status, "PASS")
                self.assertEqual(result.attempt_count, 2)

                # Semantic metrics describe only the accepted terminal attempt.
                self.assertIsNotNone(result.runtime_metrics)
                metrics = result.runtime_metrics
                self.assertEqual(metrics["tokens"]["input"], 240)
                self.assertEqual(metrics["tokens"]["output"], 100)
                self.assertEqual(metrics["tokens"]["total"], 340)
                self.assertEqual(metrics["latency"]["ttft_ms"], 300)
                self.assertEqual(metrics["latency"]["provider_ms"], 1000)
                self.assertEqual(metrics["cache"]["input_cached"], 40)
                self.assertEqual(metrics["cache"]["input_total"], 240)

                # Attempted usage preserves observed retry cost but never
                # presents that work as useful model throughput.
                attempted = result.attempted_runtime_metrics
                self.assertIsNotNone(attempted)
                self.assertEqual(attempted["tokens"]["input"], 360)
                self.assertEqual(attempted["tokens"]["output"], 150)
                self.assertEqual(attempted["tokens"]["total"], 510)
                self.assertEqual(attempted["latency"]["provider_ms"], 1500)
                self.assertNotIn("throughput", attempted)
                self.assertEqual(
                    attempted["attempts"],
                    {
                        "runner_attempts": 2,
                        "runner_retries": 1,
                        "observed_failed_model_turns": 1,
                        "failed_runner_attempts_without_usage": 0,
                    },
                )

        finally:
            runner.run_cmd = orig_run_cmd
            runner.run_omp_cmd = orig_run_omp_cmd

    def test_summarize_runtime_metrics(self) -> None:
        from dataclasses import replace
        # Create some mock AttemptResults with live metrics
        metrics_1 = {
            "source": "provider_usage",
            "latency": {"wall_ms": 1000, "ttft_ms": 200, "generation_ms": 800, "provider_ms": 1000},
            "tokens": {"input": 100, "output": 50, "reasoning_output": 0, "total": 150, "visible_output_est": 50},
            "cache": {"supported": True, "prompt_cache_hit": True, "input_cached": 20, "input_cache_write": 0, "input_uncached": 80, "input_total": 100, "cache_read_ratio": 0.2, "response_cache_hit": False},
            "throughput": {"output_tok_s": 50.0, "wall_output_tok_s": 50.0, "total_tok_s": 150.0},
            "provider_route": "test-provider/model-a",
            "notes": {"accounting": "semantic_model_turns"},
        }

        metrics_2 = {
            "source": "provider_usage",
            "latency": {"wall_ms": 2000, "ttft_ms": 300, "generation_ms": 1700, "provider_ms": 2000},
            "tokens": {"input": 200, "output": 100, "reasoning_output": 0, "total": 300, "visible_output_est": 100},
            "cache": {"supported": True, "prompt_cache_hit": True, "input_cached": 40, "input_cache_write": 0, "input_uncached": 160, "input_total": 200, "cache_read_ratio": 0.2, "response_cache_hit": False},
            "throughput": {"output_tok_s": 50.0, "wall_output_tok_s": 50.0, "total_tok_s": 150.0},
            "provider_route": "test-provider/model-a",
            "notes": {"accounting": "semantic_model_turns"},
        }

        # Mock results
        results = [
            runner.AttemptResult(
                ts="2026-06-27T00:00:00Z",
                run_id="test",
                task_id="sports_hold_vig_removal",
                agent="unit-agent",
                name="unit-agent",
                model="model-a",
                backend_provider="openai",
                thinking="none",
                harness="OMP",
                agent_execution="host",
                verifier_backend="host",
                passed=True,
                reason="passed verifier",
                status="PASS",
                attempt_dir="/tmp/attempt1",
                agent_returncode=0,
                verifier_returncode=0,
                agent_timeout=False,
                verifier_timeout=False,
                agent_elapsed_sec=1.0,
                verifier_elapsed_sec=0.2,
                agent_stdout="",
                agent_stderr="",
                verifier_stdout="",
                verifier_stderr="",
                agent_cmd=[],
                verifier_cmd=[],
                attempt_count=1,
                max_retries=1,
                runtime_metrics=metrics_1,
            ),
            runner.AttemptResult(
                ts="2026-06-27T00:00:00Z",
                run_id="test",
                task_id="sports_hold_vig_removal",
                agent="unit-agent",
                name="unit-agent",
                model="model-a",
                backend_provider="openai",
                thinking="none",
                harness="OMP",
                agent_execution="host",
                verifier_backend="host",
                passed=True,
                reason="passed verifier",
                status="PASS",
                attempt_dir="/tmp/attempt2",
                agent_returncode=0,
                verifier_returncode=0,
                agent_timeout=False,
                verifier_timeout=False,
                agent_elapsed_sec=2.0,
                verifier_elapsed_sec=0.2,
                agent_stdout="",
                agent_stderr="",
                verifier_stdout="",
                verifier_stderr="",
                agent_cmd=[],
                verifier_cmd=[],
                attempt_count=1,
                max_retries=1,
                runtime_metrics=metrics_2,
            )
        ]
        legacy_metrics = {
            **metrics_1,
            "tokens": {**metrics_1["tokens"], "input": 999, "total": 999},
        }
        legacy_metrics.pop("notes")
        results.append(
            replace(
                results[0],
                result_id="legacy",
                runtime_metrics=legacy_metrics,
            )
        )

        summary = runner.summarize(results)

        # Check top level
        self.assertIn("runtime_metrics", summary)
        top_m = summary["runtime_metrics"]
        self.assertEqual(top_m["latency"]["wall_ms"], 3000)
        self.assertEqual(top_m["tokens"]["input"], 300)
        self.assertEqual(top_m["tokens"]["output"], 150)
        self.assertEqual(top_m["tokens"]["total"], 450)

        # Check by_agent and by_task
        self.assertIn("runtime_metrics", summary["by_agent"]["unit-agent"])
        self.assertIn("runtime_metrics", summary["by_task"]["sports_hold_vig_removal"])

        # Check null cases for dry-run/oracle/no-op with null metrics
        results_null = [
            runner.AttemptResult(
                ts="2026-06-27T00:00:00Z",
                run_id="test",
                task_id="sports_hold_vig_removal",
                agent="dry",
                name="dry",
                model="model-a",
                backend_provider="openai",
                thinking="none",
                harness="OMP",
                agent_execution="host",
                verifier_backend="host",
                passed=False,
                reason="dry run skipped",
                status="DRY_RUN",
                attempt_dir="/tmp/attempt_dry",
                agent_returncode=0,
                verifier_returncode=0,
                agent_timeout=False,
                verifier_timeout=False,
                agent_elapsed_sec=0.0,
                verifier_elapsed_sec=0.0,
                agent_stdout="",
                agent_stderr="",
                verifier_stdout="",
                verifier_stderr="",
                agent_cmd=[],
                verifier_cmd=[],
                attempt_count=1,
                max_retries=1,
                runtime_metrics=None,
            )
        ]

        summary_null = runner.summarize(results_null)
        self.assertNotIn("runtime_metrics", summary_null)
        self.assertNotIn("runtime_metrics", summary_null["by_agent"]["dry"])
        self.assertNotIn("runtime_metrics", summary_null["by_task"]["sports_hold_vig_removal"])
    def test_independent_attempts_main_loop(self) -> None:
        import unittest.mock
        import json
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            runner.ARTIFACT_ROOT = temp_path

            mock_result = runner.AttemptResult(
                ts="2026-06-27T00:00:00Z",
                run_id="test-run-attempts",
                task_id="sports_hold_vig_removal",
                agent="test-agent",
                name="test-agent",
                model="model-a",
                backend_provider="openai",
                thinking="none",
                harness="OMP",
                agent_execution="host",
                verifier_backend="host",
                passed=True,
                reason="passed hidden verifier",
                status="PASS",
                attempt_dir="/tmp/attempt",
                agent_returncode=0,
                verifier_returncode=0,
                agent_timeout=False,
                verifier_timeout=False,
                agent_elapsed_sec=1.0,
                verifier_elapsed_sec=1.0,
                agent_stdout="",
                agent_stderr="",
                verifier_stdout="",
                verifier_stderr="",
                agent_cmd=[],
                verifier_cmd=[],
                attempt_count=1,
                max_retries=3,
                runtime_metrics=None,
                attempt_number=1,
                total_attempts=3,
            )

            with unittest.mock.patch.object(runner, "run_attempt", return_value=mock_result) as mock_run:
                exit_code = runner.main([
                    "--agent", "test-agent=openai/model-a",
                    "--task", "sports_hold_vig_removal",
                    "--attempts", "3",
                    "--run-id", "test-run-attempts",
                    "--allow-lower-thinking",
                    "--agent-execution", "host",
                    "--verifier", "host",
                ])

                self.assertEqual(exit_code, 0)
                self.assertEqual(mock_run.call_count, 3)

                called_attempt_numbers = {call.kwargs.get("attempt_number") for call in mock_run.call_args_list}
                self.assertEqual(called_attempt_numbers, {1, 2, 3})
                for call in mock_run.call_args_list:
                    self.assertEqual(call.kwargs.get("total_attempts"), 3)

                status_file = temp_path / "test-run-attempts" / "status.json"
                self.assertTrue(status_file.exists())
                status_data = json.loads(status_file.read_text(encoding="utf-8"))
                self.assertEqual(status_data["attempts"], 3)

            runner.ARTIFACT_ROOT = orig_artifact_root

    def test_attempt_range_numbers_continuation_without_repeating_attempt_one(self) -> None:
        import unittest.mock
        import json
        with tempfile.TemporaryDirectory() as temp_dir:
            original_root = runner.ARTIFACT_ROOT
            runner.ARTIFACT_ROOT = Path(temp_dir)
            result = runner.AttemptResult(
                ts="2026-07-12T00:00:00Z", run_id="continuation", task_id="sports_hold_vig_removal",
                agent="sol", name="sol", model="openai/model", backend_provider="openai",
                thinking="max", harness="OMP", agent_execution="host", verifier_backend="host",
                passed=True, reason="pass", status="PASS", attempt_dir="/tmp/attempt",
                agent_returncode=0, verifier_returncode=0, agent_timeout=False, verifier_timeout=False,
                agent_elapsed_sec=1.0, verifier_elapsed_sec=1.0, agent_stdout="", agent_stderr="",
                verifier_stdout="", verifier_stderr="", agent_cmd=[], verifier_cmd=[], attempt_count=1,
                max_retries=3, runtime_metrics=None, attempt_number=2, total_attempts=5,
            )
            try:
                with unittest.mock.patch.object(runner, "run_attempt", return_value=result) as run:
                    exit_code = runner.main([
                        "--agent", "sol=openai/model", "--task", "sports_hold_vig_removal",
                        "--attempts", "4", "--attempt-start", "2", "--run-id", "continuation",
                        "--allow-lower-thinking", "--agent-execution", "host", "--verifier", "host",
                    ])
                self.assertEqual(exit_code, 0)
                self.assertEqual(
                    sorted(call.kwargs["attempt_number"] for call in run.call_args_list),
                    [2, 3, 4, 5],
                )
                self.assertTrue(all(call.kwargs["total_attempts"] == 5 for call in run.call_args_list))
                status = json.loads((Path(temp_dir) / "continuation" / "status.json").read_text())
                self.assertEqual((status["attempt_start"], status["attempt_end"]), (2, 5))
                self.assertEqual(status["total_trials"], 4)
            finally:
                runner.ARTIFACT_ROOT = original_root

    def test_concurrency_and_progress_metadata(self) -> None:
        import unittest.mock
        import json
        import sys
        from io import StringIO

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            orig_stdout = sys.stdout
            runner.ARTIFACT_ROOT = temp_path

            mock_result = runner.AttemptResult(
                ts="2026-06-27T00:00:00Z",
                run_id="test-concurrency-metadata",
                task_id="sports_hold_vig_removal",
                agent="test-agent",
                name="test-agent",
                model="model-a",
                backend_provider="openai",
                thinking="none",
                harness="OMP",
                agent_execution="host",
                verifier_backend="host",
                passed=True,
                reason="passed hidden verifier",
                status="PASS",
                attempt_dir="/tmp/attempt",
                agent_returncode=0,
                verifier_returncode=0,
                agent_timeout=False,
                verifier_timeout=False,
                agent_elapsed_sec=1.0,
                verifier_elapsed_sec=1.0,
                agent_stdout="",
                agent_stderr="",
                verifier_stdout="",
                verifier_stderr="",
                agent_cmd=[],
                verifier_cmd=[],
                attempt_count=1,
                max_retries=3,
                runtime_metrics=None,
                attempt_number=1,
                total_attempts=2,
            )

            try:
                sys.stdout = StringIO()
                with unittest.mock.patch.object(runner, "run_attempt", return_value=mock_result) as mock_run:
                    exit_code = runner.main([
                        "--agent", "test-agent=openai/model-a",
                        "--task", "sports_hold_vig_removal",
                        "--attempts", "2",
                        "--concurrency", "4",
                        "--local-memory-budget-mb", "40000",
                        "--run-id", "test-concurrency-metadata",
                        "--allow-lower-thinking",
                        "--agent-execution", "host",
                        "--verifier", "host",
                    ])

                    stdout = sys.stdout.getvalue()
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(mock_run.call_count, 2)
                    self.assertIn("START agent=test-agent", stdout)
                    self.assertIn("DONE agent=test-agent", stdout)
                    self.assertIn("completed=2", stdout)

                    status_file = temp_path / "test-concurrency-metadata" / "status.json"
                    self.assertTrue(status_file.exists())
                    status_data = json.loads(status_file.read_text(encoding="utf-8"))

                    # Verify concurrency and progress fields in status.json
                    self.assertEqual(status_data["concurrency"], 4)
                    self.assertEqual(status_data["requested_concurrency"], 4)
                    self.assertEqual(status_data["effective_concurrency"], 4)
                    self.assertEqual(status_data["local_memory_budget_mb"], 40000)
                    self.assertEqual(status_data["trial_memory_reserve_mb"], 10000)
                    self.assertTrue(status_data["memory_concurrency_cap_enabled"])
                    self.assertEqual(status_data["progress_interval_sec"], runner.DEFAULT_PROGRESS_INTERVAL_SEC)
                    self.assertEqual(status_data["total_trials"], 2)
                    self.assertEqual(status_data["completed_trials"], 2)
                    self.assertEqual(status_data["running_trials"], 0)
                    self.assertEqual(status_data["pending_trials"], 0)
                    self.assertEqual(status_data["attempts"], 2)
            finally:
                sys.stdout = orig_stdout
                runner.ARTIFACT_ROOT = orig_artifact_root

    def test_resume_behavior(self) -> None:
        import unittest.mock
        import json
        import sys
        from io import StringIO
        from dataclasses import asdict

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            orig_stdout = sys.stdout
            runner.ARTIFACT_ROOT = temp_path

            run_id = "test-resume-run"
            run_dir = temp_path / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            jsonl_path = run_dir / "results.jsonl"

            def make_result(task_id: str, attempt_number: int, passed: bool = True) -> dict:
                return {
                    "ts": "2026-06-27T00:00:00Z",
                    "run_id": run_id,
                    "task_id": task_id,
                    "agent": "test-agent",
                    "name": "test-agent",
                    "model": "openai/model-a",
                    "backend_provider": "openai",
                    "thinking": "max",
                    "harness": "OMP",
                    "agent_execution": "host",
                    "verifier_backend": "host",
                    "passed": passed,
                    "reason": "mock result",
                    "status": "PASS",
                    "attempt_dir": f"/tmp/{task_id}/attempt_{attempt_number}",
                    "agent_returncode": 0,
                    "verifier_returncode": 0,
                    "agent_timeout": False,
                    "verifier_timeout": False,
                    "agent_elapsed_sec": 1.0,
                    "verifier_elapsed_sec": 1.0,
                    "agent_stdout": "",
                    "agent_stderr": "",
                    "verifier_stdout": "",
                    "verifier_stderr": "",
                    "agent_cmd": [],
                    "verifier_cmd": [],
                    "attempt_count": 1,
                    "max_retries": 3,
                    "runtime_metrics": None,
                    "attempt_number": attempt_number,
                    "total_attempts": 3,
                }

            initial_rows = [
                make_result("sports_hold_vig_removal", 1),
                make_result("sports_hold_vig_removal", 2),
                make_result("sports_hold_vig_removal", 3),
                make_result("odds_feed_data_merger", 1),
                make_result("odds_feed_data_merger", 2),
                make_result("bayesian_mcmc_rhat_diagnostic", 1),
            ]

            with jsonl_path.open("w", encoding="utf-8") as f:
                for row in initial_rows:
                    f.write(json.dumps(row) + "\n")

            resume_config = {
                "agents": [asdict(runner.parse_agent("test-agent=openai/model-a"))],
                "tasks": ["sports_hold_vig_removal", "odds_feed_data_merger", "bayesian_mcmc_rhat_diagnostic"],
                "agent_execution": "host",
                "verifier": "host",
                "dry_run": False,
                "timeout_scale": runner.DEFAULT_TIMEOUT_SCALE,
                "attempts": 3,
                "max_retries": runner.DEFAULT_MAX_RETRIES,
                "tools": runner.DEFAULT_HOST_TOOLS,
                "manifest": None,
                "task_set": None,
                "agent_set": None,
                "auth_gateway_socket": None,
            }
            (run_dir / "status.json").write_text(json.dumps({"resume_config": resume_config}) + "\n", encoding="utf-8")

            def mock_run_attempt_fn(**kwargs):
                return runner.AttemptResult(
                    ts="2026-06-27T01:00:00Z",
                    run_id=kwargs["run_id"],
                    task_id=kwargs["task"].task_id,
                    agent=kwargs["agent"].name,
                    name=kwargs["agent"].name,
                    model=kwargs["agent"].model,
                    backend_provider=kwargs["agent"].backend_provider,
                    thinking=kwargs["agent"].thinking,
                    harness=kwargs["agent"].harness,
                    agent_execution=kwargs["agent_execution"],
                    verifier_backend=kwargs["verifier_backend"],
                    passed=True,
                    reason="mocked run",
                    status="PASS",
                    attempt_dir=str(kwargs["output_root"] / kwargs["agent"].name / kwargs["task"].task_id / f"attempt_{kwargs['attempt_number']}"),
                    agent_returncode=0,
                    verifier_returncode=0,
                    agent_timeout=False,
                    verifier_timeout=False,
                    agent_elapsed_sec=0.5,
                    verifier_elapsed_sec=0.5,
                    agent_stdout="",
                    agent_stderr="",
                    verifier_stdout="",
                    verifier_stderr="",
                    agent_cmd=[],
                    verifier_cmd=[],
                    attempt_count=1,
                    max_retries=kwargs["max_retries"],
                    runtime_metrics=None,
                    attempt_number=kwargs["attempt_number"],
                    total_attempts=kwargs["total_attempts"],
                )

            try:
                sys.stdout = StringIO()
                with unittest.mock.patch.object(runner, "run_attempt", side_effect=mock_run_attempt_fn) as mock_run:
                    exit_code = runner.main([
                        "--agent", "test-agent=openai/model-a",
                        "--task", "sports_hold_vig_removal",
                        "--task", "odds_feed_data_merger",
                        "--task", "bayesian_mcmc_rhat_diagnostic",
                        "--attempts", "3",
                        "--concurrency", "1",
                        "--run-id", run_id,
                        "--allow-lower-thinking",
                        "--agent-execution", "host",
                        "--verifier", "host",
                        "--resume",
                    ])

                    self.assertEqual(exit_code, 0)
                    self.assertEqual(mock_run.call_count, 3)

                    jsonl_lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
                    results_data = [json.loads(line) for line in jsonl_lines if line.strip()]

                    self.assertEqual(len(results_data), 9)
                    for i in range(3):
                        self.assertEqual(results_data[i]["task_id"], "sports_hold_vig_removal")
                        self.assertEqual(results_data[i]["attempt_number"], i + 1)
                        self.assertEqual(results_data[i]["reason"], "mock result")

                    for i in range(6, 9):
                        self.assertEqual(results_data[i]["reason"], "mocked run")

                    status_file = run_dir / "status.json"
                    self.assertTrue(status_file.exists())
                    status_data = json.loads(status_file.read_text(encoding="utf-8"))

                    self.assertTrue(status_data.get("resume_enabled"))
                    self.assertEqual(status_data.get("resume_source_rows"), 6)
                    self.assertEqual(status_data.get("resume_kept_rows"), 6)
                    self.assertEqual(status_data.get("resume_dropped_rows"), 0)

                    backup_path_str = status_data.get("resume_backup_path")
                    self.assertIsNotNone(backup_path_str)
                    backup_path = Path(backup_path_str)
                    self.assertTrue(backup_path.exists())

                    backup_lines = backup_path.read_text(encoding="utf-8").strip().split("\n")
                    self.assertEqual(len(backup_lines), 6)
            finally:
                sys.stdout = orig_stdout
                runner.ARTIFACT_ROOT = orig_artifact_root

    def test_resume_rejects_incompatible_saved_rows(self) -> None:
        import unittest.mock
        import json
        import sys
        from dataclasses import asdict
        from io import StringIO

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            orig_stdout = sys.stdout
            runner.ARTIFACT_ROOT = temp_path

            run_id = "test-resume-incompatible-run"
            run_dir = temp_path / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            jsonl_path = run_dir / "results.jsonl"
            stale_row = {
                "ts": "2026-06-27T00:00:00Z",
                "run_id": run_id,
                "task_id": "sports_hold_vig_removal",
                "agent": "test-agent",
                "name": "test-agent",
                "model": "openai/old-model",
                "backend_provider": "openai",
                "thinking": "max",
                "harness": "OMP",
                "agent_execution": "host",
                "verifier_backend": "host",
                "passed": True,
                "reason": "stale run",
                "status": "PASS",
                "attempt_dir": "/tmp/stale",
                "agent_returncode": 0,
                "verifier_returncode": 0,
                "agent_timeout": False,
                "verifier_timeout": False,
                "agent_elapsed_sec": 1.0,
                "verifier_elapsed_sec": 1.0,
                "agent_stdout": "",
                "agent_stderr": "",
                "verifier_stdout": "",
                "verifier_stderr": "",
                "agent_cmd": [],
                "verifier_cmd": [],
                "attempt_count": 1,
                "max_retries": 3,
                "runtime_metrics": None,
                "attempt_number": 1,
                "total_attempts": 1,
            }
            jsonl_path.write_text(json.dumps(stale_row) + "\n", encoding="utf-8")
            resume_config = {
                "agents": [asdict(runner.parse_agent("test-agent=openai/model-a"))],
                "tasks": ["sports_hold_vig_removal"],
                "agent_execution": "host",
                "verifier": "host",
                "dry_run": False,
                "timeout_scale": runner.DEFAULT_TIMEOUT_SCALE,
                "attempts": 1,
                "max_retries": runner.DEFAULT_MAX_RETRIES,
                "tools": runner.DEFAULT_HOST_TOOLS,
                "manifest": None,
                "task_set": None,
                "agent_set": None,
                "auth_gateway_socket": None,
            }
            (run_dir / "status.json").write_text(json.dumps({"resume_config": resume_config}) + "\n", encoding="utf-8")

            mock_result = runner.AttemptResult(
                ts="2026-06-27T01:00:00Z",
                run_id=run_id,
                task_id="sports_hold_vig_removal",
                agent="test-agent",
                name="test-agent",
                model="openai/model-a",
                backend_provider="openai",
                thinking="max",
                harness="OMP",
                agent_execution="host",
                verifier_backend="host",
                passed=True,
                reason="fresh run",
                status="PASS",
                attempt_dir="/tmp/fresh",
                agent_returncode=0,
                verifier_returncode=0,
                agent_timeout=False,
                verifier_timeout=False,
                agent_elapsed_sec=1.0,
                verifier_elapsed_sec=1.0,
                agent_stdout="",
                agent_stderr="",
                verifier_stdout="",
                verifier_stderr="",
                agent_cmd=[],
                verifier_cmd=[],
                attempt_count=1,
                max_retries=3,
                runtime_metrics=None,
                attempt_number=1,
                total_attempts=1,
            )

            try:
                sys.stdout = StringIO()
                with unittest.mock.patch.object(runner, "run_attempt", return_value=mock_result) as mock_run:
                    exit_code = runner.main([
                        "--agent", "test-agent=openai/model-a",
                        "--task", "sports_hold_vig_removal",
                        "--attempts", "1",
                        "--concurrency", "1",
                        "--run-id", run_id,
                        "--allow-lower-thinking",
                        "--agent-execution", "host",
                        "--verifier", "host",
                        "--resume",
                    ])
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(mock_run.call_count, 1)

                    results_data = [
                        json.loads(line)
                        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
                        if line.strip()
                    ]
                    self.assertEqual(len(results_data), 2)
                    self.assertEqual(results_data[-1]["reason"], "fresh run")
                    self.assertEqual(results_data[-1]["model"], "openai/model-a")

                    status_data = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
                    self.assertTrue(status_data.get("resume_enabled"))
                    self.assertEqual(status_data.get("resume_source_rows"), 1)
                    self.assertEqual(status_data.get("resume_kept_rows"), 0)
                    self.assertEqual(status_data.get("resume_dropped_rows"), 1)
            finally:
                sys.stdout = orig_stdout
                runner.ARTIFACT_ROOT = orig_artifact_root

    def test_resume_rejects_mismatched_run_config(self) -> None:
        import unittest.mock
        import json
        import sys
        from dataclasses import asdict
        from io import StringIO

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            orig_stderr = sys.stderr
            runner.ARTIFACT_ROOT = temp_path

            run_id = "test-resume-config-mismatch-run"
            run_dir = temp_path / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "results.jsonl").write_text("{}\n", encoding="utf-8")
            saved_config = {
                "agents": [asdict(runner.parse_agent("test-agent=openai/model-a"))],
                "tasks": ["sports_hold_vig_removal"],
                "agent_execution": "host",
                "verifier": "host",
                "dry_run": True,
                "timeout_scale": runner.DEFAULT_TIMEOUT_SCALE,
                "attempts": 1,
                "max_retries": runner.DEFAULT_MAX_RETRIES,
                "tools": runner.DEFAULT_HOST_TOOLS,
            }
            (run_dir / "status.json").write_text(json.dumps({"resume_config": saved_config}) + "\n", encoding="utf-8")

            try:
                sys.stderr = StringIO()
                with unittest.mock.patch.object(runner, "run_attempt") as mock_run:
                    exit_code = runner.main([
                        "--agent", "test-agent=openai/model-a",
                        "--task", "sports_hold_vig_removal",
                        "--attempts", "1",
                        "--concurrency", "1",
                        "--run-id", run_id,
                        "--allow-lower-thinking",
                        "--agent-execution", "host",
                        "--verifier", "host",
                        "--resume",
                    ])
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(mock_run.call_count, 0)
                    self.assertIn("saved run configuration differs", sys.stderr.getvalue())
            finally:
                sys.stderr = orig_stderr
                runner.ARTIFACT_ROOT = orig_artifact_root

    def test_resume_matches_oracle_run_mode(self) -> None:
        import unittest.mock
        import json
        import sys
        from dataclasses import asdict
        from io import StringIO

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            orig_stdout = sys.stdout
            runner.ARTIFACT_ROOT = temp_path

            run_id = "test-resume-oracle-run"
            run_dir = temp_path / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": "2026-06-27T00:00:00Z",
                "run_id": run_id,
                "task_id": "sports_hold_vig_removal",
                "agent": "oracle",
                "name": "oracle",
                "model": "reference-solution",
                "backend_provider": "local",
                "thinking": "none",
                "harness": "REFERENCE",
                "agent_execution": "oracle",
                "verifier_backend": "host",
                "passed": True,
                "reason": "passed",
                "status": "PASS",
                "attempt_dir": "/tmp/oracle",
                "agent_returncode": 0,
                "verifier_returncode": 0,
                "agent_timeout": False,
                "verifier_timeout": False,
                "agent_elapsed_sec": 1.0,
                "verifier_elapsed_sec": 1.0,
                "agent_stdout": "",
                "agent_stderr": "",
                "verifier_stdout": "",
                "verifier_stderr": "",
                "agent_cmd": [],
                "verifier_cmd": [],
                "attempt_count": 1,
                "max_retries": runner.DEFAULT_MAX_RETRIES,
                "runtime_metrics": None,
                "attempt_number": 1,
                "total_attempts": 1,
            }
            (run_dir / "results.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            resume_config = {
                "agents": [asdict(runner.AgentSpec("oracle", "reference-solution", "local", "none", "REFERENCE"))],
                "tasks": ["sports_hold_vig_removal"],
                "agent_execution": "oracle",
                "verifier": "host",
                "dry_run": False,
                "timeout_scale": runner.DEFAULT_TIMEOUT_SCALE,
                "attempts": 1,
                "max_retries": runner.DEFAULT_MAX_RETRIES,
                "tools": runner.DEFAULT_HOST_TOOLS,
                "manifest": None,
                "task_set": None,
                "agent_set": None,
                "auth_gateway_socket": None,
            }
            (run_dir / "status.json").write_text(json.dumps({"resume_config": resume_config}) + "\n", encoding="utf-8")

            try:
                sys.stdout = StringIO()
                with unittest.mock.patch.object(runner, "run_attempt") as mock_run:
                    exit_code = runner.main([
                        "--oracle",
                        "--task", "sports_hold_vig_removal",
                        "--attempts", "1",
                        "--concurrency", "1",
                        "--run-id", run_id,
                        "--agent-execution", "host",
                        "--verifier", "host",
                        "--resume",
                    ])
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(mock_run.call_count, 0)
                    status_data = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
                    self.assertEqual(status_data.get("resume_kept_rows"), 1)
                    self.assertEqual(status_data.get("resume_dropped_rows"), 0)
            finally:
                sys.stdout = orig_stdout
                runner.ARTIFACT_ROOT = orig_artifact_root

    def test_resume_requires_existing_artifacts(self) -> None:
        import unittest.mock
        import sys
        from io import StringIO

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            orig_stderr = sys.stderr
            runner.ARTIFACT_ROOT = temp_path

            try:
                sys.stderr = StringIO()
                with unittest.mock.patch.object(runner, "run_attempt") as mock_run:
                    exit_code = runner.main([
                        "--agent", "test-agent=openai/model-a",
                        "--task", "sports_hold_vig_removal",
                        "--attempts", "1",
                        "--run-id", "missing-resume-run",
                        "--allow-lower-thinking",
                        "--agent-execution", "host",
                        "--verifier", "host",
                        "--resume",
                    ])
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(mock_run.call_count, 0)
                    self.assertIn("results.jsonl does not exist", sys.stderr.getvalue())
            finally:
                sys.stderr = orig_stderr
                runner.ARTIFACT_ROOT = orig_artifact_root

    def test_overwrite_protection(self) -> None:
        import unittest.mock
        import json
        import sys
        from io import StringIO

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            orig_artifact_root = runner.ARTIFACT_ROOT
            orig_stdout = sys.stdout
            runner.ARTIFACT_ROOT = temp_path

            run_id = "test-overwrite-run"
            run_dir = temp_path / run_id
            run_dir.mkdir(parents=True, exist_ok=True)
            jsonl_path = run_dir / "results.jsonl"
            jsonl_path.write_text("{}\n", encoding="utf-8")

            try:
                sys.stdout = StringIO()
                with unittest.mock.patch.object(runner, "run_attempt") as mock_run:
                    exit_code = runner.main([
                        "--agent", "test-agent=openai/model-a",
                        "--task", "sports_hold_vig_removal",
                        "--attempts", "1",
                        "--concurrency", "1",
                        "--run-id", run_id,
                        "--allow-lower-thinking",
                        "--agent-execution", "host",
                        "--verifier", "host",
                    ])
                    self.assertEqual(exit_code, 2)
                    self.assertEqual(mock_run.call_count, 0)

                    mock_result = runner.AttemptResult(
                        ts="2026-06-27T00:00:00Z",
                        run_id=run_id,
                        task_id="sports_hold_vig_removal",
                        agent="test-agent",
                        name="test-agent",
                        model="model-a",
                        backend_provider="openai",
                        thinking="none",
                        harness="OMP",
                        agent_execution="host",
                        verifier_backend="host",
                        passed=True,
                        reason="passed",
                        status="PASS",
                        attempt_dir="/tmp/attempt",
                        agent_returncode=0,
                        verifier_returncode=0,
                        agent_timeout=False,
                        verifier_timeout=False,
                        agent_elapsed_sec=1.0,
                        verifier_elapsed_sec=1.0,
                        agent_stdout="",
                        agent_stderr="",
                        verifier_stdout="",
                        verifier_stderr="",
                        agent_cmd=[],
                        verifier_cmd=[],
                        attempt_count=1,
                        max_retries=3,
                        runtime_metrics=None,
                        attempt_number=1,
                        total_attempts=1,
                    )

                    mock_run.return_value = mock_result
                    exit_code = runner.main([
                        "--agent", "test-agent=openai/model-a",
                        "--task", "sports_hold_vig_removal",
                        "--attempts", "1",
                        "--concurrency", "1",
                        "--run-id", run_id,
                        "--allow-lower-thinking",
                        "--agent-execution", "host",
                        "--verifier", "host",
                        "--overwrite-run",
                    ])
                    self.assertEqual(exit_code, 0)
                    self.assertEqual(mock_run.call_count, 1)
            finally:
                sys.stdout = orig_stdout
                runner.ARTIFACT_ROOT = orig_artifact_root


    def test_literal_max_thinking_reaches_omp(self) -> None:
        agent = runner.AgentSpec("sol", "openai-codex/gpt-5.6-sol", "openai-codex", "max")
        self.assertEqual(agent.omp_thinking, "max")
        self.assertIn("--thinking", runner.omp_command(agent, "prompt", "read"))
        cmd = runner.omp_command(agent, "prompt", "read")
        self.assertEqual(cmd[cmd.index("--thinking") + 1], "max")

    def test_structured_provider_failure_mapping(self) -> None:
        import json
        result = runner.CommandResult(
            1, False, 0.1,
            json.dumps({"type": "provider_error", "error": {"code": "429", "message": "rate_limit"}}),
            "credentials should not be parsed", [],
        )
        result = runner.classify_omp_result(result)
        self.assertEqual(result.failure_code, runner.FailureCode.PROVIDER_RATE_LIMIT)
        self.assertFalse(result.message_end)

    def test_plain_stderr_provider_rate_limit_mapping(self) -> None:
        result = runner.CommandResult(
            1,
            False,
            0.1,
            "",
            "Devin stream error permission_denied: Reached overall message rate limit. Please try again later.",
            [],
        )
        result = runner.classify_omp_result(result)
        self.assertEqual(result.failure_code, runner.FailureCode.PROVIDER_RATE_LIMIT)
        self.assertFalse(result.message_end)

    def test_captured_omp_error_provider_rate_limit_mapping(self) -> None:
        result = runner.CommandResult(
            1,
            False,
            0.1,
            "",
            "",
            [],
            capture={
                "omp_error_message": (
                    "Devin stream error permission_denied: "
                    "Reached overall message rate limit. Please try again later."
                ),
            },
        )
        result = runner.classify_omp_result(result)
        self.assertEqual(result.failure_code, runner.FailureCode.PROVIDER_RATE_LIMIT)
        self.assertFalse(result.message_end)

    def test_captured_omp_connectivity_failure_mapping(self) -> None:
        result = runner.CommandResult(
            1,
            False,
            0.1,
            "",
            "",
            [],
            capture={"omp_error_message": "Unable to connect. Is the computer able to access the url?"},
        )
        result = runner.classify_omp_result(result)
        self.assertEqual(result.failure_code, runner.FailureCode.PROVIDER_TRANSPORT)
        self.assertFalse(result.message_end)

    def test_successful_message_end_clears_recovered_rate_limit(self) -> None:
        import json
        stdout = "\n".join([
            json.dumps({"type": "provider_error", "error": {"code": "429", "message": "rate_limit"}}),
            json.dumps({"type": "message_end", "data": {"role": "assistant", "stopReason": "stop"}}),
        ])
        result = runner.classify_omp_result(
            runner.CommandResult(0, False, 1.0, stdout, "", [])
        )
        self.assertEqual(result.failure_code, runner.FailureCode.NONE)
        self.assertTrue(result.message_end)

    def test_terminal_agent_end_error_overrides_earlier_success(self) -> None:
        import json
        stdout = "\n".join([
            json.dumps({
                "type": "message_end",
                "message": {"role": "assistant", "stopReason": "stop", "content": "premature"},
            }),
            json.dumps({
                "type": "agent_end",
                "messages": [
                    {"role": "assistant", "stopReason": "stop", "content": "premature"},
                    {"role": "assistant", "stopReason": "aborted", "content": ""},
                ],
            }),
        ])
        result = runner.classify_omp_result(
            runner.CommandResult(1, False, 1.0, stdout, "", [])
        )
        self.assertEqual(result.failure_code, runner.FailureCode.AGENT_HARNESS_EXIT)
        self.assertFalse(result.message_end)

    def test_oversized_agent_end_is_summarized_without_materializing_transcript(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agent.jsonl"
            payload = {
                "type": "agent_end",
                "messages": [
                    {"role": "user", "content": "x" * 1_100_000},
                    {"role": "assistant", "stopReason": "aborted", "content": ""},
                ],
            }
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            records = list(runner.omp_metrics_capture.iter_omp_jsonl_file(path))
        self.assertEqual(len(records), 1)
        summary = json.loads(records[0])
        self.assertEqual(summary["type"], "agent_end_oversize")
        self.assertEqual(summary["stopReason"], "aborted")
        failure, message_end = runner._parse_omp_event_lines(records)
        self.assertEqual(failure, runner.FailureCode.AGENT_HARNESS_EXIT)
        self.assertFalse(message_end)

    def test_oversized_unparsed_agent_end_never_synthesizes_success(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "agent.jsonl"
            path.write_bytes(
                b'{"type":"agent_end","messages":["'
                + b"x" * 1_100_000
                + b'"],"stopReason":"stop"}\n'
            )
            records = list(runner.omp_metrics_capture.iter_omp_jsonl_file(path))
        summary = json.loads(records[0])
        self.assertEqual(summary["type"], "agent_end_oversize")
        self.assertEqual(summary["stopReason"], "")
        result = runner.classify_omp_result(
            runner.CommandResult(1, False, 1.0, records[0], "", [])
        )
        self.assertEqual(result.failure_code, runner.FailureCode.AGENT_HARNESS_EXIT)
        self.assertFalse(result.message_end)

    def test_runtime_metrics_use_precompaction_output_length(self) -> None:
        metrics = runner.omp_metrics_capture.runtime_metrics_for_run({
            "stdout": "x" * 4000,
            "omp_stdout_char_count": 8000,
            "elapsed_sec": 1.0,
        })
        self.assertEqual(metrics["tokens"]["visible_output_est"], 2000)

    def test_later_provider_error_invalidates_earlier_tool_turn(self) -> None:
        import json
        stdout = "\n".join([
            json.dumps({
                "type": "message_end",
                "message": {"role": "assistant", "stopReason": "tool_use", "content": []},
            }),
            json.dumps({
                "type": "message_end",
                "message": {"role": "assistant", "stopReason": "stop", "content": "premature"},
            }),
            json.dumps({
                "type": "provider_error",
                "error": {"code": "429", "message": "rate_limit"},
            }),
        ])
        result = runner.classify_omp_result(
            runner.CommandResult(1, False, 1.0, stdout, "", [])
        )
        self.assertEqual(result.failure_code, runner.FailureCode.PROVIDER_RATE_LIMIT)
        self.assertFalse(result.message_end)

    def test_aborted_message_is_not_completion(self) -> None:
        import json
        stdout = json.dumps({
            "type": "message_end",
            "message": {"role": "assistant", "stopReason": "aborted", "content": []},
        })
        result = runner.classify_omp_result(
            runner.CommandResult(1, False, 1.0, stdout, "", [])
        )
        self.assertEqual(result.failure_code, runner.FailureCode.AGENT_HARNESS_EXIT)
        self.assertFalse(result.message_end)


    def test_superseded_rate_limit_is_not_a_resume_head(self) -> None:
        rows = [
            {
                "result_id": "old-429",
                "agent": "unit",
                "task_id": "task",
                "attempt_number": 1,
                "failure_code": "PROVIDER_RATE_LIMIT",
            },
            {
                "result_id": "new-pass",
                "supersedes_result_id": "old-429",
                "agent": "unit",
                "task_id": "task",
                "attempt_number": 1,
                "status": "PASS",
                "failure_code": "NONE",
            },
        ]
        heads = runner.unsuperseded_rows(rows)
        self.assertEqual([row["result_id"] for row in heads], ["new-pass"])
        self.assertFalse(any(row.get("failure_code") == "PROVIDER_RATE_LIMIT" for row in heads))


    def test_task_image_cache_requires_matching_build_labels(self) -> None:
        import unittest.mock
        task = runner.task_spec("sports_hold_vig_removal")
        responses = [
            runner.CommandResult(0, False, 0.0, '{"org.quant-bench.dockerfile-sha256":"stale"}\n', "", []),
            runner.CommandResult(0, False, 0.1, "sha256:new\n", "", []),
            runner.CommandResult(0, False, 0.0, "sha256:new\n", "", []),
        ]
        with unittest.mock.patch.object(runner.shutil, "which", return_value="/usr/bin/docker"), unittest.mock.patch.object(
            runner, "run_cmd", side_effect=responses
        ) as run:
            _tag, image_id, build = runner.ensure_task_image(task)
        self.assertEqual(image_id, "sha256:new")
        self.assertIs(build, responses[1])
        build_command = run.call_args_list[1].args[0]
        self.assertEqual(build_command[1], "build")
        self.assertIn("--label", build_command)
        self.assertTrue(any("dockerfile-sha256=" in value for value in build_command))


    def test_manifest_image_lock_is_required_and_commands_use_locked_id(self) -> None:
        import unittest.mock
        task = runner.task_spec("sports_hold_vig_removal")
        metadata = runner._expected_image_lock_metadata(task)
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "image-lock.json"
            lock = {task.task_id: {**metadata, "image_id": "sha256:locked"}}
            lock_path.write_text(json.dumps(lock), encoding="utf-8")

            def fake_inspect(cmd: list[str], **kwargs):
                return runner.CommandResult(0, False, 0.01, "sha256:locked\n", "", cmd)

            with unittest.mock.patch.object(runner.shutil, "which", return_value="/usr/bin/docker"), unittest.mock.patch.object(
                runner, "run_cmd", side_effect=fake_inspect
            ) as run:
                image_ids = runner.resolve_locked_image_ids([task], lock_path=lock_path)
                self.assertEqual(image_ids, {task.task_id: "sha256:locked"})
                self.assertEqual(run.call_args.args[0][0:4], ["/usr/bin/docker", "image", "inspect", metadata["tag"]])

                attempt_dir = Path(temp_dir) / "attempt"
                runner.copy_public_task_view(task, attempt_dir)
                result = runner.run_docker_verifier(task, attempt_dir, image_id=image_ids[task.task_id])
            self.assertIn("sha256:locked", result.cmd)

            def mismatched_inspect(cmd: list[str], **kwargs):
                return runner.CommandResult(0, False, 0.01, "sha256:other\n", "", cmd)

            with unittest.mock.patch.object(runner.shutil, "which", return_value="/usr/bin/docker"), unittest.mock.patch.object(
                runner, "run_cmd", side_effect=mismatched_inspect
            ):
                with self.assertRaisesRegex(ValueError, "ID mismatch"):
                    runner.resolve_locked_image_ids([task], lock_path=lock_path)

            lock_path.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing task entry"):
                runner.resolve_locked_image_ids([task], lock_path=lock_path)

            lock[task.task_id]["dockerfile_sha256"] = "stale"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                runner.resolve_locked_image_ids([task], lock_path=lock_path)
    def test_manifest_docker_execution_dry_run_skips_image_resolution(self) -> None:
        import unittest.mock
        task = runner.task_spec("sports_hold_vig_removal")
        manifest_text = f"""
schema_version = "1.0"

[task_sets]
official = ["{task.task_id}"]

[agent_sets]
official = ["unit"]

[[tasks]]
id = "{task.task_id}"
path = "tasks/{task.task_id}"

[[agents]]
name = "unit"
model = "openai-codex/gpt-5.6-sol"
backend_provider = "openai-codex"
thinking = "max"
harness = "OMP"
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.toml"
            manifest_path.write_text(manifest_text, encoding="utf-8")
            artifact_root = Path(temp_dir) / "artifacts"
            with unittest.mock.patch.object(runner, "ARTIFACT_ROOT", artifact_root), unittest.mock.patch.object(
                runner, "resolve_locked_image_ids", return_value={task.task_id: "sha256:locked"}
            ) as resolve, unittest.mock.patch.object(runner, "ensure_task_image") as ensure:
                code = runner.main([
                    "--manifest", str(manifest_path), "--task-set", "official",
                    "--agent-set", "official", "--attempts", "1", "--dry-run",
                    "--run-id", "locked-dry-run", "--progress-interval-sec", "0",
                ])
        self.assertEqual(code, 0)
        resolve.assert_not_called()
        ensure.assert_not_called()

    def test_combined_pilot_summary_uses_only_fixed_run_ids_and_latest_heads(self) -> None:
        import json
        import unittest.mock
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir)
            fixed = artifact_root / "quant-v1-pilot-sol"
            fixed.mkdir()
            rows = [
                {
                    "result_id": "old",
                    "agent": "sol",
                    "task_id": "task-a",
                    "attempt_number": 1,
                    "thinking": "max",
                    "status": "INFRA_BLOCKED",
                    "failure_code": "PROVIDER_RATE_LIMIT",
                    "passed": False,
                    "agent_elapsed_sec": 1.0,
                    "verifier_elapsed_sec": 0.0,
                },
                {
                    "result_id": "new",
                    "supersedes_result_id": "old",
                    "agent": "sol",
                    "task_id": "task-a",
                    "attempt_number": 1,
                    "thinking": "max",
                    "status": "PASS",
                    "failure_code": "NONE",
                    "passed": True,
                    "agent_elapsed_sec": 2.0,
                    "verifier_elapsed_sec": 1.0,
                    "runtime_metrics": {
                        "tokens": {"total": 100},
                        "throughput": {"total_tok_s": 10, "wall_output_tok_s": 5},
                        "notes": {"accounting": "semantic_model_turns"},
                    },
                    "attempted_runtime_metrics": {"tokens": {"total": 120}},
                },
                {
                    "result_id": "infra",
                    "agent": "sol",
                    "task_id": "task-b",
                    "attempt_number": 1,
                    "thinking": "max",
                    "status": "INFRA_BLOCKED",
                    "failure_code": "PROVIDER_TRANSPORT",
                    "passed": False,
                    "agent_elapsed_sec": 1.0,
                    "verifier_elapsed_sec": 0.0,
                    "runtime_metrics": {
                        "tokens": {"total": 999},
                        "throughput": {"total_tok_s": 999, "wall_output_tok_s": 999},
                        "notes": {"accounting": "semantic_model_turns"},
                    },
                    "attempted_runtime_metrics": {"tokens": {"total": 999}},
                },
            ]
            (fixed / "results.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
            (fixed / "status.json").write_text(json.dumps({"complete": True, "run_state": "complete"}))
            shakedown = artifact_root / "quant-v1-pilot-sol-rerun-1"
            shakedown.mkdir()
            (shakedown / "results.jsonl").write_text(json.dumps({**rows[-1], "result_id": "wrong"}) + "\n")
            expected = {
                ("quant-v1-pilot-sol", "sol", "task-a", "max", 1),
                ("quant-v1-pilot-sol", "sol", "task-b", "max", 1),
            }
            with unittest.mock.patch.object(runner, "ARTIFACT_ROOT", artifact_root), unittest.mock.patch.object(
                runner, "PILOT_RUN_IDS", {"quant-v1-pilot-sol": "completed_sol"}
            ), unittest.mock.patch.object(runner, "expected_pilot_matrix", return_value=expected):
                destination = runner.write_combined_pilot_summary()
                payload = json.loads(destination.read_text())
                self.assertTrue(payload["complete"])
                wrong_rows = [{**row, "task_id": "wrong-task"} for row in rows]
                (fixed / "results.jsonl").write_text(
                    "\n".join(json.dumps(row) for row in wrong_rows) + "\n"
                )
                wrong_payload = json.loads(runner.write_combined_pilot_summary().read_text())
            self.assertEqual(payload["latest_row_count"], 2)
            semantic_group = next(group for group in payload["groups"] if group["task"] == "task-a")
            infra_group = next(group for group in payload["groups"] if group["task"] == "task-b")
            self.assertEqual(semantic_group["total_tokens"], 100)
            self.assertEqual(semantic_group["observed_attempted_tokens"], 120)
            self.assertEqual(infra_group["total_tokens"], 0)
            self.assertEqual(infra_group["observed_attempted_tokens"], 999)
            self.assertEqual(infra_group["mean_provider_throughput"], None)
            self.assertEqual(payload["records"][0]["wall_time_sec"], 3.0)
            self.assertNotIn("quant-v1-pilot-sol-rerun-1", payload["fixed_run_ids"])
            self.assertFalse(wrong_payload["complete"])


    def test_docker_agent_mount_and_network_isolation(self) -> None:
        import unittest.mock
        task = runner.task_spec("sports_hold_vig_removal")
        agent = runner.AgentSpec("unit", "openai-codex/gpt-5.6-sol:max", "openai-codex", "max")
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_dir = Path(temp_dir) / "attempt"
            runner.copy_public_task_view(task, attempt_dir)
            captured: list[list[str]] = []

            def fake_run(cmd: list[str], **kwargs):
                captured.append(cmd)
                return runner.CommandResult(0, False, 0.01, "", "", cmd)

            def fake_prepare_docker_fake_home(attempt: Path, _agent, _gateway) -> Path:
                agent_dir = attempt / ".docker-agent-home" / ".omp" / "agent"
                agent_dir.mkdir(parents=True, exist_ok=True)
                (agent_dir / "config.yml").write_text("telemetry: false\n", encoding="utf-8")
                (agent_dir / "models.yml").write_text(
                    "providers:\n  openai-codex:\n    baseUrl: http://127.0.0.1:8765\n"
                    "    transport: pi-native\n    models:\n      - id: gpt-5.6-sol\n",
                    encoding="utf-8",
                )
                (agent_dir / "models.db").touch()
                return attempt / ".docker-agent-home"

            with unittest.mock.patch.object(
                runner.shutil,
                "which",
                side_effect=lambda name: "/usr/bin/docker" if name == "docker" else "/usr/bin/bun" if name == "bun" else None,
            ), unittest.mock.patch.object(
                runner, "prepare_docker_fake_home", side_effect=fake_prepare_docker_fake_home
            ), unittest.mock.patch.object(runner, "run_omp_cmd", side_effect=fake_run):
                result = runner.run_docker_agent(
                    agent, task, attempt_dir, image_id="sha256:immutable", tools="read,write,edit,bash",
                    auth_gateway_socket=Path("/tmp/gateway.sock"), timeout_scale=1.0,
                )
            self.assertEqual(result.cmd[0:2], ["/usr/bin/docker", "run"])
            self.assertEqual(result.cmd[result.cmd.index("--network") + 1], "none")
            self.assertIn("--read-only", result.cmd)
            self.assertIn("--tmpfs", result.cmd)
            self.assertTrue(any("/tmp:" in item for item in result.cmd))
            self.assertTrue(any("/run:" in item for item in result.cmd))
            self.assertIn("--cidfile", result.cmd)
            self.assertEqual(
                result.cmd[result.cmd.index("--cidfile") + 1],
                str(attempt_dir / "agent-container.cid"),
            )
            self.assertTrue(any(item.endswith(":/workspace") for item in result.cmd))
            self.assertNotIn(str(task.solution_path), result.cmd)
            self.assertNotIn("DOCKER_HOST", " ".join(result.cmd))
            models_yml = (attempt_dir / ".docker-agent-home" / ".omp" / "agent" / "models.yml").read_text()
            self.assertIn("transport: pi-native", models_yml)
            self.assertIn("baseUrl: http://127.0.0.1:8765", models_yml)
            self.assertTrue((attempt_dir / ".docker-agent-home" / ".omp" / "agent" / "models.db").is_file())
            self.assertIn("-c", result.cmd)
            self.assertNotIn("-lc", result.cmd)
            shell_command = result.cmd[result.cmd.index("-c") + 1]
            self.assertIn("--model-selector openai-codex/gpt-5.6-sol:max", shell_command)


    def test_docker_oracle_uses_solution_read_only_and_immutable_id(self) -> None:
        import unittest.mock
        task = runner.task_spec("sports_hold_vig_removal")
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_dir = Path(temp_dir) / "attempt"
            runner.copy_public_task_view(task, attempt_dir)
            captured: list[list[str]] = []

            def fake_run(cmd: list[str], **kwargs):
                captured.append(cmd)
                return runner.CommandResult(0, False, 0.01, "", "", cmd)

            with unittest.mock.patch.object(runner.shutil, "which", return_value="/usr/bin/docker"), unittest.mock.patch.object(
                runner, "run_cmd", side_effect=fake_run
            ):
                result = runner.run_docker_oracle(task, attempt_dir, image_id="sha256:immutable", timeout_scale=1.0)
            self.assertIn("sha256:immutable", result.cmd)
            self.assertIn("--read-only", result.cmd)
            self.assertIn("--tmpfs", result.cmd)
            self.assertTrue(any("/tmp:" in item for item in result.cmd))
            self.assertTrue(any("/solution/solve.py:ro" in item for item in result.cmd))
            self.assertNotIn("/tests", result.cmd)
    def test_scheduler_pauses_on_first_rate_limit_and_drains_in_flight(self) -> None:
        import json
        import unittest.mock
        task_ids = ["sports_hold_vig_removal", "odds_feed_data_merger", "bayesian_mcmc_rhat_diagnostic"]
        orig_root = runner.ARTIFACT_ROOT
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                runner.ARTIFACT_ROOT = Path(temp_dir)
                calls = []

                def fake_attempt(**kwargs):
                    calls.append(kwargs["task"].task_id)
                    rate = len(calls) == 1
                    return runner.AttemptResult(
                        ts="2026-01-01T00:00:00Z", run_id=kwargs["run_id"], task_id=kwargs["task"].task_id,
                        agent=kwargs["agent"].name, name=kwargs["agent"].name, model=kwargs["agent"].model,
                        backend_provider=kwargs["agent"].backend_provider, thinking=kwargs["agent"].thinking,
                        harness=kwargs["agent"].harness, agent_execution="host", verifier_backend="host",
                        passed=not rate, status="INFRA_BLOCKED" if rate else "PASS",
                        reason=runner.FailureCode.PROVIDER_RATE_LIMIT.value if rate else "passed hidden verifier",
                        attempt_dir="", agent_returncode=1 if rate else 0, verifier_returncode=0,
                        agent_timeout=False, verifier_timeout=False, agent_elapsed_sec=0.1,
                        verifier_elapsed_sec=0.1, agent_stdout="", agent_stderr="", verifier_stdout="",
                        verifier_stderr="", agent_cmd=[], verifier_cmd=[], attempt_count=1, max_retries=0,
                        runtime_metrics=None, attempt_number=1, total_attempts=1,
                        failure_code=runner.FailureCode.PROVIDER_RATE_LIMIT.value if rate else runner.FailureCode.NONE.value,
                    )

                with unittest.mock.patch.object(runner, "run_attempt", side_effect=fake_attempt):
                    code = runner.main([
                        "--agent", "unit=openai/model-a,backend=openai,thinking=none",
                        "--task", task_ids[0], "--task", task_ids[1], "--task", task_ids[2],
                        "--attempts", "1", "--concurrency", "2", "--progress-interval-sec", "0",
                        "--local-memory-budget-mb", "20000",
                        "--run-id", "rate-pause", "--agent-execution", "host", "--verifier", "host",
                        "--allow-lower-thinking",
                    ])
                self.assertEqual(code, 75)
                self.assertEqual(len(calls), 2)
                status = json.loads((Path(temp_dir) / "rate-pause" / "status.json").read_text())
                self.assertEqual(status["run_state"], "paused")
                self.assertEqual(status["pause_failure_code"], "PROVIDER_RATE_LIMIT")
                self.assertTrue(status["paused_at"])
                self.assertGreater(status["pending_trials"], 0)
        finally:
            runner.ARTIFACT_ROOT = orig_root

    def test_scheduler_pauses_on_provider_transport_failure(self) -> None:
        import json
        import unittest.mock

        original_root = runner.ARTIFACT_ROOT
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                runner.ARTIFACT_ROOT = Path(temp_dir)
                calls = []

                def fake_attempt(**kwargs):
                    calls.append(kwargs["task"].task_id)
                    failure = len(calls) == 1
                    return runner.AttemptResult(
                        ts="2026-01-01T00:00:00Z", run_id=kwargs["run_id"], task_id=kwargs["task"].task_id,
                        agent=kwargs["agent"].name, name=kwargs["agent"].name, model=kwargs["agent"].model,
                        backend_provider=kwargs["agent"].backend_provider, thinking=kwargs["agent"].thinking,
                        harness=kwargs["agent"].harness, agent_execution="host", verifier_backend="host",
                        passed=not failure, status="INFRA_BLOCKED" if failure else "PASS",
                        reason=runner.FailureCode.PROVIDER_TRANSPORT.value if failure else "passed hidden verifier",
                        attempt_dir="", agent_returncode=1 if failure else 0, verifier_returncode=0,
                        agent_timeout=False, verifier_timeout=False, agent_elapsed_sec=0.1,
                        verifier_elapsed_sec=0.1, agent_stdout="", agent_stderr="", verifier_stdout="",
                        verifier_stderr="", agent_cmd=[], verifier_cmd=[], attempt_count=1, max_retries=0,
                        runtime_metrics=None, attempt_number=1, total_attempts=1,
                        failure_code=runner.FailureCode.PROVIDER_TRANSPORT.value if failure else runner.FailureCode.NONE.value,
                    )

                with unittest.mock.patch.object(runner, "run_attempt", side_effect=fake_attempt):
                    code = runner.main([
                        "--agent", "unit=openai/model-a,backend=openai,thinking=none",
                        "--task", "sports_hold_vig_removal", "--task", "odds_feed_data_merger",
                        "--attempts", "1", "--concurrency", "1", "--progress-interval-sec", "0",
                        "--local-memory-budget-mb", "20000", "--run-id", "transport-pause",
                        "--agent-execution", "host", "--verifier", "host", "--allow-lower-thinking",
                    ])
                self.assertEqual(code, 75)
                self.assertEqual(len(calls), 1)
                status = json.loads((Path(temp_dir) / "transport-pause" / "status.json").read_text())
                self.assertEqual(status["run_state"], "paused")
                self.assertEqual(status["pause_failure_code"], "PROVIDER_TRANSPORT")
                self.assertEqual(status["pause_reason"], "provider_transport")
        finally:
            runner.ARTIFACT_ROOT = original_root
    def test_manifest_task_limit_slices_after_selection_and_rejects_nonpositive(self) -> None:
        manifest_ids = ["task-a", "task-b", "task-c"]
        self.assertEqual(runner.selected_tasks(manifest_ids, 2), ["task-a", "task-b"])
        with self.assertRaisesRegex(ValueError, "task-limit must be positive"):
            runner.selected_tasks(manifest_ids, 0)
        with self.assertRaisesRegex(ValueError, "task-limit must be positive"):
            runner.selected_tasks(manifest_ids, -1)

    def test_manifest_task_root_rejects_escape_and_symlink(self) -> None:
        with self.assertRaises(ValueError):
            runner._validated_repository_task_root("task-a", "/tmp/task-a")
        with self.assertRaises(ValueError):
            runner._validated_repository_task_root("task-a", "tasks/../outside")
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            tasks_dir = project / "tasks"
            tasks_dir.mkdir()
            outside = project / "outside"
            outside.mkdir()
            (tasks_dir / "task-a").symlink_to(outside, target_is_directory=True)
            with unittest.mock.patch.object(runner, "PROJECT_ROOT", project), unittest.mock.patch.object(
                runner, "TASKS_DIR", tasks_dir
            ):
                with self.assertRaisesRegex(ValueError, "escapes repository"):
                    runner._validated_repository_task_root("task-a")

    def test_dry_run_skips_all_docker_image_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with unittest.mock.patch.object(runner, "ARTIFACT_ROOT", Path(temp_dir)), unittest.mock.patch.object(
                runner, "ensure_task_image"
            ) as ensure, unittest.mock.patch.object(runner, "resolve_locked_image_ids") as resolve:
                runner.main([
                    "--task", "sports_hold_vig_removal", "--agent",
                    "unit=openai/model-a,backend=openai,thinking=none",
                    "--allow-lower-thinking", "--dry-run", "--run-id", "dry-no-images",
                    "--progress-interval-sec", "0",
                ])
            ensure.assert_not_called()
            resolve.assert_not_called()

    def test_subset_image_build_preserves_unselected_lock_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            tasks_dir = project / "tasks"
            for task_id in ("subset-a", "subset-b"):
                root = tasks_dir / task_id
                root.mkdir(parents=True)
                (root / "task.toml").write_text(
                    "[metadata]\npromotion_status = \"promoted\"\n", encoding="utf-8"
                )
            lock_path = project / "benchmarks" / "image-lock.json"
            lock_path.parent.mkdir()
            lock_path.write_text(json.dumps({"subset-b": {"image_id": "sha256:keep", "tag": "old"}}))
            metadata = {
                "base_image": "python:3.12@sha256:base",
                "dockerfile_sha256": "docker-sha",
                "requirements_sha256": "req-sha",
                "image_id": "sha256:new",
            }
            with unittest.mock.patch.object(runner, "PROJECT_ROOT", project), unittest.mock.patch.object(
                runner, "TASKS_DIR", tasks_dir
            ), unittest.mock.patch.object(runner, "DEFAULT_TASKS", ("subset-a", "subset-b")), unittest.mock.patch.object(
                runner, "ensure_task_image", return_value=("subset-a:tag", "sha256:new", None)
            ), unittest.mock.patch.object(runner, "_IMAGE_METADATA", {"subset-a": metadata}):
                code = runner.main(["--task", "subset-a", "--build-images"])
            self.assertEqual(code, 0)
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(lock["subset-b"], {"image_id": "sha256:keep", "tag": "old"})
            self.assertEqual(lock["subset-a"]["image_id"], "sha256:new")

    def test_oracle_and_verifier_timeouts_remove_phase_cidfiles(self) -> None:
        task = runner.task_spec("sports_hold_vig_removal")
        timed_out = runner.CommandResult(124, True, 1.0, "", "", [], runner.FailureCode.VERIFIER_TIMEOUT)
        with tempfile.TemporaryDirectory() as temp_dir:
            attempt_dir = Path(temp_dir) / "attempt"
            runner.copy_public_task_view(task, attempt_dir)
            with unittest.mock.patch.object(runner.shutil, "which", return_value="/usr/bin/docker"), unittest.mock.patch.object(
                runner, "run_cmd", return_value=timed_out
            ), unittest.mock.patch.object(runner, "_force_remove_docker_container") as remove:
                runner.run_docker_oracle(task, attempt_dir, image_id="sha256:oracle", timeout_scale=1.0)
                remove.assert_called_once_with("/usr/bin/docker", attempt_dir / "oracle-container.cid")
                remove.reset_mock()
                runner.run_docker_verifier(task, attempt_dir, image_id="sha256:verifier", timeout_scale=1.0)
                remove.assert_called_once_with("/usr/bin/docker", attempt_dir / "verifier-container.cid")

if __name__ == "__main__":
    unittest.main()
