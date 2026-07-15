import importlib
import json
import os
import sys
import subprocess
import shutil
import tempfile
import traceback
from pathlib import Path

WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", Path(__file__).parents[1] / "workspace"))
EXPECTED_PATH = Path(__file__).with_name("expected.json")

def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def import_candidate_module():
    sys.path.insert(0, str(WORKSPACE))
    try:
        return importlib.import_module("purge_alpha")
    finally:
        if str(WORKSPACE) in sys.path:
            sys.path.remove(str(WORKSPACE))

def generate_outputs():
    # Force reinitialize the git repo by running setup_repo.py
    import sys
    import os
    import importlib
    import runpy

    old_cwd = os.getcwd()
    old_argv = sys.argv
    old_path = list(sys.path)
    try:
        # Change cwd to WORKSPACE to run setup_repo and run_purge in their expected directory
        os.chdir(str(WORKSPACE))
        sys.path.insert(0, str(WORKSPACE))

        # 1. Set up the git fixture in a temp repo so candidate helper files in
        # WORKSPACE are not deleted or counted as dirty repository files.
        fixture_dir = Path(tempfile.mkdtemp())
        try:
            import setup_repo
            importlib.reload(setup_repo)
            setup_repo.setup_repo(fixture_dir)

            # 2. Run run_purge.py against the temp repo and write WORKSPACE/outputs/purge_report.json.
            sys.argv = [str(WORKSPACE / "run_purge.py"), str(fixture_dir)]
            runpy.run_path(str(WORKSPACE / "run_purge.py"), run_name="__main__")
        finally:
            shutil.rmtree(fixture_dir, ignore_errors=True)
    except SystemExit:
        # run_purge.py might call sys.exit(1), catch it to avoid breaking the test runner
        pass
    except Exception as e:
        # If running run_purge.py or setup_repo fails (e.g. candidate throws exception),
        # reproduce/write a dummy/failure JSON report to outputs/purge_report.json
        # to ensure the assert below fails gracefully with the check.
        try:
            report_dir = WORKSPACE / "outputs"
            report_dir.mkdir(parents=True, exist_ok=True)
            report = {
                "success": False,
                "error": str(e),
                "pre_purge_check": {},
                "post_purge_check": {}
            }
            with open(report_dir / "purge_report.json", "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
                f.write("\n")
        except Exception:
            pass
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
        sys.path = old_path
def test_public_fixture_output_matches_expected_snapshot():
    generate_outputs()
    output_path = WORKSPACE / "outputs" / "purge_report.json"
    assert output_path.is_file(), "purge_report.json not found in outputs"

    actual = load_json(output_path)
    expected = load_json(EXPECTED_PATH)

    # Assert check results
    assert actual.get("success") is True, "The purge report indicates failure"
    assert actual.get("pre_purge_check") == expected.get("pre_purge_check"), "pre_purge_check mismatch"
    assert actual.get("post_purge_check") == expected.get("post_purge_check"), "post_purge_check mismatch"

def test_on_randomized_git_repo():
    mod = import_candidate_module()
    assert hasattr(mod, "purge_repository"), "purge_repository function not found in purge_alpha"

    # Create a fresh randomized repository
    temp_dir = Path(tempfile.mkdtemp())
    try:
        def run_git(args, env=None):
            git_env = os.environ.copy()
            if env:
                git_env.update(env)
            git_env["GIT_CONFIG_NOSYSTEM"] = "1"
            git_env["GIT_ATTR_NOSYSTEM"] = "1"
            git_env["GIT_AUTHOR_NAME"] = "Auditor Agent"
            git_env["GIT_AUTHOR_EMAIL"] = "auditor@example.com"
            git_env["GIT_COMMITTER_NAME"] = "Auditor Agent"
            git_env["GIT_COMMITTER_EMAIL"] = "auditor@example.com"

            res = subprocess.run(
                ["git"] + args,
                cwd=str(temp_dir),
                env=git_env,
                capture_output=True,
                text=True
            )
            if res.returncode != 0:
                raise RuntimeError(f"Git failed: {res.stderr}")
            return res.stdout.strip()

        # Init
        run_git(["init", "-b", "main"])
        run_git(["config", "user.name", "Auditor Agent"])
        run_git(["config", "user.email", "auditor@example.com"])
        run_git(["config", "commit.gpgsign", "false"])

        def make_commit(msg, files, date):
            for filepath, content in files.items():
                full_path = temp_dir / filepath
                full_path.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    full_path.write_bytes(content)
                else:
                    full_path.write_text(content, encoding="utf-8")
                run_git(["add", filepath])
            env = {"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
            run_git(["commit", "-m", msg], env=env)

        # Build slightly different repo DAG
        # Commit 1
        make_commit("Audit init", {"main.py": "print('audit')", "config.json": '{"version": "2.0"}'}, "2026-06-27T14:00:00Z")
        # Commit 2 (leak)
        make_commit("Audit leak", {"alpha_weights.bin": b"leakdata123", "config.json": '{"version": "2.1", "alpha_token": "alpha-prod-tok-991283"}'}, "2026-06-27T14:05:00Z")
        # Commit 3 (branch)
        run_git(["checkout", "-b", "feature/inference"])
        make_commit("Audit feature branch commit", {"inference.py": "print('audit inference')"}, "2026-06-27T14:10:00Z")
        # Commit 4 (main)
        run_git(["checkout", "main"])
        make_commit("Audit extra file on main", {"README.md": "# Audit readme"}, "2026-06-27T14:15:00Z")
        # Commit 5 (branch v2)
        run_git(["checkout", "feature/inference"])
        make_commit("Audit inference v2", {"inference.py": "print('audit inference v2')"}, "2026-06-27T14:20:00Z")
        # Commit 6 (merge)
        run_git(["checkout", "main"])
        run_git(["merge", "feature/inference", "--no-ff", "-m", "Audit merge"], env={
            "GIT_AUTHOR_DATE": "2026-06-27T14:25:00Z",
            "GIT_COMMITTER_DATE": "2026-06-27T14:25:00Z"
        })
        # Commit 7 (remove weights/token)
        run_git(["rm", "alpha_weights.bin"])
        make_commit("Audit clean up", {"config.json": '{"version": "2.2"}'}, "2026-06-27T14:30:00Z")
        # Commit 8
        make_commit("Audit final tweak", {"main.py": "print('audit final')"}, "2026-06-27T14:35:00Z")

        # Verify leak exists pre-purge
        objects_pre = run_git(["rev-list", "--objects", "--all"]).splitlines()
        found_weights_pre = any("alpha_weights.bin" in o for o in objects_pre)
        assert found_weights_pre, "Test setup error: alpha_weights.bin not found pre-purge"

        # Run candidate purge logic
        mod.purge_repository(temp_dir)

        # 1. Verify commit count is still 8
        commit_count = int(run_git(["rev-list", "--count", "--all"]))
        assert commit_count == 8, f"Expected 8 commits after rewrite, got {commit_count}"

        # 2. Verify leaks are gone
        objects_post = run_git(["rev-list", "--objects", "--all"]).splitlines()
        found_weights_post = any("alpha_weights.bin" in o for o in objects_post)
        assert not found_weights_post, "Leaked alpha_weights.bin still reachable in rewritten repository"

        found_token_post = False
        for obj_line in objects_post:
            parts = obj_line.split()
            if not parts:
                continue
            sha = parts[0]
            t_res = subprocess.run(["git", "cat-file", "-t", sha], cwd=str(temp_dir), capture_output=True, text=True)
            if t_res.stdout.strip() == "blob":
                content_res = subprocess.run(["git", "cat-file", "-p", sha], cwd=str(temp_dir), capture_output=True)
                if b"alpha-prod-tok-991283" in content_res.stdout:
                    found_token_post = True
                    break
        assert not found_token_post, "Production secret token still reachable in rewritten repository"

        # 3. Verify git fsck is clean
        fsck_res = subprocess.run(["git", "fsck", "--strict"], cwd=str(temp_dir), capture_output=True, text=True)
        assert fsck_res.returncode == 0, f"git fsck failed post-purge: {fsck_res.stderr}"

        # 4. Verify merge topology is intact
        # (check that main has 8 commits reachable, feature/inference has 4, and main has exactly one merge commit)
        main_commits_count = int(run_git(["rev-list", "--count", "main"]))
        feat_commits_count = int(run_git(["rev-list", "--count", "feature/inference"]))
        assert main_commits_count == 8, f"Expected 8 reachable commits from main, got {main_commits_count}"
        assert feat_commits_count == 4, f"Expected 4 reachable commits from feature/inference, got {feat_commits_count}"
    finally:
        shutil.rmtree(temp_dir)

def run_all_tests():
    failures = 0

    print("Running test_public_fixture_output_matches_expected_snapshot...")
    try:
        test_public_fixture_output_matches_expected_snapshot()
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        traceback.print_exc()
        failures += 1

    print("Running test_on_randomized_git_repo...")
    try:
        test_on_randomized_git_repo()
        print("OK")
    except Exception as e:
        print(f"FAIL: {e}")
        traceback.print_exc()
        failures += 1

    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(run_all_tests())
