"""Sparse preconditioned conjugate-gradient starter."""
from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass
class SolverResult:
    x: np.ndarray
    converged: bool
    iterations: int
    residual_norm: float
    reason: Literal["converged", "max_iter", "non_spd", "singular_preconditioner", "invalid_input"]


def pcg(indptr, indices, data, b, *, x0=None, tol=1e-8, max_iter=None, preconditioner="jacobi") -> SolverResult:
    raise NotImplementedError("implement sparse PCG without densifying")
