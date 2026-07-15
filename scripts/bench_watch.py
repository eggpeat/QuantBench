#!/usr/bin/env python3
"""Read-only terminal watcher for Quant Bench runs.

The runner writes ``status.json`` and appends result records to
``results.jsonl``.  This command deliberately treats both files as snapshots:
a replacement race or an incomplete JSON record is ignored instead of being
allowed to interrupt a live watch.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "quant-bench-runs"
MAX_JSON_LINE_BYTES = 4 * 1024 * 1024
MAX_TASK_ROWS = 200
MAX_CELL_WIDTH = 64


def resolve_run_dir(run_id: str, artifact_root: str | os.PathLike[str] = DEFAULT_ARTIFACT_ROOT) -> Path:
    """Resolve one run below *artifact_root*, rejecting traversal.

    Run IDs are intentionally a single path component.  Besides making output
    predictable, this prevents a typo such as ``../other-run`` from making a
    read-only utility inspect an unrelated directory.  Existing symlinks are
    checked after resolution as well.
    """
    value = str(run_id)
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("RUN_ID must be a non-empty path component")
    root = Path(artifact_root).expanduser().resolve()
    candidate = (root / value).resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("RUN_ID resolves outside the artifact root") from exc
    if len(relative.parts) != 1:
        raise ValueError("RUN_ID must resolve directly below the artifact root")
    return candidate


def load_status_snapshot(path: Path) -> dict[str, Any] | None:
    """Load a status snapshot, returning ``None`` for absent/partial data."""
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def load_results_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read complete JSON objects from append-only results.

    A writer may be between ``write`` calls when a watcher reads the file.  A
    malformed line (including an incomplete final line) is therefore skipped;
    all complete, valid object lines remain useful.
    """
    records: list[dict[str, Any]] = []
    try:
        with path.open("rb") as stream:
            for raw_line in stream:
                if len(raw_line) > MAX_JSON_LINE_BYTES:
                    continue
                try:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    value = json.loads(line)
                except (UnicodeError, json.JSONDecodeError):
                    continue
                if isinstance(value, dict):
                    records.append(value)
    except OSError:
        return []
    return records


def latest_unsuperseded_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return append-only rows whose result IDs have not been superseded."""
    records = [dict(row) for row in rows if isinstance(row, Mapping)]
    superseded: set[str] = set()
    for row in records:
        value = row.get("supersedes_result_id")
        if value not in (None, ""):
            superseded.add(str(value))
    return [
        row
        for row in records
        if row.get("result_id") in (None, "") or str(row.get("result_id")) not in superseded
    ]


def latest_task_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Select the last visible row for each task in append order."""
    latest: dict[str, dict[str, Any]] = {}
    for row in latest_unsuperseded_rows(rows):
        task = str(row.get("task_id") or row.get("task") or "")
        if task:
            latest[task] = dict(row)
    return latest


def _number(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and abs(number) != float("inf") else default


def _integer(value: Any, default: int | None = None) -> int | None:
    number = _number(value)
    if number is None:
        return default
    return int(number)


def _timestamp(value: Any) -> float | None:
    number = _number(value)
    if number is not None:
        # Treat very large values as milliseconds, which is common in exported
        # status snapshots.
        return number / 1000 if number > 100_000_000_000 else number
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0 or seconds != seconds:
        return "—"
    total = int(seconds)
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _elapsed_seconds(status: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], now: float | None = None) -> float | None:
    starts = ("started_at", "start_time", "created_at", "launched_at")
    ends = ("completed_at", "finished_at", "ended_at", "updated_at", "paused_at")
    start = next((_timestamp(status.get(key)) for key in starts if _timestamp(status.get(key)) is not None), None)
    if start is None:
        row_times = [_timestamp(row.get("ts")) for row in rows]
        row_times = [item for item in row_times if item is not None]
        start = min(row_times) if row_times else None
    if start is None:
        return None
    end = next((_timestamp(status.get(key)) for key in ends if _timestamp(status.get(key)) is not None), None)
    if end is None:
        end = time.time() if not status.get("complete") else start
    return max(0.0, end - start)


