"""Scalar Gaussian random-walk expectation propagation starter."""
from __future__ import annotations

from typing import Any

import numpy as np


def fit_temporal_states(
    times: Any,
    outcomes: Any,
    weights: Any,
    *,
    likelihood: str,
    process_var: float,
    initial_mean: float = 0.0,
    initial_var: float = 1.0,
    quadrature_order: int = 20,
) -> dict[str, Any]:
    """Stub: implement weighted scalar temporal EP."""
    raise NotImplementedError("implement fit_temporal_states")
