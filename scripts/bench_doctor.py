#!/usr/bin/env python3
"""Self-checking, credential-redacting readiness validator for quant-terminal-v1."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tomllib
from contextlib import closing
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 11)
MIN_MEMORY_BYTES = 48 * 1024**3
MIN_DISK_BYTES = 100 * 1024**3
THINKING_LEVELS = ("minimal", "low", "medium", "high", "xhigh", "max")
CREDENTIAL_RE = re.compile(r"(?i)(?:api[_-]?key|token|secret|password|authorization|bearer)")


def _result(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail if ok else _redact(detail)}


def _redact(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)\s*[=:]\s*[^\s,;]+", r"\1=<redacted>", text)
    text = re.sub(r"(?i)Bearer\s+[^\s]+", "Bearer <redacted>", text)
    return text[:500]


def host_memory_bytes() -> int:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 0


def artifact_free_bytes(path: Path) -> int:
    candidate = path
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    try:
        return int(shutil.disk_usage(candidate).free)
    except OSError:
        return 0


def _docker_check() -> tuple[bool, str]:
    docker = shutil.which("docker")
    if not docker:
        return False, "docker is not on PATH"
    try:
        proc = subprocess.run([docker, "version"], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"docker version failed: {type(exc).__name__}"
    return proc.returncode == 0, "docker client and daemon reachable" if proc.returncode == 0 else "docker daemon is unreachable"


def _read_db_values(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    values: list[dict[str, Any]] = []
    try:
        with closing(sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)) as db:
            tables = [row[0] for row in db.execute("select name from sqlite_master where type='table'")]
            for table in tables:
                cols = [row[1] for row in db.execute(f'pragma table_info("{table}")')]
                if not cols:
                    continue
                rows = db.execute(f'select * from "{table}" limit 5000').fetchall()
                values.extend([dict(zip(cols, row)) for row in rows])
    except sqlite3.Error:
        return []
    return values


def _walk_levels(value: object) -> list[str]:
    levels: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"maxlevel", "max_level", "highest", "highestthinking", "thinkingmax", "maxthinking"} and isinstance(item, str):
                if item in THINKING_LEVELS:
                    levels.append(item)
            levels.extend(_walk_levels(item))
    elif isinstance(value, list):
        for item in value:
            levels.extend(_walk_levels(item))
    elif isinstance(value, str) and value in THINKING_LEVELS:
        levels.append(value)
    return levels
def _selector_candidates(row: dict[str, Any], *, provider_id: str | None = None) -> set[str]:
    candidates: set[str] = set()
    for key in ("selector", "model", "id"):
        value = row.get(key)
        if isinstance(value, str):
            candidates.add(value)
    provider = provider_id or row.get("provider_id") or row.get("provider")
    model_id = row.get("id") or row.get("model")
    if isinstance(provider, str) and isinstance(model_id, str):
        candidates.add(f"{provider}/{model_id}")
    return candidates


def _json_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def supported_thinking_levels(selector: str, db_path: Path) -> tuple[set[str], bool]:
    """Return the exact selector's supported thinking levels from its DB."""
    levels: set[str] = set()
    matched = False
    for row in _read_db_values(db_path):
        provider_id = row.get("provider_id")
        row_matches = selector in _selector_candidates(row)
        for key in ("models", "metadata"):
            parsed = _json_value(row.get(key))
            entries = parsed if isinstance(parsed, list) else [parsed]
            for entry in entries:
                if not isinstance(entry, dict):
                    if row_matches:
                        matched = True
                    continue
                if row_matches or selector in _selector_candidates(entry, provider_id=provider_id if isinstance(provider_id, str) else None):
                    matched = True
                    levels.update(_walk_levels(entry))
        if row_matches and not any(key in row for key in ("models", "metadata")):
            matched = True
            levels.update(_walk_levels(row))
    return levels, matched


def _format_supported_levels(levels: set[str], confirmed: bool) -> str:
    if not confirmed:
        return "unavailable"
    return "none" if not levels else ",".join(level for level in THINKING_LEVELS if level in levels)


def _model_supports_thinking(selector: str, expected: str, db_path: Path) -> tuple[bool, str]:
    levels, confirmed = supported_thinking_levels(selector, db_path)
    supported = not levels if expected == "none" else expected in levels
    return confirmed and supported, _format_supported_levels(levels, confirmed)




def highest_known_thinking(selector: str, db_path: Path | None = None) -> tuple[str | None, bool]:
    if db_path is None:
        try:
            from quant_bench_runner import highest_known_thinking as query_thinking
            level = query_thinking(selector)
        except (OSError, RuntimeError, ValueError):
            return None, False
        return level, level is not None
    levels, confirmed = supported_thinking_levels(selector, db_path)
    if not confirmed:
        return None, False
    if not levels:
        return "none", True
    return max(levels, key=THINKING_LEVELS.index), True


