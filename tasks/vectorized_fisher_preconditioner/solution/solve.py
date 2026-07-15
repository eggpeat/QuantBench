#!/usr/bin/env python3
"""General oracle: install the reference implementation and run the fixture CLI."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

_REFERENCE = r'''"""Reference Fisher diagonal preconditioner."""
from __future__ import annotations
import numpy as np


def precondition_diagonal(raw_grad: np.ndarray, fisher_diag: np.ndarray, *, floor: float = 1e-30) -> np.ndarray:
    """Solve a diagonal Fisher system row-by-row without an N x P x P tensor.

    ``raw_grad`` is ``(N, P)`` (or one-dimensional ``(P,)``); ``fisher_diag``
    may have the same shape or one shared diagonal of shape ``(P,)``.
    """
    if isinstance(floor, (bool, np.bool_)) or not np.isscalar(floor):
        raise ValueError("floor must be a finite positive scalar")
    floor = float(floor)
    if not np.isfinite(floor) or floor <= 0.0:
        raise ValueError("floor must be a finite positive scalar")
    raw_obj = np.asarray(raw_grad)
    fisher_obj = np.asarray(fisher_diag)
    if raw_obj.dtype.kind not in "biufc" or fisher_obj.dtype.kind not in "biufc":
        raise ValueError("inputs must be numeric arrays")
    try:
        grad = np.asarray(raw_grad, dtype=np.float64)
        fisher = np.asarray(fisher_diag, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("inputs must be numeric arrays") from exc
    if grad.ndim == 0:
        grad = grad.reshape(1)
    if fisher.ndim == 0:
        valid = True
    elif fisher.shape == grad.shape:
        valid = True
    elif grad.ndim >= 1 and fisher.ndim == 1 and fisher.shape == (grad.shape[-1],):
        valid = True
    else:
        valid = False
    if not valid:
        raise ValueError("fisher_diag must match raw_grad or its final dimension")
    if not np.all(np.isfinite(grad)) or not np.all(np.isfinite(fisher)):
        raise ValueError("inputs must be finite")
    denominator = np.maximum(fisher, floor)
    output = grad / denominator
    return np.asarray(output, dtype=np.float64)
'''


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if not (workspace / "input.json").is_file():
        workspace = root / "workspace"
    (workspace / "fisher.py").write_text(_REFERENCE, encoding="utf-8")
    sys.path.insert(0, str(workspace))
    old_cwd = Path.cwd()
    try:
        os.chdir(workspace)
        runpy.run_path(str(workspace / "run_fisher.py"), run_name="__main__")
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    main()
