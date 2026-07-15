#!/usr/bin/env python3
"""Run the public CRPS fixture and write a JSON report."""
from __future__ import annotations

import json
from pathlib import Path

import scoring


def main() -> None:
    root = Path(__file__).resolve().parent
    data = json.loads((root / "input.json").read_text(encoding="utf-8"))
    weights = data["sample_weight"]
    gaussian = scoring.gaussian_crps(data["mu"], data["sigma"], data["y"], weights)
    empirical = scoring.empirical_crps(data["samples"], data["y"], weights)
    report = {
        "seed": data["seed"],
        "gaussian_crps": float(gaussian),
        "empirical_crps": float(empirical),
    }
    output = root / "outputs" / "scoring_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
