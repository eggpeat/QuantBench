"""Adaptive Dormand–Prince RK45 starter."""
from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass
class OdeResult:
    t: np.ndarray
    y: np.ndarray
    status: Literal["finished", "event", "failed"]
    n_steps: int
    n_rejected: int
    t_events: list[np.ndarray]
    y_events: list[np.ndarray]
    message: str


def integrate_rk45(fun, t_span, y0, *, rtol=1e-6, atol=1e-9, max_step=np.inf, events=None) -> OdeResult:
    raise NotImplementedError("implement adaptive RK45 integration")
