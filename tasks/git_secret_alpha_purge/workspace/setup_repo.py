import subprocess
import os
import sys
import shutil
from pathlib import Path

def run_git(args, cwd, env=None):
    git_env = os.environ.copy()
    if env:
        git_env.update(env)
    # Ensure standard env for deterministic commits
    git_env["GIT_CONFIG_NOSYSTEM"] = "1"
    git_env["GIT_ATTR_NOSYSTEM"] = "1"
    # Set default name/email if not configured
    git_env["GIT_AUTHOR_NAME"] = "Dev Agent"
    git_env["GIT_AUTHOR_EMAIL"] = "agent@example.com"
    git_env["GIT_COMMITTER_NAME"] = "Dev Agent"
    git_env["GIT_COMMITTER_EMAIL"] = "agent@example.com"

    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        env=git_env,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Git command failed: git {' '.join(args)}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    return result.stdout.strip()

def setup_repo(repo_dir: Path):
    if repo_dir.exists():
        # Remove everything except python scripts or config files
        shutil.rmtree(repo_dir / ".git", ignore_errors=True)
        for p in list(repo_dir.glob("**/*")):
            if p.is_file() and p.name not in ["setup_repo.py", "purge_alpha.py", "run_purge.py"]:
                try:
                    p.unlink()
                except OSError:
                    pass
    else:
        repo_dir.mkdir(parents=True, exist_ok=True)

    # Initialize repository
    run_git(["init", "-b", "main"], repo_dir)
    run_git(["config", "user.name", "Dev Agent"], repo_dir)
    run_git(["config", "user.email", "agent@example.com"], repo_dir)
    run_git(["config", "commit.gpgsign", "false"], repo_dir)

    # Helper to commit
    def make_commit(msg, files, date, parent_branch=None):
        if parent_branch:
            run_git(["checkout", parent_branch], repo_dir)
        for filepath, content in files.items():
            full_path = repo_dir / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                full_path.write_bytes(content)
            else:
                full_path.write_text(content, encoding="utf-8")
            run_git(["add", filepath], repo_dir)

        env = {
            "GIT_AUTHOR_DATE": date,
            "GIT_COMMITTER_DATE": date
        }
        run_git(["commit", "-m", msg], repo_dir, env=env)

    # Commit 1: Initial Commit
    make_commit(
        "Initial commit with core source files",
        {
            "main.py": (
                "import os\n"
                "import json\n\n"
                "def load_config():\n"
                "    with open('config.json', 'r') as f:\n"
                "        return json.load(f)\n\n"
                "def main():\n"
                "    config = load_config()\n"
                "    print(f'Running inference, version: {config.get(\"version\")}')\n"
                "    print('Inference completed successfully.')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "utils.py": (
                "# General utilities\n"
                "def calculate_checksum(data):\n"
                "    import hashlib\n"
                "    return hashlib.sha256(data).hexdigest()\n"
            ),
            "config.json": '{\n  "version": "1.0.0",\n  "environment": "development"\n}\n'
        },
        "2026-06-27T12:00:00Z"
    )

    # Commit 2: Leaked binary weights and secret token in config
    dummy_weights = bytes(i % 256 for i in range(100 * 1024))
    make_commit(
        "Update config for production; add model weights bin",
        {
            "alpha_weights.bin": dummy_weights,
            "config.json": (
                '{\n'
                '  "version": "1.0.1-alpha",\n'
                '  "environment": "production",\n'
                '  "alpha_token": "alpha-prod-tok-991283"\n'
                '}\n'
            )
        },
        "2026-06-27T12:10:00Z"
    )

    # Commit 3: Branch feature/inference starts from main (Commit 2)
    run_git(["checkout", "-b", "feature/inference"], repo_dir)
    make_commit(
        "Implement weight loader module in utils and basic inference logic",
        {
            "utils.py": (
                "# General utilities\n"
                "def calculate_checksum(data):\n"
                "    import hashlib\n"
                "    return hashlib.sha256(data).hexdigest()\n\n"
                "def load_weights(path):\n"
                "    with open(path, 'rb') as f:\n"
                "        return len(f.read())\n"
            ),
            "inference.py": (
                "from utils import load_weights\n\n"
                "def run():\n"
                "    w = load_weights('alpha_weights.bin')\n"
                "    print(f'Loaded {w} bytes of weights.')\n"
            )
        },
        "2026-06-27T12:20:00Z"
    )

    # Commit 4: Switch back to main, add README
    run_git(["checkout", "main"], repo_dir)
    make_commit(
        "Add project documentation README.md",
        {
            "README.md": (
                "# Alpha Inference Engine\n\n"
                "High performance inference framework for alpha model.\n"
            )
        },
        "2026-06-27T12:30:00Z"
    )

    # Commit 5: Go back to feature/inference, improve comments
    run_git(["checkout", "feature/inference"], repo_dir)
    make_commit(
        "Log more details in inference model loading step",
        {
            "inference.py": (
                "from utils import load_weights\n\n"
                "def run():\n"
                "    print('Initializing weights...')\n"
                "    w = load_weights('alpha_weights.bin')\n"
                "    print(f'Loaded {w} bytes of weights.')\n"
            )
        },
        "2026-06-27T12:40:00Z"
    )

    # Commit 6: Merge feature/inference into main
    run_git(["checkout", "main"], repo_dir)
    run_git(["merge", "feature/inference", "--no-ff", "-m", "Merge branch 'feature/inference' into main"], repo_dir, env={
        "GIT_AUTHOR_DATE": "2026-06-27T12:50:00Z",
        "GIT_COMMITTER_DATE": "2026-06-27T12:50:00Z"
    })

    # Commit 7: Remove weights and token from latest version
    make_commit(
        "Deprecate local weights, clean up credentials config",
        {
            "config.json": (
                '{\n'
                '  "version": "1.1.0",\n'
                '  "environment": "production"\n'
                '}\n'
            )
        },
        "2026-06-27T13:00:00Z"
    )
    run_git(["rm", "alpha_weights.bin", "inference.py"], repo_dir)
    run_git(["commit", "-m", "Remove leaked model weights and inference modules", "--amend", "--no-edit"], repo_dir, env={
        "GIT_AUTHOR_DATE": "2026-06-27T13:00:00Z",
        "GIT_COMMITTER_DATE": "2026-06-27T13:00:00Z"
    })

    # Commit 8: Add latency profiling to main.py
    make_commit(
        "Add profiling measurement code to main entrypoint",
        {
            "main.py": (
                "import os\n"
                "import json\n"
                "import time\n\n"
                "def load_config():\n"
                "    with open('config.json', 'r') as f:\n"
                "        return json.load(f)\n\n"
                "def main():\n"
                "    start = time.perf_counter()\n"
                "    config = load_config()\n"
                "    print(f'Running inference, version: {config.get(\"version\")}')\n"
                "    print('Inference completed successfully.')\n"
                "    duration = time.perf_counter() - start\n"
                "    print(f'Profiled time: {duration:.4f}s')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        },
        "2026-06-27T13:10:00Z"
    )

if __name__ == "__main__":
    import sys
    setup_repo(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent)
