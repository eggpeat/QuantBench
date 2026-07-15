#!/usr/bin/env python3
"""Read-only factual report generator for Quant Bench artifact runs.

The runner deliberately remains the source of truth for attempt rows.  This
module only reads its JSONL/status artifacts and performs deterministic
aggregation; it never imports the runner (whose module has CLI-adjacent
runtime dependencies) or mutates an artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import tomllib
from xml.sax.saxutils import escape

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "benchmarks" / "quant-terminal-v1.toml"

DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "quant-bench-runs"
DEFAULT_EXPECTED_TASKS = 40
DEFAULT_EXPECTED_ATTEMPTS = 5
ALLOWED_STATUSES = ("PASS", "REJECT", "TIME_LIMIT", "INFRA_BLOCKED")
SEMANTIC_STATUSES = frozenset(("PASS", "REJECT"))
BUDGETED_STATUSES = frozenset(("PASS", "REJECT", "TIME_LIMIT"))
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ReportError(ValueError):
    """An actionable input or aggregation error."""


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _json_number(value: Any) -> int | float | None:
    """Return a finite JSON number, preserving integral values."""
    number = _finite_number(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else number


def exact_median(values: Iterable[float]) -> float | None:
    ordered = sorted(float(value) for value in values if _finite_number(value) is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def nearest_rank_p90(values: Iterable[float]) -> float | None:
    ordered = sorted(float(value) for value in values if _finite_number(value) is not None)
    if not ordered:
        return None
    index = max(0, math.ceil(0.9 * len(ordered)) - 1)
    return ordered[index]


def _timestamp_rank(value: Any) -> tuple[int, str]:
    text = str(value or "")
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return (int(parsed.timestamp() * 1_000_000), text)
        except (TypeError, ValueError, OverflowError):
            # A malformed timestamp is still ordered deterministically; the
            # row validator reports only fields which make aggregation unsafe.
            pass
    return (-1, text)


def _row_identity(row: Mapping[str, Any], line_number: int) -> tuple[str, str, int]:
    agent = row.get("agent")
    task_id = row.get("task_id")
    attempt = row.get("attempt_number")
    if not isinstance(agent, str) or not agent.strip():
        raise ReportError(f"results.jsonl line {line_number}: missing non-empty 'agent'")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ReportError(f"results.jsonl line {line_number}: missing non-empty 'task_id'")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ReportError(f"results.jsonl line {line_number}: 'attempt_number' must be a positive integer")
    status = row.get("status")
    if status not in ALLOWED_STATUSES:
        raise ReportError(
            f"results.jsonl line {line_number}: unsupported status {status!r}; expected one of {', '.join(ALLOWED_STATUSES)}"
        )
    return agent, task_id, attempt


def unsuperseded_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match quant_bench_runner.unsuperseded_rows without importing runner."""
    superseded = {str(row["supersedes_result_id"]) for row in rows if row.get("supersedes_result_id")}
    return [row for row in rows if not row.get("result_id") or str(row.get("result_id")) not in superseded]


