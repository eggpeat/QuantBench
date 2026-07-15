"""Oracle solution for rank-normalized split R-hat diagnostics."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


DIAGNOSTICS_SOURCE = r'''"""Rank-normalized split R-hat and effective sample sizes."""

from __future__ import annotations

import math
from numbers import Real
from statistics import NormalDist


def _validate_chains(parameter, chains):
    if not isinstance(chains, (list, tuple)) or len(chains) < 2:
        raise ValueError(f"{parameter} must contain at least two chains")
    if not all(isinstance(chain, (list, tuple)) for chain in chains):
        raise ValueError(f"{parameter} chains must be sequences")
    n = len(chains[0])
    if n < 4:
        raise ValueError(f"{parameter} chains must contain at least four draws")
    for chain in chains:
        if len(chain) != n:
            raise ValueError(f"{parameter} chains must have equal lengths")
        for draw in chain:
            if isinstance(draw, bool) or not isinstance(draw, Real):
                raise ValueError(f"{parameter} contains a non-numeric draw")
            if not math.isfinite(float(draw)):
                raise ValueError(f"{parameter} contains a non-finite draw")
    return n


def _rankdata(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        value = values[order[i]]
        while j < len(order) and values[order[j]] == value:
            j += 1
        rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = rank
        i = j
    return ranks


def _split_chains(chains):
    n = len(chains[0])
    half = n // 2
    usable = 2 * half
    return [list(chain[:half]) for chain in chains] + [list(chain[half:usable]) for chain in chains]


def _rhat(chains):
    m = len(chains)
    n = len(chains[0])
    means = [sum(chain) / n for chain in chains]
    variances = [
        sum((value - mean) ** 2 for value in chain) / (n - 1)
        for chain, mean in zip(chains, means)
    ]
    within = sum(variances) / m
    overall = sum(means) / m
    between = n * sum((mean - overall) ** 2 for mean in means) / (m - 1)
    if within == 0.0:
        return 1.0 if between == 0.0 else math.inf
    variance_hat = ((n - 1.0) / n) * within + between / n
    return max(1.0, math.sqrt(max(variance_hat / within, 0.0)))


def _autocovariance(chain, lag):
    n = len(chain)
    mean = sum(chain) / n
    return sum((chain[i] - mean) * (chain[i + lag] - mean) for i in range(n - lag)) / n


def _autocorrelation_ess(chains):
    """Vehtari/Stan split-chain ESS with Geyer's initial monotone sequence."""
    m = len(chains)
    n = len(chains[0])
    total_n = m * n
    means = [sum(chain) / n for chain in chains]
    variances = [
        sum((value - mean) ** 2 for value in chain) / (n - 1)
        for chain, mean in zip(chains, means)
    ]
    within = sum(variances) / m
    overall = sum(means) / m
    between = n * sum((mean - overall) ** 2 for mean in means) / (m - 1)
    variance_plus = ((n - 1.0) / n) * within + between / n
    if variance_plus <= 1e-30:
        return float(total_n)
    rho = [1.0]
    for lag in range(1, n):
        mean_autocovariance = sum(_autocovariance(chain, lag) for chain in chains) / m
        rho.append(1.0 - (within - mean_autocovariance) / variance_plus)
    pairs = []
    previous = math.inf
    for lag in range(1, n - 1, 2):
        pair = rho[lag] + rho[lag + 1]
        if not math.isfinite(pair) or pair < 0.0:
            break
        pair = min(pair, previous)
        pairs.append(pair)
        previous = pair
    tau = max(1.0, 1.0 + 2.0 * sum(pairs))
    return min(float(total_n), max(1.0, total_n / tau))


def _quantile(values, probability):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def _tail_ess(raw_chains):
    values = [value for chain in raw_chains for value in chain]
    low = _quantile(values, 0.05)
    high = _quantile(values, 0.95)
    low_chains = [[1.0 if value <= low else 0.0 for value in chain] for chain in raw_chains]
    high_chains = [[1.0 if value >= high else 0.0 for value in chain] for chain in raw_chains]
    return min(_autocorrelation_ess(low_chains), _autocorrelation_ess(high_chains))


def compute_rhat(chains_by_parameter):
    """Return rank-normalized split R-hat, bulk ESS, and tail ESS."""
    if not isinstance(chains_by_parameter, dict):
        raise ValueError("chains_by_parameter must be a mapping")
    diagnostics = {}
    for parameter, chains in chains_by_parameter.items():
        n_original = _validate_chains(parameter, chains)
        split = _split_chains(chains)
        flat = [value for chain in split for value in chain]
        ranks = _rankdata(flat)
        normal = NormalDist()
        normalized = [normal.inv_cdf((rank - 0.5) / len(flat)) for rank in ranks]
        normalized_chains = [
            normalized[offset : offset + len(split[0])]
            for offset in range(0, len(normalized), len(split[0]))
        ]
        ordered = sorted(flat)
        midpoint = len(ordered) // 2
        median = (
            ordered[midpoint]
            if len(ordered) % 2
            else (ordered[midpoint - 1] + ordered[midpoint]) / 2.0
        )
        folded = [abs(value - median) for value in flat]
        folded_ranks = _rankdata(folded)
        folded_normalized = [
            normal.inv_cdf((rank - 0.5) / len(folded))
            for rank in folded_ranks
        ]
        folded_chains = [
            folded_normalized[offset : offset + len(split[0])]
            for offset in range(0, len(folded_normalized), len(split[0]))
        ]
        rhat = max(_rhat(normalized_chains), _rhat(folded_chains))
        bulk_ess = _autocorrelation_ess(normalized_chains)
        tail_ess = _tail_ess(split)
        diagnostics[parameter] = {
            "rhat": round(rhat, 6) if math.isfinite(rhat) else math.inf,
            "ess_bulk": round(bulk_ess, 6),
            "ess_tail": round(tail_ess, 6),
            "n_chains": len(chains),
            "draws_per_chain": n_original,
        }
    return diagnostics
'''


RUNNER_SOURCE = r'''"""Run rank-normalized split R-hat diagnostics for workspace chains."""

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
'''


def solve(workspace: Path) -> None:
    (workspace / "diagnostics.py").write_text(DIAGNOSTICS_SOURCE, encoding="utf-8")
    (workspace / "run_diagnostics.py").write_text(RUNNER_SOURCE, encoding="utf-8")
    namespace = {}
    exec(DIAGNOSTICS_SOURCE, namespace)
    with (workspace / "chains.json").open("r", encoding="utf-8") as handle:
        chains = json.load(handle)
    result = namespace["compute_rhat"](chains)
    output_dir = workspace / "outputs"
    output_dir.mkdir(exist_ok=True)
    with (output_dir / "rhat.json").open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> None:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    solve(workspace.resolve())


if __name__ == "__main__":
    main()
