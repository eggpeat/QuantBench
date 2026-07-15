#!/usr/bin/env python3
"""Run the seeded public temporal EP fixture and write a JSON report."""
from __future__ import annotations

import json
from pathlib import Path

from temporal_ep import fit_temporal_states


root = Path(__file__).resolve().parent
with (root / "input.json").open(encoding="utf-8") as fh:
    data = json.load(fh)
result = fit_temporal_states(
    data["times"], data["outcomes"], data["weights"],
    likelihood=data["likelihood"], process_var=data["process_var"],
    initial_mean=data["initial_mean"], initial_var=data["initial_var"],
    quadrature_order=data["quadrature_order"],
)
report = {"seed": data["seed"]}
for key, value in result.items():
    report[key] = value.tolist() if hasattr(value, "tolist") else value
(root / "outputs").mkdir(exist_ok=True)
with (root / "outputs" / "temporal_report.json").open("w", encoding="utf-8") as fh:
    json.dump(report, fh, sort_keys=True, separators=(",", ":"))
    fh.write("\n")