def latest_unsuperseded_rows(path: Path) -> list[dict[str, Any]]:
    """Read a run's JSONL and select the latest row for each logical trial.

    Unlike the live runner, a report cannot silently skip malformed input: the
    line number is included in every error so a bad artifact can be repaired.
    """
    if not path.is_file():
        raise ReportError(f"missing results.jsonl: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReportError(f"{path} line {line_number}: invalid JSON ({exc.msg})") from exc
        if not isinstance(row, dict):
            raise ReportError(f"{path} line {line_number}: row must be a JSON object")
        _row_identity(row, line_number)
        rows.append(row)
    heads = unsuperseded_rows(rows)
    latest: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in heads:
        key = _row_identity(row, 0)
        latest[key] = row
    # Preserve the runner's last-row behavior while making ordering stable.
    return list(latest.values())


def _safe_run_ids(run_ids: Iterable[str]) -> list[str]:
    values = list(run_ids)
    if not values:
        raise ReportError("at least one run ID is required")
    if len(set(values)) != len(values):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        raise ReportError(f"duplicate run ID(s): {', '.join(duplicates)}")
    for run_id in values:
        if not isinstance(run_id, str) or not _SAFE_RUN_ID.fullmatch(run_id) or run_id in {".", ".."} or ".." in run_id:
            raise ReportError(f"unsafe run ID {run_id!r}; use letters, digits, '_', '-', and '.' only (no '..')")
    return sorted(values)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ReportError(f"missing {label}: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReportError(f"{label} is not valid JSON ({path}: {exc.msg})") from exc
    if not isinstance(payload, dict):
        raise ReportError(f"{label} must contain a JSON object: {path}")
    return payload

def _load_manifest_contract(path: Path | str) -> dict[str, Any]:
    """Load the frozen publication contract from a TOML manifest."""
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.is_file():
        raise ReportError(f"missing benchmark manifest: {manifest_path}")
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        manifest = tomllib.loads(manifest_bytes.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ReportError(f"benchmark manifest is not valid TOML ({manifest_path}: {exc})") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ReportError(f"cannot read benchmark manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ReportError(f"benchmark manifest must contain a TOML table: {manifest_path}")

    task_sets = manifest.get("task_sets")
    official = task_sets.get("official") if isinstance(task_sets, dict) else None
    if (
        not isinstance(official, list)
        or not official
        or any(not isinstance(task_id, str) or not task_id.strip() for task_id in official)
        or len(set(official)) != len(official)
    ):
        raise ReportError("benchmark manifest task_sets.official must be a unique non-empty list of task IDs")
    task_rows = manifest.get("tasks")
    if not isinstance(task_rows, list):
        raise ReportError("benchmark manifest must declare [[tasks]] rows")
    declared_tasks = {
        str(row.get("id"))
        for row in task_rows
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("id")
    }
    missing_declarations = sorted(set(official) - declared_tasks)
    if missing_declarations:
        raise ReportError(
            "benchmark manifest task_sets.official references undeclared task IDs: "
            + ", ".join(missing_declarations)
        )

    agent_rows = manifest.get("agents")
    if not isinstance(agent_rows, list):
        raise ReportError("benchmark manifest must declare [[agents]] rows")
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in agent_rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
            raise ReportError("benchmark manifest agent rows require non-empty names")
        name = str(row["name"])
        if name in by_name:
            raise ReportError(f"benchmark manifest has duplicate agent name: {name}")
        by_name[name] = row
    agent_sets = manifest.get("agent_sets")
    official_agents = agent_sets.get("official") if isinstance(agent_sets, dict) else None
    if official_agents is None:
        selected_names = sorted(by_name)
    elif (
        not isinstance(official_agents, list)
        or not official_agents
        or any(not isinstance(name, str) or not name.strip() for name in official_agents)
        or len(set(official_agents)) != len(official_agents)
    ):
        raise ReportError("benchmark manifest agent_sets.official must be a unique non-empty list of agent names")
    else:
        selected_names = [str(name) for name in official_agents]
    unknown_agents = sorted(set(selected_names) - set(by_name))
    if unknown_agents:
        raise ReportError(
            "benchmark manifest agent_sets.official references undeclared agents: " + ", ".join(unknown_agents)
        )
    configurations: set[tuple[str | None, ...]] = set()
    for name in selected_names:
        row = by_name[name]
        values: list[str | None] = []
        for key in ("backend_provider", "model", "thinking", "harness"):
            value = row.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ReportError(f"benchmark manifest agent {name!r} field {key!r} must be a non-empty string or null")
            values.append(value)
        configurations.add(tuple(values))
    if not configurations:
        raise ReportError("benchmark manifest declares no publication agent configurations")

    benchmark = manifest.get("benchmark")
    manifest_attempts: int | None = None
    if isinstance(benchmark, dict) and benchmark.get("attempts") is not None:
        attempts = benchmark.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 1:
            raise ReportError("benchmark manifest benchmark.attempts must be a positive integer")
        manifest_attempts = attempts
    results_source_manifest_sha256 = manifest_sha256
    if isinstance(benchmark, dict) and "results_source_manifest_sha256" in benchmark:
        declared_source_hash = benchmark.get("results_source_manifest_sha256")
        if (
            not isinstance(declared_source_hash, str)
            or not _SHA256_RE.fullmatch(declared_source_hash)
        ):
            raise ReportError(
                "benchmark.results_source_manifest_sha256 must be exactly 64 lowercase hexadecimal characters"
            )
        results_source_manifest_sha256 = declared_source_hash
    accepted_run_manifest_sha256 = [manifest_sha256]
    if results_source_manifest_sha256 != manifest_sha256:
        accepted_run_manifest_sha256.append(results_source_manifest_sha256)
    try:
        manifest_label = manifest_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        manifest_label = manifest_path.name
    return {
        "path": manifest_label,
        "accepted_run_manifest_sha256": tuple(accepted_run_manifest_sha256),
        "results_source_manifest_sha256": results_source_manifest_sha256,
        "sha256": manifest_sha256,
        "publication_sha256": manifest_sha256,
        "directory": manifest_path.parent,
        "task_ids": tuple(str(task_id) for task_id in official),
        "configurations": frozenset(configurations),
        "attempts": manifest_attempts,
    }


def _config_value(row: Mapping[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None or isinstance(value, str):
        return value
    raise ReportError(f"configuration field {key!r} must be a string or null, got {type(value).__name__}")

def _configuration_identity(row: Mapping[str, Any]) -> tuple[str | None, ...]:
    return tuple(_config_value(row, key) for key in ("backend_provider", "model", "thinking", "harness"))
_IMAGE_VALUE_KEYS = ("task_image_id", "image_id", "image_digest", "final_image_id")
_IMAGE_MAP_KEYS = ("task_image_identity", "task_images", "image_ids", "task_image_ids", "task_image_id", "images")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _path_label(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.name

def _load_image_lock_contract(manifest_contract: Mapping[str, Any]) -> dict[str, Any]:
    """Load the lock beside the selected manifest without trusting run metadata."""
    lock_path = (Path(manifest_contract["directory"]) / "image-lock.json").resolve()
    result: dict[str, Any] = {
        "path": _path_label(lock_path),
        "sha256": None,
        "image_ids": {},
        "error": None,
    }
    try:
        lock_bytes = lock_path.read_bytes()
        result["sha256"] = hashlib.sha256(lock_bytes).hexdigest()
        parsed = json.loads(lock_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        result["error"] = f"image lock unavailable: {lock_path}"
        return result
    except json.JSONDecodeError as exc:
        result["error"] = f"image lock is not valid JSON: {lock_path}"
        return result
    if not isinstance(parsed, Mapping):
        result["error"] = f"image lock must be a JSON object: {lock_path}"
        return result
    entries: Any = parsed.get("tasks", parsed)
    if not isinstance(entries, Mapping):
        result["error"] = f"image lock task entries are malformed: {lock_path}"
        return result
    for task_id, entry in entries.items():
        if isinstance(entry, Mapping):
            image_id = _immutable_image_id(entry.get("image_id"))
            if image_id is not None:
                result["image_ids"][str(task_id)] = image_id
    return result




def _status_values(status: Mapping[str, Any], key: str) -> list[tuple[str, Any]]:
    values: list[tuple[str, Any]] = []
    if key in status:
        values.append(("status", status[key]))
    resume_config = status.get("resume_config")
    if isinstance(resume_config, Mapping) and key in resume_config:
        values.append(("resume_config", resume_config[key]))
    return values


def _status_field(status: Mapping[str, Any], key: str) -> Any:
    values = _status_values(status, key)
    for _, value in values:
        if value is not None:
            return value
    return None


def _immutable_image_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.startswith("sha256:") or len(value) <= len("sha256:"):
        return None
    return value


def _metadata_image_id(value: Any) -> str | None:
    if isinstance(value, Mapping):
        present = [
            value.get(key)
            for key in ("task_image_id", "image_id", "final_image_id", "image_digest", "digest", "id")
            if key in value
        ]
        if not present:
            return None
        ids = [_immutable_image_id(candidate) for candidate in present]
        if any(image_id is None for image_id in ids):
            return None
        unique = set(ids)
        return next(iter(unique)) if len(unique) == 1 else None
    return _immutable_image_id(value)
def _status_image_maps(status: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], list[str]]:
    maps: list[Mapping[str, Any]] = []
    malformed: list[str] = []
    sources: list[tuple[str, Mapping[str, Any]]] = [("status", status)]
    resume_config = status.get("resume_config")
    if isinstance(resume_config, Mapping):
        sources.append(("resume_config", resume_config))
    for source, container in sources:
        for key in _IMAGE_MAP_KEYS:
            if key not in container:
                continue
            value = container[key]
            if isinstance(value, Mapping):
                maps.append(value)
            else:
                malformed.append(f"{source}.{key}")
    return maps, malformed


def _status_manifest_evidence(
    status: Mapping[str, Any],
    expected: str | Iterable[str],
) -> tuple[str | None, list[str]]:
    reasons: list[str] = []
    accepted = (expected,) if isinstance(expected, str) else tuple(expected)
    accepted = tuple(dict.fromkeys(str(value) for value in accepted if value))
    values = _status_values(status, "manifest_sha256")
    valid: list[tuple[str, str]] = []
    for source, value in values:
        if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
            reasons.append(f"{source}.manifest_sha256 is malformed")
        else:
            valid.append((source, value))
    if not values:
        reasons.append("missing status manifest_sha256 evidence")
    unique = {value for _, value in valid}
    if len(unique) > 1:
        reasons.append("status manifest_sha256 values conflict")
    observed = next(iter(unique), None)
    if observed is not None and observed not in accepted:
        expected_text = ", ".join(accepted) if accepted else "<none>"
        reasons.append(
            f"status manifest_sha256={observed!r} does not match accepted run manifest hash(es): {expected_text}"
        )
    return observed, reasons


def _status_mode_evidence(status: Mapping[str, Any], key: str, aliases: tuple[str, ...] = ()) -> tuple[Any, list[str]]:
    values: list[tuple[str, Any]] = []
    for name in (key, *aliases):
        values.extend(_status_values(status, name))
    reasons: list[str] = []
    if not values:
        return None, [f"missing status {key} evidence"]
    observed = values[0][1]
    if any(value != observed for _, value in values[1:]):
        reasons.append(f"status {key} values conflict")
    return observed, reasons


def _format_task_ids(task_ids: Iterable[str], limit: int = 8) -> str:
    values = sorted(set(str(task_id) for task_id in task_ids))
    if len(values) <= limit:
        return ", ".join(values)
    return ", ".join(values[:limit]) + f", ... ({len(values)} total)"


def _run_execution_evidence(
    status: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]],
    *,
    manifest_sha256: str = "",
    accepted_manifest_sha256: Iterable[str] | None = None,
    expected_run_source_manifest_sha256: str | None = None,
    image_lock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    accepted_hashes = tuple(
        dict.fromkeys(
            str(value)
            for value in (
                accepted_manifest_sha256 if accepted_manifest_sha256 is not None else (manifest_sha256,)
            )
            if value
        )
    )
    expected_run_source_manifest_sha256 = (
        expected_run_source_manifest_sha256
        or (accepted_hashes[-1] if accepted_hashes else manifest_sha256)
    )
    image_lock = image_lock or {"image_ids": {}, "error": "image lock evidence was not supplied"}
    run_rows = list(rows)
    reasons: list[str] = []
    complete = status.get("complete") is True
    run_state = status.get("run_state")
    if not complete or run_state != "complete":
        reasons.append("status is not a complete terminal run")
    manifest_observed, manifest_reasons = _status_manifest_evidence(status, accepted_hashes)
    reasons.extend(manifest_reasons)
    dry_run, dry_reasons = _status_mode_evidence(status, "dry_run")
    reasons.extend(dry_reasons)
    if dry_run is not False:
        reasons.append("dry_run evidence is not false")
    agent_execution, agent_reasons = _status_mode_evidence(status, "agent_execution")
    reasons.extend(agent_reasons)
    if agent_execution != "docker":
        reasons.append(f"agent_execution={agent_execution!r}, expected 'docker'")
    verifier, verifier_reasons = _status_mode_evidence(status, "verifier", ("verifier_backend",))
    reasons.extend(verifier_reasons)
    if verifier != "docker":
        reasons.append(f"verifier={verifier!r}, expected 'docker'")

    task_values = _status_values(status, "tasks")
    selected_lists: list[list[str]] = []
    for source, value in task_values:
        if (
            not isinstance(value, list)
            or any(not isinstance(task, str) or not task.strip() for task in value)
            or len(set(value)) != len(value)
        ):
            reasons.append(f"{source}.tasks is malformed")
            continue
        selected_lists.append([str(task) for task in value])
    if selected_lists:
        selected_tasks = selected_lists[0]
        if any(candidate != selected_tasks for candidate in selected_lists[1:]):
            reasons.append("status selected task lists conflict")
    else:
        selected_tasks = sorted({str(row.get("task_id")) for row in run_rows if row.get("task_id")})
        if not selected_tasks:
            reasons.append("missing selected task evidence")

    row_task_ids = {str(row.get("task_id")) for row in run_rows}
    extra_row_tasks = row_task_ids - set(selected_tasks)
    if extra_row_tasks:
        reasons.append("result rows contain unselected task(s): " + _format_task_ids(extra_row_tasks))

    bad_agent_rows = [row for row in run_rows if row.get("agent_execution") != "docker"]
    bad_verifier_rows = [row for row in run_rows if row.get("verifier_backend") != "docker"]
    if bad_agent_rows:
        reasons.append(f"result rows require agent_execution='docker' ({len(bad_agent_rows)} non-Docker row(s))")
    if bad_verifier_rows:
        reasons.append(f"result rows require verifier_backend='docker' ({len(bad_verifier_rows)} non-Docker row(s))")

    lock_ids = image_lock.get("image_ids") if isinstance(image_lock.get("image_ids"), Mapping) else {}
    lock_error = image_lock.get("error")
    if lock_error:
        reasons.append(str(lock_error))

    status_maps, malformed_maps = _status_image_maps(status)
    if malformed_maps:
        reasons.append("status task image metadata is malformed: " + ", ".join(malformed_maps[:8]))
    image_ids: dict[str, str] = {}
    row_ids: dict[str, str] = {}
    status_ids: dict[str, str] = {}
    for task_id in selected_tasks:
        task_rows = [row for row in run_rows if str(row.get("task_id")) == task_id]
        row_candidates: list[str] = []
        row_invalid = False
        for row in task_rows:
            present = False
            values: list[str] = []
            for key in _IMAGE_VALUE_KEYS:
                if key not in row:
                    continue
                present = True
                image_id = _metadata_image_id(row[key])
                if image_id is None:
                    row_invalid = True
                else:
                    values.append(image_id)
            if not present:
                row_invalid = True
            row_candidates.extend(values)
            if len(set(values)) > 1:
                reasons.append(f"result row image IDs conflict for task {task_id}")
        if row_invalid or not task_rows:
            reasons.append(f"missing or malformed result row image ID for task {task_id}")
        if len(set(row_candidates)) > 1:
            reasons.append(f"result row image IDs conflict for task {task_id}")
        elif row_candidates:
            row_ids[task_id] = row_candidates[0]

        status_candidates: list[str] = []
        status_invalid = False
        for image_map in status_maps:
            if task_id not in image_map:
                continue
            image_id = _metadata_image_id(image_map[task_id])
            if image_id is None:
                status_invalid = True
            else:
                status_candidates.append(image_id)
        if status_invalid or not status_candidates:
            reasons.append(f"missing or malformed status image ID for task {task_id}")
        if len(set(status_candidates)) > 1:
            reasons.append(f"status image IDs conflict for task {task_id}")
        elif status_candidates:
            status_ids[task_id] = status_candidates[0]

        lock_id = lock_ids.get(task_id)
        if not isinstance(lock_id, str) or _immutable_image_id(lock_id) is None:
            reasons.append(f"missing or malformed image-lock ID for task {task_id}")
        else:
            if task_id in row_ids and row_ids[task_id] != lock_id:
                reasons.append(f"result row image ID does not match image lock for task {task_id}")
            if task_id in status_ids and status_ids[task_id] != lock_id:
                reasons.append(f"status image ID does not match image lock for task {task_id}")
            if task_id in row_ids and task_id in status_ids and row_ids[task_id] != status_ids[task_id]:
                reasons.append(f"result/status image IDs conflict for task {task_id}")
            if task_id in row_ids and task_id in status_ids and row_ids[task_id] == lock_id:
                image_ids[task_id] = lock_id

    reasons = list(dict.fromkeys(reasons))[:32]
    selected_lock_ids = {
        task_id: lock_ids[task_id]
        for task_id in selected_tasks
        if isinstance(lock_ids.get(task_id), str)
    }
    return {
        "complete_terminal": complete and run_state == "complete",
        "dry_run": dry_run,
        "agent_execution": agent_execution,
        "verifier": verifier,
        "manifest_sha256": manifest_sha256,
        "expected_run_source_manifest_sha256": expected_run_source_manifest_sha256,
        "results_source_manifest_sha256": expected_run_source_manifest_sha256,
        "accepted_run_manifest_sha256": list(accepted_hashes),
        "status_manifest_sha256": manifest_observed,
        "image_lock_sha256": image_lock.get("sha256"),
        "image_lock_ids": dict(sorted(selected_lock_ids.items())),
        "selected_tasks": selected_tasks,
        "image_ids": image_ids,
        "comparable": not reasons,
        "reasons": reasons,
    }



def _cross_run_dedupe(rows_by_run: Mapping[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    chosen: dict[tuple[Any, ...], tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for run_id in sorted(rows_by_run):
        for row in rows_by_run[run_id]:
            identity = (*_configuration_identity(row), *_row_identity(row, 0))
            result_id = str(row.get("result_id") or "")
            ts_rank = _timestamp_rank(row.get("ts", row.get("timestamp")))
            # Timestamp and result identity intentionally decide which split
            # run owns a logical cell.  Run ID/JSON order make ties stable.
            rank = (ts_rank[0], ts_rank[1], result_id, run_id)
            existing = chosen.get(identity)
            if existing is None or rank >= existing[0]:
                copied = dict(row)
                copied["_run_id"] = run_id
                chosen[identity] = (rank, copied)
    return [chosen[key][1] for key in sorted(chosen, key=lambda item: tuple("" if value is None else str(value) for value in item))]


def _duration(row: Mapping[str, Any]) -> float | None:
    agent = _finite_number(row.get("agent_elapsed_sec"))
    verifier = _finite_number(row.get("verifier_elapsed_sec"))
    if agent is not None and verifier is not None and agent >= 0 and verifier >= 0:
        return agent + verifier
    value = _finite_number(row.get("duration_sec"))
    return value if value is not None and value >= 0 else None


def _metrics(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("runtime_metrics")
    return value if isinstance(value, Mapping) else {}


def _metric_group(row: Mapping[str, Any], group: str) -> Mapping[str, Any]:
    value = _metrics(row).get(group)
    return value if isinstance(value, Mapping) else {}


def _metric_summary(rows: list[dict[str, Any]], group: str, keys: Iterable[str], denominator: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    observed: dict[str, int] = {}
    for key in sorted(set(keys)):
        values: list[float] = []
        for row in rows:
            number = _finite_number(_metric_group(row, group).get(key))
            if number is not None:
                values.append(number)
        observed[key] = len(values)
        result[key] = {
            "total": _json_number(sum(values)) if len(values) == denominator else None,
            "observed_sum": _json_number(sum(values)),
            "coverage": len(values),
            "expected": denominator,
        }
    return result


def _status_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("status")) for row in rows)
    return {status: counts.get(status, 0) for status in ALLOWED_STATUSES}


def _task_distribution(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: Counter[tuple[int, int]] = Counter()
    for task in tasks:
        grouped[(int(task["semantic_passes"]), int(task["semantic_trials"]))] += 1
    return [
        {"semantic_passes": passes, "semantic_trials": trials, "tasks": count, "rate": (passes / trials if trials else None)}
        for (passes, trials), count in sorted(grouped.items())
    ]


def _best_expected_slot_count(
    rows: Iterable[Mapping[str, Any]],
    expected_tasks: int,
    expected_attempt_numbers: Iterable[int],
) -> int:
    expected = set(expected_attempt_numbers)
    by_task: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        attempt = int(row["attempt_number"])
        if attempt in expected:
            by_task[str(row["task_id"])].add(attempt)
    per_task = sorted((len(attempts) for attempts in by_task.values()), reverse=True)
    return sum(per_task[:expected_tasks])


def _model_summary(
    config: tuple[Any, ...],
    rows: list[dict[str, Any]],
    expected_tasks: int,
    expected_attempts: int,
    *,
    official_task_ids: Iterable[str] = (),
    declared_configurations: Iterable[tuple[str | None, ...]] = (),
    manifest_attempts: int | None = None,
    execution_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    backend_provider, model, thinking, harness = config
    statuses = _status_counts(rows)
    semantic_rows = [row for row in rows if row.get("status") in SEMANTIC_STATUSES]
    budgeted_rows = [row for row in rows if row.get("status") in BUDGETED_STATUSES]
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_task[str(row["task_id"])].append(row)
    tasks: list[dict[str, Any]] = []
    for task_id in sorted(by_task):
        task_rows = sorted(by_task[task_id], key=lambda row: int(row["attempt_number"]))
        task_statuses = _status_counts(task_rows)
        task_semantic = [r for r in task_rows if r.get("status") in SEMANTIC_STATUSES]
        task_budgeted = [r for r in task_rows if r.get("status") in BUDGETED_STATUSES]
        tasks.append({
            "task_id": task_id,
            "observed_attempts": len(task_rows),
            "attempt_numbers": [int(row["attempt_number"]) for row in task_rows],
            "status_counts": task_statuses,
            "semantic_trials": len(task_semantic),
            "semantic_passes": sum(1 for row in task_semantic if row.get("status") == "PASS"),
            "semantic_pass_rate": (sum(1 for row in task_semantic if row.get("status") == "PASS") / len(task_semantic) if task_semantic else None),
            "budgeted_trials": len(task_budgeted),
            "budgeted_pass_rate": (sum(1 for row in task_budgeted if row.get("status") == "PASS") / len(task_budgeted) if task_budgeted else None),
        })
    expected_attempt_numbers = list(range(1, expected_attempts + 1))
    complete = len(tasks) == expected_tasks and all(task["attempt_numbers"] == expected_attempt_numbers for task in tasks)
    official_task_set = {str(task_id) for task_id in official_task_ids}
    observed_task_set = set(by_task)
    missing_task_ids = sorted(official_task_set - observed_task_set)
    unexpected_task_ids = sorted(observed_task_set - official_task_set)
    manifest_task_set_match = bool(official_task_set) and not missing_task_ids and not unexpected_task_ids
    manifest_configuration_declared = config in set(declared_configurations)
    manifest_attempts_match = manifest_attempts is None or expected_attempts == manifest_attempts
    expected_cells = expected_tasks * expected_attempts
    # Semantic timing/throughput excludes infrastructure failures, just as
    # semantic pass rates do.  A provider failure must not make a model look
    # faster or slower.
    semantic_durations = [value for row in semantic_rows if (value := _duration(row)) is not None]
    duration_observed_total = _json_number(sum(semantic_durations))
    duration = {
        "median_sec": exact_median(semantic_durations),
        "p90_sec": nearest_rank_p90(semantic_durations),
        "total_sec": duration_observed_total if len(semantic_durations) == len(semantic_rows) else None,
        "observed_sum_sec": duration_observed_total,
        "coverage": len(semantic_durations),
        "expected": len(semantic_rows),
    }
    token_keys = {"input", "output", "reasoning_output", "total", "visible_output_est"}
    cache_keys = {"input_cached", "input_cache_write", "input_uncached", "input_total", "cache_read_ratio"}
    for row in semantic_rows:
        token_keys.update(_metric_group(row, "tokens").keys())
        cache_keys.update(_metric_group(row, "cache").keys())
    token_metrics = _metric_summary(semantic_rows, "tokens", token_keys, len(semantic_rows))
    cache_metrics = _metric_summary(semantic_rows, "cache", cache_keys, len(semantic_rows))
    throughput_values = []
    wall_throughput_values = []
    for row in semantic_rows:
        throughput_metrics = _metric_group(row, "throughput")
        value = _finite_number(throughput_metrics.get("output_tok_s"))
        if value is not None:
            throughput_values.append(value)
        wall_value = _finite_number(throughput_metrics.get("wall_output_tok_s"))
        if wall_value is not None:
            wall_throughput_values.append(wall_value)
    throughput = {
        "provider_output_tok_s_median": exact_median(throughput_values),
        "provider_output_tok_s_coverage": len(throughput_values),
        "wall_output_tok_s_median": exact_median(wall_throughput_values),
        "wall_output_tok_s_coverage": len(wall_throughput_values),
        "definition": "Provider-reported/generated-duration throughput from runtime_metrics.throughput.output_tok_s; not end-to-end speed.",
    }
    token_totals = {key: value["total"] for key, value in token_metrics.items()}
    token_observed = {key: value["observed_sum"] for key, value in token_metrics.items()}
    token_coverage = {key: value["coverage"] for key, value in token_metrics.items()}
    cache_totals = {key: value["total"] for key, value in cache_metrics.items()}
    cache_observed = {key: value["observed_sum"] for key, value in cache_metrics.items()}
    cache_coverage = {key: value["coverage"] for key, value in cache_metrics.items()}
    cache_pairs: list[tuple[float, float]] = []
    for row in semantic_rows:
        cached = _finite_number(_metric_group(row, "cache").get("input_cached"))
        input_total = _finite_number(_metric_group(row, "cache").get("input_total"))
        if cached is not None and input_total is not None:
            cache_pairs.append((cached, input_total))
    cache_ratio_complete = len(cache_pairs) == len(semantic_rows)
    cache_ratio_denominator = sum(input_total for _, input_total in cache_pairs)
    weighted_cache_ratio = (
        sum(cached for cached, _ in cache_pairs) / cache_ratio_denominator
        if cache_ratio_complete and cache_ratio_denominator > 0
        else None
    )
    cache_metrics["cache_read_ratio"] = {
        "total": weighted_cache_ratio,
        "observed_sum": weighted_cache_ratio,
        "coverage": len(cache_pairs),
        "expected": len(semantic_rows),
    }
    cache_totals["cache_read_ratio"] = weighted_cache_ratio
    cache_observed["cache_read_ratio"] = weighted_cache_ratio
    cache_coverage["cache_read_ratio"] = len(cache_pairs)
    semantic_passes = statuses["PASS"]
    semantic_denominator = statuses["PASS"] + statuses["REJECT"]
    budgeted_denominator = semantic_denominator + statuses["TIME_LIMIT"]
    observed_tasks = len(tasks)
    infra_clear = statuses["INFRA_BLOCKED"] == 0
    observed_expected_cells = _best_expected_slot_count(rows, expected_tasks, expected_attempt_numbers)
    semantic_observed_expected_cells = _best_expected_slot_count(
        semantic_rows, expected_tasks, expected_attempt_numbers
    )
    semantic_coverage = {
        "observed_cells": semantic_observed_expected_cells,
        "observed_rows": semantic_denominator,
        "unexpected_cells": max(0, semantic_denominator - semantic_observed_expected_cells),
        "expected_cells": expected_cells,
        "missing_cells": expected_cells - semantic_observed_expected_cells,
        "complete": complete and semantic_observed_expected_cells == expected_cells,
    }
    attempts: list[dict[str, Any]] = []
    for attempt_number in expected_attempt_numbers:
        attempt_semantic_rows = [
            row for row in semantic_rows if int(row["attempt_number"]) == attempt_number
        ]
        attempt_budgeted_rows = [
            row for row in budgeted_rows if int(row["attempt_number"]) == attempt_number
        ]
        attempt_tasks = {str(row["task_id"]) for row in attempt_budgeted_rows}
        attempt_passes = sum(
            1 for row in attempt_budgeted_rows if row.get("status") == "PASS"
        )
        attempts.append({
            "attempt_number": attempt_number,
            "semantic_passes": attempt_passes,
            "semantic_trials": len(attempt_semantic_rows),
            "semantic_pass_rate": (
                attempt_passes / len(attempt_semantic_rows)
                if attempt_semantic_rows
                else None
            ),
            "pass_rate": (
                attempt_passes / len(attempt_semantic_rows)
                if attempt_semantic_rows
                else None
            ),
            "budgeted_passes": attempt_passes,
            "budgeted_trials": len(attempt_budgeted_rows),
            "budgeted_pass_rate": (
                attempt_passes / len(attempt_budgeted_rows)
                if attempt_budgeted_rows
                else None
            ),
            "complete": (
                len(attempt_budgeted_rows) == expected_tasks
                and len(attempt_tasks) == expected_tasks
            ),
        })
    observed_attempt_rates = [
        attempt["semantic_pass_rate"]
        for attempt in attempts
        if attempt["semantic_pass_rate"] is not None
    ]
    attempt_range_complete = (
        complete
        and infra_clear
        and all(attempt["semantic_trials"] == expected_tasks for attempt in attempts)
    )
    attempt_pass_rate_range = {
        "complete": attempt_range_complete,
        "minimum": min(observed_attempt_rates) if attempt_range_complete else None,
        "maximum": max(observed_attempt_rates) if attempt_range_complete else None,
        "spread": (
            max(observed_attempt_rates) - min(observed_attempt_rates)
            if attempt_range_complete
            else None
        ),
        "observed_minimum": min(observed_attempt_rates) if observed_attempt_rates else None,
        "observed_maximum": max(observed_attempt_rates) if observed_attempt_rates else None,
        "definition": "Descriptive minimum and maximum semantic pass rates across repeated attempt numbers; not a confidence interval.",
    }
    observed_budgeted_attempt_rates = [
        attempt["budgeted_pass_rate"]
        for attempt in attempts
        if attempt["budgeted_pass_rate"] is not None
    ]
    budgeted_distribution_complete = (
        complete
        and infra_clear
        and len(observed_budgeted_attempt_rates) == expected_attempts
        and all(attempt["complete"] for attempt in attempts)
    )
    attempt_budgeted_pass_rate_distribution = {
        "complete": budgeted_distribution_complete,
        "median": (
            exact_median(observed_budgeted_attempt_rates)
            if budgeted_distribution_complete
            else None
        ),
        "minimum": (
            min(observed_budgeted_attempt_rates)
            if budgeted_distribution_complete
            else None
        ),
        "maximum": (
            max(observed_budgeted_attempt_rates)
            if budgeted_distribution_complete
            else None
        ),
        "spread": (
            max(observed_budgeted_attempt_rates) - min(observed_budgeted_attempt_rates)
            if budgeted_distribution_complete
            else None
        ),
        "observed_median": exact_median(observed_budgeted_attempt_rates),
        "observed_minimum": (
            min(observed_budgeted_attempt_rates)
            if observed_budgeted_attempt_rates
            else None
        ),
        "observed_maximum": (
            max(observed_budgeted_attempt_rates)
            if observed_budgeted_attempt_rates
            else None
        ),
        "definition": "Median and raw distribution of complete per-attempt budgeted pass rates; TIME_LIMIT counts as a non-pass and INFRA_BLOCKED invalidates comparison.",
    }
    execution_evidence = execution_evidence or {}
    contributing_run_ids = sorted({str(row.get("_run_id")) for row in rows if row.get("_run_id")})
    execution_runs = {
        run_id: dict(execution_evidence.get(run_id, {
            "comparable": False,
            "reasons": ["missing status execution evidence"],
        }))
        for run_id in contributing_run_ids
    }
    execution_comparable = bool(execution_runs) and all(
        bool(evidence.get("comparable")) for evidence in execution_runs.values()
    )
    comparability_reasons: list[str] = []
    if not complete:
        comparability_reasons.append("result matrix is incomplete")
    if not infra_clear:
        comparability_reasons.append("INFRA_BLOCKED result rows are present")
    if not manifest_task_set_match:
        comparability_reasons.append("task set does not match the frozen manifest")
    if not manifest_configuration_declared:
        comparability_reasons.append("configuration is not declared in the frozen manifest")
    if not manifest_attempts_match:
        comparability_reasons.append("attempt count does not match the frozen manifest")
    if not execution_comparable:
        for run_id in contributing_run_ids:
            for reason in execution_runs[run_id].get("reasons", []):
                comparability_reasons.append(f"{run_id}: {reason}")
    comparability_reasons = list(dict.fromkeys(comparability_reasons))
    comparable = not comparability_reasons
    coverage = {
        "expected_tasks": expected_tasks,
        "expected_attempts": expected_attempts,
        "expected_cells": expected_cells,
        "observed_tasks": observed_tasks,
        "observed_cells": observed_expected_cells,
        "observed_rows": len(rows),
        "unexpected_cells": max(0, len(rows) - observed_expected_cells),
        "missing_cells": expected_cells - observed_expected_cells,
        "complete": complete,
        "infra_clear": infra_clear,
        "manifest_task_set_match": manifest_task_set_match,
        "manifest_configuration_declared": manifest_configuration_declared,
        "manifest_attempts_match": manifest_attempts_match,
        "semantic": semantic_coverage,
        "execution_comparable": execution_comparable,
        "execution_reasons": comparability_reasons,
        "comparable": comparable,
    }
    return {
        "configuration": {"backend_provider": backend_provider, "model": model, "thinking": thinking, "harness": harness, "agents": sorted({str(row.get("agent")) for row in rows})},
        "manifest": {
            "task_set_match": manifest_task_set_match,
            "missing_task_ids": missing_task_ids,
            "unexpected_task_ids": unexpected_task_ids,
            "configuration_declared": manifest_configuration_declared,
            "attempts_match": manifest_attempts_match,
        },
        "coverage": coverage,
        "comparable": comparable,
        "execution": {
            "comparable": execution_comparable,
            "runs": execution_runs,
            "reasons": comparability_reasons,
        },
        "comparability_reasons": comparability_reasons,
        "status_counts": statuses,
        "semantic_trials": semantic_denominator,
        "semantic_passes": semantic_passes,
        "semantic_pass_rate": (semantic_passes / semantic_denominator if semantic_denominator else None),
        "budgeted_trials": budgeted_denominator,
        "budgeted_pass_rate": (semantic_passes / budgeted_denominator if budgeted_denominator else None),
        "attempts": attempts,
        "attempt_pass_rate_range": attempt_pass_rate_range,
        "attempt_budgeted_pass_rate_distribution": attempt_budgeted_pass_rate_distribution,
        "median_attempt_budgeted_pass_rate": attempt_budgeted_pass_rate_distribution["median"],
        "task_reliability_distribution": _task_distribution(tasks),
        "tasks": tasks,
        "duration": duration,
        "duration_median_sec": duration["median_sec"],
        "duration_p90_sec": duration["p90_sec"],
        "duration_total_sec": duration["total_sec"],
        "tokens": {"metrics": token_metrics, "totals": token_totals, "observed_sums": token_observed, "coverage": token_coverage, "semantic_rows": len(semantic_rows)},
        "token_totals": token_totals,
        "token_observed_sums": token_observed,
        "token_coverage": token_coverage,
        "cache": {"metrics": cache_metrics, "totals": cache_totals, "observed_sums": cache_observed, "coverage": cache_coverage, "semantic_rows": len(semantic_rows)},
        "cache_totals": cache_totals,
        "cache_observed_sums": cache_observed,
        "cache_coverage": cache_coverage,
        "throughput": throughput,
    }


def build_report(
    run_ids: Iterable[str],
    artifact_root: Path | str = DEFAULT_ARTIFACT_ROOT,
    *,
    expected_tasks: int = DEFAULT_EXPECTED_TASKS,
    expected_attempts: int = DEFAULT_EXPECTED_ATTEMPTS,
    manifest_path: Path | str = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Load and aggregate one or more run IDs without writing artifacts."""
    safe_ids = _safe_run_ids(run_ids)
    if isinstance(expected_tasks, bool) or not isinstance(expected_tasks, int) or expected_tasks < 1:
        raise ReportError("expected_tasks must be a positive integer")
    if isinstance(expected_attempts, bool) or not isinstance(expected_attempts, int) or expected_attempts < 1:
        raise ReportError("expected_attempts must be a positive integer")
    contract = _load_manifest_contract(manifest_path)
    image_lock = _load_image_lock_contract(contract)
    root = Path(artifact_root).resolve()
    states: dict[str, dict[str, Any]] = {}
    rows_by_run: dict[str, list[dict[str, Any]]] = {}
    for run_id in safe_ids:
        run_root = root / run_id
        status = _read_json(run_root / "status.json", f"status.json for run {run_id!r}")
        rows_by_run[run_id] = latest_unsuperseded_rows(run_root / "results.jsonl")
        execution = _run_execution_evidence(
            status,
            rows_by_run[run_id],
            manifest_sha256=contract["sha256"],
            accepted_manifest_sha256=contract["accepted_run_manifest_sha256"],
            expected_run_source_manifest_sha256=contract["results_source_manifest_sha256"],
            image_lock=image_lock,
        )
        states[run_id] = {
            "complete": bool(status.get("complete")),
            "run_state": status.get("run_state"),
            "execution": execution,
        }
    rows = _cross_run_dedupe(rows_by_run)
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        config = _configuration_identity(row)
        grouped[config].append(row)
    models = [
        _model_summary(
            config,
            sorted(group_rows, key=lambda row: (str(row.get("task_id")), int(row.get("attempt_number")))),
            expected_tasks,
            expected_attempts,
            official_task_ids=contract["task_ids"],
            declared_configurations=contract["configurations"],
            manifest_attempts=contract["attempts"],
            execution_evidence={
                run_id: states[run_id]["execution"]
                for run_id in safe_ids
            },
        )
        for config, group_rows in sorted(grouped.items(), key=lambda item: tuple("" if value is None else str(value) for value in item[0]))
    ]
    # The generated time is factual metadata; all content and ordering around
    manifest_configurations = [
        {
            "backend_provider": configuration[0],
            "model": configuration[1],
            "thinking": configuration[2],
            "harness": configuration[3],
        }
        for configuration in sorted(
            contract["configurations"],
            key=lambda item: tuple("" if value is None else str(value) for value in item),
        )
    ]
    report_comparability_reasons = list(dict.fromkeys(
        f"{model['configuration'].get('model')}: {reason}"
        for model in models
        for reason in model.get("comparability_reasons", [])
    ))
    # it is deterministic for a fixed artifact set.
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "manifest": {
            "path": contract["path"],
            "sha256": contract["sha256"],
            "manifest_sha256": contract["sha256"],
            "publication_sha256": contract["sha256"],
            "expected_run_source_manifest_sha256": contract["results_source_manifest_sha256"],
            "results_source_manifest_sha256": contract["results_source_manifest_sha256"],
            "accepted_run_manifest_sha256": list(contract["accepted_run_manifest_sha256"]),
            "official_task_ids": list(contract["task_ids"]),
            "declared_configurations": manifest_configurations,
            "attempts": contract["attempts"],
            "image_lock": {
                "path": image_lock["path"],
                "sha256": image_lock["sha256"],
                "task_image_ids": dict(sorted(image_lock["image_ids"].items())),
            },
            "image_lock_path": image_lock["path"],
            "image_lock_sha256": image_lock["sha256"],
        },
        "input": {"run_ids": safe_ids, "runs": states, "expected_tasks": expected_tasks, "expected_attempts": expected_attempts, "observed_rows": len(rows)},
        "metric_definitions": {
            "semantic_pass_rate": "PASS / (PASS + REJECT); INFRA_BLOCKED and TIME_LIMIT are excluded.",
            "budgeted_pass_rate": "PASS / (PASS + REJECT + TIME_LIMIT); INFRA_BLOCKED is excluded.",
            "median_attempt_budgeted_pass_rate": "Median of the complete per-attempt budgeted pass rates; each attempt is weighted equally, TIME_LIMIT counts as a non-pass, and INFRA_BLOCKED invalidates comparison.",
            "duration": "For semantic PASS/REJECT rows: agent_elapsed_sec + verifier_elapsed_sec when both are available, otherwise duration_sec; infrastructure and time-limit rows are excluded.",
            "attempt_pass_rate_range": "Descriptive min-max of complete per-attempt semantic pass rates across tasks; this stochastic range is not a confidence interval.",
            "provider_output_tok_s": "Median of finite runtime_metrics.throughput.output_tok_s values; provider-reported/generated-duration throughput, not end-to-end speed.",
            "wall_output_tok_s": "Median of finite runtime_metrics.throughput.wall_output_tok_s values; reported separately from provider throughput.",
            "token_cache_totals": "Complete totals are null unless every semantic row has a finite value; observed sums and coverage are always retained.",
        },
        "comparable": all(model["comparable"] for model in models) if models else False,
        "comparability_reasons": report_comparability_reasons,
        "comparability": {
            "comparable": all(model["comparable"] for model in models) if models else False,
            "reasons": report_comparability_reasons,
        },
        "models": models,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# Quant Bench Report", "", f"Generated: `{report.get('generated_at', '')}`", ""]
    lines.extend([
        "## Leaderboard",
        "",
        "| Model | Configuration | Coverage | Comparable | Median attempt pass | Attempt range | Median duration (s) | Provider output tok/s (median) |",
        "|---|---|---:|:---:|---:|---:|---:|---:|",
    ])
    models = list(report.get("models", []))

    def sort_key(model: Mapping[str, Any]) -> tuple[Any, ...]:
        rate = model.get("median_attempt_budgeted_pass_rate")
        config = model.get("configuration", {})
        return (
            not bool(model.get("comparable")),
            -(float(rate) if isinstance(rate, (int, float)) else -1.0),
            str(config.get("model", "")),
            json.dumps(config, sort_keys=True, separators=(",", ":")),
        )

    def fmt(value: Any) -> str:
        if value is None:
            return "—"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            text = f"{float(value):.4f}".rstrip("0").rstrip(".")
            return text or "0"
        return str(value)

    def fmt_percent(value: Any) -> str:
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return "—"
        return f"{float(value) * 100:.1f}%"

    def fmt_percentage_points(value: Any) -> str:
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return "—"
        return f"{float(value) * 100:.1f} pp"





    models = sorted(models, key=sort_key)
    for model in models:
        config = model.get("configuration", {})
        coverage = model.get("coverage", {})
        expected = coverage.get("expected_cells", 0)
        observed = coverage.get("observed_cells", 0)
        median_attempt_pass = model.get("median_attempt_budgeted_pass_rate")
        duration = model.get("duration", {}).get("median_sec")
        throughput = model.get("throughput", {}).get("provider_output_tok_s_median")
        attempt_distribution = model.get("attempt_budgeted_pass_rate_distribution", {})
        range_text = (
            f"{fmt_percent(attempt_distribution.get('minimum'))}–"
            f"{fmt_percent(attempt_distribution.get('maximum'))}"
            if attempt_distribution.get("complete")
            else "—"
        )
        model_selector = str(config.get("model") or "")
        public_name = _PUBLIC_MODEL_NAMES.get(
            model_selector, model_selector or "unknown"
        )
        backend = str(config.get("backend_provider") or "")
        config_parts = [model_selector, str(config.get("thinking") or ""), str(config.get("harness") or "")]
        if backend and not model_selector.startswith(f"{backend}/"):
            config_parts.insert(0, backend)
        config_label = " · ".join(part for part in config_parts if part)
        lines.append(
            f"| {public_name} | `{config_label}` | {observed}/{expected} | "
            f"{'yes' if model.get('comparable') else 'no'} | "
            f"{fmt_percent(median_attempt_pass)} | {range_text} | "
            f"{fmt(duration)} | {fmt(throughput)} |"
        )
    for model in models:
        config = model.get("configuration", {})
        model_selector = str(config.get("model") or "")
        title = _PUBLIC_MODEL_NAMES.get(
            model_selector, model_selector or "unknown model"
        )
        coverage = model.get("coverage", {})
        semantic_coverage = coverage.get("semantic", {})
        duration = model.get("duration", {})
        tokens = model.get("tokens", {})
        token_totals = model.get("token_totals", tokens.get("totals", {}))
        token_observed = model.get("token_observed_sums", tokens.get("observed_sums", {}))
        token_coverage = model.get("token_coverage", tokens.get("coverage", {}))
        semantic_rows = tokens.get("semantic_rows", model.get("semantic_trials", 0))
        cache = model.get("cache", {})
        cache_totals = model.get("cache_totals", cache.get("totals", {}))
        cache_observed = model.get("cache_observed_sums", cache.get("observed_sums", {}))
        cache_coverage = model.get("cache_coverage", cache.get("coverage", {}))
        throughput = model.get("throughput", {})
        attempts = model.get("attempts", [])
        attempt_distribution = model.get("attempt_budgeted_pass_rate_distribution", {})
        attempt_text = ", ".join(
            f"{attempt.get('attempt_number')}="
            f"{fmt_percent(attempt.get('budgeted_pass_rate'))} "
            f"({attempt.get('budgeted_passes', 0)}/"
            f"{attempt.get('budgeted_trials', 0)})"
            for attempt in attempts
        )
        attempt_distribution_text = (
            f"median {fmt_percent(attempt_distribution.get('median'))}; "
            f"range {fmt_percent(attempt_distribution.get('minimum'))}–"
            f"{fmt_percent(attempt_distribution.get('maximum'))}; "
            f"spread {fmt_percentage_points(attempt_distribution.get('spread'))}"
            if attempt_distribution.get("complete")
            else "— (incomplete or infrastructure-blocked attempt distribution)"
        )
        token_total = token_totals.get("total")
        token_observed_total = token_observed.get("total")
        token_total_text = (
            f"complete total **{fmt(token_total)}** (coverage {token_coverage.get('total', 0)}/{semantic_rows}); "
            f"observed sum **{fmt(token_observed_total)}**"
        )
        if token_total is None and token_observed_total is not None and token_coverage.get("total", 0) < semantic_rows:
            token_total_text += " (partial telemetry)"
        cached_text = (
            f"complete total **{fmt(cache_totals.get('input_cached'))}** "
            f"(coverage {cache_coverage.get('input_cached', 0)}/{semantic_rows}); "
            f"observed sum **{fmt(cache_observed.get('input_cached'))}**"
        )
        cache_ratio_text = (
            f"{fmt(cache_totals.get('cache_read_ratio'))} "
            f"(coverage {cache_coverage.get('cache_read_ratio', 0)}/{semantic_rows}; weighted from complete cached/input totals)"
        )
        reliability = json.dumps(model.get("task_reliability_distribution", []), sort_keys=True, separators=(",", ":"))
        lines.extend([
            "",
            f"## {title}",
            "",
            f"Configuration: `{json.dumps(config, sort_keys=True, separators=(',', ':'))}`",
            "",
            f"- Comparable: **{'yes' if model.get('comparable') else 'no'}**",
            f"- Statuses: `{json.dumps(model.get('status_counts', {}), sort_keys=True)}`",
            f"- Semantic cells: **{semantic_coverage.get('observed_cells', 0)}/{semantic_coverage.get('expected_cells', 0)}**",
            f"- Per-attempt budgeted pass rates: **{attempt_text}**",
            f"- Attempt distribution: **{attempt_distribution_text}** ({len(attempts)} equally weighted attempts; TIME_LIMIT counts as a non-pass)",
            f"- Verified duration: median **{fmt(duration.get('median_sec'))} s**, p90 **{fmt(duration.get('p90_sec'))} s**, complete total **{fmt(duration.get('total_sec'))} s**, observed sum **{fmt(duration.get('observed_sum_sec'))} s** (coverage {duration.get('coverage', 0)}/{duration.get('expected', 0)})",
            f"- Total tokens: {token_total_text}",
            f"- Cached-input tokens: {cached_text}",
            f"- Weighted cache read ratio: **{cache_ratio_text}**",
            f"- Provider-reported/generated-duration throughput median: **{fmt(throughput.get('provider_output_tok_s_median'))}** tok/s (coverage {throughput.get('provider_output_tok_s_coverage', 0)}; not end-to-end speed)",
            f"- Wall output tok/s median: **{fmt(throughput.get('wall_output_tok_s_median'))}** (coverage {throughput.get('wall_output_tok_s_coverage', 0)})",
            f"- Task reliability distribution: `{reliability}`",
            "",
            "### Tasks",
            "",
            "| Task | Attempts | PASS | REJECT | TIME_LIMIT | INFRA_BLOCKED | Semantic pass |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ])
        for task in model.get("tasks", []):
            statuses = task.get("status_counts", {})
            lines.append(
                f"| {task.get('task_id')} | {task.get('observed_attempts', 0)} | {statuses.get('PASS', 0)} | "
                f"{statuses.get('REJECT', 0)} | {statuses.get('TIME_LIMIT', 0)} | {statuses.get('INFRA_BLOCKED', 0)} | "
                f"{fmt(task.get('semantic_pass_rate'))} |"
            )
    return "\n".join(lines) + "\n"


_PUBLIC_MODEL_NAMES = {
    "openai-codex/gpt-5.6-luna": "OpenAI GPT 5.6 Luna",
    "openai-codex/gpt-5.6-sol": "OpenAI GPT 5.6 Sol",
    "openai-codex/gpt-5.6-terra": "OpenAI GPT 5.6 Terra",
    "devin/swe-1-7": "Devin SWE 1.7",
}
_CHART_PALETTES = {
    "dark": {
        "text_primary": "#E6EDF3",
        "text_secondary": "#8B949E",
        "grid": "#30363D",
        "accent": "#35CAFF",
        "point_stroke": "#0D1117",
        "median": "#F4AC41",
    },
    "light": {
        "text_primary": "#1F2328",
        "text_secondary": "#656D76",
        "grid": "#D0D7DE",
        "accent": "#0E9BE0",
        "point_stroke": "#FFFFFF",
        "median": "#B45309",
    },
}


def _chart_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_attempt_distribution_svg(
    report: Mapping[str, Any], *, theme: str = "dark"
) -> str:
    """Render complete per-attempt budgeted pass rates without density smoothing."""
    if theme not in _CHART_PALETTES:
        raise ReportError(f"unsupported distribution SVG theme: {theme}")
    palette = _CHART_PALETTES[theme]
    source_models = list(report.get("models", []))
    if not source_models:
        raise ReportError("distribution SVG requires at least one model")
    expected_attempts = int(report.get("manifest", {}).get("attempts") or 0)
    expected_tasks = int(report.get("input", {}).get("expected_tasks") or 0)
    if expected_attempts < 1 or expected_tasks < 1:
        raise ReportError("distribution SVG requires positive task and attempt counts")

    chart_models: list[dict[str, Any]] = []
    for model in source_models:
        config = model.get("configuration", {})
        selector = str(config.get("model") or "unknown")
        distribution = model.get("attempt_budgeted_pass_rate_distribution", {})
        if not model.get("comparable") or not distribution.get("complete"):
            raise ReportError(
                f"distribution SVG requires a comparable complete matrix: {selector}"
            )
        rates: list[tuple[int, float]] = []
        for attempt in model.get("attempts", []):
            rate = _finite_number(attempt.get("budgeted_pass_rate"))
            attempt_number = attempt.get("attempt_number")
            if (
                rate is None
                or rate < 0
                or rate > 1
                or isinstance(attempt_number, bool)
                or not isinstance(attempt_number, int)
            ):
                raise ReportError(
                    f"distribution SVG has invalid attempt data: {selector}"
                )
            rates.append((attempt_number, rate))
        if len(rates) != expected_attempts or {
            attempt_number for attempt_number, _ in rates
        } != set(range(1, expected_attempts + 1)):
            raise ReportError(
                f"distribution SVG requires attempts 1..{expected_attempts}: {selector}"
            )
        median = exact_median(rate for _, rate in rates)
        declared_median = _finite_number(distribution.get("median"))
        if (
            median is None
            or declared_median is None
            or not math.isclose(median, declared_median, rel_tol=0, abs_tol=1e-12)
        ):
            raise ReportError(
                f"distribution SVG median does not match attempt data: {selector}"
            )
        chart_models.append({
            "selector": selector,
            "display_name": _PUBLIC_MODEL_NAMES.get(
                selector, selector.rsplit("/", 1)[-1]
            ),
            "rates": sorted(rates),
            "median": median,
            "minimum": min(rate for _, rate in rates),
            "maximum": max(rate for _, rate in rates),
        })
    chart_models.sort(
        key=lambda model: (-float(model["median"]), str(model["selector"]))
    )

    all_rates = [
        rate for model in chart_models for _, rate in model["rates"]
    ]
    domain_min = math.floor(min(all_rates) * 100 / 5) * 5
    domain_max = math.ceil(max(all_rates) * 100 / 5) * 5
    while domain_max - domain_min < 20:
        if domain_min > 0:
            domain_min -= 5
        elif domain_max < 100:
            domain_max += 5
        else:
            break
    domain_min = max(0, domain_min)
    domain_max = min(100, domain_max)
    domain_span = domain_max - domain_min
    if domain_span <= 0:
        raise ReportError("distribution SVG cannot determine a non-zero axis")

    width = 720
    plot_left = 230
    plot_right = 700
    plot_width = plot_right - plot_left
    row_top = 128
    row_gap = 75
    axis_y = row_top + row_gap * (len(chart_models) - 1) + 57
    footnote_y = axis_y + 36
    height = footnote_y + 15

    def x_position(rate: float) -> float:
        percent = rate * 100
        return plot_left + (percent - domain_min) / domain_span * plot_width

    description = " ".join(
        (
            f"{model['display_name']}: attempts "
            f"{', '.join(_chart_percent(rate) for _, rate in model['rates'])}; "
            f"median {_chart_percent(float(model['median']))}."
        )
        for model in chart_models
    )
    axis_disclosure = (
        f"Pass-rate axis zoomed to {domain_min:.1f}–{domain_max:.1f}%."
        if (domain_min, domain_max) != (0, 100)
        else "Full 0.0–100.0% pass-rate axis."
    )
    svg = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
            'aria-labelledby="qbd-title qbd-desc" '
            'font-family="ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        ),
        (
            "<title id=\"qbd-title\">Budgeted pass-rate distribution across "
            f"{expected_attempts} attempts, by agent configuration</title>"
        ),
        (
            f'<desc id="qbd-desc">{escape(description)} Dots are individual '
            "attempts and stack where tied; the gold marker is the median; "
            f"the cyan line is the min–max range. {axis_disclosure}</desc>"
        ),
        (
            f'<line x1="16" y1="1" x2="704" y2="1" stroke="{palette["grid"]}" '
            'stroke-width="1"/>'
        ),
        (
            f'<text x="16" y="30" fill="{palette["text_primary"]}" '
            'font-size="16" font-weight="650">'
            f"Budgeted pass rate across {expected_attempts} attempts</text>"
        ),
        (
            f'<circle cx="174" cy="56" r="3.5" fill="{palette["accent"]}" '
            f'stroke="{palette["point_stroke"]}" stroke-width=".75"/>'
        ),
        (
            f'<text x="185" y="60" fill="{palette["text_secondary"]}" '
            'font-size="10.5">single attempt</text>'
        ),
        (
            f'<line x1="290" y1="56" x2="310" y2="56" '
            f'stroke="{palette["accent"]}" stroke-width="2.5" '
            'stroke-linecap="round" opacity=".65"/>'
        ),
        (
            f'<text x="320" y="60" fill="{palette["text_secondary"]}" '
            'font-size="10.5">min–max range</text>'
        ),
        (
            f'<line x1="441" y1="45" x2="441" y2="64" '
            f'stroke="{palette["median"]}" stroke-width="2"/>'
        ),
        (
            f'<polygon points="441,40 446,45 441,50 436,45" '
            f'fill="{palette["median"]}"/>'
        ),
        (
            f'<text x="452" y="60" fill="{palette["text_secondary"]}" '
            'font-size="10.5">median</text>'
        ),
    ]

    grid_top = 82
    grid_bottom = axis_y - 18
    for tick in range(domain_min, domain_max + 1, 5):
        x = plot_left + (tick - domain_min) / domain_span * plot_width
        svg.extend([
            (
                f'<line x1="{x:.2f}" y1="{grid_top}" x2="{x:.2f}" '
                f'y2="{grid_bottom}" stroke="{palette["grid"]}" '
                'stroke-width="1"/>'
            ),
            (
                f'<text x="{x:.2f}" y="{axis_y + 15}" text-anchor="middle" '
                f'fill="{palette["text_secondary"]}" font-size="10">'
                f"{tick:.1f}%</text>"
            ),
        ])
    svg.append(
        f'<line x1="{plot_left}" y1="{axis_y - 18}" x2="{plot_right}" '
        f'y2="{axis_y - 18}" stroke="{palette["grid"]}" stroke-width="1"/>'
    )

    for index, model in enumerate(chart_models):
        y = row_top + index * row_gap
        minimum_x = x_position(float(model["minimum"]))
        maximum_x = x_position(float(model["maximum"]))
        median_x = x_position(float(model["median"]))
        svg.extend([
            (
                f'<text x="212" y="{y - 4}" text-anchor="end" '
                f'fill="{palette["text_primary"]}" font-size="12.5" '
                'font-weight="600">'
                f'{escape(str(model["display_name"]))}</text>'
            ),
            (
                f'<text x="212" y="{y + 15}" text-anchor="end" '
                f'fill="{palette["median"]}" font-size="15" font-weight="700">'
                f'{_chart_percent(float(model["median"]))}</text>'
            ),
            (
                f'<line x1="{minimum_x:.2f}" y1="{y}" x2="{maximum_x:.2f}" '
                f'y2="{y}" stroke="{palette["accent"]}" stroke-width="2.5" '
                'stroke-linecap="round" opacity=".55"/>'
            ),
            (
                f'<line x1="{median_x:.2f}" y1="{y - 27}" '
                f'x2="{median_x:.2f}" y2="{y + 27}" '
                f'stroke="{palette["median"]}" stroke-width="2" '
                'stroke-linecap="round" opacity=".9"/>'
            ),
        ])
        grouped_rates: dict[float, list[int]] = defaultdict(list)
        for attempt_number, rate in model["rates"]:
            grouped_rates[float(rate)].append(int(attempt_number))
        for rate, attempt_numbers in sorted(grouped_rates.items()):
            for point_index, attempt_number in enumerate(attempt_numbers):
                offset = (point_index - (len(attempt_numbers) - 1) / 2) * 7
                svg.append(
                    f'<circle cx="{x_position(rate):.2f}" '
                    f'cy="{y + offset:.2f}" r="4.5" '
                    f'fill="{palette["accent"]}" '
                    f'stroke="{palette["point_stroke"]}" stroke-width=".75">'
                    f"<title>Attempt {attempt_number}: {_chart_percent(rate)}</title>"
                    "</circle>"
                )
        svg.append(
            f'<polygon points="{median_x:.2f},{y - 32} '
            f'{median_x + 5:.2f},{y - 27} {median_x:.2f},{y - 22} '
            f'{median_x - 5:.2f},{y - 27}" fill="{palette["median"]}"/>'
        )
        if index < len(chart_models) - 1:
            svg.append(
                f'<line x1="16" y1="{y + 37.5:.2f}" x2="704" '
                f'y2="{y + 37.5:.2f}" stroke="{palette["grid"]}" '
                'stroke-width=".75" opacity=".45"/>'
            )
    svg.extend([
        (
            f'<text x="16" y="{footnote_y}" fill="{palette["text_secondary"]}" '
            'font-size="9">'
            f"Each dot is one of {expected_attempts} attempts; tied attempts "
            f"stack vertically. {axis_disclosure} No mean or aggregate count."
            "</text>"
        ),
        (
            f'<line x1="16" y1="{height - 1}" x2="704" y2="{height - 1}" '
            f'stroke="{palette["grid"]}" stroke-width="1"/>'
        ),
        "</svg>",
    ])
    return "\n".join(svg) + "\n"


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return left.exists() and right.exists() and left.samefile(right)
    except OSError:
        return False


def _paths_overlap(left: Path, right: Path) -> bool:
    return (
        left == right
        or _same_existing_file(left, right)
        or left in right.parents
        or right in left.parents
    )


def _validate_output_paths(
    artifact_root: Path | str,
    run_ids: Iterable[str],
    json_output: Path | None,
    markdown_output: Path | None,
    svg_light_output: Path | None = None,
    svg_dark_output: Path | None = None,
    *,
    manifest_path: Path | str | None = None,
) -> None:
    destinations = [
        path.resolve()
        for path in (json_output, markdown_output, svg_light_output, svg_dark_output)
        if path is not None
    ]
    for index, destination in enumerate(destinations):
        if any(
            _paths_overlap(destination, other)
            for other in destinations[index + 1:]
        ):
            raise ReportError("report output paths must be different")
    root = Path(artifact_root).resolve()
    run_roots = {(root / str(run_id)).resolve() for run_id in run_ids}
    protected = set(run_roots)
    protected.update(
        run_root / filename
        for run_root in run_roots
        for filename in ("results.jsonl", "status.json")
    )
    if manifest_path is not None:
        manifest = Path(manifest_path).expanduser().resolve()
        protected.update((manifest, (manifest.parent / "image-lock.json").resolve()))
    conflicts = sorted(
        str(destination)
        for destination in destinations
        if any(_paths_overlap(destination, source) for source in protected)
    )
    if conflicts:
        raise ReportError(f"output path would overwrite benchmark input: {', '.join(conflicts)}")




def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_ids", metavar="RUN_ID", nargs="+", help="artifact run ID(s)")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH, help="frozen benchmark manifest (default: benchmarks/quant-terminal-v1.toml)")
    parser.add_argument("--expected-tasks", type=int, default=DEFAULT_EXPECTED_TASKS)
    parser.add_argument("--expected-attempts", type=int, default=DEFAULT_EXPECTED_ATTEMPTS)
    parser.add_argument("--json-output", type=Path, help="write JSON report to this path (default: stdout)")
    parser.add_argument("--markdown-output", type=Path, help="write Markdown report to this path (default: stdout when JSON output is selected)")
    parser.add_argument("--svg-light-output", type=Path, help="write light-theme attempt-distribution SVG to this path")
    parser.add_argument("--svg-dark-output", type=Path, help="write dark-theme attempt-distribution SVG to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_report(
            args.run_ids,
            args.artifact_root,
            expected_tasks=args.expected_tasks,
            expected_attempts=args.expected_attempts,
            manifest_path=args.manifest,
        )
        markdown = render_markdown(report)
        encoded = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        svg_light = (
            render_attempt_distribution_svg(report, theme="light")
            if args.svg_light_output
            else None
        )
        svg_dark = (
            render_attempt_distribution_svg(report, theme="dark")
            if args.svg_dark_output
            else None
        )
        _validate_output_paths(
            args.artifact_root,
            report["input"]["run_ids"],
            args.json_output,
            args.markdown_output,
            args.svg_light_output,
            args.svg_dark_output,
            manifest_path=args.manifest,
        )
        if args.json_output:
            _write_text(args.json_output, encoded)
        if args.markdown_output:
            _write_text(args.markdown_output, markdown)
        if args.svg_light_output and svg_light is not None:
            _write_text(args.svg_light_output, svg_light)
        if args.svg_dark_output and svg_dark is not None:
            _write_text(args.svg_dark_output, svg_dark)
        if not args.json_output and not args.markdown_output:
            print(encoded, end="")
            print(markdown, file=sys.stderr, end="")
        elif not args.json_output:
            print(encoded, end="")
        elif not args.markdown_output:
            print(markdown, file=sys.stderr, end="")
        return 0
    except (OSError, ReportError) as exc:
        print(f"bench_report: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
