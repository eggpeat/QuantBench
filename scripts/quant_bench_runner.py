#!/usr/bin/env python3
"""Terminal-Bench-style Quant Bench runner.

The agent phase sees only a staged `instruction.md` and `workspace/` tree.
Hidden `tests/` and `solution/` files stay in the source task directory until
verification. Verification can run in Docker, or in a host fallback used for
local development when Docker is unavailable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import asyncio
import enum
import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

# Import/reuse the standard-library runtime metric helpers used by Quant Bench.
try:
    import omp_metrics_capture
except ImportError:
    try:
        from scripts import omp_metrics_capture
    except ImportError:
        _scripts_dir = Path(__file__).resolve().parent
        if str(_scripts_dir) not in sys.path:
            sys.path.insert(0, str(_scripts_dir))
        import omp_metrics_capture

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = PROJECT_ROOT / "tasks"
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "quant-bench-runs"
SANDBOX_RUNNER = PROJECT_ROOT / "scripts" / "sandbox_bwrap.py"
PILOT_RUN_IDS = {
    "quant-v1-pilot-sol": "completed_sol",
    "quant-v1-pilot-luna-xhigh": "completed_luna",
    "quant-v1-pilot-terra-xhigh": "completed_terra",
}

DEFAULT_TASKS = (
    "sports_hold_vig_removal",
    "odds_feed_data_merger",
    "bayesian_mcmc_rhat_diagnostic",
    "async_odds_scraper_shutdown",
    "poker_shove_fold_equity",
    "quant_var_expected_shortfall",
    "kalman_live_market_filter",
    "empirical_bayes_ctr_shrinkage",
    "sports_injury_steam_audit",
    "market_log_latency_summary",
    "sports_settlement_ledger_reconciliation",
    "sqlite_wal_odds_recovery",
    "poker_side_pot_resolution_engine",
    "stan_to_python_football_prop_model",
    "sportsbook_parlay_synthetic_risk",
    "quant_cointegration_pairs_trade",
    "empirical_bayes_true_skill",
    "sports_backtest_query_optimize",
    "llm_news_batch_scheduler",
    "data_quality_leakage_client_model",
    "kalman_2d_market_tracker",
    "range_equity_engine",
    "poker_hand_history_state_machine",
    "git_secret_alpha_purge",
)
THINKING_ORDER = ("minimal", "low", "medium", "high", "xhigh", "max")
THINKING_VALUES = {"none", "off", *THINKING_ORDER, "auto"}
DEFAULT_HOST_TOOLS = "read,write,edit,bash"
DEFAULT_SANDBOX_TOOLS = "read,write,edit"
DEFAULT_TIMEOUT_SCALE = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_ATTEMPTS = 5
DEFAULT_CONCURRENCY = 64
DEFAULT_PROGRESS_INTERVAL_SEC = 60.0
DEFAULT_LOCAL_MEMORY_BUDGET_MB = 10000
DEFAULT_TRIAL_MEMORY_RESERVE_MB = 10000

QUANT_BENCH_AGENT_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    # Public candidate listing is limited to complete 40-task, five-attempt runs.
    ("gpt-5-6-sol", "openai-codex/gpt-5.6-sol", "openai-codex"),
    ("gpt-5-6-luna", "openai-codex/gpt-5.6-luna", "openai-codex"),
    ("gpt-5-6-terra", "openai-codex/gpt-5.6-terra", "openai-codex"),
    ("swe-1-7-devin", "devin/swe-1-7", "devin"),
    ("gemini-3-5-flash-antigravity", "google-antigravity/gemini-3.5-flash", "google-antigravity"),
    ("muse-spark-1-1", "meta/muse-spark-1.1", "meta"),
)

# Reserved for future completed text-only candidates. Unfinished benchmark
# configurations are intentionally absent from the public candidate listing.
QUANT_BENCH_TEXT_ONLY_HOLDOUTS: tuple[tuple[str, str, str], ...] = ()


_OMP_MODELS_CACHE: dict[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class AgentSpec:
    name: str
    model: str
    backend_provider: str
    thinking: str
    harness: str = "OMP"

    @property
    def omp_model(self) -> str:
        base, _thinking = split_model_ref(self.model)
        return base

    @property
    def omp_thinking(self) -> str | None:
        if self.thinking in {"none", "off"}:
            return "off" if self.thinking == "off" else None
        # "max" is an OMP-native level; never alias it to xhigh.
        return self.thinking


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    root: Path
    instruction_path: Path
    workspace_path: Path
    tests_path: Path
    dockerfile_path: Path
    solution_path: Path
    agent_timeout_sec: int | None
    verifier_timeout_sec: int
    build_timeout_sec: int
    cpus: int = 1
    memory_mb: int = 1024
    requires_image: bool = False
    promotion_status: str = "unknown"
    source_status: str = "unknown"

class FailureCode(str, enum.Enum):
    NONE = "NONE"
    DOCKER_BUILD = "DOCKER_BUILD"
    DOCKER_LAUNCH = "DOCKER_LAUNCH"
    MODEL_METADATA = "MODEL_METADATA"
    GATEWAY_UNAVAILABLE = "GATEWAY_UNAVAILABLE"
    PROVIDER_AUTH = "PROVIDER_AUTH"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_TRANSPORT = "PROVIDER_TRANSPORT"
    AGENT_HARNESS_EXIT = "AGENT_HARNESS_EXIT"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"
    VERIFIER_TIMEOUT = "VERIFIER_TIMEOUT"
    VERIFIER_REJECT = "VERIFIER_REJECT"


def _failure_value(value: FailureCode | str | None) -> str:
    if isinstance(value, FailureCode):
        return value.value
    return str(value or FailureCode.NONE.value)


@dataclass
class CommandResult:
    returncode: int
    timeout: bool
    elapsed_sec: float
    stdout: str
    stderr: str
    cmd: list[str]
    failure_code: FailureCode | str = FailureCode.NONE
    message_end: bool = False
    capture: dict[str, Any] | None = None



@dataclass
class AttemptResult:
    ts: str
    run_id: str
    task_id: str
    agent: str
    name: str
    model: str
    backend_provider: str
    thinking: str
    harness: str
    agent_execution: str
    verifier_backend: str
    passed: bool
    status: str
    reason: str
    attempt_dir: str
    agent_returncode: int | None
    verifier_returncode: int | None
    agent_timeout: bool
    verifier_timeout: bool
    agent_elapsed_sec: float
    verifier_elapsed_sec: float
    agent_stdout: str
    agent_stderr: str
    verifier_stdout: str
    verifier_stderr: str
    agent_cmd: list[str]
    verifier_cmd: list[str]
    attempt_count: int
    max_retries: int
    runtime_metrics: dict[str, Any] | None = None
    attempt_number: int = 1
    total_attempts: int = 1
    result_id: str = ""
    supersedes_result_id: str | None = None
    rerun: int = 0
    failure_code: str = FailureCode.NONE.value
    image_id: str = ""
    image_tag: str = ""
    base_image_id: str = ""
    dockerfile_sha256: str = ""
    requirements_sha256: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def path_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug or "item"


def compact_text(value: str, limit: int = 4000) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[:limit] + f"... [truncated {len(value) - limit} chars]"


def run_cmd(cmd: list[str], *, cwd: Path, timeout: int | None, env: dict[str, str] | None = None) -> CommandResult:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=env,
        )
        return CommandResult(
            returncode=int(proc.returncode),
            timeout=False,
            elapsed_sec=round(time.monotonic() - start, 3),
            stdout=proc.stdout,
            stderr=proc.stderr,
            cmd=cmd,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            returncode=124,
            timeout=True,
            elapsed_sec=round(time.monotonic() - start, 3),
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
            cmd=cmd,
            failure_code=FailureCode.VERIFIER_TIMEOUT,
        )
def _tail_text(path: Path, limit: int = 4000) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - limit))
        return handle.read().decode("utf-8", errors="replace")


def run_omp_cmd(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int | None,
    capture_dir: Path,
    env: dict[str, str] | None = None,
    timeout_cleanup: Callable[[], None] | None = None,
) -> CommandResult:
    """Run OMP with file-backed output so long JSON sessions are never buffered."""
    stdout_path = capture_dir / "agent-stdout.jsonl"
    stderr_path = capture_dir / "agent-stderr.log"
    start = time.monotonic()
    timed_out = False
    returncode = 124
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                text=True,
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=timeout,
                env=env,
            )
            returncode = int(proc.returncode)
        except subprocess.TimeoutExpired:
            timed_out = True
            if timeout_cleanup is not None:
                timeout_cleanup()

    elapsed_sec = round(time.monotonic() - start, 3)
    capture: dict[str, Any] = {
        "stdout": "",
        "stderr": _tail_text(stderr_path),
        "returncode": returncode,
        "elapsed_sec": elapsed_sec,
        "omp_stdout_path": str(stdout_path),
        "omp_stderr_path": str(stderr_path),
    }
    omp_metrics_capture.capture_omp_json_file(capture, stdout_path)
    capture["omp_stdout_char_count"] = len(str(capture.get("stdout") or ""))
    capture["stdout"] = compact_text(str(capture.get("stdout") or ""))
    capture["stderr"] = compact_text(str(capture.get("stderr") or ""))
    if "omp_error_message" in capture:
        capture["omp_error_message"] = compact_text(str(capture["omp_error_message"]))
    result = CommandResult(
        returncode=int(capture["returncode"]),
        timeout=timed_out,
        elapsed_sec=elapsed_sec,
        stdout=str(capture.get("stdout") or ""),
        stderr=str(capture.get("stderr") or ""),
        cmd=cmd,
        failure_code=FailureCode.AGENT_TIMEOUT if timed_out else FailureCode.NONE,
        capture=capture,
    )
    failure, message_end = _parse_omp_event_lines(
        omp_metrics_capture.iter_omp_jsonl_file(stdout_path)
    )
    result.failure_code = FailureCode.AGENT_TIMEOUT if timed_out else failure
    result.message_end = message_end
    return classify_omp_result(result)


def load_toml(path: Path) -> dict[str, Any]:
    import tomllib

    with path.open("rb") as handle:
        parsed = tomllib.load(handle)
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a TOML object")
    return parsed

_MANIFEST_CACHE: dict[str, Any] | None = None
_MANIFEST_PATH: Path | None = None


def load_benchmark_manifest(path: str | Path) -> dict[str, Any]:
    """Load and validate the versioned benchmark manifest."""
    manifest_path = Path(path).expanduser().resolve()
    data = load_toml(manifest_path)
    if str(data.get("schema_version", "")) != "1.0":
        raise ValueError(f"unsupported benchmark schema_version in {manifest_path}")
    tasks = data.get("tasks", [])
    agents = data.get("agents", [])
    if not isinstance(tasks, list) or not isinstance(agents, list):
        raise ValueError("manifest requires [[tasks]] and [[agents]] rows")
    task_ids = [str(row.get("id", "")) for row in tasks if isinstance(row, dict)]
    agent_names = [str(row.get("name", "")) for row in agents if isinstance(row, dict)]
    if any(not item for item in task_ids + agent_names):
        raise ValueError("manifest task/agent rows require nonempty ids")
    if len(task_ids) != len(set(task_ids)) or len(agent_names) != len(set(agent_names)):
        raise ValueError("manifest task and agent names must be unique")
    for row in tasks:
        if isinstance(row, dict):
            _validated_repository_task_root(str(row.get("id", "")), row.get("path"))
    for section in ("task_sets", "agent_sets"):
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"manifest [{section}] must be a table")
        declared = set(task_ids if section == "task_sets" else agent_names)
        for set_name, members in values.items():
            if not isinstance(members, list) or len(members) != len(set(members)):
                raise ValueError(f"manifest {section}.{set_name} must be a unique list")
            unknown = sorted(set(map(str, members)) - declared)
            if unknown:
                raise ValueError(f"manifest {section}.{set_name} references unknown rows: {unknown}")
    return data


def manifest_task_rows(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in manifest.get("tasks", []) if isinstance(row, dict) and row.get("id")}


def manifest_agents(manifest: dict[str, Any], agent_set: str | None = None) -> list[AgentSpec]:
    rows = {str(row["name"]): row for row in manifest.get("agents", []) if isinstance(row, dict) and row.get("name")}
    names = list(rows)
    if agent_set is not None:
        names = [str(name) for name in manifest.get("agent_sets", {}).get(agent_set, [])]
        if agent_set not in manifest.get("agent_sets", {}):
            raise ValueError(f"unknown manifest agent set: {agent_set}")
    result = []
    for name in names:
        row = rows[name]
        result.append(AgentSpec(
            name=name,
            model=str(row["model"]),
            backend_provider=str(row["backend_provider"]),
            thinking=str(row["thinking"]),
            harness=str(row.get("harness", "OMP")),
        ))
    return result


def manifest_task_ids(manifest: dict[str, Any], task_set: str | None = None) -> list[str]:
    rows = manifest_task_rows(manifest)
    if task_set is None:
        return list(rows)
    sets = manifest.get("task_sets", {})
    if task_set not in sets:
        raise ValueError(f"unknown manifest task set: {task_set}")
    names = [str(value) for value in sets[task_set]]
    unknown = sorted(set(names) - set(rows))
    if unknown:
        raise ValueError(f"manifest task set references unknown rows: {unknown}")
    return names


def _validated_repository_task_root(task_id: str, raw_path: str | Path | None = None) -> Path:
    task_path = Path(task_id)
    if not task_id or task_path.is_absolute() or ".." in task_path.parts:
        raise ValueError(f"manifest task root is unsafe for {task_id!r}")
    expected_lexical = TASKS_DIR / task_path
    expected_root = expected_lexical.resolve(strict=False)
    canonical_expected = PROJECT_ROOT / "tasks" / task_path
    if expected_root != canonical_expected:
        raise ValueError(f"manifest task root escapes repository tasks/{task_id}")
    if raw_path is None:
        candidate = expected_lexical
    else:
        candidate = Path(str(raw_path))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"manifest task root is unsafe for {task_id!r}")
        candidate = PROJECT_ROOT / candidate
    candidate_root = candidate.resolve(strict=False)
    if candidate_root != expected_root:
        raise ValueError(f"manifest task root must equal repository tasks/{task_id}")
    return expected_root


def task_spec_from_manifest(task_id: str, manifest: dict[str, Any]) -> TaskSpec:
    row = manifest_task_rows(manifest).get(task_id)
    raw_path = row.get("path") if row is not None else None
    root = _validated_repository_task_root(task_id, raw_path)
    return task_spec(task_id, root=root)


def task_spec(task_id: str, *, root: Path | None = None) -> TaskSpec:
    root = (root or (TASKS_DIR / task_id)).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"unknown task: {task_id}")
    metadata = load_toml(root / "task.toml")
    raw_task = metadata.get("task", {}) if isinstance(metadata.get("task"), dict) else {}
    raw_agent = metadata.get("agent", {}) if isinstance(metadata.get("agent"), dict) else {}
    raw_verifier = metadata.get("verifier", {}) if isinstance(metadata.get("verifier"), dict) else {}
    raw_environment = metadata.get("environment", {}) if isinstance(metadata.get("environment"), dict) else {}
    raw_metadata = metadata.get("metadata", {}) if isinstance(metadata.get("metadata"), dict) else {}
    agent_timeout = raw_agent.get("timeout_sec")
    verifier_timeout = raw_verifier.get("timeout_sec", 600)
    build_timeout = raw_environment.get("build_timeout_sec", 600)
    cpus = int(math.ceil(float(raw_environment.get("cpus", 1))))
    memory_mb = int(math.ceil(float(raw_environment.get("memory_mb", 1024))))

    requires_image = raw_task.get("requires_image", False)
    if isinstance(requires_image, str):
        requires_image = requires_image.lower() == "true"
    else:
        requires_image = bool(requires_image)

    promotion_status = str(raw_metadata.get("promotion_status", "unknown")).strip().lower()
    source_status = str(raw_metadata.get("source_status", "unknown")).strip().lower()

    agent_timeout_sec = None if agent_timeout is None else max(1, math.ceil(float(agent_timeout)))
    verifier_timeout_sec = max(1, math.ceil(float(verifier_timeout)))

    return TaskSpec(
        task_id=task_id,
        root=root,
        instruction_path=root / "instruction.md",
        workspace_path=root / "workspace",
        tests_path=root / "tests",
        dockerfile_path=root / "environment" / "Dockerfile",
        solution_path=root / "solution" / "solve.py",
        agent_timeout_sec=agent_timeout_sec,
        verifier_timeout_sec=verifier_timeout_sec,
        build_timeout_sec=max(1, math.ceil(float(build_timeout))),
        cpus=cpus,
        memory_mb=memory_mb,
        requires_image=requires_image,
        promotion_status=promotion_status,
        source_status=source_status,
    )


def split_model_ref(model: str) -> tuple[str, str | None]:
    base, sep, suffix = model.rpartition(":")
    if sep and suffix in THINKING_VALUES and base:
        return base, suffix
    return model, None


def infer_backend_provider(model: str) -> str:
    base, _thinking = split_model_ref(model)
    provider, sep, _rest = base.partition("/")
    return provider if sep and provider else "unknown"


def infer_thinking(model: str) -> str:
    _base, thinking = split_model_ref(model)
    return thinking or "max"


def model_lookup_key(model: str) -> str:
    base, _thinking = split_model_ref(model)
    _provider, sep, model_id = base.partition("/")
    return model_id if sep else base


def _load_omp_models_cache(timeout: int = 20) -> dict[str, dict[str, Any]]:
    global _OMP_MODELS_CACHE
    if _OMP_MODELS_CACHE is not None:
        return _OMP_MODELS_CACHE
    _OMP_MODELS_CACHE = {}
    try:
        completed = subprocess.run(
            ["omp", "models", "--json"],
            cwd=PROJECT_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        if completed.returncode == 0:
            parsed = json.loads(completed.stdout)
            models = parsed.get("models") if isinstance(parsed, dict) else None
            if isinstance(models, list):
                for item in models:
                    if isinstance(item, dict) and "selector" in item:
                        _OMP_MODELS_CACHE[item["selector"]] = item
    except Exception:
        pass
    return _OMP_MODELS_CACHE


def candidate_tuples_for_slate(slate: str) -> tuple[tuple[str, str, str], ...]:
    if slate == "text-compatible":
        return QUANT_BENCH_AGENT_CANDIDATES + QUANT_BENCH_TEXT_ONLY_HOLDOUTS
    if slate == "multimodal":
        return QUANT_BENCH_AGENT_CANDIDATES
    raise ValueError(f"unsupported agent slate {slate!r}")


def get_agent_candidates(thinking_resolver=None, slate: str = "multimodal") -> list[dict[str, Any]]:
    if thinking_resolver is None:
        thinking_resolver = highest_known_thinking
    candidates = candidate_tuples_for_slate(slate)
    rows = []
    for name, model, backend_provider in candidates:
        rows.append({
            "name": name,
            "model": model,
            "backend_provider": backend_provider,
            "thinking": thinking_resolver(model),
            "harness": "OMP",
        })
    return rows

def highest_known_thinking(model: str, timeout: int = 20) -> str | None:
    """Resolve the exact selector's highest supported level.

    ``None`` is returned when metadata is unavailable; callers that are about
    to launch a live wave must fail closed rather than silently selecting a
    neighboring route.
    """
    base, _thinking = split_model_ref(model)
    cache = _load_omp_models_cache(timeout=timeout)
    selected = cache.get(base)
    if selected is None:
        query = model_lookup_key(model)
        try:
            completed = subprocess.run(
                ["omp", "models", "find", query, "--json"],
                cwd=PROJECT_ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
        models = parsed.get("models") if isinstance(parsed, dict) else None
        if not isinstance(models, list):
            return None
        selected = next((item for item in models if isinstance(item, dict) and item.get("selector") == base), None)
        if selected is None:
            raise RuntimeError(f"OMP model metadata not found for exact selector: {base}")
    raw_supported = selected.get("thinking") if isinstance(selected, dict) else None
    if raw_supported is None or raw_supported == []:
        return "none"
    if isinstance(raw_supported, str):
        raw_supported = [raw_supported]
    supported = [value for value in raw_supported if value in THINKING_ORDER]
    if not supported:
        return "none"
    rank = {value: index for index, value in enumerate(THINKING_ORDER)}
    return max(supported, key=lambda value: rank[value])


def with_max_thinking(agent: AgentSpec) -> AgentSpec:
    if agent.harness != "OMP":
        return agent
    level = highest_known_thinking(agent.model)
    if level is None:
        raise RuntimeError(f"OMP metadata unavailable for exact selector: {agent.omp_model}")
    return AgentSpec(
        name=agent.name,
        model=agent.omp_model,
        backend_provider=agent.backend_provider,
        thinking=level,
        harness=agent.harness,
    )


def slug_model_name(model: str) -> str:
    base, thinking = split_model_ref(model)
    provider, sep, model_id = base.partition("/")
    name = model_id if sep else base
    if thinking:
        name = f"{name}-{thinking}"
    return path_slug(name)


def resolve_agent_by_name(name_or_model: str) -> tuple[str, str, str] | None:
    for row in candidate_tuples_for_slate("text-compatible"):
        if row[0] == name_or_model:
            return row
    return None


def is_text_only_agent(agent: AgentSpec) -> bool:
    base_model, _ = split_model_ref(agent.model)
    for h_name, h_model, _ in QUANT_BENCH_TEXT_ONLY_HOLDOUTS:
        h_base, _ = split_model_ref(h_model)
        if agent.name == h_name or base_model == h_base:
            return True
    return False


def parse_agent(value: str) -> AgentSpec:
    """Parse NAME=MODEL[,backend=...][,thinking=...][,harness=...]."""
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("empty --agent")
    first = parts[0]

    resolved = None
    if "=" in first:
        name, model_or_name = first.split("=", 1)
        name = name.strip()
        model_or_name = model_or_name.strip()
        resolved = resolve_agent_by_name(model_or_name)
    else:
        model_or_name = first
        resolved = resolve_agent_by_name(model_or_name)

    if resolved:
        c_name, c_model, c_provider = resolved
        name = name if ("=" in first and name) else c_name
        model = c_model
        default_provider = c_provider
    else:
        if "=" in first:
            name, model = first.split("=", 1)
            name = name.strip() or slug_model_name(model)
        else:
            model = first
            name = slug_model_name(model)
        default_provider = infer_backend_provider(model)

    metadata: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            raise ValueError(f"agent metadata must be key=value: {part!r}")
        key, item = part.split("=", 1)
        metadata[key.strip().replace("-", "_")] = item.strip()
    thinking = metadata.get("thinking", infer_thinking(model))
    if thinking not in THINKING_VALUES:
        raise ValueError(f"unsupported thinking value {thinking!r}; expected one of {sorted(THINKING_VALUES)}")
    return AgentSpec(
        name=path_slug(name),
        model=model.strip(),
        backend_provider=metadata.get("backend", metadata.get("backend_provider", default_provider)),
        thinking=thinking,
        harness=metadata.get("harness", "OMP"),
    )


def copy_public_task_view(task: TaskSpec, attempt_dir: Path) -> None:
    if attempt_dir.exists():
        shutil.rmtree(attempt_dir)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(task.instruction_path, attempt_dir / "instruction.md")
    shutil.copytree(task.workspace_path, attempt_dir / "workspace", symlinks=True)
    (attempt_dir / "workspace" / "outputs").mkdir(exist_ok=True)
def _parse_omp_event_lines(lines: Iterable[str]) -> tuple[FailureCode, bool]:
    """Parse structured OMP JSON events incrementally."""
    failure = FailureCode.NONE
    message_end = False
    for raw in lines:
        try:
            event = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or event.get("event") or "").lower()
        payload = event.get("data") if isinstance(event.get("data"), dict) else event
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        terminal: dict[str, Any] | None = None
        if event_type in {"message_end", "assistant_message_end"}:
            terminal = message or payload
        elif event_type == "agent_end":
            messages = event.get("messages")
            if isinstance(messages, list):
                for item in messages:
                    if isinstance(item, dict) and item.get("role") == "assistant":
                        terminal = item
        elif (
            event_type == "agent_end_oversize"
            and event.get("stopReason") in {"error", "failed", "aborted"}
        ):
            terminal = event
        elif event_type == "oversize_json_event":
            message_end = False
            failure = FailureCode.AGENT_HARNESS_EXIT
        if terminal is not None:
            role = terminal.get("role")
            stop_reason = str(terminal.get("stopReason") or "").lower()
            if role in (None, "assistant") and stop_reason in {"stop", "end_turn", "complete", "completed"}:
                message_end = True
                failure = FailureCode.NONE
            elif stop_reason in {"error", "failed", "aborted"}:
                message_end = False
                failure = FailureCode.AGENT_HARNESS_EXIT
            else:
                message_end = False
        text_parts: list[str] = []
        for obj in (payload, message, event):
            if not isinstance(obj, dict):
                continue
            for key in ("error", "code", "message", "type", "errorMessage"):
                value = obj.get(key)
                if isinstance(value, (str, int, float)):
                    text_parts.append(str(value)[:1000])
            error = obj.get("error")
            if isinstance(error, dict):
                for key in ("code", "message", "type", "errorMessage"):
                    value = error.get(key)
                    if isinstance(value, (str, int, float)):
                        text_parts.append(str(value)[:1000])
        lower = " ".join(text_parts).lower()
        if "gateway" in event_type and any(token in lower for token in ("unavailable", "refused", "missing", "socket")):
            failure = FailureCode.GATEWAY_UNAVAILABLE
            message_end = False
        if "429" in lower or "rate_limit" in lower or "rate limit" in lower:
            failure = FailureCode.PROVIDER_RATE_LIMIT
            message_end = False
        elif any(token in lower for token in ("authentication", "unauthorized", "invalid_api_key", "provider_auth")):
            message_end = False
            failure = FailureCode.PROVIDER_AUTH
        elif any(token in lower for token in ("transport", "connection", "network_error")):
            message_end = False
            failure = FailureCode.PROVIDER_TRANSPORT
    return failure, message_end


def parse_omp_events(stdout: str) -> tuple[FailureCode, bool]:
    """Parse structured OMP JSON events from an in-memory compatibility path."""
    return _parse_omp_event_lines((stdout or "").splitlines())

def classify_omp_result(result: CommandResult) -> CommandResult:
    parsed_failure, parsed_message_end = parse_omp_events(result.stdout)
    failure = parsed_failure
    message_end = parsed_message_end or result.message_end
    if failure == FailureCode.NONE and _failure_value(result.failure_code) != FailureCode.NONE.value:
        failure = FailureCode(_failure_value(result.failure_code))
    if result.timeout:
        failure = FailureCode.AGENT_TIMEOUT
    elif message_end:
        # OMP may recover from a transient provider error and still emit a
        # successful terminal assistant message. The completed model result,
        # not an earlier retry event, determines whether verification runs.
        failure = FailureCode.NONE
    elif failure == FailureCode.NONE and result.returncode != 0:
        diagnostic = "\n".join((
            result.stderr or "",
            str((result.capture or {}).get("omp_error_message") or ""),
        )).lower()
        if "429" in diagnostic or "rate_limit" in diagnostic or "rate limit" in diagnostic:
            failure = FailureCode.PROVIDER_RATE_LIMIT
        elif any(token in diagnostic for token in (
            "unable to connect",
            "connection error",
            "network error",
            "network_error",
            "typo in the url or port",
        )):
            failure = FailureCode.PROVIDER_TRANSPORT
        else:
            failure = FailureCode.AGENT_HARNESS_EXIT
    result.failure_code = failure
    result.message_end = message_end
    return result


def agent_model_ref(agent: AgentSpec) -> str:
    """Return the exact OMP selector, including an active thinking suffix."""
    return f"{agent.omp_model}:{agent.omp_thinking}" if agent.omp_thinking else agent.omp_model


def prepare_docker_fake_home(attempt_dir: Path, agent: AgentSpec, gateway_socket: Path | None) -> Path:
    fake_home = attempt_dir / ".docker-agent-home"
    if fake_home.exists():
        shutil.rmtree(fake_home)
    agent_dir = fake_home / ".omp" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "config.yml").write_text("telemetry: false\n", encoding="utf-8")
    sandbox_spec = importlib.util.spec_from_file_location("bench_sandbox_bwrap", SANDBOX_RUNNER)
    if sandbox_spec is None or sandbox_spec.loader is None:
        raise RuntimeError("cannot load sandbox metadata helpers")
    sandbox_module = importlib.util.module_from_spec(sandbox_spec)
    sandbox_spec.loader.exec_module(sandbox_module)
    provider = agent.backend_provider or infer_backend_provider(agent.model)
    endpoint = "http://127.0.0.1:8765" if gateway_socket else "http://127.0.0.1:1"
    model_ref = agent_model_ref(agent)
    sandbox_module.copy_model_cache(
        sandbox_module.HOST_AGENT_DIR,
        agent_dir,
        allowed_providers={provider},
        allowed_model_ref=model_ref,
    )
    (agent_dir / "models.yml").write_text(
        sandbox_module.gateway_models_yml(endpoint, [provider], model_ref=model_ref), encoding="utf-8"
    )
    (fake_home / "gateway_socket_proxy.py").write_text(
        "from pathlib import Path\n"
        f"exec(compile(Path({str(PROJECT_ROOT / 'scripts' / 'gateway_socket_proxy.py')!r}).read_text(), "
        f"{str(PROJECT_ROOT / 'scripts' / 'gateway_socket_proxy.py')!r}, 'exec'))\n",
        encoding="utf-8",
    )
    os.chmod(fake_home / "gateway_socket_proxy.py", 0o644)
    for path in (fake_home, agent_dir):
        try:
            os.chown(path, os.getuid(), os.getgid())
        except PermissionError:
            pass
    return fake_home


def _docker_runtime_root() -> Path:
    packaged = Path.home() / ".bun" / "install" / "global" / "node_modules"
    if (packaged / "@oh-my-pi" / "pi-coding-agent" / "dist" / "cli.js").is_file():
        return packaged
    omp = shutil.which("omp")
    if omp:
        resolved = Path(omp).resolve()
        if resolved.parent.name == "bin":
            return resolved.parent.parent
    return Path(sys.executable).resolve().parent.parent


_IMAGE_METADATA: dict[str, dict[str, str]] = {}
IMAGE_LABEL_PREFIX = "org.quant-bench"


def _image_labels(metadata: dict[str, str]) -> dict[str, str]:
    return {
        f"{IMAGE_LABEL_PREFIX}.dockerfile-sha256": metadata.get("dockerfile_sha256", ""),
        f"{IMAGE_LABEL_PREFIX}.requirements-sha256": metadata.get("requirements_sha256", ""),
        f"{IMAGE_LABEL_PREFIX}.base-image": metadata.get("base_image", ""),
    }


def ensure_task_image(task: TaskSpec) -> tuple[str, str, CommandResult | None]:
    """Build once and return ``(mutable local tag, immutable image id, result)``."""
    docker = shutil.which("docker")
    metadata = task_image_hashes(task)
    if task.dockerfile_path.exists():
        for line in task.dockerfile_path.read_text(encoding="utf-8").splitlines():
            if line.strip().upper().startswith("FROM "):
                metadata["base_image"] = line.split()[1]
                break
    if docker is None:
        return docker_image_tag(task), "", CommandResult(
            127, False, 0.0, "", "docker executable not found", [], FailureCode.DOCKER_BUILD
        )
    local_tag = docker_image_tag(task)
    expected_labels = _image_labels(metadata)
    inspect = run_cmd(
        [docker, "image", "inspect", local_tag, "--format", "{{json .Config.Labels}}"],
        cwd=PROJECT_ROOT,
        timeout=30,
    )
    cached_labels: dict[str, Any] = {}
    if inspect.returncode == 0 and inspect.stdout.strip():
        try:
            parsed_labels = json.loads(inspect.stdout)
            if isinstance(parsed_labels, dict):
                cached_labels = parsed_labels
        except json.JSONDecodeError:
            cached_labels = {}
    if cached_labels and all(cached_labels.get(key) == value for key, value in expected_labels.items()):
        cached_id = run_cmd(
            [docker, "image", "inspect", local_tag, "--format", "{{.Id}}"],
            cwd=PROJECT_ROOT,
            timeout=30,
        )
        if cached_id.returncode == 0 and cached_id.stdout.strip():
            image_id = cached_id.stdout.strip()
            _IMAGE_METADATA[task.task_id] = {**metadata, "image_id": image_id}
            return local_tag, image_id, None
    label_args = [item for key, value in expected_labels.items() for item in ("--label", f"{key}={value}")]
    build = run_cmd(
        [docker, "build", "-q", *label_args, "-f", str(task.dockerfile_path), "-t", local_tag, str(task.dockerfile_path.parent)],
        cwd=PROJECT_ROOT,
        timeout=task.build_timeout_sec,
    )
    if build.returncode != 0 or build.timeout:
        build.failure_code = FailureCode.DOCKER_BUILD
        return local_tag, "", build
    inspected = run_cmd([docker, "image", "inspect", local_tag, "--format", "{{.Id}}"], cwd=PROJECT_ROOT, timeout=30)
    if inspected.returncode != 0 or not inspected.stdout.strip():
        inspected.failure_code = FailureCode.DOCKER_BUILD
        return local_tag, "", inspected
    image_id = inspected.stdout.strip()
    _IMAGE_METADATA[task.task_id] = {**metadata, "image_id": image_id}
    return local_tag, image_id, build


def _docker_resource_flags(task: TaskSpec) -> list[str]:
    return [
        "--pids-limit", "100",
        "--memory", f"{task.memory_mb}m",
        "--cpus", str(task.cpus),
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
    ]


def _docker_read_only_flags(*, include_run: bool = False) -> list[str]:
    flags = ["--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m"]
    if include_run:
        flags.extend(["--tmpfs", "/run:rw,nosuid,nodev,size=16m"])
    return flags


def _force_remove_docker_container(docker: str, cidfile: Path) -> None:
    try:
        container_id = cidfile.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if not container_id:
        return
    try:
        subprocess.run(
            [docker, "rm", "-f", container_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_docker_agent(
    agent: AgentSpec,
    task: TaskSpec,
    attempt_dir: Path,
    *,
    image_id: str,
    tools: str,
    auth_gateway_socket: Path | None,
    timeout_scale: float,
) -> CommandResult:
    docker = shutil.which("docker")
    if docker is None:
        return CommandResult(127, False, 0.0, "", "docker executable not found", [], FailureCode.DOCKER_LAUNCH)
    timeout = None if task.agent_timeout_sec is None else max(1, math.ceil(task.agent_timeout_sec * timeout_scale))
    fake_home = prepare_docker_fake_home(attempt_dir, agent, auth_gateway_socket)
    cidfile = attempt_dir / "agent-container.cid"
    cidfile.unlink(missing_ok=True)
    runtime = _docker_runtime_root()
    omp_cmd = omp_command(agent, task_prompt(task), tools, max_time=timeout)
    bun = shutil.which("bun")
    packaged_cli = runtime / "@oh-my-pi" / "pi-coding-agent" / "dist" / "cli.js"
    if packaged_cli.is_file():
        if bun is None:
            return CommandResult(127, False, 0.0, "", "bun executable not found", [], FailureCode.DOCKER_LAUNCH)
        omp_cmd[0:1] = ["/usr/local/bin/bun", "/opt/node_modules/@oh-my-pi/pi-coding-agent/dist/cli.js"]
    command = "umask 0022; exec " + " ".join(shlex_quote(item) for item in omp_cmd)
    if auth_gateway_socket:
        command = (
            "umask 0022; exec python /home/agent/gateway_socket_proxy.py run-tcp "
            "--socket /run/omp-auth-gateway.sock --listen 127.0.0.1:8765 "
            f"--model-selector {shlex_quote(agent_model_ref(agent))} -- sh -c "
            + shlex_quote(command)
        )
    cmd = [
        docker, "run", "--rm", "--cidfile", str(cidfile), "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        *_docker_read_only_flags(include_run=auth_gateway_socket is not None),
        *_docker_resource_flags(task),
        "-e", "HOME=/home/agent", "-e", "PATH=/opt/omp-runtime/bin:/usr/local/bin:/usr/bin:/bin",
        "-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1", "-e", "MKL_NUM_THREADS=1",
        "-v", f"{attempt_dir / 'workspace'}:/workspace",
        "-v", f"{fake_home}:/home/agent",
        "-v", f"{runtime}:/opt/node_modules:ro",
        "-v", f"{PROJECT_ROOT / 'scripts' / 'gateway_socket_proxy.py'}:/home/agent/gateway_socket_proxy.py:ro",
    ]
    if bun is not None and packaged_cli.is_file():
        cmd.extend(["-v", f"{bun}:/usr/local/bin/bun:ro"])
    if auth_gateway_socket:
        cmd.extend(["-v", f"{auth_gateway_socket}:/run/omp-auth-gateway.sock"])
    cmd.extend(["--entrypoint", "sh", image_id, "-c", command])
    return run_omp_cmd(
        cmd,
        cwd=PROJECT_ROOT,
        timeout=(timeout + 45 if timeout is not None else None),
        capture_dir=attempt_dir,
        timeout_cleanup=lambda: _force_remove_docker_container(docker, cidfile),
    )


def shlex_quote(value: str) -> str:
    import shlex
    return shlex.quote(value)


def run_docker_oracle(task: TaskSpec, attempt_dir: Path, *, image_id: str, timeout_scale: float) -> CommandResult:
    docker = shutil.which("docker")
    if docker is None:
        return CommandResult(127, False, 0.0, "", "docker executable not found", [], FailureCode.DOCKER_LAUNCH)
    solution = task.solution_path if task.solution_path.exists() else task.root / "solution" / "solve.sh"
    if not solution.exists():
        return CommandResult(2, False, 0.0, "", "missing solution", [], FailureCode.DOCKER_LAUNCH)
    workspace = attempt_dir / "workspace"
    cidfile = attempt_dir / "oracle-container.cid"
    cidfile.unlink(missing_ok=True)
    timeout = None if task.agent_timeout_sec is None else max(1, math.ceil(task.agent_timeout_sec * timeout_scale))
    suffix = solution.suffix.lower()
    entry = ["python", "/solution/solve.py", "/workspace"] if suffix == ".py" else ["bash", "/solution/solve.sh", "/workspace"]
    entry_command = "umask 0022; exec " + " ".join(shlex_quote(item) for item in entry)
    cmd = [
        docker, "run", "--rm", "--cidfile", str(cidfile), "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        *_docker_read_only_flags(),
        *_docker_resource_flags(task), "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1", "-e", "MKL_NUM_THREADS=1",
        "-v", f"{workspace}:/workspace", "-v", f"{solution}:/solution/{solution.name}:ro",
        "-w", "/workspace", "--entrypoint", "sh", image_id, "-c", entry_command,
    ]
    result = run_cmd(cmd, cwd=PROJECT_ROOT, timeout=(timeout + 45 if timeout is not None else None))
    if result.timeout:
        _force_remove_docker_container(docker, cidfile)
        result.failure_code = FailureCode.AGENT_TIMEOUT
    return result


def run_oracle_solution(task: TaskSpec, attempt_dir: Path) -> CommandResult:
    workspace = attempt_dir / "workspace"
    if task.solution_path.exists():
        result = run_cmd([sys.executable, str(task.solution_path), str(workspace)], cwd=attempt_dir, timeout=task.agent_timeout_sec)
        if result.timeout:
            result.failure_code = FailureCode.AGENT_TIMEOUT
        return result
    shell_solution = task.root / "solution" / "solve.sh"
    if shell_solution.exists():
        result = run_cmd(["bash", str(shell_solution), str(workspace)], cwd=attempt_dir, timeout=task.agent_timeout_sec)
        if result.timeout:
            result.failure_code = FailureCode.AGENT_TIMEOUT
        return result
    return CommandResult(2, False, 0.0, "", f"missing solution for {task.task_id}", [])


def task_prompt(task: TaskSpec) -> str:
    instruction = task.instruction_path.read_text(encoding="utf-8")
    return textwrap.dedent(
        f"""
        You are solving Quant Bench task `{task.task_id}` in a Terminal-Bench-style sandbox.

        Visible files:
        - `instruction.md`: the task instructions.
        - `workspace/`: the only candidate workspace. Edit files only under `workspace/`.

        Hidden from you: `tests/`, `tests/expected.json`, and `solution/`.
        Do not look for hidden tests or reference solutions. Implement the requested code and outputs from the instructions and visible fixtures only.

        Task instructions:
        {instruction}
        """
    ).strip()


def omp_command(agent: AgentSpec, prompt: str, tools: str, max_time: int | None = None) -> list[str]:
    cmd = ["omp", "--no-session", "--auto-approve", "--model", agent.omp_model, "--mode", "json"]
    if agent.omp_thinking:
        cmd.extend(["--thinking", agent.omp_thinking])
    if max_time is not None:
        cmd.extend(["--max-time", str(max_time)])
    if tools:
        cmd.extend(["--tools", tools])
    else:
        cmd.append("--no-tools")
    cmd.extend(["-p", prompt])
    return cmd


def run_omp_agent(
    agent: AgentSpec,
    task: TaskSpec,
    attempt_dir: Path,
    *,
    execution: str,
    tools: str,
    auth_gateway_url: str | None,
    timeout_scale: float,
) -> CommandResult:
    prompt = task_prompt(task)
    timeout = None if task.agent_timeout_sec is None else max(1, math.ceil(task.agent_timeout_sec * timeout_scale))
    cmd = omp_command(agent, prompt, tools, max_time=timeout)
    if execution == "host":
        return run_omp_cmd(cmd, cwd=attempt_dir, timeout=timeout, capture_dir=attempt_dir)
    if execution != "bwrap":
        raise ValueError(f"unknown agent execution: {execution}")
    sandbox_root = attempt_dir.parent / f".sandbox-{attempt_dir.name}"
    if sandbox_root.exists():
        shutil.rmtree(sandbox_root)
    sandbox_cmd = [
        sys.executable,
        str(SANDBOX_RUNNER),
        "--workspace",
        str(attempt_dir),
        "--sandbox-root",
        str(sandbox_root),
    ]
    if auth_gateway_url:
        sandbox_cmd.extend(["--share-net", "--auth-gateway-url", auth_gateway_url])
        provider = infer_backend_provider(agent.model)
        if provider != "unknown":
            sandbox_cmd.extend(["--gateway-provider", provider])
    sandbox_cmd.extend(["--", *cmd])
    return run_omp_cmd(
        sandbox_cmd,
        cwd=PROJECT_ROOT,
        timeout=timeout + 45 if timeout is not None else None,
        capture_dir=attempt_dir,
    )




PYTEST_STYLE_RUNNER = r'''
from pathlib import Path
import asyncio
import importlib.util
import inspect
import os
import sys
import tempfile
import traceback
import subprocess


def main(argv):
    if len(argv) != 3:
        print("usage: runner.py TEST_OUTPUTS_PY WORKSPACE", file=sys.stderr)
        return 2
    test_path = Path(argv[1]).resolve()
    workspace = Path(argv[2]).resolve()
    os.environ["TASK_WORKSPACE"] = str(workspace)
    sys.path.insert(0, str(workspace))
    spec = importlib.util.spec_from_file_location("hidden_task_test_outputs", test_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    tests = []
    for name, fn in vars(module).items():
        if name.startswith("test_") and callable(fn):
            try:
                line = inspect.getsourcelines(fn)[1]
            except Exception:
                line = 10**9
            tests.append((line, name, fn))
    failures = []
    for _line, name, fn in sorted(tests):
        kwargs = {}
        temp_dirs = []
        unsupported = []
        for param in inspect.signature(fn).parameters.values():
            if param.name == "tmp_path":
                temp_dir = tempfile.TemporaryDirectory()
                temp_dirs.append(temp_dir)
                kwargs[param.name] = Path(temp_dir.name)
            else:
                unsupported.append(param.name)
        if unsupported:
            failures.append((name, "unsupported pytest fixture(s): " + ", ".join(unsupported)))
            continue
        try:
            result = fn(**kwargs)
            if inspect.isawaitable(result):
                asyncio.run(result)
        except Exception:
            failures.append((name, traceback.format_exc()))
        finally:
            for temp_dir in temp_dirs:
                temp_dir.cleanup()
    if failures:
        for name, detail in failures:
            print(f"--- {name} FAILED ---")
            print(detail)
        return 1
    print(f"PASS {len(tests)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
'''.lstrip()


def write_pytest_style_runner(path: Path) -> None:
    path.write_text(PYTEST_STYLE_RUNNER, encoding="utf-8")




def run_host_verifier(task: TaskSpec, attempt_dir: Path) -> CommandResult:
    runner = attempt_dir / ".hidden_pytest_style_runner.py"
    write_pytest_style_runner(runner)
    home = attempt_dir / ".host-verifier-home"
    home.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TASK_SCRIPT_TIMEOUT_SEC": str(task.verifier_timeout_sec),
    }
    return run_cmd(
        [sys.executable, str(runner), str(task.tests_path / "test_outputs.py"), str(attempt_dir / "workspace")],
        cwd=attempt_dir,
        timeout=task.verifier_timeout_sec,
        env=env,
    )


def docker_image_tag(task: TaskSpec) -> str:
    hasher = hashlib.sha256()
    hasher.update(task.task_id.encode("utf-8"))
    environment_root = task.dockerfile_path.parent
    if environment_root.is_dir():
        for path in sorted(p for p in environment_root.rglob("*") if p.is_file()):
            hasher.update(str(path.relative_to(environment_root)).encode("utf-8"))
            hasher.update(path.read_bytes())
    elif task.dockerfile_path.exists():
        hasher.update(task.dockerfile_path.read_bytes())
    digest = hasher.hexdigest()[:16]
    return f"quant-bench-{path_slug(task.task_id).lower()}:{digest}"


def task_image_hashes(task: TaskSpec) -> dict[str, str]:
    dockerfile_sha = hashlib.sha256(task.dockerfile_path.read_bytes()).hexdigest() if task.dockerfile_path.exists() else ""
    req_parts = []
    env = task.dockerfile_path.parent
    for path in sorted(env.glob("*requirements*")):
        if path.is_file():
            req_parts.append(path.read_bytes())
    requirements_sha = hashlib.sha256(b"".join(req_parts)).hexdigest() if req_parts else ""
    return {"dockerfile_sha256": dockerfile_sha, "requirements_sha256": requirements_sha}

IMAGE_LOCK_PATH = PROJECT_ROOT / "benchmarks" / "image-lock.json"


def load_image_lock(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load the checked-in immutable image lock used by manifest runs."""
    lock_path = Path(IMAGE_LOCK_PATH if path is None else path).expanduser().resolve()
    try:
        parsed = json.loads(lock_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"image lock unavailable: {lock_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"image lock is not valid JSON: {lock_path}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"image lock must be a JSON object: {lock_path}")
    entries: dict[str, dict[str, Any]] = {}
    for task_id, entry in parsed.items():
        if not isinstance(entry, dict):
            raise ValueError(f"image lock entry for {task_id} must be an object")
        entries[str(task_id)] = entry
    return entries