def _manifest(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        value = tomllib.load(handle)
    if not isinstance(value, dict):
        raise ValueError("manifest must be a TOML table")
    return value


def _task_checks(manifest_path: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    official = manifest.get("task_sets", {}).get("official", [])
    results: list[dict[str, Any]] = []
    if not isinstance(official, list):
        return [_result("task manifest", False, "task_sets.official is missing")]
    for task_id in official:
        root = PROJECT_ROOT / "tasks" / str(task_id)
        ok = root.is_dir() and (root / "task.toml").is_file() and (root / "instruction.md").is_file() and (root / "workspace").is_dir()
        results.append(_result(f"task:{task_id}", ok, "required task layout" if ok else "missing task layout"))
    try:
        validator = PROJECT_ROOT / "scripts" / "validate_bench_tasks.py"
        if validator.exists():
            proc = subprocess.run([sys.executable, str(validator), str(manifest_path)], capture_output=True, text=True, timeout=60, check=False)
            results.append(_result("task validator", proc.returncode == 0, "validator passed" if proc.returncode == 0 else "validator reported failures"))
    except (OSError, subprocess.TimeoutExpired) as exc:
        results.append(_result("task validator", False, type(exc).__name__))
    return results


def _readable_without_disclosure(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            handle.read(1)
        return True
    except OSError:
        return False


def _model_checks(manifest: dict[str, Any], agent_dir: Path) -> list[dict[str, Any]]:
    rows = manifest.get("agents", [])
    db_path = agent_dir / "models.db"
    results = [
        _result("OMP config readable", _readable_without_disclosure(agent_dir / "config.yml")),
        _result("OMP models database readable", _readable_without_disclosure(db_path)),
    ]
    if not isinstance(rows, list):
        return results + [_result("manifest agents", False, "agents table is missing")]
    for row in rows:
        if not isinstance(row, dict):
            results.append(_result("agent metadata", False, "agent row is not a table"))
            continue
        selector = row.get("model")
        expected = row.get("thinking")
        if not isinstance(selector, str) or not isinstance(expected, str):
            results.append(_result("agent metadata", False, "model and thinking are required"))
            continue
        supported, observed = _model_supports_thinking(selector, expected, db_path)
        results.append(_result(f"selector:{selector}", supported, f"expected {expected}, supported {observed}"))
    return results


def _sha256(path: Path) -> str | None:
    import hashlib
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _task_image_inputs(task_id: str, task_root: Path) -> dict[str, str]:
    import hashlib
    dockerfile = task_root / "environment" / "Dockerfile"
    dockerfile_bytes = dockerfile.read_bytes()
    dockerfile_sha = hashlib.sha256(dockerfile_bytes).hexdigest()
    requirements = [
        path.read_bytes()
        for path in sorted(dockerfile.parent.glob("*requirements*"))
        if path.is_file()
    ]
    requirements_sha = hashlib.sha256(b"".join(requirements)).hexdigest() if requirements else ""
    base = ""
    for line in dockerfile_bytes.decode("utf-8").splitlines():
        if line.strip().upper().startswith("FROM "):
            base = line.strip().split(None, 1)[1]
            break
    hasher = hashlib.sha256()
    hasher.update(task_id.encode("utf-8"))
    for path in sorted(p for p in dockerfile.parent.rglob("*") if p.is_file()):
        hasher.update(str(path.relative_to(dockerfile.parent)).encode("utf-8"))
        hasher.update(path.read_bytes())
    tag = f"quant-bench-{task_id.lower()}:{hasher.hexdigest()[:16]}"
    return {
        "base": base,
        "base_digest": base.partition("@")[2],
        "dockerfile_sha256": dockerfile_sha,
        "requirements_sha256": requirements_sha,
        "tag": tag,
    }


def _image_checks(manifest: dict[str, Any], *, require_images: bool, lock_path: Path) -> list[dict[str, Any]]:
    if not lock_path.exists():
        return [_result("image locks", not require_images, "image-lock.json is missing")]
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [_result("image locks", False, "image-lock.json is unreadable")]
    entries = raw.get("tasks", raw) if isinstance(raw, dict) else {}
    if not isinstance(entries, dict):
        return [_result("image locks", False, "image lock entries are malformed")]
    checks: list[dict[str, Any]] = []
    task_paths = {
        row.get("id"): PROJECT_ROOT / str(row.get("path"))
        for row in manifest.get("tasks", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    for task_id in manifest.get("task_sets", {}).get("official", []):
        entry = entries.get(task_id)
        if not isinstance(entry, dict):
            checks.append(_result(f"image-lock:{task_id}", False, "missing task lock"))
            continue
        try:
            expected = _task_image_inputs(task_id, task_paths[task_id])
        except (KeyError, OSError, UnicodeDecodeError):
            checks.append(_result(f"image-lock:{task_id}", False, "task image inputs unreadable"))
            continue
        base = entry.get("base_image_id") or entry.get("base") or ""
        base_digest = entry.get("base_digest") or (base.partition("@")[2] if isinstance(base, str) else "")
        final = entry.get("image_id") or entry.get("final_image_id") or entry.get("final_digest")
        hashes_match = (
            base == expected["base"]
            and base_digest == expected["base_digest"]
            and entry.get("dockerfile_sha256") == expected["dockerfile_sha256"]
            and entry.get("requirements_sha256") == expected["requirements_sha256"]
            and entry.get("tag") == expected["tag"]
        )
        checks.append(_result(f"image-lock:{task_id}", hashes_match, "image inputs match lock" if hashes_match else "stale or mismatched image lock"))
        if not require_images:
            continue
        tag = entry.get("tag")
        if not isinstance(final, str) or not final:
            checks.append(_result(f"image:{task_id}", False, "final immutable image ID missing"))
            continue
        if not isinstance(tag, str) or not tag:
            checks.append(_result(f"image:{task_id}", False, "locked image tag missing"))
            continue
        docker = shutil.which("docker")
        if not docker:
            checks.append(_result(f"image:{task_id}", False, "docker client is unavailable"))
            continue
        try:
            proc = subprocess.run(
                [docker, "image", "inspect", "--format", "{{.Id}}", tag],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            checks.append(_result(f"image:{task_id}", False, "docker image tag inspect failed"))
            continue
        if proc.returncode != 0:
            checks.append(_result(f"image:{task_id}", False, "locked image tag is missing"))
            continue
        observed = proc.stdout.strip()
        if observed != final:
            checks.append(_result(f"image:{task_id}", False, f"locked tag ID mismatch: expected {final}, observed {observed or '<empty>'}"))
        else:
            checks.append(_result(f"image:{task_id}", True, "locked tag ID matches immutable image ID"))
    return checks


def run_doctor(
    manifest_path: Path,
    *,
    require_images: bool = False,
    agent_execution: str = "docker",
    verifier: str = "docker",
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(_result("python", sys.version_info[:2] >= MIN_PYTHON, f"{sys.version_info.major}.{sys.version_info.minor}"))
    needs_bwrap = agent_execution == "bwrap"
    needs_docker = agent_execution == "docker" or verifier == "docker"
    commands = ["git", "bun", "omp"]
    if needs_bwrap:
        commands.append("bwrap")
    if needs_docker:
        commands.append("docker")
    for command in commands:
        resolved = shutil.which(command)
        checks.append(_result(f"command:{command}", resolved is not None, resolved or f"{command} unavailable"))
    if needs_docker:
        docker_ok, docker_detail = _docker_check()
        checks.append(_result("docker daemon", docker_ok, docker_detail))
    memory = host_memory_bytes()
    checks.append(_result("host memory", memory >= MIN_MEMORY_BYTES, f"{memory // (1024**3)} GiB available"))
    artifact_root = PROJECT_ROOT / "artifacts"
    free = artifact_free_bytes(artifact_root)
    checks.append(_result("artifact disk", free >= MIN_DISK_BYTES, f"{free // (1024**3)} GiB free"))
    try:
        manifest = _manifest(manifest_path)
        checks.append(_result("manifest readable", True))
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        checks.append(_result("manifest readable", False, type(exc).__name__))
        return {"ok": False, "manifest": str(manifest_path), "checks": checks}
    agent_dir = Path(os.environ.get("OMP_AGENT_DIR", str(Path.home() / ".omp" / "agent"))).expanduser()
    checks.extend(_model_checks(manifest, agent_dir))
    checks.extend(_task_checks(manifest_path, manifest))
    lock = PROJECT_ROOT / "benchmarks" / "image-lock.json"
    checks.extend(_image_checks(manifest, require_images=require_images, lock_path=lock))
    return {"ok": all(item["ok"] for item in checks), "manifest": str(manifest_path), "checks": checks}




def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "benchmarks" / "quant-terminal-v1.toml")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable redacted JSON")
    parser.add_argument("--require-images", action="store_true")
    parser.add_argument("--agent-execution", choices=("host", "bwrap", "docker"), default="docker")
    parser.add_argument("--verifier", choices=("docker", "host"), default="docker")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    report = run_doctor(
        args.manifest,
        require_images=args.require_images,
        agent_execution=args.agent_execution,
        verifier=args.verifier,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for item in report["checks"]:
            print(f"{'PASS' if item['ok'] else 'FAIL'} {item['name']}: {item['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
