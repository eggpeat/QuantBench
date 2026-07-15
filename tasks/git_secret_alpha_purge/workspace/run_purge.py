#!/usr/bin/env python3
"""Runner and validation script for the Git history purge task.
It verifies the repository state before and after, runs the candidate's solution, and writes outputs/purge_report.json.
"""

import os
import sys
import json
import subprocess
import shutil
from pathlib import Path

WORKSPACE_DIR = Path(__file__).parent.resolve()
OUTPUTS_DIR = WORKSPACE_DIR / "outputs"
REPO_DIR = WORKSPACE_DIR

def run_git(args, env=None):
    git_env = os.environ.copy()
    if env:
        git_env.update(env)
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_ATTR_NOSYSTEM"] = "1"

    result = subprocess.run(
        ["git"] + args,
        cwd=str(REPO_DIR),
        env=git_env,
        capture_output=True,
        text=True,
        errors="ignore",
    )
    return result

def get_reachable_blobs():
    # Get all reachable objects from branches and tags
    res = run_git(["rev-list", "--objects", "--branches", "--tags"])
    if res.returncode != 0:
        return []
    blobs = []
    for line in res.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            sha, path = parts
            blobs.append((sha, path))
    return blobs

def check_secret_in_any_blob(secret):
    blobs = get_reachable_blobs()
    for sha, path in blobs:
        res = run_git(["cat-file", "-p", sha])
        if res.returncode == 0:
            if secret in res.stdout:
                return True
    return False

def check_file_in_any_commit(filename):
    blobs = get_reachable_blobs()
    for sha, path in blobs:
        if path == filename or Path(path).name == filename:
            return True
    return False

def verify_topology():
    res = run_git(["log", "--format=%H %P", "--branches", "--tags"])
    if res.returncode != 0:
        return None

    # Get branch targets
    main_res = run_git(["rev-parse", "main"])
    feat_res = run_git(["rev-parse", "feature/inference"])
    if main_res.returncode != 0 or feat_res.returncode != 0:
        return None

    main_head = main_res.stdout.strip()
    feat_head = feat_res.stdout.strip()

    dag = {}
    for line in res.stdout.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        c = parts[0]
        parents = parts[1:]
        dag[c] = parents

    # Check DAG matches topology
    # H8 -> H7 -> H6 -> [H4, H5]
    # H4 -> H2 -> H1 -> []
    # H5 -> H3 -> H2
    try:
        H8 = main_head
        if len(dag.get(H8, [])) != 1: return False
        H7 = dag[H8][0]
        if len(dag.get(H7, [])) != 1: return False
        H6 = dag[H7][0]
        if len(dag.get(H6, [])) != 2: return False

        # Merge parents can be in either order
        p1, p2 = dag[H6]
        if feat_head in (p1, p2):
            H5 = feat_head
            H4 = p1 if p2 == H5 else p2
        else:
            return False

        if len(dag.get(H5, [])) != 1: return False
        H3 = dag[H5][0]
        if len(dag.get(H3, [])) != 1: return False
        H2_from_3 = dag[H3][0]

        if len(dag.get(H4, [])) != 1: return False
        H2_from_4 = dag[H4][0]

        if H2_from_3 != H2_from_4: return False
        H2 = H2_from_3

        if len(dag.get(H2, [])) != 1: return False
        H1 = dag[H2][0]

        if len(dag.get(H1, [])) != 0: return False

        # Check total number of unique commits in this DAG
        all_commits = {H8, H7, H6, H5, H4, H3, H2, H1}
        if len(all_commits) != 8 or len(dag) != 8:
            return False

        return True
    except Exception:
        return False

