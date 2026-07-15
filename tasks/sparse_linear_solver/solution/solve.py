#!/usr/bin/env python3
"""General oracle: install the reference sparse PCG solver and run the fixture CLI."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

_REFERENCE = r'''"""Sparse preconditioned conjugate-gradient solver."""
from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class SolverResult:
    """Result of pcg."""

    x: np.ndarray
    converged: bool
    iterations: int
    residual_norm: float
    reason: Literal["converged", "max_iter", "non_spd", "singular_preconditioner", "invalid_input"]


def _validate(indptr, indices, data, b):
    indptr = np.asarray(indptr)
    indices = np.asarray(indices)
    data = np.asarray(data)
    b = np.asarray(b, dtype=float)
    if (
        indptr.ndim != 1
        or indices.ndim != 1
        or data.ndim != 1
        or b.ndim != 1
        or indptr.dtype.kind not in "iub"
        or indices.dtype.kind not in "iub"
    ):
        raise ValueError("invalid sparse matrix inputs")
    n = len(indptr) - 1
    if n < 0 or len(b) != n:
        raise ValueError("dimension mismatch")
    if len(indices) != len(data):
        raise ValueError("indices and data length mismatch")
    if n == 0:
        return indptr, indices, data, b, 0
    if indptr[0] != 0 or indptr[-1] != len(data):
        raise ValueError("invalid indptr")
    if not np.all(np.diff(indptr) >= 0):
        raise ValueError("invalid indptr")
    if len(indices) > 0:
        if indices.min() < 0 or indices.max() >= n:
            raise ValueError("column index out of bounds")
    if not np.all(np.isfinite(data)) or not np.all(np.isfinite(b)):
        raise ValueError("non-finite inputs")
    return indptr, indices, data, b, n


def _csr_matvec(indptr, indices, data, x):
    n = len(indptr) - 1
    row_counts = np.diff(indptr)
    row_idx = np.repeat(np.arange(n, dtype=np.int64), row_counts)
    return np.bincount(row_idx, weights=data * x[indices], minlength=n)


def _csr_diagonal(indptr, indices, data, n):
    diag = np.zeros(n, dtype=float)
    for i in range(n):
        for idx in range(indptr[i], indptr[i + 1]):
            if indices[idx] == i:
                diag[i] = data[idx]
                break
    return diag


def pcg(
    indptr,
    indices,
    data,
    b,
    *,
    x0=None,
    tol: float = 1e-8,
    max_iter: int | None = None,
    preconditioner: str = "jacobi",
) -> SolverResult:
    """Solve a sparse SPD system with preconditioned conjugate gradients."""
    indptr, indices, data, b, n = _validate(indptr, indices, data, b)
    if n == 0:
        return SolverResult(
            x=np.zeros(0, dtype=float),
            converged=True,
            iterations=0,
            residual_norm=0.0,
            reason="converged",
        )

    if max_iter is None:
        max_iter = 10 * n
    if max_iter < 0:
        raise ValueError("max_iter must be non-negative")
    if tol < 0.0 or not np.isfinite(tol):
        raise ValueError("tol must be finite and non-negative")

    if preconditioner == "jacobi":
        diag = _csr_diagonal(indptr, indices, data, n)
        if np.any(diag == 0.0):
            return SolverResult(
                x=np.zeros(n, dtype=float),
                converged=False,
                iterations=0,
                residual_norm=float(np.linalg.norm(b)),
                reason="singular_preconditioner",
            )
        m_inv = 1.0 / diag
    elif preconditioner == "none":
        m_inv = np.ones(n, dtype=float)
    else:
        raise ValueError(f"unknown preconditioner: {preconditioner}")

    x = np.zeros(n, dtype=float) if x0 is None else np.asarray(x0, dtype=float).copy()
    if len(x) != n:
        raise ValueError("x0 dimension mismatch")

    r = b - _csr_matvec(indptr, indices, data, x)
    z = m_inv * r
    p = z.copy()
    rz = float(r @ z)
    norm_b = float(np.linalg.norm(b))
    threshold = tol * max(norm_b, 1.0)

    residual_norm = float(np.linalg.norm(r))
    if residual_norm <= threshold:
        return SolverResult(
            x=x,
            converged=True,
            iterations=0,
            residual_norm=residual_norm,
            reason="converged",
        )

    for k in range(max_iter):
        ap = _csr_matvec(indptr, indices, data, p)
        p_ap = float(p @ ap)
        if p_ap <= 0.0:
            return SolverResult(
                x=x,
                converged=False,
                iterations=k,
                residual_norm=residual_norm,
                reason="non_spd",
            )
        alpha = rz / p_ap
        x += alpha * p
        r -= alpha * ap
        residual_norm = float(np.linalg.norm(r))
        if residual_norm <= threshold:
            return SolverResult(
                x=x,
                converged=True,
                iterations=k + 1,
                residual_norm=residual_norm,
                reason="converged",
            )
        z = m_inv * r
        rz_new = float(r @ z)
        beta = rz_new / rz
        p = z + beta * p
        rz = rz_new

    return SolverResult(
        x=x,
        converged=False,
        iterations=max_iter,
        residual_norm=residual_norm,
        reason="max_iter",
    )
'''


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if not (workspace / "input.json").is_file():
        workspace = root / "workspace"
    (workspace / "sparse_solver.py").write_text(_REFERENCE, encoding="utf-8")
    sys.path.insert(0, str(workspace))
    old_cwd = Path.cwd()
    try:
        os.chdir(workspace)
        runpy.run_path(str(workspace / "run_sparse.py"), run_name="__main__")
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    main()
