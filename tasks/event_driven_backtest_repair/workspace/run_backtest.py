#!/usr/bin/env python3
"""CLI for the event-driven CSV backtester."""
from __future__ import annotations

import argparse
from pathlib import Path

from backtester import run_backtest


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prices", type=Path, default=root / "prices.csv")
    parser.add_argument("--signals", type=Path, default=root / "signals.csv")
    parser.add_argument("--actions", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=root / "config.json")
    parser.add_argument("--output-dir", type=Path, default=root / "outputs")
    parser.add_argument("--seed", type=int, default=100)
    args = parser.parse_args(argv)
    config_path = args.config if args.config.exists() else None
    run_backtest(args.prices, args.signals, args.actions, args.output_dir,
                 config_path=config_path, seed=args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
