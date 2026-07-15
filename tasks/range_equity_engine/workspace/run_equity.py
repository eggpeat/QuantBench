#!/usr/bin/env python3
"""Runner script to evaluate range equity scenarios."""

import json
import os
from pathlib import Path
import range_equity

def main():
    workspace_dir = Path(__file__).parent
    scenarios_path = workspace_dir / "scenarios.json"
    output_dir = workspace_dir / "outputs"
    output_path = output_dir / "equity.json"

    if not scenarios_path.exists():
        print(f"Error: scenarios.json not found in {workspace_dir}")
        return

    with open(scenarios_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    results = []
    for scenario in data.get("scenarios", []):
        scenario_id = scenario["scenario_id"]
        p1_range = scenario["p1_range"]
        p2_range = scenario["p2_range"]
        board = scenario.get("board", [])

        print(f"Evaluating scenario: {scenario_id}...")
        p1_eq, p2_eq, tie_prob = range_equity.calculate_equity(p1_range, p2_range, board)

        results.append({
            "scenario_id": scenario_id,
            "p1_equity": round(p1_eq, 5),
            "p2_equity": round(p2_eq, 5),
            "tie_probability": round(tie_prob, 5)
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump({"scenarios": results}, fh, indent=2)
    print(f"Saved results to {output_path}")

if __name__ == "__main__":
    main()
