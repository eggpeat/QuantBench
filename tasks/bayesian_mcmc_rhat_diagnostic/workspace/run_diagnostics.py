"""Run rank-normalized split R-hat diagnostics for workspace chains."""

import json
from pathlib import Path

from diagnostics import compute_rhat


def main() -> None:
    workspace = Path(__file__).resolve().parent
    with (workspace / "chains.json").open("r", encoding="utf-8") as handle:
        chains = json.load(handle)
    result = compute_rhat(chains)
    output_dir = workspace / "outputs"
    output_dir.mkdir(exist_ok=True)
    with (output_dir / "rhat.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
