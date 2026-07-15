"""Run the side pot evaluator against hands.json."""

import json
from pathlib import Path

from side_pots import settle_all


def main():
    workspace = Path.cwd()
    hands_path = workspace / "hands.json"
    output_path = workspace / "outputs" / "settlements.json"

    with hands_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    # The payload has a list of hands under the "hands" key.
    settled = settle_all(payload["hands"])

    result = {"settlements": settled}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
