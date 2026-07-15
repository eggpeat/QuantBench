from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bench_doctor", ROOT / "scripts" / "bench_doctor.py")
assert SPEC is not None and SPEC.loader is not None
bench_doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench_doctor)


class BenchDoctorTests(unittest.TestCase):
    def manifest(self, root: Path, *, model: str | None = None, thinking: str | None = None) -> Path:
        rows = "schema_version = \"1.0\"\n[task_sets]\nofficial = []\n"
        if model is not None:
            rows += f"\n[[agents]]\nmodel = \"{model}\"\nthinking = \"{thinking}\"\n"
        path = root / "manifest.toml"
        path.write_text(rows, encoding="utf-8")
        return path

    def test_missing_docker_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.manifest(Path(tmp))
            with mock.patch.object(bench_doctor.shutil, "which", return_value=None), mock.patch.object(bench_doctor, "host_memory_bytes", return_value=64 * 1024**3), mock.patch.object(bench_doctor, "artifact_free_bytes", return_value=200 * 1024**3):
                report = bench_doctor.run_doctor(path)
        self.assertFalse(report["ok"])
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "docker daemon")["ok"])

    def test_unreachable_docker_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.manifest(Path(tmp))
            with mock.patch.object(bench_doctor.shutil, "which", return_value="/usr/bin/docker"), mock.patch.object(bench_doctor, "_docker_check", return_value=(False, "docker daemon is unreachable")), mock.patch.object(bench_doctor, "host_memory_bytes", return_value=64 * 1024**3), mock.patch.object(bench_doctor, "artifact_free_bytes", return_value=200 * 1024**3):
                report = bench_doctor.run_doctor(path)
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "docker daemon")["ok"])

    def test_low_memory_and_disk_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.manifest(Path(tmp))
            with mock.patch.object(bench_doctor.shutil, "which", return_value="/usr/bin/tool"), mock.patch.object(bench_doctor, "_docker_check", return_value=(True, "ok")), mock.patch.object(bench_doctor, "host_memory_bytes", return_value=1), mock.patch.object(bench_doctor, "artifact_free_bytes", return_value=1):
                report = bench_doctor.run_doctor(path)
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "host memory")["ok"])
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "artifact disk")["ok"])

    def test_artifact_free_bytes_uses_existing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "artifacts" / "nested"
            usage = mock.Mock(free=123)
            with mock.patch.object(bench_doctor.shutil, "disk_usage", return_value=usage) as disk_usage:
                self.assertEqual(bench_doctor.artifact_free_bytes(missing), 123)
            disk_usage.assert_called_once_with(root)

    def test_host_only_doctor_skips_container_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.manifest(Path(tmp))
            with (
                mock.patch.object(bench_doctor.shutil, "which", return_value="/usr/bin/tool") as which,
                mock.patch.object(bench_doctor, "_docker_check") as docker_check,
                mock.patch.object(bench_doctor, "host_memory_bytes", return_value=64 * 1024**3),
                mock.patch.object(bench_doctor, "artifact_free_bytes", return_value=200 * 1024**3),
                mock.patch.object(bench_doctor, "_task_checks", return_value=[]),
                mock.patch.object(bench_doctor, "_model_checks", return_value=[]),
            ):
                report = bench_doctor.run_doctor(path, agent_execution="host", verifier="host")
        names = {item["name"] for item in report["checks"]}
        self.assertNotIn("command:docker", names)
        self.assertNotIn("command:bwrap", names)
        self.assertNotIn("docker daemon", names)
        docker_check.assert_not_called()
        self.assertEqual([call.args[0] for call in which.call_args_list], ["git", "bun", "omp"])

    def test_default_docker_doctor_skips_bwrap_but_checks_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.manifest(Path(tmp))
            with (
                mock.patch.object(bench_doctor.shutil, "which", return_value="/usr/bin/tool"),
                mock.patch.object(bench_doctor, "_docker_check", return_value=(True, "ok")),
                mock.patch.object(bench_doctor, "host_memory_bytes", return_value=64 * 1024**3),
                mock.patch.object(bench_doctor, "artifact_free_bytes", return_value=200 * 1024**3),
                mock.patch.object(bench_doctor, "_task_checks", return_value=[]),
                mock.patch.object(bench_doctor, "_model_checks", return_value=[]),
            ):
                report = bench_doctor.run_doctor(path)
        names = {item["name"] for item in report["checks"]}
        self.assertIn("command:docker", names)
        self.assertIn("docker daemon", names)
        self.assertNotIn("command:bwrap", names)

    def test_missing_exact_selector_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.manifest(root, model="provider/missing", thinking="high")
            agent = root / "agent"
            agent.mkdir()
            (agent / "config.yml").write_text("defaultThinkingLevel: high\n", encoding="utf-8")
            with sqlite3.connect(agent / "models.db") as db:
                db.execute("create table models(selector text, metadata text)")
                db.execute("insert into models values (?, ?)", ("provider/missing-neighbor", json.dumps({"thinking": {"efforts": ["high"]}})))
                db.commit()
            checks = bench_doctor._model_checks(bench_doctor._manifest(path), agent)
        self.assertFalse(next(item for item in checks if item["name"] == "selector:provider/missing")["ok"])

    def test_supported_lower_thinking_level_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.manifest(root, model="provider/model", thinking="low")
            agent = root / "agent"
            agent.mkdir()
            (agent / "config.yml").write_text("defaultThinkingLevel: low\n", encoding="utf-8")
            with sqlite3.connect(agent / "models.db") as db:
                db.execute(
                    "create table model_cache(provider_id text, version integer, updated_at integer, authoritative integer, static_fingerprint text, models text)"
                )
                db.execute(
                    "insert into model_cache values (?, ?, ?, ?, ?, ?)",
                    ("provider", 1, 0, 0, "", json.dumps([{"id": "model", "thinking": {"efforts": ["low", "medium"]}}])),
                )
                db.commit()
            checks = bench_doctor._model_checks(bench_doctor._manifest(path), agent)
        self.assertTrue(next(item for item in checks if item["name"] == "selector:provider/model")["ok"])

    def test_unsupported_lower_thinking_level_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.manifest(root, model="provider/model", thinking="low")
            agent = root / "agent"
            agent.mkdir()
            (agent / "config.yml").write_text("defaultThinkingLevel: low\n", encoding="utf-8")
            with sqlite3.connect(agent / "models.db") as db:
                db.execute("create table models(selector text, metadata text)")
                db.execute("insert into models values (?, ?)", ("provider/model", json.dumps({"thinking": {"efforts": ["medium"]}})))
                db.commit()
            checks = bench_doctor._model_checks(bench_doctor._manifest(path), agent)
        self.assertFalse(next(item for item in checks if item["name"] == "selector:provider/model")["ok"])

    def test_json_redacts_credentials(self) -> None:
        result = bench_doctor._result("credential", False, "api_key=super-secret-token")
        self.assertNotIn("super-secret-token", json.dumps(result))
        self.assertIn("redacted", result["detail"])

    def test_fully_mocked_machine_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = self.manifest(root)
            (root / "tasks").mkdir()
            with mock.patch.object(bench_doctor.shutil, "which", return_value="/usr/bin/tool"), mock.patch.object(bench_doctor, "_docker_check", return_value=(True, "ok")), mock.patch.object(bench_doctor, "host_memory_bytes", return_value=64 * 1024**3), mock.patch.object(bench_doctor, "artifact_free_bytes", return_value=200 * 1024**3), mock.patch.object(bench_doctor, "_task_checks", return_value=[bench_doctor._result("tasks", True)]), mock.patch.object(bench_doctor, "_model_checks", return_value=[bench_doctor._result("selectors", True)]):
                report = bench_doctor.run_doctor(path)
        self.assertTrue(report["ok"])

    def test_image_checks_reject_stale_input_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task_root = root / "tasks" / "unit"
            environment = task_root / "environment"
            environment.mkdir(parents=True)
            (environment / "Dockerfile").write_text(
                "FROM python:3.12-slim@sha256:" + "a" * 64 + "\nCOPY requirements.txt /tmp/requirements.txt\n",
                encoding="utf-8",
            )
            (environment / "requirements.txt").write_text("pytest==8.4.2\n", encoding="utf-8")
            manifest = {
                "tasks": [{"id": "unit", "path": "tasks/unit"}],
                "task_sets": {"official": ["unit"]},
            }
            expected = bench_doctor._task_image_inputs("unit", task_root)
            lock_path = root / "image-lock.json"
            stale = {**expected, "image_id": "sha256:final", "dockerfile_sha256": "0" * 64}
            lock_path.write_text(json.dumps({"unit": stale}), encoding="utf-8")
            with mock.patch.object(bench_doctor, "PROJECT_ROOT", root):
                checks = bench_doctor._image_checks(manifest, require_images=False, lock_path=lock_path)
            self.assertFalse(next(item for item in checks if item["name"] == "image-lock:unit")["ok"])

            lock_path.write_text(json.dumps({"unit": {**expected, "image_id": "sha256:final"}}), encoding="utf-8")
            with mock.patch.object(bench_doctor, "PROJECT_ROOT", root):
                checks = bench_doctor._image_checks(manifest, require_images=False, lock_path=lock_path)
            self.assertTrue(next(item for item in checks if item["name"] == "image-lock:unit")["ok"])

            inspect = mock.Mock(returncode=0, stdout="sha256:other\n")
            with (
                mock.patch.object(bench_doctor, "PROJECT_ROOT", root),
                mock.patch.object(bench_doctor.shutil, "which", return_value="/usr/bin/docker"),
                mock.patch.object(bench_doctor.subprocess, "run", return_value=inspect) as run,
            ):
                checks = bench_doctor._image_checks(manifest, require_images=True, lock_path=lock_path)
            image_check = next(item for item in checks if item["name"] == "image:unit")
            self.assertFalse(image_check["ok"])
            self.assertIn("ID mismatch", image_check["detail"])
            self.assertEqual(
                run.call_args.args[0],
                ["/usr/bin/docker", "image", "inspect", "--format", "{{.Id}}", expected["tag"]],
            )


    def test_empty_metadata_thinking_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "models.db"
            with sqlite3.connect(db_path) as db:
                db.execute("create table models(selector text, metadata text)")
                db.execute("insert into models values (?, ?)", ("provider/model", json.dumps({"thinking": None})))
                db.commit()
            self.assertEqual(bench_doctor.highest_known_thinking("provider/model", db_path), ("none", True))


if __name__ == "__main__":
    unittest.main()
