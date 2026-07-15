"""Constrained minimum-variance portfolio optimization starter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class OptimizationResult:
    weights: np.ndarray | None
    objective: float | None
    success: bool
    status: str
    message: str
    expected_return: float | None = None
    turnover: float | None = None

    @property
    def variance(self) -> float | None:
        return self.objective

    def as_dict(self) -> dict[str, Any]:
        return {
            "weights": None if self.weights is None else self.weights.tolist(),
            "objective": self.objective,
            "variance": self.objective,
            "success": self.success,
            "status": self.status,
            "message": self.message,
            "expected_return": self.expected_return,
            "turnover": self.turnover,
        }


def min_variance_portfolio(
    covariance: Any,
    expected_returns: Any | None = None,
    *,
    target_return: float | None = None,
    bounds: Any | None = None,
    sector_labels: Any | None = None,
    sector_bounds: Any | None = None,
    previous_weights: Any | None = None,
    turnover_limit: float | None = None,
    ridge: float = 1e-8,
    mean_returns: Any | None = None,
    returns: Any | None = None,
) -> OptimizationResult:
    """Stub: implement the constrained minimum-variance optimizer."""
    raise NotImplementedError("implement min_variance_portfolio")