def verify_working_directory():
    # Make sure we are on main
    status_res = run_git(["status", "--porcelain"])
    if status_res.returncode != 0 or status_res.stdout.strip() != "":
        return False

    # Check files at HEAD
    files = ["main.py", "utils.py", "config.json", "README.md"]
    for f in files:
        if not (REPO_DIR / f).is_file():
            return False

    # Check contents of config.json
    try:
        config_content = json.loads((REPO_DIR / "config.json").read_text(encoding="utf-8"))
        if "alpha_token" in config_content:
            return False
        if config_content.get("version") != "1.1.0" or config_content.get("environment") != "production":
            return False
    except Exception:
        return False

    # Check that alpha_weights.bin and inference.py do not exist in CWD
    if (REPO_DIR / "alpha_weights.bin").exists() or (REPO_DIR / "inference.py").exists():
        return False

    return True

def main():
    global REPO_DIR
    if len(sys.argv) > 1:
        REPO_DIR = Path(sys.argv[1]).resolve()
    print("=== Starting Git Secret Purge Evaluation ===")

    # 1. Ensure the repo is clean and populated
    if not (REPO_DIR / ".git").exists():
        print("Git repository not found. Setting up...")
        import setup_repo
        setup_repo.setup_repo(REPO_DIR)

    # 2. Collect pre-purge stats
    leaked_file_pre = check_file_in_any_commit("alpha_weights.bin")
    secret_token_pre = check_secret_in_any_blob("alpha-prod-tok-991283")

    print(f"Pre-purge: alpha_weights.bin found = {leaked_file_pre}")
    print(f"Pre-purge: secret token found = {secret_token_pre}")

    pre_purge_check = {
        "leaked_file_found_in_history": leaked_file_pre,
        "secret_token_found_in_history": secret_token_pre
    }
    existing_report = OUTPUTS_DIR / "purge_report.json"
    if existing_report.is_file() and not (leaked_file_pre or secret_token_pre):
        try:
            previous_pre = json.loads(existing_report.read_text(encoding="utf-8")).get("pre_purge_check")
            if isinstance(previous_pre, dict) and (
                previous_pre.get("leaked_file_found_in_history") or previous_pre.get("secret_token_found_in_history")
            ):
                pre_purge_check = previous_pre
        except Exception:
            pass


    # 3. Load and run the candidate's purge logic
    sys.path.insert(0, str(WORKSPACE_DIR))
    try:
        import purge_alpha
        print("Running candidate's purge_repository...")
        purge_alpha.purge_repository(REPO_DIR)
    except Exception as e:
        print(f"Error during purge execution: {e}")
        import traceback
        traceback.print_exc()
        # Create failure report
        report = {
            "pre_purge_check": pre_purge_check,
            "post_purge_check": {
                "leaked_file_removed": False,
                "secret_token_removed": False,
                "merge_topology_preserved": False,
                "current_working_directory_clean": False,
                "commit_count": 0
            },
            "error": str(e),
            "success": False
        }
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUTS_DIR / "purge_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        sys.exit(1)

    # 4. Collect post-purge stats
    leaked_file_post = check_file_in_any_commit("alpha_weights.bin")
    secret_token_post = check_secret_in_any_blob("alpha-prod-tok-991283")
    topology_ok = verify_topology()
    cwd_ok = verify_working_directory()

    # Count commits
    commit_res = run_git(["rev-list", "--count", "--all"])
    commit_count = int(commit_res.stdout.strip()) if commit_res.returncode == 0 else 0

    print(f"Post-purge: alpha_weights.bin found = {leaked_file_post}")
    print(f"Post-purge: secret token found = {secret_token_post}")
    print(f"Post-purge: topology preserved = {topology_ok}")
    print(f"Post-purge: working directory clean/correct = {cwd_ok}")
    print(f"Post-purge: total commit count = {commit_count}")

    success = (not leaked_file_post) and (not secret_token_post) and topology_ok and cwd_ok

    report = {
        "pre_purge_check": pre_purge_check,
        "post_purge_check": {
            "leaked_file_removed": not leaked_file_post,
            "secret_token_removed": not secret_token_post,
            "merge_topology_preserved": bool(topology_ok),
            "current_working_directory_clean": bool(cwd_ok),
            "commit_count": commit_count
        },
        "success": success
    }

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUTS_DIR / "purge_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"Report written. Success = {success}")
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
