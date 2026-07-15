from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_bench_tasks", ROOT / "scripts" / "validate_bench_tasks.py")
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class ValidateBenchTaskTests(unittest.TestCase):
    def test_docker_run_applies_resource_limits_and_timeout(self) -> None:
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(validator.subprocess, "run", return_value=completed) as run:
            validator._docker_run(
                "sha256:image",
                [(Path("/tmp/workspace"), "/workspace", "rw")],
                ["python", "probe.py"],
                resources={"memory_mb": 4096, "cpus": 2},
                timeout=17.0,
            )
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--pids-limit") + 1], "100")
        self.assertEqual(command[command.index("--memory") + 1], "4096m")
        self.assertEqual(command[command.index("--cpus") + 1], "2")
        self.assertEqual(run.call_args.kwargs["timeout"], 17.0)
        self.assertIn("--network", command)
        self.assertIn("no-new-privileges", command)
    def test_manifest_task_paths_must_be_exact_and_relative(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "benchmarks" / "manifest.toml"
            manifest_path.parent.mkdir()
            for raw_path in ("/tmp/tasks/a", "tasks/../outside", "tasks/b"):
                with self.subTest(raw_path=raw_path):
                    errors: list[str] = []
                    validator._validate_manifest(
                        manifest_path,
                        {"tasks": [{"id": "a", "path": raw_path}]},
                        errors,
                    )
                    self.assertIn("a: path must be exactly tasks/a", errors)

    def test_manifest_task_path_symlink_must_stay_under_task_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "benchmarks" / "manifest.toml"
            manifest_path.parent.mkdir()
            (root / "tasks").mkdir()
            outside = root / "outside"
            outside.mkdir()
            (root / "tasks" / "a").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(validator.ValidationError):
                validator._relative_task_root(manifest_path, {"id": "a", "path": "tasks/a"})


if __name__ == "__main__":
    unittest.main()