def _task_base_image(task: TaskSpec) -> str:
    if not task.dockerfile_path.is_file():
        return ""
    for line in task.dockerfile_path.read_text(encoding="utf-8").splitlines():
        if line.strip().upper().startswith("FROM "):
            return line.strip().split(None, 1)[1]
    return ""


def _expected_image_lock_metadata(task: TaskSpec) -> dict[str, str]:
    base_image = _task_base_image(task)
    hashes = task_image_hashes(task)
    return {
        "tag": docker_image_tag(task),
        "base": base_image,
        "base_digest": base_image.partition("@")[2],
        **hashes,
    }


def resolve_locked_image_id(
    task: TaskSpec,
    *,
    lock: dict[str, dict[str, Any]] | None = None,
    lock_path: str | Path | None = None,
) -> str:
    """Validate a task's lock metadata and return its exact local image ID."""
    resolved_lock_path = IMAGE_LOCK_PATH if lock_path is None else lock_path
    locks = load_image_lock(resolved_lock_path) if lock is None else lock
    entry = locks.get(task.task_id)
    if not isinstance(entry, dict):
        raise ValueError(f"image lock missing task entry: {task.task_id}")
    expected = _expected_image_lock_metadata(task)
    mismatches = [
        key for key, value in expected.items()
        if entry.get(key) != value
    ]
    if mismatches:
        joined = ", ".join(mismatches)
        raise ValueError(f"image lock metadata mismatch for {task.task_id}: {joined}")
    image_id = entry.get("image_id")
    if not isinstance(image_id, str) or not image_id.startswith("sha256:") or not image_id[7:]:
        raise ValueError(f"image lock requires immutable image_id for {task.task_id}")
    docker = shutil.which("docker")
    if docker is None:
        raise ValueError("docker executable not found")
    inspected = run_cmd(
        [docker, "image", "inspect", expected["tag"], "--format", "{{.Id}}"],
        cwd=PROJECT_ROOT,
        timeout=30,
    )
    local_id = inspected.stdout.strip()
    if inspected.returncode != 0 or not local_id:
        raise ValueError(f"locked image tag unavailable for {task.task_id}: {expected['tag']}")
    if local_id != image_id:
        raise ValueError(
            f"locked image ID mismatch for {task.task_id}: expected {image_id}, found {local_id}"
        )
    _IMAGE_METADATA[task.task_id] = {**expected, "image_id": image_id}
    return image_id


