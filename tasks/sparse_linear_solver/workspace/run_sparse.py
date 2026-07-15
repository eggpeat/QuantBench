#!/usr/bin/env python3
"""Run the public sparse-solver fixture and write a JSON report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import sparse_solver


def main() -> None:
    root = Path(__file__).resolve().parent
    data = json.loads((root / "input.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(data["seed"])
    n = data["n"]
    diag = data["diag"]
    off = data["offdiag"]

    indptr = np.zeros(n + 1, dtype=np.int64)
    indices = []
    data_vals = []
    for i in range(n):
        row_cols = []
        row_vals = []
        if i > 0:
            row_cols.append(i - 1)
            row_vals.append(off)
        row_cols.append(i)
        row_vals.append(diag)
        if i < n - 1:
            row_cols.append(i + 1)
            row_vals.append(off)
        indices.extend(row_cols)
        data_vals.extend(row_vals)
        indptr[i + 1] = indptr[i] + len(row_cols)

    b = rng.normal(size=n) * data["rhs_scale"]
    result = sparse_solver.pcg(
        indptr,
        np.array(indices, dtype=np.int64),
        np.array(data_vals, dtype=float),
        b,
        tol=data["tol"],
    )

    report = {
        "seed": data["seed"],
        "n": n,
        "converged": result.converged,
        "iterations": result.iterations,
        "residual_norm": result.residual_norm,
        "reason": result.reason,
        "x_l1": float(np.sum(np.abs(result.x))),
    }
    output = root / "outputs" / "sparse_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
