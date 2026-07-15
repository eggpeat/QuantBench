#!/usr/bin/env python3
"""Intentional dense-matrix mutant."""
import os
import sys
from pathlib import Path

_MUTANT = r'''"""Dense-matrix PCG (intentionally violates the no-densify rule)."""
from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class SolverResult:
    x: np.ndarray
    converged: bool
    iterations: int
    residual_norm: float
    reason: Literal["converged", "max_iter", "non_spd", "singular_preconditioner", "invalid_input"]


def pcg(indptr, indices, data, b, *, x0=None, tol=1e-8, max_iter=None, preconditioner="jacobi"):
    n = len(indptr) - 1
    b = np.asarray(b, dtype=float)
    if max_iter is None:
        max_iter = 10 * n
    A = np.zeros((n, n), dtype=float)
    for i in range(n):
        for idx in range(indptr[i], indptr[i + 1]):
            A[i, indices[idx]] = data[idx]
    try:
        x = np.linalg.solve(A, b)
        return SolverResult(
            x=x,
            converged=True,
            iterations=0,
            residual_norm=float(np.linalg.norm(b - A @ x)),
            reason="converged",
        )
    except np.linalg.LinAlgError:
        return SolverResult(
            x=np.zeros(n, dtype=float),
            converged=False,
            iterations=0,
            residual_norm=float(np.linalg.norm(b)),
            reason="non_spd",
        )
'''


def main() -> None:
    workspace = Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve()
    (workspace / "sparse_solver.py").write_text(_MUTANT, encoding="utf-8")


if __name__ == "__main__":
    main()