def resolve_locked_image_ids(
    tasks: Iterable[TaskSpec],
    *,
    lock_path: str | Path | None = None,
) -> dict[str, str]:
    """Validate all task lock entries before any official Docker phase starts."""
    resolved_lock_path = IMAGE_LOCK_PATH if lock_path is None else lock_path
    lock = load_image_lock(resolved_lock_path)
    return {
        task.task_id: resolve_locked_image_id(task, lock=lock, lock_path=lock_path)
        for task in tasks
    }



def run_docker_verifier(task: TaskSpec, attempt_dir: Path, *, image_id: str | None = None, timeout_scale: float = 1.0) -> CommandResult:
    docker = shutil.which("docker")
    if docker is None:
        return CommandResult(127, False, 0.0, "", "docker executable not found", [], FailureCode.DOCKER_LAUNCH)
    if image_id is None:
        _tag, image_id, build = ensure_task_image(task)
        if build is not None and (build.returncode != 0 or build.timeout):
            return build
    if not image_id:
        return CommandResult(125, False, 0.0, "", "immutable image id unavailable", [], FailureCode.DOCKER_BUILD)
    workspace = attempt_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    cidfile = attempt_dir / "verifier-container.cid"
    cidfile.unlink(missing_ok=True)
    command = "umask 0022; exec python -m pytest -q /tests"
    cmd = [
        docker, "run", "--rm", "--cidfile", str(cidfile), "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
        *_docker_read_only_flags(),
        *_docker_resource_flags(task),
        "-e", "TASK_WORKSPACE=/workspace",
        "-e", f"TASK_SCRIPT_TIMEOUT_SEC={task.verifier_timeout_sec}",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "HOME=/tmp",
        "-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1", "-e", "MKL_NUM_THREADS=1",
        "-v", f"{workspace}:/workspace", "-v", f"{task.tests_path}:/tests:ro",
        "-w", "/workspace", "--entrypoint", "sh", image_id, "-c", command,
    ]
    result = run_cmd(cmd, cwd=PROJECT_ROOT, timeout=max(1, math.ceil(task.verifier_timeout_sec * timeout_scale)))
    if result.timeout:
        _force_remove_docker_container(docker, cidfile)
        result.failure_code = FailureCode.VERIFIER_TIMEOUT
    elif result.returncode != 0:
        result.failure_code = FailureCode.VERIFIER_REJECT
    return result


