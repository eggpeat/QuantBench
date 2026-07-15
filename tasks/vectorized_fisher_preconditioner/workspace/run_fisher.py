#!/usr/bin/env python3
"""Run the public Fisher fixture and write a JSON report."""
from __future__ import annotations

import json
from pathlib import Path

import fisher


def main() -> None:
    root = Path(__file__).resolve().parent
    data = json.loads((root / "input.json").read_text(encoding="utf-8"))
    result = fisher.precondition_diagonal(
        data["raw_grad"], data["fisher_diag"], floor=data["floor"]
    )
    result = result.tolist()
    report = {
        "seed": data["seed"],
        "shape": list(result and [len(result), len(result[0])]),
        "values": result,
        "l1": float(sum(abs(value) for row in result for value in row)),
    }
    output = root / "outputs" / "fisher_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
