"""Event-driven CSV backtester exercise.

Implement ``run_backtest`` and the helpers used by ``run_backtest.py``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def run_backtest(
    prices_path: str | Path,
    signals_path: str | Path,
    actions_path: str | Path,
    output_dir: str | Path,
    *,
    config_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
    seed: int = 100,
) -> dict[str, float | int]:
    """Run the event stream and write trades.csv, equity.csv, metrics.json."""
    raise NotImplementedError("implement run_backtest")
