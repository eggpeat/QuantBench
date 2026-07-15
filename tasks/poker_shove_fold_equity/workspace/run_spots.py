"""Run the shove/fold evaluator against spots.json."""

import json
from pathlib import Path

from poker_ev import evaluate_spots


def main():
    workspace = Path.cwd()
    spots_path = workspace / "spots.json"
    output_path = workspace / "outputs" / "shove_fold.json"

    with spots_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    result = evaluate_spots(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