def run_verifier(task: TaskSpec, attempt_dir: Path, backend: str, *, image_id: str | None = None, timeout_scale: float = 1.0) -> CommandResult:
    if backend == "host":
        return run_host_verifier(task, attempt_dir)
    if backend == "docker":
        return run_docker_verifier(task, attempt_dir, image_id=image_id, timeout_scale=timeout_scale)
    raise ValueError(f"unknown verifier backend: {backend}")


def is_docker_build_command(cmd: list[str]) -> bool:
    return len(cmd) >= 2 and Path(cmd[0]).name == "docker" and cmd[1] == "build"


def result_reason(agent_result: CommandResult, verifier_result: CommandResult) -> tuple[bool, str]:
    af = _failure_value(agent_result.failure_code)
    vf = _failure_value(verifier_result.failure_code)
    if agent_result.timeout or af == FailureCode.AGENT_TIMEOUT.value:
        return False, "agent timeout"
    if af in {FailureCode.PROVIDER_AUTH.value, FailureCode.PROVIDER_RATE_LIMIT.value, FailureCode.PROVIDER_TRANSPORT.value,
              FailureCode.GATEWAY_UNAVAILABLE.value, FailureCode.MODEL_METADATA.value}:
        return False, af
    # A completed assistant message is a model completion even when a tool
    # subprocess returned nonzero; proceed to hidden verification.
    if (agent_result.returncode != 0 or af == FailureCode.AGENT_HARNESS_EXIT.value) and not agent_result.message_end:
        return False, "agent nonzero exit"
    if is_docker_build_command(verifier_result.cmd) or vf == FailureCode.DOCKER_BUILD.value:
        return False, "verifier build timeout" if verifier_result.timeout else "verifier build failed"
    if verifier_result.timeout or vf == FailureCode.VERIFIER_TIMEOUT.value:
        return False, "verifier timeout"
    if vf == FailureCode.DOCKER_LAUNCH.value or (
        verifier_result.returncode == 127 and "docker executable not found" in verifier_result.stderr
    ):
        return False, "verifier infrastructure unavailable"
    if verifier_result.returncode != 0:
        return False, "verifier failed"
    return True, "passed hidden verifier"
