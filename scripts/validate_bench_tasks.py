#!/usr/bin/env python3
"""Validate the scored quant-terminal-v1 task manifest and integrity gates.

The default invocation is read-only and checks task schemas, provenance, layout,
public-view contamination, and immutable image contracts.  Optional integrity
flags execute mutant and stochastic oracle/verifier trials in fresh Docker
workspaces; these are deliberately explicit because they perform work.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Iterable


OFFICIAL_TASKS = [
    "sports_hold_vig_removal", "odds_feed_data_merger", "bayesian_mcmc_rhat_diagnostic",
    "async_odds_scraper_shutdown", "poker_shove_fold_equity", "quant_var_expected_shortfall",
    "kalman_live_market_filter", "empirical_bayes_ctr_shrinkage", "sports_injury_steam_audit",
    "market_log_latency_summary", "sports_settlement_ledger_reconciliation", "sqlite_wal_odds_recovery",
    "poker_side_pot_resolution_engine", "stan_to_python_football_prop_model",
    "sportsbook_parlay_synthetic_risk", "quant_cointegration_pairs_trade", "empirical_bayes_true_skill",
    "sports_backtest_query_optimize", "llm_news_batch_scheduler", "data_quality_leakage_client_model",
    "kalman_2d_market_tracker", "range_equity_engine", "poker_hand_history_state_machine",
    "git_secret_alpha_purge", "heteroscedastic_oof_calibration",
    "distributional_boosting_boundary_stability", "vectorized_fisher_preconditioner",
    "crps_vectorization_and_scoring", "adaptive_conformal_intervals", "feature_selection_knockoff_fdr",
    "incremental_schur_feature_selector", "stability_selection_resampling",
    "temporal_ep_weighted_likelihood", "linear_residual_boosting_pipeline",
    "portfolio_optimizer_constraints", "event_driven_backtest_repair", "adaptive_ode_event_integration",
    "sparse_linear_solver", "bitemporal_asof_join", "incremental_feature_materialization",
]
PILOT_TASKS = [
    "heteroscedastic_oof_calibration", "distributional_boosting_boundary_stability",
    "vectorized_fisher_preconditioner", "feature_selection_knockoff_fdr",
    "temporal_ep_weighted_likelihood", "event_driven_backtest_repair",
    "adaptive_ode_event_integration", "bitemporal_asof_join",
]
AGENT_ROWS = {
    "gpt-5-6-sol": ("openai-codex/gpt-5.6-sol", "openai-codex", "max"),
    "gpt-5-6-luna": ("openai-codex/gpt-5.6-luna", "openai-codex", "xhigh"),
    "gpt-5-6-terra": ("openai-codex/gpt-5.6-terra", "openai-codex", "xhigh"),
    "swe-1-7-devin": ("devin/swe-1-7", "devin", "none"),
}
WAVES = {
    "completed_sol": ["gpt-5-6-sol"],
    "completed_luna": ["gpt-5-6-luna"],
    "completed_terra": ["gpt-5-6-terra"],
    "completed_devin": ["swe-1-7-devin"],
    "official": list(AGENT_ROWS),
}
MUTANTS = {
    "bayesian_mcmc_rhat_diagnostic": "unsplit_rhat",
    "heteroscedastic_oof_calibration": "in_sample_residuals",
    "distributional_boosting_boundary_stability": "unsafe_nb_gradient",
    "vectorized_fisher_preconditioner": "matrix_solve",
    "crps_vectorization_and_scoring": "pairwise_tensor",
    "adaptive_conformal_intervals": "naive_quantile",
    "feature_selection_knockoff_fdr": "marginal_topk",
    "incremental_schur_feature_selector": "full_inverse",
    "stability_selection_resampling": "global_preprocessing",
    "temporal_ep_weighted_likelihood": "unweighted_updates",
    "linear_residual_boosting_pipeline": "validation_leak",
    "portfolio_optimizer_constraints": "ignore_turnover",
    "event_driven_backtest_repair": "lookahead_join",
    "adaptive_ode_event_integration": "fixed_step",
    "sparse_linear_solver": "densify",
    "bitemporal_asof_join": "latest_revision",
    "incremental_feature_materialization": "append_without_recompute",
}

_REAL_PROVIDER_SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
)
_GENERIC_SECRET_PATTERNS = (
    re.compile(r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][^'\"]{12,}['\"]", re.I),
    re.compile(r"\b(?=[A-Za-z0-9_-]{12,}\b)(?=[A-Za-z0-9_-]*\d)(?:[A-Za-z0-9]+[-_])+(?:token|tok|secret|key)[-_A-Za-z0-9]{4,}\b", re.I),
)
_USER_HOME_PATH = re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+(?:/|$)")


class ValidationError(ValueError):
    """Raised when a manifest or task violates the scored contract."""



def _require_unique(values: list[str], label: str, errors: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            errors.append(f"duplicate {label}: {value}")
        seen.add(value)


def _load(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValidationError(f"cannot parse {path}: {exc}") from exc
    return value


def _relative_task_root(manifest_path: Path, row: dict[str, Any]) -> Path:
    task_id = row.get("id")
    raw_path = row.get("path")
    expected = f"tasks/{task_id}" if isinstance(task_id, str) else None
    if not isinstance(raw_path, str) or expected is None:
        raise ValidationError("task row must declare string id and path")
    candidate = Path(raw_path)
    if candidate.is_absolute() or raw_path != expected or ".." in candidate.parts:
        raise ValidationError(f"{task_id}: path must be exactly {expected}")
    repo_root = manifest_path.resolve().parent.parent
    task_root = (repo_root / "tasks").resolve()
    resolved = (repo_root / candidate).resolve()
    try:
        resolved.relative_to(task_root)
    except ValueError as exc:
        raise ValidationError(f"{task_id}: task path resolves outside repository task root") from exc
    return resolved


def _public_files(task_root: Path) -> Iterable[Path]:
    for path in task_root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(task_root)
        if "tests" in relative.parts or "solution" in relative.parts:
            continue
        yield path


def _validate_manifest(manifest_path: Path, manifest: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != "1.0":
        errors.append("manifest schema_version must be 1.0")
    benchmark = manifest.get("benchmark")
    expected_benchmark = {
        "id": "quant-terminal-v1",
        "attempts": 5,
        "max_retries": 3,
        "timeout_scale": 1.0,
        "results_source_manifest_sha256": "09fcd2fd2ac0e1370981d3efafc7d89e6280012735b65a5501422db6349d730a",
    }
    if benchmark != expected_benchmark:
        errors.append(f"benchmark contract mismatch: {benchmark!r}")
    task_sets = manifest.get("task_sets")
    if not isinstance(task_sets, dict) or task_sets.get("official") != OFFICIAL_TASKS or task_sets.get("pilot") != PILOT_TASKS:
        errors.append("task_sets official/pilot do not match the frozen contract")
    agent_sets = manifest.get("agent_sets")
    if not isinstance(agent_sets, dict):
        errors.append("missing agent_sets table")
    else:
        for name, expected in WAVES.items():
            if agent_sets.get(name) != expected:
                errors.append(f"agent set {name} does not match frozen roster")
    rows = manifest.get("tasks")
    if not isinstance(rows, list):
        errors.append("manifest must declare [[tasks]] rows")
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            _relative_task_root(manifest_path, row)
        except ValidationError as exc:
            errors.append(str(exc))
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    _require_unique([value for value in ids if isinstance(value, str)], "manifest task id", errors)
    if ids != OFFICIAL_TASKS:
        errors.append("manifest task rows must contain exactly the 40 official IDs in order")
    agents = manifest.get("agents")
    if not isinstance(agents, list):
        errors.append("manifest must declare [[agents]] rows")
        agents = []
    names = [row.get("name") for row in agents if isinstance(row, dict)]
    _require_unique([value for value in names if isinstance(value, str)], "agent name", errors)
    if len(agents) != len(AGENT_ROWS):
        errors.append("manifest must declare exactly four completed agents")
    for row in agents:
        if not isinstance(row, dict):
            errors.append("agent row must be a table")
            continue
        name = row.get("name")
        expected = AGENT_ROWS.get(name)
        if expected is None:
            errors.append(f"unknown agent row: {name!r}")
            continue
        model, provider, thinking = expected
        if (row.get("model"), row.get("backend_provider"), row.get("thinking"), row.get("harness"), row.get("metadata_confirmed")) != (model, provider, thinking, "OMP", True):
            errors.append(f"agent row mismatch for {name}")
    gates = manifest.get("integrity_gates")
    if not isinstance(gates, list) or len(gates) != len(MUTANTS):
        errors.append("manifest must declare exactly seventeen integrity gates")
        gates = gates if isinstance(gates, list) else []
    gate_tasks: list[str] = []
    for gate in gates:
        if not isinstance(gate, dict):
            errors.append("integrity gate must be a table")
            continue
        task = gate.get("task")
        gate_tasks.append(task)
        expected_mutant = MUTANTS.get(task)
        expected_path = f"tasks/{task}/tests/mutants/{expected_mutant}/solve.py" if expected_mutant else None
        if expected_mutant is None or gate.get("mutant_id") != expected_mutant or gate.get("mutant_path") != expected_path or gate.get("repeat_mode") != "verifier" or gate.get("repeat_runs") != 3:
            errors.append(f"integrity gate mismatch for {task!r}")
    _require_unique([task for task in gate_tasks if isinstance(task, str)], "integrity gate task", errors)
    if set(gate_tasks) != set(MUTANTS):
        errors.append("integrity gates do not cover the required 17 tasks")
    return [row for row in rows if isinstance(row, dict)]


def _validate_task(task_id: str, task_root: Path, gate: dict[str, Any] | None, errors: list[str]) -> dict[str, Any] | None:
    task_path = task_root / "task.toml"
    if not task_path.is_file():
        errors.append(f"{task_id}: missing task.toml")
        return None
    try:
        config = _load(task_path)
    except ValidationError as exc:
        errors.append(str(exc))
        return None
    if config.get("schema_version") != "1.3":
        errors.append(f"{task_id}: schema_version must be 1.3")
    task = config.get("task") or {}
    metadata = config.get("metadata") or {}
    provenance = config.get("provenance") or {}
    environment = config.get("environment") or {}
    if task.get("name") != f"quant-bench/{task_id}":
        errors.append(f"{task_id}: task.name must use the quant-bench namespace")
    if task.get("requires_image") is not False:
        errors.append(f"{task_id}: task.requires_image must be false")
    for field in ("difficulty", "category"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            errors.append(f"{task_id}: metadata.{field} must be nonempty")
    if metadata.get("promotion_status") != "promoted":
        errors.append(f"{task_id}: metadata.promotion_status must be promoted")
    blockers = provenance.get("promotion_blockers", config.get("promotion_blockers", []))
    if blockers:
        errors.append(f"{task_id}: promotion blockers present")
    if not isinstance(provenance, dict) or not any(value not in (None, "", [], {}) for value in provenance.values()):
        errors.append(f"{task_id}: provenance must be nonempty")
    if environment.get("network_mode") != "no-network":
        errors.append(f"{task_id}: environment.network_mode must be no-network")
    image = environment.get("docker_image")
    if not isinstance(image, str) or not re.search(r"@sha256:[0-9a-f]{64}$", image):
        errors.append(f"{task_id}: environment.docker_image must use an immutable digest")
    required = [task_root / "instruction.md", task_root / "environment" / "Dockerfile", task_root / "tests" / "test_outputs.py"]
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"{task_id}: missing required file {path.relative_to(task_root)}")
    workspace = task_root / "workspace"
    if not workspace.is_dir() or not any(path.is_file() and path.name != ".gitkeep" for path in workspace.rglob("*")):
        errors.append(f"{task_id}: workspace must be nonempty")
    solution = next((task_root / "solution" / name for name in ("solve.py", "solve.sh") if (task_root / "solution" / name).is_file()), None)
    if solution is None:
        errors.append(f"{task_id}: missing solution/solve.py or solution/solve.sh")
    elif not os.access(solution, os.X_OK):
        errors.append(f"{task_id}: solution entry point must be executable")
    dockerfile = task_root / "environment" / "Dockerfile"
    if dockerfile.is_file():
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"^FROM\s+\S+@sha256:[0-9a-f]{64}\s*$", text, re.MULTILINE):
            errors.append(f"{task_id}: Dockerfile base image must use an immutable digest")
        if "pytest==8.4.2" not in text:
            errors.append(f"{task_id}: Dockerfile must install pytest==8.4.2")
    canaries = metadata.get("synthetic_secret_canaries", [])
    if canaries and (task_id != "git_secret_alpha_purge" or canaries != ["alpha-prod-tok-991283"]):
        errors.append(f"{task_id}: invalid synthetic_secret_canaries declaration")
    allowed = set(canaries) if task_id == "git_secret_alpha_purge" else set()
    for path in _public_files(task_root):
        relative = path.relative_to(task_root)
        if relative.parts and relative.parts[0] == "workspace" and (
            any(part.lower().startswith(("expected", "answer", "gold")) for part in relative.parts)
            or ("outputs" in relative.parts and path.name != ".gitkeep")
        ):
            errors.append(f"{task_id}: precomputed expected-output file in public view: {relative}")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _USER_HOME_PATH.search(text):
            errors.append(f"{task_id}: absolute user-home path appears in public view ({relative})")
        for pattern in _REAL_PROVIDER_SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"{task_id}: real provider credential prefix in public view ({relative})")
        for pattern in _GENERIC_SECRET_PATTERNS:
            for match in pattern.findall(text):
                if not any(canary in match for canary in allowed):
                    errors.append(f"{task_id}: credential-like literal in public view ({relative})")
    for path in workspace.rglob("*") if workspace.is_dir() else ():
        if path.is_file() and any(part in {"tests", "solution"} for part in path.relative_to(task_root).parts):
            errors.append(f"{task_id}: workspace includes tests/solution content")
    if gate is not None:
        mutant_path = task_root.parent.parent / gate["mutant_path"]
        if not mutant_path.is_file():
            errors.append(f"{task_id}: integrity mutant missing: {gate['mutant_path']}")
    return config


def _docker_run(
    image: str,
    mounts: list[tuple[Path, str, str]],
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    resources: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    resources = resources or {}
    args = [
        "docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--user", f"{os.getuid()}:{os.getgid()}",
        "--pids-limit", "100",
        "--memory", f"{int(resources.get('memory_mb', 1024))}m",
        "--cpus", str(resources.get("cpus", 1)),
        "--workdir", "/workspace",
    ]
    for host, target, mode in mounts:
        args.extend(["-v", f"{host}:{target}:{mode}"])
    for key, value in (env or {}).items():
        args.extend(["-e", f"{key}={value}"])
    args.extend(["-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1", "-e", "MKL_NUM_THREADS=1"])
    args.extend([image, *command])
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)


def _prepare_owned_workspace(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    uid, gid = os.getuid(), os.getgid()
    for path in (destination, *destination.rglob("*")):
        try:
            os.chown(path, uid, gid)
        except PermissionError:
            if path.is_file() and path.stat().st_uid != uid:
                raise


def _run_gate(task_id: str, task_root: Path, config: dict[str, Any], mutant_path: Path, *, expect_reject: bool, image: str | None = None) -> None:
    image = image or config["environment"]["docker_image"]
    with tempfile.TemporaryDirectory(prefix=f"bench-{task_id}-") as temporary:
        workspace = Path(temporary) / "workspace"
        _prepare_owned_workspace(task_root / "workspace", workspace)
        solver = _docker_run(
            image,
            [(workspace, "/workspace", "rw"), (mutant_path, "/solution/solve.py", "ro")],
            ["python", "/solution/solve.py", "/workspace"],
            env={"TASK_WORKSPACE": "/workspace"},
            resources=config.get("environment"),
            timeout=float(config.get("agent", {}).get("timeout_sec", 3600)),
        )
        if solver.returncode != 0:
            raise ValidationError(f"{task_id}: mutant solver failed ({solver.stderr[-500:]})")
        verifier = _docker_run(
            image,
            [(workspace, "/workspace", "rw"), (task_root / "tests", "/tests", "ro")],
            ["python", "-m", "pytest", "-q", "/tests"],
            env={"TASK_WORKSPACE": "/workspace"},
            resources=config.get("environment"),
            timeout=float(config.get("verifier", {}).get("timeout_sec", 3600)),
        )
        rejected = verifier.returncode != 0
        if rejected != expect_reject:
            raise ValidationError(f"{task_id}: verifier {'accepted' if not rejected else 'rejected'} unexpected trial")


def validate_manifest(manifest_path: str | Path, *, run_mutants: bool = False, repeat_stochastic: int = 0) -> list[str]:
    path = Path(manifest_path).resolve()
    errors: list[str] = []
    try:
        manifest = _load(path)
    except ValidationError as exc:
        return [str(exc)]
    rows = _validate_manifest(path, manifest, errors)
    gates = {gate.get("task"): gate for gate in manifest.get("integrity_gates", []) if isinstance(gate, dict)}
    configs: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = row.get("id")
        if not isinstance(task_id, str):
            errors.append("task row id must be a string")
            continue
        try:
            task_root = _relative_task_root(path, row)
        except ValidationError:
            continue
        config = _validate_task(task_id, task_root, gates.get(task_id), errors)
        if config is not None:
            configs[task_id] = config
    lock_path = path.parent / "image-lock.json"
    try:
        image_locks = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        image_locks = {}
    if run_mutants and not errors:
        for task_id, mutant_id in MUTANTS.items():
            row = next(row for row in rows if row["id"] == task_id)
            root = _relative_task_root(path, row)
            mutant_path = root / "tests" / "mutants" / mutant_id / "solve.py"
            try:
                image = image_locks.get(task_id, {}).get("image_id")
                if not image:
                    raise ValidationError(f"{task_id}: final image lock missing")
                _run_gate(task_id, root, configs[task_id], mutant_path, expect_reject=True, image=image)
            except (OSError, subprocess.SubprocessError, ValidationError) as exc:
                errors.append(str(exc))
    if repeat_stochastic:
        if repeat_stochastic < 1:
            errors.append("--repeat-stochastic must be positive")
        elif not errors:
            for task_id in MUTANTS:
                config = configs[task_id]
                row = next(row for row in rows if row["id"] == task_id)
                root = _relative_task_root(path, row)
                solution = root / "solution" / "solve.py"
                if not solution.is_file():
                    continue
                for _ in range(repeat_stochastic):
                    try:
                        image = image_locks.get(task_id, {}).get("image_id")
                        if not image:
                            raise ValidationError(f"{task_id}: final image lock missing")
                        _run_gate(task_id, root, config, solution, expect_reject=False, image=image)
                    except (OSError, subprocess.SubprocessError, ValidationError) as exc:
                        errors.append(str(exc))
                        break
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--run-mutants", action="store_true")
    parser.add_argument("--repeat-stochastic", type=int, default=0, metavar="N")
    args = parser.parse_args(argv)
    errors = validate_manifest(args.manifest, run_mutants=args.run_mutants, repeat_stochastic=args.repeat_stochastic)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"validated {len(OFFICIAL_TASKS)} promoted tasks and {len(MUTANTS)} integrity gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
