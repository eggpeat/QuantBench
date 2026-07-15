#!/usr/bin/env python3
"""Intentional fixed-step mutant that ignores adaptive error control."""
import os
import sys
from pathlib import Path

_MUTANT = r'''"""Fixed-step ODE integrator (ignores error estimation)."""
from dataclasses import dataclass
from typing import Callable, List

import numpy as np


@dataclass(frozen=True)
class OdeResult:
    t: np.ndarray
    y: np.ndarray
    status: str  # one of "finished", "event", "failed"
    n_steps: int
    n_rejected: int
    t_events: List[np.ndarray]
    y_events: List[np.ndarray]
    message: str


def integrate_rk45(
    fun,
    t_span,
    y0,
    *,
    rtol=1e-6,
    atol=1e-9,
    max_step=float("inf"),
    events=None,
):
    t0, tf = float(t_span[0]), float(t_span[1])
    y = np.atleast_1d(np.asarray(y0, dtype=float)).copy()
    direction = 1 if tf >= t0 else -1
    h = 0.05 * direction
    if max_step != float("inf"):
        h = min(abs(h), max_step) * direction
    t = t0
    ts = [t]
    ys = [y.copy()]
    n_steps = 0
    while (direction > 0 and t < tf) or (direction < 0 and t > tf):
        remaining = tf - t
        if direction > 0:
            h = min(h, remaining)
        else:
            h = max(h, remaining)
        if h == 0.0:
            break
        # One fixed RK4 step.
        k1 = np.asarray(fun(t, y), dtype=float)
        k2 = np.asarray(fun(t + h / 2, y + h * k1 / 2), dtype=float)
        k3 = np.asarray(fun(t + h / 2, y + h * k2 / 2), dtype=float)
        k4 = np.asarray(fun(t + h, y + h * k3), dtype=float)
        y = y + (h / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        t = t + h
        n_steps += 1
        ts.append(t)
        ys.append(y.copy())
    return OdeResult(
        t=np.array(ts, dtype=float),
        y=np.column_stack(ys),
        status="finished",
        n_steps=n_steps,
        n_rejected=0,
        t_events=[np.array([], dtype=float) for _ in (events or [])],
        y_events=[np.empty((y.shape[0], 0)) for _ in (events or [])],
        message="Fixed-step integration finished",
    )
'''


def main() -> None:
    workspace = Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve()
    (workspace / "ode.py").write_text(_MUTANT, encoding="utf-8")


if __name__ == "__main__":
    main()