def result_status(passed: bool, reason: str) -> str:
    if passed:
        return "PASS"
    if reason in {"agent timeout", "verifier timeout"}:
        return "TIME_LIMIT"
    if reason in {
        "agent nonzero exit", "verifier build timeout", "verifier build failed",
        "verifier infrastructure unavailable", FailureCode.DOCKER_BUILD.value,
        FailureCode.DOCKER_LAUNCH.value, FailureCode.MODEL_METADATA.value,
        FailureCode.GATEWAY_UNAVAILABLE.value, FailureCode.PROVIDER_AUTH.value,
        FailureCode.PROVIDER_RATE_LIMIT.value, FailureCode.PROVIDER_TRANSPORT.value,
        FailureCode.AGENT_HARNESS_EXIT.value,
    }:
        return "INFRA_BLOCKED"
    return "REJECT"


def run_attempt(
    *,
    run_id: str,
    task: TaskSpec,
    agent: AgentSpec,
    output_root: Path,
    verifier_backend: str,
    agent_execution: str,
    tools: str,
    auth_gateway_url: str | None,
    timeout_scale: float,
    oracle: bool,
    dry_run: bool,
    no_op: bool = False,
    max_retries: int = DEFAULT_MAX_RETRIES,
    attempt_number: int = 1,
    total_attempts: int = 1,
    image_id: str | None = None,
    auth_gateway_socket: Path | None = None,
    rerun: int = 0,
    supersedes_result_id: str | None = None,
) -> AttemptResult:
    if total_attempts > 1 or attempt_number > 1:
        attempt_dir = output_root / path_slug(agent.name) / path_slug(task.task_id) / f"attempt_{attempt_number}"
    else:
        attempt_dir = output_root / path_slug(agent.name) / path_slug(task.task_id)
    max_retries = max(0, max_retries)
    all_attempt_metrics = []
    reason = "initial attempt"
    for attempt in range(1, max_retries + 2):
        if attempt > 1:
            print(
                f"  [Attempt {attempt}/{max_retries + 1}] Retrying task {task.task_id} "
                f"after retryable failure: {reason}",
                flush=True,
            )
        copy_public_task_view(task, attempt_dir)
        if dry_run:
            agent_result = CommandResult(0, False, 0.0, "dry run: agent skipped", "", [])
            verifier_result = CommandResult(0, False, 0.0, "dry run: verifier skipped", "", [])
            passed = False
            reason = "dry run skipped"
            status = "DRY_RUN"
            runtime_metrics = None
        else:
            if no_op:
                agent_result = CommandResult(0, False, 0.0, "no-op: agent skipped", "", [])
                runtime_metrics = None
            else:
                if oracle:
                    if agent_execution == "docker":
                        if image_id is None:
                            _tag, image_id, build = ensure_task_image(task)
                            if build is not None and (build.returncode != 0 or build.timeout):
                                agent_result = build
                            else:
                                agent_result = run_docker_oracle(task, attempt_dir, image_id=image_id, timeout_scale=timeout_scale)
                        else:
                            agent_result = run_docker_oracle(task, attempt_dir, image_id=image_id, timeout_scale=timeout_scale)
                    else:
                        agent_result = run_oracle_solution(task, attempt_dir)
                elif agent_execution == "docker":
                    if image_id is None:
                        _tag, image_id, build = ensure_task_image(task)
                        if build is not None and (build.returncode != 0 or build.timeout):
                            agent_result = build
                        else:
                            agent_result = run_docker_agent(
                                agent, task, attempt_dir, image_id=image_id, tools=tools,
                                auth_gateway_socket=auth_gateway_socket, timeout_scale=timeout_scale,
                            )
                    else:
                        agent_result = run_docker_agent(
                            agent, task, attempt_dir, image_id=image_id, tools=tools,
                            auth_gateway_socket=auth_gateway_socket, timeout_scale=timeout_scale,
                        )
                else:
                    agent_result = run_omp_agent(
                        agent, task, attempt_dir, execution=agent_execution, tools=tools,
                        auth_gateway_url=auth_gateway_url, timeout_scale=timeout_scale,
                    )
                if not oracle and agent.harness == "OMP":
                    agent_result = classify_omp_result(agent_result)
                if not oracle and agent.harness == "OMP":
                    run_dict = dict(agent_result.capture) if agent_result.capture is not None else {
                        "stdout": agent_result.stdout,
                        "stderr": agent_result.stderr,
                        "returncode": agent_result.returncode,
                        "elapsed_sec": agent_result.elapsed_sec,
                    }
                    if agent_result.capture is None:
                        omp_metrics_capture.finalize_omp_run_capture(run_dict)
                    agent_result.stdout = run_dict["stdout"]
                    agent_result.stderr = run_dict["stderr"]
                    agent_result.returncode = run_dict["returncode"]
                    runtime_metrics = omp_metrics_capture.runtime_metrics_for_run(
                        run_dict,
                        model=agent.model,
                        auth_gateway_url=auth_gateway_url,
                    )
                else:
                    runtime_metrics = None
                if (
                    not oracle
                    and task.agent_timeout_sec is not None
                    and agent_result.returncode != 0
                    and not agent_result.timeout
                    and agent_result.elapsed_sec >= max(1, math.ceil(task.agent_timeout_sec * timeout_scale))
                ):
                    agent_result.timeout = True
                    agent_result.failure_code = FailureCode.AGENT_TIMEOUT
            can_verify = (agent_result.returncode == 0 or agent_result.message_end) and not agent_result.timeout
            verifier_result = (
                run_verifier(task, attempt_dir, verifier_backend, image_id=image_id, timeout_scale=timeout_scale)
                if can_verify
                else CommandResult(2, False, 0.0, "", "verifier skipped because agent failed", [])
            )
            passed, reason = result_reason(agent_result, verifier_result)
            status = result_status(passed, reason)
        if runtime_metrics is not None:
            all_attempt_metrics.append(runtime_metrics)
        failure_code = _failure_value(agent_result.failure_code)
        if failure_code == FailureCode.NONE.value:
            failure_code = _failure_value(verifier_result.failure_code)
        is_retryable = status == "INFRA_BLOCKED" and (
            failure_code in {
                FailureCode.DOCKER_BUILD.value, FailureCode.DOCKER_LAUNCH.value,
                FailureCode.MODEL_METADATA.value, FailureCode.GATEWAY_UNAVAILABLE.value,
                FailureCode.PROVIDER_AUTH.value, FailureCode.PROVIDER_TRANSPORT.value,
                FailureCode.AGENT_HARNESS_EXIT.value,
            } or reason in {"agent nonzero exit", "verifier build timeout", "verifier build failed"}
        )
        if not is_retryable or attempt >= max_retries + 1:
            if len(all_attempt_metrics) > 1:
                final_metrics = omp_metrics_capture.runtime_metrics_summary(
                    [{"runtime_metrics": m} for m in all_attempt_metrics]
                )
            elif len(all_attempt_metrics) == 1:
                final_metrics = all_attempt_metrics[0]
            else:
                final_metrics = None

            return AttemptResult(
                ts=now_iso(),
                run_id=run_id,
                task_id=task.task_id,
                agent=agent.name,
                name=agent.name,
                model=agent.model,
                backend_provider=agent.backend_provider,
                thinking=agent.thinking,
                harness=agent.harness,
                agent_execution="no-op" if no_op else "oracle" if oracle else agent_execution,
                verifier_backend=verifier_backend,
                passed=passed,
                reason=reason,
                status=status,
                image_id=image_id or "",
                image_tag=docker_image_tag(task) if image_id else "",
                base_image_id=_IMAGE_METADATA.get(task.task_id, {}).get("base_image", ""),
                dockerfile_sha256=_IMAGE_METADATA.get(task.task_id, {}).get("dockerfile_sha256", ""),
                requirements_sha256=_IMAGE_METADATA.get(task.task_id, {}).get("requirements_sha256", ""),
                attempt_dir=str(attempt_dir),
                agent_returncode=agent_result.returncode,
                verifier_returncode=verifier_result.returncode,
                agent_timeout=agent_result.timeout,
                verifier_timeout=verifier_result.timeout,
                agent_elapsed_sec=agent_result.elapsed_sec,
                verifier_elapsed_sec=verifier_result.elapsed_sec,
                agent_stdout=compact_text(agent_result.stdout),
                agent_stderr=compact_text(agent_result.stderr),
                verifier_stdout=compact_text(verifier_result.stdout),
                verifier_stderr=compact_text(verifier_result.stderr),
                agent_cmd=agent_result.cmd,
                verifier_cmd=verifier_result.cmd,
                attempt_count=attempt,
                max_retries=max_retries,
                runtime_metrics=final_metrics,
                attempt_number=attempt_number,
                total_attempts=total_attempts,
                result_id=f"{run_id}:{agent.name}:{task.task_id}:{attempt_number}:{rerun}:{int(time.time_ns())}",
                supersedes_result_id=supersedes_result_id,
                rerun=rerun,
                failure_code=failure_code,
            )

