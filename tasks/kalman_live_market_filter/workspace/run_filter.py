#!/usr/bin/env python3
"""Run Kalman filter on market observations."""

import json
import sys
from pathlib import Path
from market_filter import filter_series


def round_floats(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    elif isinstance(obj, dict):
        return {k: round_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [round_floats(x) for x in obj]
    return obj


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    config_path = workspace / "config.json"
    obs_path = workspace / "observations.json"
    output_dir = workspace / "outputs"
    output_path = output_dir / "filtered_market.json"

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    with open(obs_path, "r", encoding="utf-8") as f:
        observations = json.load(f)

    result = filter_series(config, observations)
    rounded_result = round_floats(result)

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(rounded_result, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main()
