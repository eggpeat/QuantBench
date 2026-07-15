#!/usr/bin/env python3
"""Run the Kalman 2D filter on observations and write the outputs."""

import csv
import json
import os
import sys
from pathlib import Path

# Add current directory to path so we can import kalman2d
sys.path.insert(0, str(Path(__file__).parent))
import kalman2d


def round_floats(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    elif isinstance(obj, list):
        return [round_floats(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: round_floats(v) for k, v in obj.items()}
    return obj


def main():
    workspace_dir = Path(__file__).parent
    config_path = workspace_dir / "config.json"
    obs_path = workspace_dir / "observations.csv"
    output_path = workspace_dir / "outputs" / "filtered_states.json"

    # Load configuration
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # Load observations from CSV
    rows = []
    with open(obs_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                time_val = int(row["time"])
            except ValueError:
                time_val = float(row["time"])

            rows.append({
                "time": time_val,
                "price": float(row["price"])
            })

    # Run the Kalman filter
    result = kalman2d.filter_series(rows, config)

    # Round all output float values
    rounded_result = round_floats(result)

    # Write output to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rounded_result, f, indent=2)


if __name__ == "__main__":
    main()