def summarize(results: list[AttemptResult]) -> dict[str, Any]:
    # Append-only histories can contain superseded reruns; score only the
    # latest unsuperseded result for each logical trial.
    superseded = {row.supersedes_result_id for row in results if row.supersedes_result_id}
    visible = [row for row in results if row.result_id not in superseded]
    results = visible
    by_agent: dict[str, dict[str, Any]] = {}
    by_task: dict[str, dict[str, Any]] = {}
    by_status: dict[str, int] = {}
    scored = [row for row in results if row.status != "DRY_RUN"]
    semantic_scored = [row for row in scored if row.status in {"PASS", "REJECT"}]
    for row in results:
        for bucket, key in ((by_agent, row.agent), (by_task, row.task_id)):
            item = bucket.setdefault(
                key,
                {
                    "total": 0,
                    "scored": 0,
                    "passed": 0,
                    "pass_rate": None,
                    "budgeted_pass_rate": None,
                    "semantic_scored": 0,
                    "semantic_pass_rate": None,
                    "time_limited": 0,
                    "infra_blocked": 0,
                    "rejected": 0,
                },
            )
            item["total"] += 1
            if row.status != "DRY_RUN":
                item["scored"] += 1
                item["passed"] += int(row.passed)
                item["budgeted_pass_rate"] = round(item["passed"] / item["scored"], 4)
                item["pass_rate"] = item["budgeted_pass_rate"]
            if row.status in {"PASS", "REJECT"}:
                item["semantic_scored"] += 1
                item["semantic_pass_rate"] = round(item["passed"] / item["semantic_scored"], 4)
            if row.status == "TIME_LIMIT":
                item["time_limited"] += 1
            elif row.status == "INFRA_BLOCKED":
                item["infra_blocked"] += 1
            elif row.status == "REJECT":
                item["rejected"] += 1
        by_status[row.status] = by_status.get(row.status, 0) + 1

    # Add runtime speed/token/cache summaries inside by_agent and by_task when live metrics exist
    for agent_name, item in by_agent.items():
        agent_results = [r for r in results if r.agent == agent_name]
        agent_metrics = [r.runtime_metrics for r in agent_results if r.runtime_metrics is not None]
        if agent_metrics:
            item["runtime_metrics"] = omp_metrics_capture.runtime_metrics_summary(
                [{"runtime_metrics": m} for m in agent_metrics]
            )

    for task_id, item in by_task.items():
        task_results = [r for r in results if r.task_id == task_id]
        task_metrics = [r.runtime_metrics for r in task_results if r.runtime_metrics is not None]
        if task_metrics:
            item["runtime_metrics"] = omp_metrics_capture.runtime_metrics_summary(
                [{"runtime_metrics": m} for m in task_metrics]
            )

    passed_count = sum(1 for row in scored if row.passed)
    semantic_passed_count = sum(1 for row in semantic_scored if row.passed)
    budgeted_pass_rate = round(passed_count / len(scored), 4) if scored else None
    summary_dict = {
        "total": len(results),
        "scored": len(scored),
        "passed": passed_count,
        "pass_rate": budgeted_pass_rate,
        "budgeted_pass_rate": budgeted_pass_rate,
        "semantic_scored": len(semantic_scored),
        "semantic_pass_rate": round(semantic_passed_count / len(semantic_scored), 4) if semantic_scored else None,
        "time_limited": sum(1 for row in scored if row.status == "TIME_LIMIT"),
        "infra_blocked": sum(1 for row in scored if row.status == "INFRA_BLOCKED"),
        "rejected": sum(1 for row in scored if row.status == "REJECT"),
        "by_status": by_status,
        "by_agent": by_agent,
        "by_task": by_task,
    }

    # Add runtime speed/token/cache summaries at top-level when live metrics exist
    top_metrics = [r.runtime_metrics for r in results if r.runtime_metrics is not None]
    if top_metrics:
        summary_dict["runtime_metrics"] = omp_metrics_capture.runtime_metrics_summary(
            [{"runtime_metrics": m} for m in top_metrics]
        )

    return summary_dict


def selected_tasks(values: list[str] | None, limit: int | None) -> list[str]:
    tasks = list(values or DEFAULT_TASKS)
    if limit is not None:
        if limit <= 0:
            raise ValueError("--task-limit must be positive")
        tasks = tasks[:limit]
    return tasks

def validate_promoted_tasks(tasks: list[TaskSpec], *, allow_unpromoted: bool) -> None:
    if allow_unpromoted:
        return
    unpromoted = [task for task in tasks if task.promotion_status != "promoted"]
    if not unpromoted:
        return
    details = ", ".join(f"{task.task_id}({task.promotion_status})" for task in unpromoted)
    raise ValueError(f"unpromoted tasks require --allow-unpromoted-tasks: {details}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Quant Bench tasks with hidden pytest-style verification.")
    parser.add_argument("--manifest", type=Path, help="Versioned benchmark manifest.")
    parser.add_argument("--task-set", help="Manifest task-set name.")
    parser.add_argument("--agent-set", help="Manifest agent-set/wave name.")
    parser.add_argument("--list-tasks", action="store_true", help="List built-in Quant Bench task ids and exit.")
    parser.add_argument(
        "--agent-slate",
        choices=("multimodal", "text-compatible"),
        default="multimodal",
        help="Candidate view used by --list-agent-candidates; only completed public candidates are listed.",
    )
    parser.add_argument(
        "--list-agent-candidates",
        action="store_true",
        help="Print JSON rows for the selected --agent-slate and exit.",
    )
    parser.add_argument("--task", action="append", help="Task id to run. Defaults to the built-in Quant Bench task set.")
    parser.add_argument("--task-limit", type=int, help="Limit selected tasks after filtering; useful for pilots.")
    parser.add_argument(
        "--allow-unpromoted-tasks",
        action="store_true",
        help="Allow draft/non-promoted task ids for diagnostics only.",
    )
    parser.add_argument(
        "--agent",
        action="append",
        help=(
            "Agent spec: NAME=MODEL[,backend=PROVIDER][,thinking=LEVEL][,harness=OMP]. "
            "Thinking defaults to max supported unless --allow-lower-thinking is set. If omitted with --oracle, records a single oracle agent."
        ),
    )
    parser.add_argument("--oracle", action="store_true", help="Run each task's reference solution instead of an OMP agent.")
    parser.add_argument(
        "--no-op",
        action="store_true",
        help="Run hidden verification against the public workspace without an agent; expected to reject and used as a task-integrity diagnostic.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Stage attempts and emit rows without running agent or verifier.")
    parser.add_argument("--verifier", choices=("docker", "host"), default="docker")
    parser.add_argument("--agent-execution", choices=("host", "bwrap", "docker"), default="docker")
    parser.add_argument("--auth-gateway-url", help="Loopback auth-gateway URL for bwrap agent execution.")
    parser.add_argument("--auth-gateway-socket", type=Path, help="Host Unix socket mounted into Docker agents.")
    parser.add_argument(
        "--allow-lower-thinking",
        action="store_true",
        help="Do not force OMP agents to the highest locally-known supported thinking level.",
    )
    parser.add_argument("--tools", help="OMP tools to expose to the solving agent.")
    parser.add_argument("--timeout-scale", type=float, default=DEFAULT_TIMEOUT_SCALE)
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Max retries for retryable infrastructure failures.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=DEFAULT_ATTEMPTS,
        help="Number of independent attempts to run per task.",
    )
    parser.add_argument(
        "--attempt-start",
        type=int,
        default=1,
        help="First logical attempt number; use 2 with --attempts 4 to continue attempts 2-5.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help="Number of trials to execute concurrently.",
    )
    parser.add_argument(
        "--progress-interval-sec",
        type=float,
        default=DEFAULT_PROGRESS_INTERVAL_SEC,
        help="Seconds between terminal/status heartbeat updates while trials are still running; 0 disables heartbeats.",
    )
    parser.add_argument(
        "--local-memory-budget-mb",
        type=int,
        default=DEFAULT_LOCAL_MEMORY_BUDGET_MB,
        help="Scheduling budget in MB used only to reduce concurrency; this is not a process or cgroup memory limit.",
    )
    parser.add_argument(
        "--trial-memory-reserve-mb",
        type=int,
        default=DEFAULT_TRIAL_MEMORY_RESERVE_MB,
        help="Conservative per-OMP-trial scheduling reservation in MB; this is not a hard memory limit.",
    )
    parser.add_argument(
        "--disable-memory-concurrency-cap",
        action="store_true",
        help="Disable the scheduling-only memory concurrency cap.",
    )
    parser.add_argument("--run-id", help="Artifact run id. Defaults to UTC timestamp.")
    parser.add_argument("--resume", action="store_true", help="Resume an interrupted run from the first incomplete task.")
    parser.add_argument("--retry-status", choices=("INFRA_BLOCKED",))
    parser.add_argument("--retry-failure-code", choices=tuple(code.value for code in FailureCode if code not in {FailureCode.NONE, FailureCode.VERIFIER_REJECT, FailureCode.AGENT_TIMEOUT, FailureCode.VERIFIER_TIMEOUT}))
    parser.add_argument("--build-images", action="store_true")
    parser.add_argument("--container-smoke", action="store_true")
    parser.add_argument("--overwrite-run", action="store_true", help="Overwrite an existing run directory.")
    return parser.parse_args(argv)


def get_effective_concurrency(args: argparse.Namespace) -> int:
    if args.disable_memory_concurrency_cap:
        return args.concurrency
    return min(
        args.concurrency,
        max(1, math.floor(args.local_memory_budget_mb / args.trial_memory_reserve_mb))
    )


def unsuperseded_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    superseded = {
        str(row["supersedes_result_id"])
        for row in rows
        if row.get("supersedes_result_id")
    }
    return [
        row
        for row in rows
        if not row.get("result_id") or str(row.get("result_id")) not in superseded
    ]


def latest_unsuperseded_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    heads = unsuperseded_rows(rows)
    latest: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in heads:
        key = (row.get("agent"), row.get("task_id"), row.get("attempt_number"))
        latest[key] = row
    return list(latest.values())


def _percentile(values: list[float], level: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(level * len(ordered)) - 1)]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def expected_pilot_matrix() -> set[tuple[str, str, str, str, int]]:
    manifest = load_benchmark_manifest(PROJECT_ROOT / "benchmarks" / "quant-terminal-v1.toml")
    tasks = manifest_task_ids(manifest, "pilot")
    return {
        (run_id, agent.name, task_id, agent.thinking, 1)
        for run_id, agent_set in PILOT_RUN_IDS.items()
        for agent in manifest_agents(manifest, agent_set)
        for task_id in tasks
    }