def _runtime_seconds(row: Mapping[str, Any]) -> float | None:
    direct = ("runtime_sec", "runtime_seconds", "elapsed_sec", "duration_sec", "wall_time_sec", "wall_clock_sec")
    for key in direct:
        value = _number(row.get(key))
        if value is not None:
            return max(0.0, value)
    metrics = row.get("runtime_metrics")
    if isinstance(metrics, Mapping):
        for key in direct:
            value = _number(metrics.get(key))
            if value is not None:
                return max(0.0, value)
    agent = _number(row.get("agent_elapsed_sec"))
    verifier = _number(row.get("verifier_elapsed_sec"))
    if agent is not None or verifier is not None:
        return max(0.0, (agent or 0.0) + (verifier or 0.0))
    return None


def _truncate(value: Any, width: int = MAX_CELL_WIDTH) -> str:
    text = str(value) if value not in (None, "") else "—"
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    return text[: max(1, width - 1)] + "…"


def _safe_failure(row: Mapping[str, Any]) -> str:
    status = str(row.get("status") or "").upper()
    failure = row.get("failure_code")
    if failure in (None, "", "NONE") and status in {"PASS", "REJECT"}:
        return "—"
    return _truncate(failure if failure not in (None, "") else "—", 28)


def _task_ids(status: Mapping[str, Any], visible_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    configured = status.get("tasks")
    result: list[str] = []
    if isinstance(configured, (list, tuple)):
        for value in configured:
            task = str(value)
            if task and task not in result:
                result.append(task)
    for row in visible_rows:
        task = str(row.get("task_id") or row.get("task") or "")
        if task and task not in result:
            result.append(task)
    return result


def _counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key in ("PASS", "REJECT", "TIME_LIMIT", "INFRA_BLOCKED")}
    for row in rows:
        status = str(row.get("status") or "").upper()
        if status in counts:
            counts[status] += 1
    return counts


