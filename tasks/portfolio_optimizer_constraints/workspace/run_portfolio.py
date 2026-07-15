#!/usr/bin/env python3
"""Run the deterministic public portfolio fixture and emit a JSON report."""
from __future__ import annotations

import json
from pathlib import Path

from portfolio import min_variance_portfolio


WORKSPACE = Path(__file__).resolve().parent


def main() -> None:
    data = json.loads((WORKSPACE / "input.json").read_text(encoding="utf-8"))
    result = min_variance_portfolio(
        data["covariance"],
        data["expected_returns"],
        target_return=data["target_return"],
        bounds=data["bounds"],
        sector_labels=data["sector_labels"],
        sector_bounds=data["sector_bounds"],
        previous_weights=data["previous_weights"],
        turnover_limit=data["turnover_limit"],
        ridge=data["ridge"],
    )
    report = {"seed": data["seed"], **result.as_dict()}
    output_dir = WORKSPACE / "outputs"
    output_dir.mkdir(exist_ok=True)
    (output_dir / "portfolio_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not result.success:
        raise SystemExit(f"portfolio optimization failed: {result.message}")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
