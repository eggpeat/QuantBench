"""Intentional integrity mutant: classic unsplit R-hat without rank normalization."""
from __future__ import annotations
import json
import math
import sys
from pathlib import Path


def compute_rhat(chains_by_parameter):
    output = {}
    for name, chains in chains_by_parameter.items():
        m = len(chains)
        n = len(chains[0])
        means = [sum(c) / n for c in chains]
        within = sum(sum((x - mean) ** 2 for x in c) / (n - 1) for c, mean in zip(chains, means)) / m
        overall = sum(means) / m
        between = n * sum((mean - overall) ** 2 for mean in means) / (m - 1)
        output[name] = {"rhat": math.sqrt(((n - 1) * within + between) / (n * within))}
    return output


def solve(workspace: Path) -> None:
    chains = json.loads((workspace / "chains.json").read_text())
    result = compute_rhat(chains)
    output = workspace / "outputs"
    output.mkdir(exist_ok=True)
    (output / "rhat.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    solve(Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve())