def _snapshot_counts(status: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = _counts(rows)
    summary = status.get("summary")
    by_status = summary.get("by_status") if isinstance(summary, Mapping) else None
    if not isinstance(by_status, Mapping):
        return counts
    for key in counts:
        value = _integer(by_status.get(key), 0)
        counts[key] = value or 0
    return counts


def _snapshot_rows(status: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summary = status.get("summary")
    by_status = summary.get("by_status") if isinstance(summary, Mapping) else None
    if not isinstance(by_status, Mapping):
        return [dict(row) for row in rows]
    remaining = {
        key: _integer(by_status.get(key), 0) or 0
        for key in ("PASS", "REJECT", "TIME_LIMIT", "INFRA_BLOCKED")
    }
    selected: list[dict[str, Any]] = []
    for row in reversed(rows):
        row_status = str(row.get("status") or "").upper()
        if remaining.get(row_status, 0) > 0:
            selected.append(dict(row))
            remaining[row_status] -= 1
    selected.reverse()
    return selected


def render_snapshot(
    run_id: str,
    status: Mapping[str, Any] | None,
    rows: Sequence[Mapping[str, Any]],
    *,
    now: float | None = None,
    color: bool = False,
) -> str:
    """Render one bounded, credential-free snapshot as plain text."""
    visible = latest_unsuperseded_rows(rows)
    if status is None:
        return f"Run {_truncate(run_id, 80)!r} not found or status is temporarily unavailable."
    visible = _snapshot_rows(status, visible)

    state = str(status.get("run_state") or ("complete" if status.get("complete") else "running")).upper()
    complete = _integer(status.get("completed_trials"), len(visible)) or 0
    running = _integer(status.get("running_trials"), 0) or 0
    total = _integer(status.get("total_trials"))
    task_ids = _task_ids(status, visible)
    if total is None:
        total = len(task_ids)
    pending = _integer(status.get("pending_trials"))
    if pending is None:
        pending = max(0, total - complete - running)
    concurrency = _integer(status.get("effective_concurrency"), _integer(status.get("concurrency")))
    pause_reason = status.get("pause_reason")
    elapsed = _format_duration(_elapsed_seconds(status, rows, now))
    counts = _snapshot_counts(status, visible)

    lines = [f"Quant Bench run: {_truncate(run_id, 100)}"]
    lines.append(
        f"State: {state}    Progress: {complete}/{running}/{pending}/{total} "
        "(completed/running/pending/total)"
    )
    lines.append(f"Concurrency: {concurrency if concurrency is not None else '—'}    Elapsed: {elapsed}")
    lines.append(f"Pause: {_truncate(pause_reason, 60) if pause_reason else '—'}")
    lines.append(
        "Results: " + "  ".join(f"{name}={counts[name]}" for name in ("PASS", "REJECT", "TIME_LIMIT", "INFRA_BLOCKED"))
    )
    lines.append("")

    headers = ("Task", "Agent", "Status", "Failure", "Runtime")
    widths = (42, 28, 16, 28, 12)
    lines.append("  ".join(header.ljust(width) for header, width in zip(headers, widths)).rstrip())
    lines.append("  ".join("-" * width for width in widths).rstrip())

    by_task = latest_task_rows(rows)
    for index, task in enumerate(task_ids[:MAX_TASK_ROWS]):
        row = by_task.get(task)
        if row is None:
            cells = (task, "—", "PENDING", "—", "—")
        else:
            row_status = str(row.get("status") or "UNKNOWN").upper()
            cells = (
                task,
                row.get("agent") or row.get("name") or "—",
                row_status,
                _safe_failure(row),
                _format_duration(_runtime_seconds(row)),
            )
            if color and row_status in {"PASS", "REJECT", "TIME_LIMIT", "INFRA_BLOCKED"}:
                code = {"PASS": "32", "REJECT": "31", "TIME_LIMIT": "33", "INFRA_BLOCKED": "35"}[row_status]
                cells = (*cells[:2], f"\033[{code}m{cells[2]}\033[0m", *cells[3:])
        rendered = []
        for value, width in zip(cells, widths):
            text = _truncate(value, width)
            # ANSI sequences should not affect visible padding.
            visible_text = text.replace("\033[32m", "").replace("\033[31m", "").replace("\033[33m", "").replace("\033[35m", "").replace("\033[0m", "")
            rendered.append(text + " " * max(0, width - len(visible_text)))
        lines.append("  ".join(rendered).rstrip())
    if len(task_ids) > MAX_TASK_ROWS:
        lines.append(f"… {len(task_ids) - MAX_TASK_ROWS} additional tasks omitted")
    return "\n".join(lines)


def render_dashboard(
    snapshots: Sequence[tuple[str, Mapping[str, Any] | None, Sequence[Mapping[str, Any]]]],
    *,
    now: float | None = None,
    color: bool = False,
) -> str:
    """Render several benchmark runs as one expanded dashboard."""
    totals = {key: 0 for key in ("complete", "running", "pending", "total", "concurrency")}
    counts = {key: 0 for key in ("PASS", "REJECT", "TIME_LIMIT", "INFRA_BLOCKED")}
    states: dict[str, int] = {}
    sections: list[str] = []
    for run_id, status, rows in snapshots:
        sections.append(render_snapshot(run_id, status, rows, now=now, color=color))
        if status is None:
            states["UNAVAILABLE"] = states.get("UNAVAILABLE", 0) + 1
            continue
        visible = _snapshot_rows(status, latest_unsuperseded_rows(rows))
        state = str(status.get("run_state") or ("complete" if status.get("complete") else "running")).upper()
        states[state] = states.get(state, 0) + 1
        complete = _integer(status.get("completed_trials"), len(visible)) or 0
        running = _integer(status.get("running_trials"), 0) or 0
        total = _integer(status.get("total_trials"), complete + running) or 0
        pending = _integer(status.get("pending_trials"), max(0, total - complete - running)) or 0
        concurrency = _integer(status.get("effective_concurrency"), _integer(status.get("concurrency"))) or 0
        totals["complete"] += complete
        totals["running"] += running
        totals["pending"] += pending
        totals["total"] += total
        totals["concurrency"] += concurrency
        current_counts = _snapshot_counts(status, visible)
        for key in counts:
            counts[key] += current_counts[key]
    state_text = "  ".join(f"{key}={value}" for key, value in sorted(states.items()))
    lines = [
        f"Quant Bench dashboard: {len(snapshots)} runs",
        f"States: {state_text or '—'}",
        (
            f"Overall progress: {totals['complete']}/{totals['running']}/{totals['pending']}/{totals['total']} "
            "(completed/running/pending/total)"
        ),
        f"Active workers: {totals['running']}    Configured concurrency: {totals['concurrency']}",
        "Overall results: " + "  ".join(f"{key}={counts[key]}" for key in counts),
        "",
        ("═" * 120).join(f"\n{section}\n" for section in sections).strip(),
    ]
    return "\n".join(lines)


class BenchWatch:
    """Stateful reader that retains the last valid status during write races."""

    def __init__(self, run_id: str, artifact_root: str | os.PathLike[str]) -> None:
        self.run_id = run_id
        self.run_dir = resolve_run_dir(run_id, artifact_root)
        self.status: dict[str, Any] | None = None
        self.rows: list[dict[str, Any]] = []

    def refresh(self) -> None:
        snapshot = load_status_snapshot(self.run_dir / "status.json")
        if snapshot is not None:
            self.status = snapshot
        # Unlike status, results are append-only: a temporary read failure can
        # safely retain the prior complete set rather than flashing empty data.
        result_path = self.run_dir / "results.jsonl"
        if result_path.exists():
            loaded = load_results_jsonl(result_path)
            if loaded or result_path.stat().st_size == 0:
                self.rows = loaded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch one or more Quant Bench runs (read-only).")
    parser.add_argument("run_ids", metavar="RUN_ID", nargs="+")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT), help="Artifact root containing run directories")
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds (default: 2)")
    parser.add_argument("--once", action="store_true", help="Render one snapshot and exit")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI clearing and status colors")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.interval < 0:
        print("bench_watch: --interval must be non-negative", file=sys.stderr)
        return 2
    try:
        watches = [BenchWatch(run_id, args.artifact_root) for run_id in args.run_ids]
    except ValueError as exc:
        print(f"bench_watch: {exc}", file=sys.stderr)
        return 2

    is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    interactive = is_tty and not args.once
    try:
        while True:
            for watch in watches:
                watch.refresh()
            missing = [watch for watch in watches if watch.status is None and not watch.run_dir.exists()]
            if len(missing) == len(watches):
                for watch in missing:
                    print(render_snapshot(watch.run_id, None, watch.rows))
                return 1
            if interactive and not args.no_color:
                # Erase scrollback plus the viewport so each refresh replaces
                # the prior dashboard while retaining the current snapshot for copy mode.
                print("\033[3J\033[2J\033[H", end="")
            color = interactive and not args.no_color
            if len(watches) == 1:
                output = render_snapshot(watches[0].run_id, watches[0].status, watches[0].rows, color=color)
            else:
                output = render_dashboard(
                    [(watch.run_id, watch.status, watch.rows) for watch in watches],
                    color=color,
                )
            print(output, flush=True)
            # Non-TTY output is intentionally one bounded snapshot. A caller
            # that wants follow mode can allocate a TTY; --once is deterministic
            # in both environments.
            if args.once or not is_tty:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