def write_combined_pilot_summary() -> Path:
    records: list[dict[str, Any]] = []
    run_states: dict[str, Any] = {}
    for run_id, wave in PILOT_RUN_IDS.items():
        run_root = ARTIFACT_ROOT / run_id
        status_path = run_root / "status.json"
        if status_path.is_file():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                run_states[run_id] = {
                    "complete": bool(status.get("complete")),
                    "run_state": status.get("run_state"),
                }
            except (OSError, json.JSONDecodeError):
                run_states[run_id] = {"complete": False, "run_state": "unreadable"}
        for row in latest_unsuperseded_rows(run_root / "results.jsonl"):
            metrics = row.get("runtime_metrics") if isinstance(row.get("runtime_metrics"), dict) else {}
            records.append({
                "wave": wave,
                "run_id": run_id,
                "agent": row.get("agent"),
                "task": row.get("task_id"),
                "attempt_number": row.get("attempt_number"),
                "thinking": row.get("thinking"),
                "status": row.get("status"),
                "failure_code": row.get("failure_code"),
                "passed": bool(row.get("passed")),
                "wall_time_sec": float(row.get("agent_elapsed_sec", 0.0) or 0.0) + float(row.get("verifier_elapsed_sec", 0.0) or 0.0),
                "tokens": (metrics.get("tokens") or {}).get("total") if isinstance(metrics.get("tokens"), dict) else None,
                "cache_ratio": (metrics.get("cache") or {}).get("cache_read_ratio") if isinstance(metrics.get("cache"), dict) else None,
                "provider_throughput": (metrics.get("throughput") or {}).get("total_tok_s") if isinstance(metrics.get("throughput"), dict) else None,
                "wall_throughput": (metrics.get("throughput") or {}).get("wall_output_tok_s") if isinstance(metrics.get("throughput"), dict) else None,
            })
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["wave"], record["agent"], record["task"], record["thinking"])
        grouped.setdefault(key, []).append(record)
    groups = []
    for (wave, agent, task, thinking), rows in sorted(grouped.items(), key=lambda item: tuple(str(value) for value in item[0])):
        wall_times = [float(row["wall_time_sec"]) for row in rows]
        status_counts: dict[str, int] = {}
        failure_counts: dict[str, int] = {}
        for row in rows:
            status_counts[str(row["status"])] = status_counts.get(str(row["status"]), 0) + 1
            failure_counts[str(row["failure_code"])] = failure_counts.get(str(row["failure_code"]), 0) + 1
        groups.append({
            "wave": wave,
            "agent": agent,
            "task": task,
            "thinking": thinking,
            "rows": len(rows),
            "pass_rate": sum(1 for row in rows if row["passed"]) / len(rows),
            "status_counts": status_counts,
            "failure_code_counts": failure_counts,
            "median_wall_time_sec": _percentile(wall_times, 0.5),
            "p90_wall_time_sec": _percentile(wall_times, 0.9),
            "total_tokens": sum(row["tokens"] for row in rows if isinstance(row["tokens"], (int, float))),
            "mean_cache_ratio": _mean([float(row["cache_ratio"]) for row in rows if isinstance(row["cache_ratio"], (int, float))]),
            "mean_provider_throughput": _mean([float(row["provider_throughput"]) for row in rows if isinstance(row["provider_throughput"], (int, float))]),
            "mean_wall_throughput": _mean([float(row["wall_throughput"]) for row in rows if isinstance(row["wall_throughput"], (int, float))]),
        })
    observed_matrix = {
        (
            str(record["run_id"]),
            str(record["agent"]),
            str(record["task"]),
            str(record["thinking"]),
            int(record["attempt_number"]),
        )
        for record in records
        if isinstance(record.get("attempt_number"), int)
    }
    expected_matrix = expected_pilot_matrix()
    payload = {
        "fixed_run_ids": list(PILOT_RUN_IDS),
        "run_states": run_states,
        "latest_row_count": len(records),
        "expected_latest_rows": len(expected_matrix),
        "complete": observed_matrix == expected_matrix and all(
            run_states.get(run_id, {}).get("complete") for run_id in PILOT_RUN_IDS
        ),
        "records": records,
        "groups": groups,
    }
    destination = ARTIFACT_ROOT / "quant-v1-pilot-summary.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def run_container_smoke(task: TaskSpec, image_id: str) -> CommandResult:
    """Exercise the exact solver isolation boundary without a model call."""
    import socketserver
    import threading

    class EchoHandler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            while True:
                data = self.request.recv(65536)
                if not data:
                    return
                self.request.sendall(data)

    docker = shutil.which("docker")
    if docker is None:
        return CommandResult(127, False, 0.0, "", "docker executable not found", [], FailureCode.DOCKER_LAUNCH)
    with tempfile.TemporaryDirectory(prefix="quant-container-smoke-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        shutil.copytree(task.workspace_path, workspace)
        fake_home = root / "home"
        fake_home.mkdir()
        helper = PROJECT_ROOT / "scripts" / "gateway_socket_proxy.py"
        socket_path = root / "gateway.sock"
        server = socketserver.UnixStreamServer(str(socket_path), EchoHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        smoke_model_ref = "openai-codex/gpt-5.6-sol:max"
        body = json.dumps({"model": "gpt-5.6-sol"}, separators=(",", ":")).encode("utf-8")
        request = (
            b"POST /v1/responses HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        probe = textwrap.dedent(
            f"""
            import socket
            request = {request!r}
            sock = socket.create_connection(("127.0.0.1", 8765), 2)
            sock.sendall(request)
            sock.shutdown(socket.SHUT_WR)
            response = bytearray()
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response.extend(chunk)
            sock.close()
            assert bytes(response) == request
            for host, port in [("1.1.1.1", 80), ("127.0.0.1", 9)]:
                try:
                    socket.create_connection((host, port), 0.5)
                except OSError:
                    pass
                else:
                    raise SystemExit(f"unexpected network access: {{host}}:{{port}}")
            print("bridge and network isolation verified")
            """
        )
        command = (
            "umask 0022; exec python /home/agent/gateway_socket_proxy.py run-tcp "
            "--socket /run/omp-auth-gateway.sock --listen 127.0.0.1:8765 "
            f"--model-selector {shlex_quote(smoke_model_ref)} -- "
            "python -c " + shlex_quote(probe)
        )
        cmd = [
            docker, "run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
            *_docker_read_only_flags(include_run=True),
            *_docker_resource_flags(task),
            "-e", "HOME=/home/agent", "-e", "PATH=/opt/omp-runtime/bin:/usr/local/bin:/usr/bin:/bin",
            "-v", f"{workspace}:/workspace",
            "-v", f"{fake_home}:/home/agent",
            "-v", f"{_docker_runtime_root()}:/opt/omp-runtime:ro",
            "-v", f"{helper}:/home/agent/gateway_socket_proxy.py:ro",
            "-v", f"{socket_path}:/run/omp-auth-gateway.sock",
            "-w", "/workspace", "--entrypoint", "sh", image_id, "-c", command,
        ]
        try:
            return run_cmd(cmd, cwd=PROJECT_ROOT, timeout=120)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.list_tasks:
        try:
            manifest = load_benchmark_manifest(args.manifest) if args.manifest else None
            available = manifest_task_ids(manifest, args.task_set or "official") if manifest else list(DEFAULT_TASKS)
            for task_id in selected_tasks(available, args.task_limit):
                print(task_id)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
    if args.list_agent_candidates:
        try:
            if args.manifest:
                manifest = load_benchmark_manifest(args.manifest)
                agent_set = args.agent_set or "official"
                for agent in manifest_agents(manifest, agent_set):
                    row = asdict(agent)
                    # ``thinking`` is the frozen evaluated value in the
                    # manifest.  Never replace it with current provider
                    # metadata; that would silently rewrite published
                    # configuration identity.
                    try:
                        current = highest_known_thinking(agent.model)
                    except (OSError, RuntimeError, ValueError):
                        current = None
                    row["current_highest_thinking"] = current
                    print(json.dumps(row))
            else:
                for row in get_agent_candidates(highest_known_thinking, slate=args.agent_slate):
                    print(json.dumps(row))
        except (OSError, RuntimeError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
    if args.timeout_scale <= 0:
        print("--timeout-scale must be positive", file=sys.stderr)
        return 2
    if args.max_retries < 0:
        print("--max-retries must be non-negative", file=sys.stderr)
        return 2
    if args.attempts < 1:
        print("--attempts must be at least 1", file=sys.stderr)
        return 2
    if args.attempt_start < 1:
        print("--attempt-start must be at least 1", file=sys.stderr)
        return 2
    attempt_end = args.attempt_start + args.attempts - 1
    if args.concurrency < 1:
        print("--concurrency must be at least 1", file=sys.stderr)
        return 2
    if args.progress_interval_sec < 0:
        print("--progress-interval-sec must be non-negative", file=sys.stderr)
        return 2
    if (args.retry_status or args.retry_failure_code) and not args.resume:
        print("--retry-status/--retry-failure-code require --resume", file=sys.stderr)
        return 2
    if not args.disable_memory_concurrency_cap:
        if args.local_memory_budget_mb <= 0:
            print("--local-memory-budget-mb must be positive", file=sys.stderr)
            return 2
        if args.trial_memory_reserve_mb <= 0:
            print("--trial-memory-reserve-mb must be positive", file=sys.stderr)
            return 2

    effective_concurrency = get_effective_concurrency(args)
    manifest = None
    if args.manifest:
        try:
            manifest = load_benchmark_manifest(args.manifest)
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.agent_execution == "bwrap" and args.auth_gateway_url is None and not args.oracle and not args.no_op and not args.dry_run:
        print("--agent-execution bwrap needs --auth-gateway-url for live remote OMP model calls", file=sys.stderr)
        return 2
    try:
        available_task_ids = (
            manifest_task_ids(manifest, args.task_set) if manifest else list(DEFAULT_TASKS)
        )
        build_universe_task_ids = (
            list(manifest_task_rows(manifest)) if manifest else list(DEFAULT_TASKS)
        )
        task_ids = selected_tasks(args.task if args.task else available_task_ids, args.task_limit)
        tasks = [task_spec_from_manifest(task_id, manifest or {}) for task_id in task_ids]
        validate_promoted_tasks(tasks, allow_unpromoted=args.allow_unpromoted_tasks)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.container_smoke:
        if args.dry_run:
            return 0
        if len(tasks) != 1:
            print("--container-smoke requires exactly one task", file=sys.stderr)
            return 2
        try:
            if manifest is not None:
                smoke_image = resolve_locked_image_ids(tasks)[tasks[0].task_id]
            else:
                _tag, smoke_image, build = ensure_task_image(tasks[0])
                if (build is not None and (build.returncode != 0 or build.timeout)) or not smoke_image:
                    return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        probe = run_container_smoke(tasks[0], smoke_image)
        print(probe.stdout, end="")
        if probe.stderr:
            print(probe.stderr, file=sys.stderr, end="")
        return 0 if probe.returncode == 0 and not probe.timeout else 1
    if args.build_images:
        if args.dry_run:
            return 0
        lock_path = PROJECT_ROOT / "benchmarks" / "image-lock.json"
        if len(task_ids) < len(build_universe_task_ids):
            try:
                locks = load_image_lock(lock_path)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        else:
            locks = {}
        for task in tasks:
            tag, image_id, build = ensure_task_image(task)
            if build is not None and (build.returncode != 0 or build.timeout) or not image_id:
                print(f"image build failed: {task.task_id}", file=sys.stderr)
                return 1
            metadata = _IMAGE_METADATA.get(task.task_id, {})
            base_image = metadata.get("base_image", "")
            locks[task.task_id] = {
                "tag": tag,
                "image_id": image_id,
                "base": base_image,
                "base_digest": base_image.partition("@")[2],
                "dockerfile_sha256": metadata.get("dockerfile_sha256", ""),
                "requirements_sha256": metadata.get("requirements_sha256", ""),
            }
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = lock_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(locks, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, lock_path)
        return 0
    if args.oracle and args.no_op:
        print("--oracle and --no-op are mutually exclusive", file=sys.stderr)
        return 2
    if args.agent:
        try:
            parsed_agents = [parse_agent(value) for value in args.agent]
            agents = parsed_agents if args.allow_lower_thinking else [with_max_thinking(agent) for agent in parsed_agents]
        except (ValueError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
    elif manifest and args.agent_set:
        try:
            agents = manifest_agents(manifest, args.agent_set)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    elif manifest and not args.oracle and not args.no_op and "initial" in manifest.get("agent_sets", {}):
        agents = manifest_agents(manifest, "initial")
    elif args.oracle:
        agents = [AgentSpec("oracle", "reference-solution", "local", "none", "REFERENCE")]
    elif args.no_op:
        agents = [AgentSpec("no-op", "no-agent", "local", "none", "NOOP")]
    else:
        print("provide --agent, --agent-set, --oracle, or --no-op", file=sys.stderr)
        return 2
    tools = args.tools
    if tools is None:
        tools = DEFAULT_SANDBOX_TOOLS if args.agent_execution == "bwrap" else DEFAULT_HOST_TOOLS
    run_id = path_slug(args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output_root = ARTIFACT_ROOT / run_id
    jsonl_path = output_root / "results.jsonl"
    status_path = output_root / "status.json"
    run_mode = "oracle" if args.oracle else "no-op" if args.no_op else args.agent_execution
    resume_config = {
        "agents": [asdict(agent) for agent in agents],
        "tasks": task_ids,
        "manifest": str(args.manifest) if args.manifest else None,
        "task_set": args.task_set,
        "agent_set": args.agent_set,
        "auth_gateway_socket": str(args.auth_gateway_socket) if args.auth_gateway_socket else None,
        "agent_execution": run_mode,
        "verifier": args.verifier,
        "dry_run": bool(args.dry_run),
        "timeout_scale": args.timeout_scale,
        "attempts": args.attempts,
        "attempt_start": args.attempt_start,
        "attempt_end": attempt_end,
        "max_retries": args.max_retries,
        "tools": tools,
    }


    if args.resume and args.overwrite_run:
        print("Error: --resume and --overwrite-run are mutually exclusive", file=sys.stderr)
        return 2
    if args.resume and not jsonl_path.exists():
        print(f"Error: cannot resume {run_id}: results.jsonl does not exist.", file=sys.stderr)
        return 2
    if jsonl_path.exists() and not args.resume and not args.overwrite_run:
        print(
            f"Error: results.jsonl already exists at {jsonl_path}. "
            "Specify --resume to resume or --overwrite-run to overwrite.",
            file=sys.stderr,
        )
        return 2
    supersede_for_trial: dict[tuple[str, str, int], str] = {}
    rerun_for_trial: dict[tuple[str, str, int], int] = {}

    output_root.mkdir(parents=True, exist_ok=True)
    results: list[AttemptResult] = []
    skipped_incompatible = 0
    trials_to_run = []
    for agent in agents:
        for task in tasks:
            if task.requires_image and is_text_only_agent(agent):
                skipped_incompatible += 1
                print(
                    f"[{now_iso()}] SKIP agent={agent.name} task={task.task_id} "
                    "(task requires image, agent is text-only)",
                    flush=True,
                )
                continue
            for attempt_number in range(args.attempt_start, attempt_end + 1):
                trials_to_run.append((agent, task, attempt_number))

    total_trials = len(trials_to_run)
    image_ids: dict[str, str] = {}
    if (args.agent_execution == "docker" or args.verifier == "docker") and not args.dry_run:
        if manifest is not None:
            try:
                image_ids = resolve_locked_image_ids(tasks)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
        else:
            for task in tasks:
                _tag, image_id, build = ensure_task_image(task)
                if build is not None and (build.returncode != 0 or build.timeout):
                    print(f"image preparation failed for {task.task_id}: {build.stderr}", file=sys.stderr)
                    return 1
                if not image_id:
                    print(f"image preparation failed for {task.task_id}", file=sys.stderr)
                    return 1
                image_ids[task.task_id] = image_id
    manifest_sha256 = (
        hashlib.sha256(args.manifest.read_bytes()).hexdigest()
        if args.manifest and args.manifest.is_file()
        else None
    )
    task_input_identity: dict[str, dict[str, str]] = {}
    for task in tasks:
        hashes = task_image_hashes(task)
        base_image = ""
        if task.dockerfile_path.is_file():
            for line in task.dockerfile_path.read_text(encoding="utf-8").splitlines():
                if line.strip().upper().startswith("FROM "):
                    base_image = line.strip().split(None, 1)[1]
                    break
        task_input_identity[task.task_id] = {
            **hashes,
            "base_image": base_image,
            "input_tag": docker_image_tag(task),
            "image_id": image_ids.get(task.task_id, ""),
        }
    resume_config["manifest_sha256"] = manifest_sha256
    resume_config["task_image_identity"] = task_input_identity

    loaded_rows = []
    kept_rows = []
    resume_start_index = 0
    backup_path = None
    resume_start_agent = None
    resume_start_task = None

    if args.resume and jsonl_path.exists():
        if not status_path.exists():
            print(f"Error: cannot resume {run_id}: missing status.json with run configuration.", file=sys.stderr)
            return 2
        try:
            saved_status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"Error: cannot resume {run_id}: status.json is not valid JSON.", file=sys.stderr)
            return 2
        saved_config = saved_status.get("resume_config") or {}
        compatible = isinstance(saved_config, dict) and all(resume_config.get(key) == value for key, value in saved_config.items())
        if not compatible:
            print(
                f"Error: cannot resume {run_id}: saved run configuration differs from current invocation.",
                file=sys.stderr,
            )
            return 2

        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        loaded_rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        def planned_resume_key(agent: AgentSpec, task: TaskSpec, attempt_number: int) -> tuple[Any, ...]:
            return (
                agent.name,
                agent.model,
                agent.backend_provider,
                agent.thinking,
                agent.harness,
                run_mode,
                args.verifier,
                attempt_end,
                args.max_retries,
                task.task_id,
                attempt_number,
            )

        def row_resume_key(row: dict[str, Any]) -> tuple[Any, ...]:
            return (
                row.get("agent"),
                row.get("model"),
                row.get("backend_provider"),
                row.get("thinking"),
                row.get("harness"),
                row.get("agent_execution"),
                row.get("verifier_backend"),
                row.get("total_attempts"),
                row.get("max_retries"),
                row.get("task_id"),
                row.get("attempt_number"),
            )

        retry_selected_rows: dict[int, dict[str, Any]] = {}
        planned_keys = [planned_resume_key(agent, task, attempt_number) for agent, task, attempt_number in trials_to_run]
        planned_key_to_idx = {key: idx for idx, key in enumerate(planned_keys)}

        completed_planned_indices = set()
        completed_rows_by_idx = {}
        duplicate_count = 0
        unknown_count = 0
        retry_requested = bool(args.retry_status or args.retry_failure_code)
        head_rows = unsuperseded_rows(loaded_rows)
        latest_row_by_idx: dict[int, dict[str, Any]] = {}
        for row in head_rows:
            row_key = row_resume_key(row)
            if row_key not in planned_key_to_idx:
                unknown_count += 1
                continue
            idx = planned_key_to_idx[row_key]
            if idx in latest_row_by_idx:
                duplicate_count += 1
            latest_row_by_idx[idx] = row

        for idx, row in latest_row_by_idx.items():
            selected_for_retry = retry_requested and (
                (args.retry_status and row.get("status") == args.retry_status)
                or (args.retry_failure_code and row.get("failure_code") == args.retry_failure_code)
            )
            if selected_for_retry:
                retry_selected_rows[idx] = row
                key = trials_to_run[idx]
                supersede_for_trial[(key[0].name, key[1].task_id, key[2])] = str(row.get("result_id", ""))
                rerun_for_trial[(key[0].name, key[1].task_id, key[2])] = int(row.get("rerun", 0) or 0) + 1
            else:
                completed_planned_indices.add(idx)
                completed_rows_by_idx[idx] = row

        if duplicate_count > 0:
            print(f"Warning: Found {duplicate_count} duplicate rows in results.jsonl.", file=sys.stderr)
        if unknown_count > 0:
            print(f"Warning: Found {unknown_count} unknown rows in results.jsonl that do not match planned trials.", file=sys.stderr)

        missing_idx = None
        for idx in range(total_trials):
            if idx not in completed_planned_indices:
                missing_idx = idx
                break

        if missing_idx is not None:
            resume_start_index = missing_idx
            start_agent, start_task, _ = trials_to_run[resume_start_index]
            resume_start_agent = start_agent.name
            resume_start_task = start_task.task_id
        else:
            resume_start_index = total_trials

        for idx in sorted(completed_rows_by_idx):
            kept_rows.append(completed_rows_by_idx[idx])

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = jsonl_path.with_suffix(f".{timestamp}.bak")
        shutil.copy2(jsonl_path, backup_path)

        for row in kept_rows:
            fields_set = {f.name for f in fields(AttemptResult)}
            filtered = {k: v for k, v in row.items() if k in fields_set}
            results.append(AttemptResult(**filtered))

        if resume_start_index < total_trials:
            print(
                f"RESUME: kept={len(kept_rows)} rows, dropped={len(loaded_rows) - len(kept_rows)} rows, "
                f"start_agent={resume_start_agent}, start_task={resume_start_task} (attempt 1)",
                flush=True,
            )
        else:
            print(
                f"RESUME: kept={len(kept_rows)} rows, dropped={len(loaded_rows) - len(kept_rows)} rows, "
                "all trials completed.",
                flush=True,
            )
    if args.resume:
        retry_indices = sorted(retry_selected_rows)
        remaining_indices = [
            idx for idx in range(resume_start_index, total_trials)
            if idx not in completed_planned_indices and idx not in retry_selected_rows
        ]
        resume_trial_indices = retry_indices + remaining_indices
    else:
        resume_trial_indices = list(range(total_trials))

    completed_trials = len(kept_rows)
    running_trials = 0
    pending_trials = len(resume_trial_indices)

    def status_payload(*, complete: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "complete": complete,
            "jsonl_path": str(jsonl_path),
            "summary": summarize(results),
            "skipped_incompatible": skipped_incompatible,
            "max_retries": args.max_retries,
            "timeout_scale": args.timeout_scale,
            "attempts": args.attempts,
            "attempt_start": args.attempt_start,
            "attempt_end": attempt_end,
            "concurrency": effective_concurrency,
            "requested_concurrency": args.concurrency,
            "effective_concurrency": effective_concurrency,
            "local_memory_budget_mb": args.local_memory_budget_mb,
            "trial_memory_reserve_mb": args.trial_memory_reserve_mb,
            "memory_concurrency_cap_enabled": not args.disable_memory_concurrency_cap,
            "progress_interval_sec": args.progress_interval_sec,
            "total_trials": total_trials,
            "completed_trials": completed_trials,
            "running_trials": running_trials,
            "pending_trials": pending_trials,
            "resume_enabled": bool(args.resume),
            "resume_config": resume_config,
            "resume_source_rows": len(loaded_rows) if args.resume else None,
            "resume_kept_rows": len(kept_rows) if args.resume else None,
            "resume_dropped_rows": (len(loaded_rows) - len(kept_rows)) if args.resume else None,
            "resume_start_agent": resume_start_agent if args.resume else None,
            "resume_start_task": resume_start_task if args.resume else None,
            "resume_start_attempt": 1 if (args.resume and resume_start_index < total_trials) else None,
            "resume_backup_path": str(backup_path) if (args.resume and backup_path) else None,
            "run_state": "paused" if paused else ("complete" if complete else "running"),
            "pause_reason": (
                "provider_rate_limit"
                if pause_failure_code == FailureCode.PROVIDER_RATE_LIMIT.value
                else "provider_transport"
            ) if paused else None,
            "pause_failure_code": pause_failure_code,
            "paused_at": paused_at,
        }
        if complete:
            payload.update(
                {
                    "agents": [asdict(agent) for agent in agents],
                    "tasks": task_ids,
                    "agent_execution": run_mode,
                    "verifier": args.verifier,
                }
            )
        return payload

    def write_status(*, complete: bool) -> None:
        status_path.write_text(json.dumps(status_payload(complete=complete), indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if effective_concurrency < args.concurrency:
        print(
            f"CAP requested={args.concurrency} effective={effective_concurrency} "
            f"memory_budget_mb={args.local_memory_budget_mb} trial_reserve_mb={args.trial_memory_reserve_mb}",
            flush=True,
        )

    with jsonl_path.open("a" if args.resume else "w", encoding="utf-8") as jsonl:
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_concurrency) as executor:
            futures = {}
            trial_iterator = iter(trials_to_run[idx] for idx in resume_trial_indices)
            pause_failure_code = None
            paused = False
            paused_at = None

            def submit_next():
                nonlocal pending_trials, running_trials
                if paused:
                    return False
                try:
                    agent_item, task_item, attempt_num = next(trial_iterator)
                except StopIteration:
                    return False

                print(
                    f"[{now_iso()}] START agent={agent_item.name} model={agent_item.model} task={task_item.task_id} "
                    f"attempt={attempt_num}/{attempt_end}",
                    flush=True,
                )

                future = executor.submit(
                    run_attempt,
                    run_id=run_id,
                    task=task_item,
                    agent=agent_item,
                    output_root=output_root,
                    verifier_backend=args.verifier,
                    agent_execution=args.agent_execution,
                    tools=tools,
                    auth_gateway_url=args.auth_gateway_url,
                    timeout_scale=args.timeout_scale,
                    oracle=args.oracle,
                    dry_run=args.dry_run,
                    no_op=args.no_op,
                    max_retries=args.max_retries,
                    attempt_number=attempt_num,
                    image_id=image_ids.get(task_item.task_id),
                    auth_gateway_socket=args.auth_gateway_socket,
                    supersedes_result_id=supersede_for_trial.get((agent_item.name, task_item.task_id, attempt_num)),
                    rerun=rerun_for_trial.get((agent_item.name, task_item.task_id, attempt_num), 0),
                    total_attempts=attempt_end,
                )
                futures[future] = (agent_item, task_item, attempt_num)
                pending_trials -= 1
                running_trials += 1
                return True

            for _ in range(effective_concurrency):
                if not submit_next():
                    break
            write_status(complete=False)

            while futures:
                wait_timeout = None if args.progress_interval_sec == 0 else args.progress_interval_sec
                done, _ = concurrent.futures.wait(
                    futures.keys(),
                    timeout=wait_timeout,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    print(
                        f"[{now_iso()}] PROGRESS completed={completed_trials} total={total_trials} "
                        f"running={running_trials} pending={pending_trials}",
                        flush=True,
                    )
                    write_status(complete=False)
                    continue
                for future in done:
                    agent_item, task_item, attempt_num = futures.pop(future)
                    try:
                        row = future.result()
                    except Exception as exc:
                        print(f"[{now_iso()}] Trial failed with exception: {exc}", file=sys.stderr)
                        traceback.print_exc(file=sys.stderr)
                        row = AttemptResult(
                            ts=now_iso(),
                            run_id=run_id,
                            task_id=task_item.task_id,
                            agent=agent_item.name,
                            name=agent_item.name,
                            model=agent_item.model,
                            backend_provider=agent_item.backend_provider,
                            thinking=agent_item.thinking,
                            harness=agent_item.harness,
                            agent_execution="no-op" if args.no_op else "oracle" if args.oracle else args.agent_execution,
                            verifier_backend=args.verifier,
                            passed=False,
                            reason=f"thread execution failure: {exc}",
                            status="INFRA_BLOCKED",
                            attempt_dir=str(
                                output_root / path_slug(agent_item.name) / path_slug(task_item.task_id) / f"attempt_{attempt_num}"
                                if args.attempts > 1 or attempt_num > 1
                                else output_root / path_slug(agent_item.name) / path_slug(task_item.task_id)
                            ),
                            agent_returncode=1,
                            verifier_returncode=1,
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
                            max_retries=args.max_retries,
                            runtime_metrics=None,
                            attempt_number=attempt_num,
                            total_attempts=attempt_end,
                        )

                    completed_trials += 1
                    running_trials -= 1

                    print(
                        f"[{now_iso()}] DONE agent={agent_item.name} model={agent_item.model} task={task_item.task_id} "
                        f"attempt={attempt_num}/{attempt_end} status={row.status} "
                        f"(completed={completed_trials}, total={total_trials}, "
                        f"running={running_trials}, pending={pending_trials})",
                        flush=True,
                    )

                    results.append(row)
                    jsonl.write(json.dumps(asdict(row), sort_keys=True) + "\n")
                    failure_code = _failure_value(row.failure_code)
                    if failure_code in {
                        FailureCode.PROVIDER_RATE_LIMIT.value,
                        FailureCode.PROVIDER_TRANSPORT.value,
                    }:
                        paused = True
                        paused_at = paused_at or now_iso()
                        pause_failure_code = failure_code
                    jsonl.flush()
                while not paused and running_trials < effective_concurrency and pending_trials > 0:
                    if not submit_next():
                        break
    summary = summarize(results)
    (output_root / "pilot-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if paused:
        write_status(complete=False)
        if run_id in PILOT_RUN_IDS:
            write_combined_pilot_summary()
        print(f"status={status_path}")
        print(f"jsonl={jsonl_path}")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 75
    write_status(complete=True)
    if run_id in PILOT_RUN_IDS:
        write_combined_pilot_summary()
    print(f"status={status_path}")
    print(f"jsonl={jsonl_path}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.dry_run:
        return 0 if results else 1
    return 0 if results and all(row.passed for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
