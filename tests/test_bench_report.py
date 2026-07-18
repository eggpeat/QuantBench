import json
import hashlib
import math
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from scripts import bench_report


class BenchReportTest(unittest.TestCase):
    def make_run(self, root, run_id, rows, *, complete=True, run_state="complete", status_fields=None):
        run = Path(root) / run_id
        run.mkdir(parents=True)
        (run / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        status = {"complete": complete, "run_state": run_state}
        status.update(status_fields or {})
        (run / "status.json").write_text(json.dumps(status), encoding="utf-8")

    def row(self, *, result_id, task="t1", attempt=1, status="PASS", ts="2026-01-01T00:00:00Z", agent="a", model="m", provider="p", thinking="high", harness="OMP", duration=1.0, metrics=None, supersedes=None, agent_execution=None, verifier_backend=None, image_id=None, task_image_id=None):
        row = {
            "result_id": result_id,
            "supersedes_result_id": supersedes,
            "ts": ts,
            "agent": agent,
            "task_id": task,
            "attempt_number": attempt,
            "status": status,
            "model": model,
            "backend_provider": provider,
            "thinking": thinking,
            "harness": harness,
            "agent_elapsed_sec": duration,
            "verifier_elapsed_sec": 0.0,
            "runtime_metrics": metrics,
        }
        if agent_execution is not None:
            row["agent_execution"] = agent_execution
        if verifier_backend is not None:
            row["verifier_backend"] = verifier_backend
        if image_id is not None:
            row["image_id"] = image_id
        if task_image_id is not None:
            row["task_image_id"] = task_image_id
        return row

    def metrics(self, total=10, output_speed=5, wall_speed=4, cache=2):
        return {"tokens": {"input": total, "output": total // 2, "total": total + total // 2}, "cache": {"input_cached": cache, "input_total": total}, "throughput": {"output_tok_s": output_speed, "wall_output_tok_s": wall_speed}}

    def manifest_contract(self):
        with bench_report.DEFAULT_MANIFEST_PATH.open("rb") as handle:
            return tomllib.load(handle)
    def tiny_manifest(self, root, lock_id="sha256:locked", source_hash=None, accepted_hashes=None):
        manifest = Path(root) / "manifest.toml"
        source_declaration = (
            f"results_source_manifest_sha256 = \"{source_hash}\"\n" if source_hash is not None else ""
        )
        accepted_declaration = (
            f"accepted_run_manifest_sha256 = {json.dumps(accepted_hashes)}\n"
            if accepted_hashes is not None
            else ""
        )
        manifest.write_text(
            "[task_sets]\nofficial = [\"t1\"]\n"
            "[[tasks]]\nid = \"t1\"\n"
            "[agent_sets]\nofficial = [\"a\"]\n"
            "[[agents]]\nname = \"a\"\nbackend_provider = \"p\"\n"
            "model = \"m\"\nthinking = \"high\"\nharness = \"OMP\"\n"
            f"[benchmark]\nattempts = 1\n{source_declaration}{accepted_declaration}",
            encoding="utf-8",
        )
        (manifest.parent / "image-lock.json").write_text(
            json.dumps({"t1": {"image_id": lock_id}}), encoding="utf-8"
        )
        return manifest, hashlib.sha256(manifest.read_bytes()).hexdigest()
    def strict_status(self, manifest_sha256, image_id="sha256:locked"):
        return {
            "manifest_sha256": manifest_sha256,
            "dry_run": False,
            "agent_execution": "docker",
            "verifier": "docker",
            "tasks": ["t1"],
            "resume_config": {
                "manifest_sha256": manifest_sha256,
                "task_image_identity": {"t1": {"image_id": image_id}},
            },
        }

    def manifest_rows(self, task_ids, *, model, provider, thinking, harness, agent, status="PASS"):
        return [
            self.row(
                result_id=f"{task_id}-{attempt}",
                task=task_id,
                attempt=attempt,
                status=status,
                agent=agent,
                model=model,
                provider=provider,
                thinking=thinking,
                harness=harness,
            )
            for task_id in task_ids
            for attempt in range(1, 6)
        ]

    def test_superseded_and_cross_run_dedupe_uses_timestamp_and_result_identity(self):
        with tempfile.TemporaryDirectory() as td:
            old = self.row(result_id="old", status="INFRA_BLOCKED", ts="2026-01-01T00:00:01Z")
            new = self.row(result_id="new", status="PASS", ts="2026-01-01T00:00:02Z", supersedes="old")
            split = self.row(result_id="split", status="REJECT", ts="2026-01-01T00:00:03Z")
            self.make_run(td, "r1", [old, new])
            self.make_run(td, "r2", [split])
            report = bench_report.build_report(["r1", "r2"], td, expected_tasks=1, expected_attempts=1)
            model = report["models"][0]
            self.assertEqual(model["status_counts"], {"PASS": 0, "REJECT": 1, "TIME_LIMIT": 0, "INFRA_BLOCKED": 0})
            self.assertEqual(report["input"]["observed_rows"], 1)
            self.assertEqual(model["configuration"]["model"], "m")

    def test_cross_run_dedupe_preserves_distinct_configurations(self):
        with tempfile.TemporaryDirectory() as td:
            self.make_run(td, "r1", [self.row(result_id="one", model="m1", provider="p1")])
            self.make_run(td, "r2", [self.row(result_id="two", model="m2", provider="p2", ts="2026-01-02T00:00:00Z")])
            report = bench_report.build_report(["r1", "r2"], td, expected_tasks=1, expected_attempts=1)
            self.assertEqual([model["configuration"]["model"] for model in report["models"]], ["m1", "m2"])
            self.assertEqual(report["input"]["observed_rows"], 2)
    def test_configuration_fields_reject_non_string_values(self):
        with tempfile.TemporaryDirectory() as td:
            row = self.row(result_id="bad")
            row["thinking"] = False
            self.make_run(td, "r", [row])
            with self.assertRaisesRegex(bench_report.ReportError, "thinking.*string or null"):
                bench_report.build_report(["r"], td, expected_tasks=1, expected_attempts=1)

    def test_forty_arbitrary_tasks_are_not_comparable(self):
        contract = self.manifest_contract()
        declared = contract["agents"][0]
        arbitrary_tasks = [f"arbitrary-{index:02d}" for index in range(40)]
        rows = self.manifest_rows(
            arbitrary_tasks,
            model=declared["model"],
            provider=declared["backend_provider"],
            thinking=declared["thinking"],
            harness=declared["harness"],
            agent=declared["name"],
        )
        with tempfile.TemporaryDirectory() as td:
            self.make_run(td, "r", rows)
            report = bench_report.build_report(["r"], td, expected_tasks=40, expected_attempts=5)
        model = report["models"][0]
        self.assertTrue(model["coverage"]["complete"])
        self.assertFalse(model["manifest"]["task_set_match"])
        self.assertEqual(model["manifest"]["missing_task_ids"], sorted(contract["task_sets"]["official"]))
        self.assertEqual(model["manifest"]["unexpected_task_ids"], arbitrary_tasks)
        self.assertFalse(model["comparable"])
        self.assertFalse(report["comparable"])

    def test_forty_by_five_undeclared_configuration_is_not_comparable(self):
        contract = self.manifest_contract()
        rows = self.manifest_rows(
            contract["task_sets"]["official"],
            model="unlisted/model",
            provider="unlisted-provider",
            thinking="max",
            harness="OMP",
            agent="unlisted-agent",
        )
        with tempfile.TemporaryDirectory() as td:
            self.make_run(td, "r", rows)
            report = bench_report.build_report(["r"], td, expected_tasks=40, expected_attempts=5)
        model = report["models"][0]
        self.assertTrue(model["coverage"]["complete"])
        self.assertTrue(model["manifest"]["task_set_match"])
        self.assertFalse(model["manifest"]["configuration_declared"])
        self.assertFalse(model["comparable"])
        self.assertFalse(report["comparable"])



    def test_semantic_and_budgeted_denominators_exclude_infrastructure(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [self.row(result_id="p", status="PASS"), self.row(result_id="r", status="REJECT", task="t2"), self.row(result_id="l", status="TIME_LIMIT", task="t3"), self.row(result_id="i", status="INFRA_BLOCKED", task="t4")]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=4, expected_attempts=1)["models"][0]
            self.assertEqual(model["semantic_trials"], 2)
            self.assertEqual(model["semantic_pass_rate"], 0.5)
            self.assertEqual(model["budgeted_trials"], 3)
            self.assertAlmostEqual(model["budgeted_pass_rate"], 1 / 3)

    def test_partial_coverage_not_comparable_and_task_reliability(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [self.row(result_id="p1", status="PASS"), self.row(result_id="r2", status="REJECT", task="t2"), self.row(result_id="p3", status="PASS", task="t2", attempt=2)]
            self.make_run(td, "r", rows, complete=False, run_state="running")
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=2)["models"][0]
            self.assertFalse(model["comparable"])
            self.assertEqual(model["coverage"]["observed_cells"], 3)
            self.assertEqual(model["task_reliability_distribution"], [{"semantic_passes": 1, "semantic_trials": 1, "tasks": 1, "rate": 1.0}, {"semantic_passes": 1, "semantic_trials": 2, "tasks": 1, "rate": 0.5}])

    def test_completeness_requires_exact_attempt_number_set(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [self.row(result_id="two", attempt=2), self.row(result_id="three", attempt=3)]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=1, expected_attempts=2)["models"][0]
            self.assertFalse(model["coverage"]["complete"])
            self.assertEqual(model["coverage"]["observed_cells"], 1)
            self.assertEqual(model["coverage"]["observed_rows"], 2)
            self.assertEqual(model["coverage"]["unexpected_cells"], 1)
            self.assertEqual(model["coverage"]["missing_cells"], 1)
            self.assertEqual(model["coverage"]["semantic"]["observed_cells"], 1)
            self.assertEqual(model["coverage"]["semantic"]["unexpected_cells"], 1)
            self.assertEqual(model["coverage"]["semantic"]["missing_cells"], 1)
            self.assertFalse(model["coverage"]["semantic"]["complete"])
            self.assertFalse(model["comparable"])


    def test_expected_cell_coverage_limits_excess_task_ids(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="t1a1", task="t1", attempt=1),
                self.row(result_id="t1a2", task="t1", attempt=2),
                self.row(result_id="t2a1", task="t2", attempt=1),
                self.row(result_id="t3a1", task="t3", attempt=1),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=2)["models"][0]
            self.assertEqual(model["coverage"]["observed_cells"], 3)
            self.assertEqual(model["coverage"]["unexpected_cells"], 1)
            self.assertEqual(model["coverage"]["missing_cells"], 1)
            self.assertEqual(model["coverage"]["semantic"]["observed_cells"], 3)
            self.assertFalse(model["coverage"]["complete"])


    def test_attempt_pass_rate_range_reports_complete_stochastic_variation(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="a1", task="t1", attempt=1, status="PASS"),
                self.row(result_id="a2", task="t2", attempt=1, status="REJECT"),
                self.row(result_id="b1", task="t1", attempt=2, status="PASS"),
                self.row(result_id="b2", task="t2", attempt=2, status="PASS"),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=2)["models"][0]
            self.assertEqual([attempt["pass_rate"] for attempt in model["attempts"]], [0.5, 1.0])
            self.assertEqual(
                model["attempt_pass_rate_range"],
                {
                    "complete": True,
                    "minimum": 0.5,
                    "maximum": 1.0,
                    "spread": 0.5,
                    "observed_minimum": 0.5,
                    "observed_maximum": 1.0,
                    "definition": "Descriptive minimum and maximum semantic pass rates across repeated attempt numbers; not a confidence interval.",
                },
            )
            distribution = model["attempt_budgeted_pass_rate_distribution"]
            self.assertTrue(distribution["complete"])
            self.assertEqual(distribution["median"], 0.75)
            self.assertEqual(distribution["minimum"], 0.5)
            self.assertEqual(distribution["maximum"], 1.0)
            self.assertEqual(model["median_attempt_budgeted_pass_rate"], 0.75)
            markdown = bench_report.render_markdown(
                bench_report.build_report(
                    ["r"], td, expected_tasks=2, expected_attempts=2
                )
            )
            self.assertIn("Median attempt pass", markdown)
            self.assertIn("50.0%–100.0%", markdown)
            self.assertIn("median 75.0%", markdown)

    def test_attempt_budgeted_median_counts_time_limit_as_non_pass(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="a1", task="t1", attempt=1, status="PASS"),
                self.row(
                    result_id="a2", task="t2", attempt=1, status="TIME_LIMIT"
                ),
                self.row(result_id="b1", task="t1", attempt=2, status="PASS"),
                self.row(result_id="b2", task="t2", attempt=2, status="PASS"),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(
                ["r"], td, expected_tasks=2, expected_attempts=2
            )["models"][0]
            self.assertEqual(
                [attempt["semantic_pass_rate"] for attempt in model["attempts"]],
                [1.0, 1.0],
            )
            self.assertEqual(
                [attempt["budgeted_pass_rate"] for attempt in model["attempts"]],
                [0.5, 1.0],
            )
            self.assertFalse(model["attempt_pass_rate_range"]["complete"])
            distribution = model["attempt_budgeted_pass_rate_distribution"]
            self.assertTrue(distribution["complete"])
            self.assertEqual(distribution["median"], 0.75)
            self.assertEqual(distribution["spread"], 0.5)

    def test_attempt_pass_rate_range_is_null_for_partial_matrix(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="a1", task="t1", attempt=1, status="PASS"),
                self.row(result_id="a2", task="t2", attempt=1, status="REJECT"),
                self.row(result_id="b1", task="t1", attempt=2, status="PASS"),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=2)["models"][0]
            self.assertFalse(model["attempt_pass_rate_range"]["complete"])
            self.assertIsNone(model["attempt_pass_rate_range"]["minimum"])
            self.assertEqual(model["attempt_pass_rate_range"]["observed_minimum"], 0.5)
            distribution = model["attempt_budgeted_pass_rate_distribution"]
            self.assertFalse(distribution["complete"])
            self.assertIsNone(distribution["median"])
            self.assertEqual(distribution["observed_median"], 0.75)

    def test_exact_even_odd_medians_and_nearest_rank_p90(self):
        self.assertEqual(bench_report.exact_median([1, 3, 2]), 2.0)
        self.assertEqual(bench_report.exact_median([1, 2, 3, 4]), 2.5)
        self.assertEqual(bench_report.nearest_rank_p90([1, 2, 3, 4, 5]), 5.0)
        self.assertEqual(bench_report.nearest_rank_p90([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), 9.0)

    def test_missing_and_nonfinite_throughput_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="a", metrics=self.metrics(output_speed=1, wall_speed=2)),
                self.row(result_id="b", task="t2", metrics=self.metrics(output_speed=float("nan"), wall_speed=float("inf"))),
                self.row(result_id="c", task="t3", status="REJECT", metrics={}),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=3, expected_attempts=1)["models"][0]
            self.assertEqual(model["throughput"]["provider_output_tok_s_median"], 1.0)
            self.assertEqual(model["throughput"]["provider_output_tok_s_coverage"], 1)
            self.assertEqual(model["throughput"]["wall_output_tok_s_median"], 2.0)

    def test_infrastructure_metrics_do_not_distort_semantic_duration_or_throughput(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="semantic", duration=10.0, metrics=self.metrics(output_speed=10, wall_speed=9)),
                self.row(result_id="infra", task="t2", status="INFRA_BLOCKED", duration=0.01, metrics=self.metrics(output_speed=10000, wall_speed=9000)),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=1)["models"][0]
            self.assertEqual(model["duration"]["median_sec"], 10.0)
            self.assertEqual(model["throughput"]["provider_output_tok_s_median"], 10.0)
            self.assertEqual(model["throughput"]["provider_output_tok_s_coverage"], 1)

    def test_matrix_complete_infrastructure_run_is_not_comparable(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="semantic", status="PASS"),
                self.row(result_id="infra", task="t2", status="INFRA_BLOCKED"),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=1)["models"][0]
            self.assertTrue(model["coverage"]["complete"])
            self.assertFalse(model["coverage"]["infra_clear"])
            self.assertEqual(model["coverage"]["semantic"]["observed_cells"], 1)
            self.assertFalse(model["comparable"])

    def test_token_coverage_nulls_complete_totals_but_keeps_observed_sums(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [self.row(result_id="a", metrics=self.metrics(total=10)), self.row(result_id="b", task="t2", status="REJECT", metrics={"tokens": {"total": 4}, "cache": {"input_cached": 1}})]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=1)["models"][0]
            self.assertIsNone(model["token_totals"]["input"])
            self.assertEqual(model["token_observed_sums"]["total"], 19)
            self.assertEqual(model["token_coverage"]["total"], 2)
            self.assertIsNone(model["cache_totals"]["input_total"])
            self.assertEqual(model["cache_coverage"]["input_cached"], 2)

    def test_cache_ratio_coverage_counts_only_paired_rows(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [
                self.row(result_id="cached", metrics={"cache": {"input_cached": 4}}),
                self.row(result_id="total", task="t2", metrics={"cache": {"input_total": 10}}),
            ]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=1)["models"][0]
            self.assertEqual(model["cache_coverage"]["cache_read_ratio"], 0)
            self.assertIsNone(model["cache_totals"]["cache_read_ratio"])

    def test_partial_duration_has_observed_sum_but_no_complete_total(self):
        with tempfile.TemporaryDirectory() as td:
            rows = [self.row(result_id="timed", duration=5), self.row(result_id="missing", task="t2", duration=None)]
            self.make_run(td, "r", rows)
            model = bench_report.build_report(["r"], td, expected_tasks=2, expected_attempts=1)["models"][0]
            self.assertEqual(model["duration"]["observed_sum_sec"], 5)
            self.assertIsNone(model["duration"]["total_sec"])
            self.assertEqual(model["duration"]["coverage"], 1)
    def test_duration_definition_describes_semantic_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            row = self.row(result_id="legacy", duration=None)
            row["duration_sec"] = 7
            self.make_run(td, "r", [row])
            report = bench_report.build_report(["r"], td, expected_tasks=1, expected_attempts=1)
            self.assertEqual(report["models"][0]["duration"]["median_sec"], 7)
            definition = report["metric_definitions"]["duration"]
            self.assertIn("PASS/REJECT", definition)
            self.assertIn("duration_sec", definition)



    def test_markdown_has_deterministic_headings_and_table(self):
        with tempfile.TemporaryDirectory() as td:
            self.make_run(td, "r", [self.row(result_id="a", metrics=self.metrics(total=10))])
            report = bench_report.build_report(["r"], td, expected_tasks=1, expected_attempts=1)
            markdown = bench_report.render_markdown(report)
            self.assertIn("# Quant Bench Report", markdown)
            self.assertIn("## Leaderboard", markdown)
            self.assertIn("| Model | Configuration | Coverage", markdown)
            self.assertIn("## m", markdown)
            self.assertIn("Semantic cells:", markdown)
            self.assertIn("Total tokens:", markdown)
            self.assertIn("Cached-input tokens:", markdown)
            self.assertIn("Weighted cache read ratio:", markdown)
            self.assertIn("Verified duration:", markdown)
            self.assertIn("Task reliability distribution:", markdown)
            self.assertNotIn("speed score", markdown.lower())
            self.assertNotIn("cost score", markdown.lower())
    def test_comparability_requires_complete_non_dry_docker_evidence_and_images(self):
        with tempfile.TemporaryDirectory() as td:
            manifest = Path(td) / "manifest.toml"
            manifest.write_text(
                "[task_sets]\nofficial = [\"t1\"]\n"
                "[[tasks]]\nid = \"t1\"\n"
                "[agent_sets]\nofficial = [\"a\"]\n"
                "[[agents]]\nname = \"a\"\nbackend_provider = \"p\"\n"
                "model = \"m\"\nthinking = \"high\"\nharness = \"OMP\"\n"
                "[benchmark]\nattempts = 1\n",
                encoding="utf-8",
            )
            (manifest.parent / "image-lock.json").write_text(
                json.dumps({"t1": {"image_id": "sha256:immutable"}}), encoding="utf-8"
            )
            manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
            evidence = {
                "manifest_sha256": manifest_sha256,
                "dry_run": False,
                "agent_execution": "docker",
                "verifier": "docker",
                "tasks": ["t1"],
                "resume_config": {
                    "task_image_identity": {"t1": {"image_id": "sha256:immutable"}},
                },
            }
            cases = [
                ("official-docker", evidence, True, "complete"),
                ("host", {**evidence, "agent_execution": "host", "verifier": "host"}, True, "complete"),
                ("dry", {**evidence, "dry_run": True}, True, "complete"),
                ("incomplete", evidence, False, "running"),
                ("missing-image", {key: value for key, value in evidence.items() if key != "resume_config"}, True, "complete"),
            ]
            for run_id, status_fields, complete, run_state in cases:
                with self.subTest(run_id=run_id):
                    self.make_run(
                        td,
                        run_id,
                        [
                            self.row(
                                result_id=run_id,
                                agent_execution="docker",
                                verifier_backend="docker",
                                image_id="sha256:immutable",
                            )
                        ],
                        complete=complete,
                        run_state=run_state,
                        status_fields=status_fields,
                    )
                    report = bench_report.build_report(
                        [run_id],
                        td,
                        expected_tasks=1,
                        expected_attempts=1,
                        manifest_path=manifest,
                    )
                    model = report["models"][0]
                    self.assertEqual(model["comparable"], run_id == "official-docker")
                    if run_id == "official-docker":
                        self.assertEqual(model["execution"]["runs"][run_id]["image_ids"], {"t1": "sha256:immutable"})
                    else:
                        self.assertTrue(model["comparability_reasons"])


    def strict_row(self, result_id="r", *, image_id="sha256:locked", agent_execution="docker", verifier_backend="docker"):
        return self.row(
            result_id=result_id,
            agent_execution=agent_execution,
            verifier_backend=verifier_backend,
            task_image_id=image_id,
        )

    def strict_report(self, root, *, status=None, row=None, lock_id="sha256:locked"):
        manifest, manifest_sha256 = self.tiny_manifest(root, lock_id=lock_id)
        self.make_run(
            root,
            "r",
            [row or self.strict_row(image_id=lock_id)],
            status_fields=status or self.strict_status(manifest_sha256, image_id=lock_id),
        )
        return bench_report.build_report(
            ["r"], root, expected_tasks=1, expected_attempts=1, manifest_path=manifest
        )

    def test_attempt_distribution_svg_renders_raw_points_and_median(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.strict_report(td)
            report["models"][0]["configuration"]["model"] = (
                "openai-codex/gpt-5.6-sol"
            )
            dark_svg = bench_report.render_attempt_distribution_svg(
                report, theme="dark"
            )
            light_svg = bench_report.render_attempt_distribution_svg(
                report, theme="light"
            )
            self.assertIn('role="img"', dark_svg)
            self.assertIn("across 1 attempts", dark_svg)
            self.assertIn("OpenAI GPT 5.6 Sol", dark_svg)
            self.assertIn("Attempt 1: 100.0%", dark_svg)
            self.assertIn("No mean or aggregate count", dark_svg)
            self.assertIn("#E6EDF3", dark_svg)
            self.assertIn("#1F2328", light_svg)
            self.assertNotEqual(dark_svg, light_svg)
            self.assertNotIn("<script", dark_svg)

            report["models"][0]["attempt_budgeted_pass_rate_distribution"][
                "median"
            ] = 0.5
            with self.assertRaisesRegex(
                bench_report.ReportError, "median does not match"
            ):
                bench_report.render_attempt_distribution_svg(report)

    def test_manifest_hash_mismatch_is_not_comparable(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, manifest_sha256 = self.tiny_manifest(td)
            status = self.strict_status(manifest_sha256)
            status["resume_config"]["manifest_sha256"] = "0" * 64
            self.make_run(td, "r", [self.strict_row()], status_fields=status)
            report = bench_report.build_report(
                ["r"], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
            )
            reasons = report["models"][0]["comparability_reasons"]
            self.assertFalse(report["comparable"])
            self.assertTrue(any("manifest_sha256 values conflict" in reason for reason in reasons))

    def test_host_result_row_cannot_hide_behind_docker_status(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.strict_report(
                td,
                row=self.strict_row(agent_execution="host", verifier_backend="host"),
            )
            reasons = report["models"][0]["comparability_reasons"]
            self.assertFalse(report["comparable"])
            self.assertTrue(any("result rows require agent_execution" in reason for reason in reasons))
            self.assertTrue(any("result rows require verifier_backend" in reason for reason in reasons))

    def test_result_image_must_match_frozen_lock(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.strict_report(td, row=self.strict_row(image_id="sha256:wrong"))
            reasons = report["models"][0]["comparability_reasons"]
            self.assertFalse(report["comparable"])
            self.assertTrue(any("result row image ID does not match image lock" in reason for reason in reasons))

    def test_result_and_status_image_ids_must_agree(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, manifest_sha256 = self.tiny_manifest(td)
            status = self.strict_status(manifest_sha256, image_id="sha256:status")
            self.make_run(td, "r", [self.strict_row(image_id="sha256:row")], status_fields=status)
            report = bench_report.build_report(
                ["r"], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
            )
            reasons = report["models"][0]["comparability_reasons"]
            self.assertFalse(report["comparable"])
            self.assertTrue(any("result/status image IDs conflict" in reason for reason in reasons))

    def test_missing_lock_task_is_not_comparable(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, manifest_sha256 = self.tiny_manifest(td)
            (manifest.parent / "image-lock.json").write_text("{}", encoding="utf-8")
            status = self.strict_status(manifest_sha256)
            self.make_run(td, "r", [self.strict_row()], status_fields=status)
            report = bench_report.build_report(
                ["r"], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
            )
            reasons = report["models"][0]["comparability_reasons"]
            self.assertFalse(report["comparable"])
            self.assertTrue(any("missing or malformed image-lock" in reason for reason in reasons))

    def test_official_matching_execution_evidence_is_comparable_and_provenanced(self):
        with tempfile.TemporaryDirectory() as td:
            report = self.strict_report(td)
            self.assertTrue(report["comparable"])
            self.assertEqual(report["manifest"]["sha256"], report["input"]["runs"]["r"]["execution"]["manifest_sha256"])
            self.assertEqual(report["manifest"]["image_lock"]["path"], "image-lock.json")
            self.assertEqual(
                report["manifest"]["image_lock"]["task_image_ids"], {"t1": "sha256:locked"}
            )

    def test_valid_results_source_manifest_hash_declaration_accepts_both_exact_hashes(self):
        source_hash = "a" * 64
        with tempfile.TemporaryDirectory() as td:
            manifest, publication_hash = self.tiny_manifest(td, source_hash=source_hash)
            for run_id, status_hash in (("r-source", source_hash), ("r-publication", publication_hash)):
                with self.subTest(status_hash=status_hash):
                    self.make_run(
                        td,
                        run_id,
                        [self.strict_row(result_id=run_id)],
                        status_fields=self.strict_status(status_hash),
                    )
                    report = bench_report.build_report(
                        [run_id], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
                    )
                    self.assertTrue(report["comparable"])
                    self.assertNotEqual(publication_hash, source_hash)
                    self.assertEqual(
                        report["manifest"]["accepted_run_manifest_sha256"],
                        [publication_hash, source_hash],
                    )
                    self.assertEqual(
                        report["input"]["runs"][run_id]["execution"]["status_manifest_sha256"],
                        status_hash,
                    )
    def test_additional_accepted_manifest_hashes_support_exact_recovery_sources(self):
        source_hash = "a" * 64
        recovery_hashes = ["b" * 64, "c" * 64]
        with tempfile.TemporaryDirectory() as td:
            manifest, publication_hash = self.tiny_manifest(
                td, source_hash=source_hash, accepted_hashes=recovery_hashes
            )
            for run_id, status_hash in (
                ("r-source", source_hash),
                ("r-recovery-1", recovery_hashes[0]),
                ("r-recovery-2", recovery_hashes[1]),
                ("r-publication", publication_hash),
            ):
                with self.subTest(status_hash=status_hash):
                    self.make_run(
                        td,
                        run_id,
                        [self.strict_row(result_id=run_id)],
                        status_fields=self.strict_status(status_hash),
                    )
                    report = bench_report.build_report(
                        [run_id], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
                    )
                    self.assertTrue(report["comparable"])
                    self.assertEqual(
                        report["manifest"]["accepted_run_manifest_sha256"],
                        [publication_hash, source_hash, *recovery_hashes],
                    )

    def test_malformed_additional_manifest_hash_declaration_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, _ = self.tiny_manifest(td, accepted_hashes=["A" * 64])
            with self.assertRaisesRegex(
                bench_report.ReportError, "accepted_run_manifest_sha256"
            ):
                bench_report.build_report(
                    ["r"], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
                )

    def test_malformed_results_source_manifest_hash_declaration_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, _ = self.tiny_manifest(td, source_hash="A" * 64)
            with self.assertRaisesRegex(
                bench_report.ReportError, "results_source_manifest_sha256"
            ):
                bench_report.build_report(
                    ["r"], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
                )

    def test_results_source_manifest_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            source_hash = "a" * 64
            manifest, publication_hash = self.tiny_manifest(td, source_hash=source_hash)
            self.make_run(
                td,
                "r",
                [self.strict_row()],
                status_fields=self.strict_status("b" * 64),
            )
            report = bench_report.build_report(
                ["r"], td, expected_tasks=1, expected_attempts=1, manifest_path=manifest
            )
            self.assertFalse(report["comparable"])
            self.assertTrue(
                any(
                    "accepted run manifest hash(es)" in reason
                    for reason in report["models"][0]["comparability_reasons"]
                )
            )

    def test_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            self.make_run(td, "r", [self.row(result_id="a")])
            json_out = Path(td) / "report.json"
            md_out = Path(td) / "report.md"
            rc = bench_report.main(["r", "--artifact-root", td, "--expected-tasks", "1", "--expected-attempts", "1", "--json-output", str(json_out), "--markdown-output", str(md_out)])
            self.assertEqual(rc, 0)
            payload = json.loads(json_out.read_text())
            self.assertEqual(payload["schema_version"], 1)
            self.assertNotIn("artifact_root", payload["input"])
            self.assertEqual(payload["manifest"]["path"], "benchmarks/quant-terminal-v1.toml")
            self.assertIn("# Quant Bench Report", md_out.read_text())

    def test_cli_writes_attempt_distribution_svg(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, manifest_sha256 = self.tiny_manifest(td)
            self.make_run(
                td,
                "r",
                [self.strict_row()],
                status_fields=self.strict_status(manifest_sha256),
            )
            json_out = Path(td) / "report.json"
            md_out = Path(td) / "report.md"
            light_svg_out = Path(td) / "distribution-light.svg"
            dark_svg_out = Path(td) / "distribution-dark.svg"
            rc = bench_report.main([
                "r",
                "--artifact-root",
                td,
                "--manifest",
                str(manifest),
                "--expected-tasks",
                "1",
                "--expected-attempts",
                "1",
                "--json-output",
                str(json_out),
                "--markdown-output",
                str(md_out),
                "--svg-light-output",
                str(light_svg_out),
                "--svg-dark-output",
                str(dark_svg_out),
            ])
            self.assertEqual(rc, 0)
            self.assertIn("#1F2328", light_svg_out.read_text())
            self.assertIn("#E6EDF3", dark_svg_out.read_text())

    def test_cli_rejects_image_lock_and_parent_child_output_collisions(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, manifest_sha256 = self.tiny_manifest(td)
            self.make_run(
                td,
                "r",
                [self.strict_row()],
                status_fields=self.strict_status(manifest_sha256),
            )
            base_args = [
                "r",
                "--artifact-root",
                td,
                "--manifest",
                str(manifest),
                "--expected-tasks",
                "1",
                "--expected-attempts",
                "1",
            ]
            image_lock = Path(td) / "image-lock.json"
            original_lock = image_lock.read_bytes()
            self.assertEqual(
                bench_report.main(
                    base_args + ["--svg-light-output", str(image_lock)]
                ),
                2,
            )
            self.assertEqual(image_lock.read_bytes(), original_lock)
            run_output = Path(td) / "r" / "report.svg"
            self.assertEqual(
                bench_report.main(
                    base_args + ["--svg-light-output", str(run_output)]
                ),
                2,
            )
            self.assertFalse(run_output.exists())

            parent_output = Path(td) / "report-output"
            child_output = parent_output / "distribution.svg"
            self.assertEqual(
                bench_report.main(
                    base_args
                    + [
                        "--json-output",
                        str(parent_output),
                        "--svg-light-output",
                        str(child_output),
                    ]
                ),
                2,
            )
            self.assertFalse(parent_output.exists())

    def test_cli_rejects_output_aliases_without_overwriting_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            self.make_run(td, "r", [self.row(result_id="a")])
            source = Path(td) / "r" / "results.jsonl"
            original = source.read_text()
            self.assertEqual(
                bench_report.main(["r", "--artifact-root", td, "--expected-tasks", "1", "--expected-attempts", "1", "--json-output", str(source)]),
                2,
            )
            self.assertEqual(source.read_text(), original)
            manifest = bench_report.DEFAULT_MANIFEST_PATH
            manifest_original = manifest.read_bytes()
            self.assertEqual(
                bench_report.main(
                    ["r", "--artifact-root", td, "--expected-tasks", "1", "--expected-attempts", "1", "--json-output", str(manifest)]
                ),
                2,
            )
            self.assertEqual(manifest.read_bytes(), manifest_original)
            shared = Path(td) / "shared.out"
            self.assertEqual(
                bench_report.main(["r", "--artifact-root", td, "--expected-tasks", "1", "--expected-attempts", "1", "--json-output", str(shared), "--markdown-output", str(shared)]),
                2,
            )
            self.assertFalse(shared.exists())
            hard_link = Path(td) / "hard-linked-output"
            os.link(source, hard_link)
            self.assertEqual(
                bench_report.main(["r", "--artifact-root", td, "--expected-tasks", "1", "--expected-attempts", "1", "--json-output", str(hard_link)]),
                2,
            )
            self.assertEqual(source.read_text(), original)


    def test_cli_rejects_duplicate_and_unsafe_ids(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(bench_report.main(["same", "same", "--artifact-root", td]), 2)
            self.assertEqual(bench_report.main(["../escape", "--artifact-root", td]), 2)


if __name__ == "__main__":
    unittest.main()
