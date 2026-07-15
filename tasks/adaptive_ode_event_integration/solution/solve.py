#!/usr/bin/env python3
"""General oracle: install the reference RK45 integrator and run the fixture CLI."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

_REFERENCE = r'''"""Adaptive Dormand-Prince RK45 ODE integration with event detection."""
from dataclasses import dataclass
from typing import Callable, List

import numpy as np


@dataclass(frozen=True)
class OdeResult:
    """Result of integrate_rk45."""

    t: np.ndarray
    y: np.ndarray
    status: str  # one of "finished", "event", "failed"
    n_steps: int
    n_rejected: int
    t_events: List[np.ndarray]
    y_events: List[np.ndarray]
    message: str


_DP_C = np.array([0.0, 1.0 / 5.0, 3.0 / 10.0, 4.0 / 5.0, 8.0 / 9.0, 1.0, 1.0], dtype=float)
_DP_A = [
    [],
    [1.0 / 5.0],
    [3.0 / 40.0, 9.0 / 40.0],
    [44.0 / 45.0, -56.0 / 15.0, 32.0 / 9.0],
    [19372.0 / 6561.0, -25360.0 / 2187.0, 64448.0 / 6561.0, -212.0 / 729.0],
    [9017.0 / 3168.0, -355.0 / 33.0, 46732.0 / 5247.0, 49.0 / 176.0, -5103.0 / 18656.0],
    [35.0 / 384.0, 0.0, 500.0 / 1113.0, 125.0 / 192.0, -2187.0 / 6784.0, 11.0 / 84.0],
]
_DP_B5 = np.array([35.0 / 384.0, 0.0, 500.0 / 1113.0, 125.0 / 192.0, -2187.0 / 6784.0, 11.0 / 84.0, 0.0], dtype=float)
_DP_B4 = np.array([5179.0 / 57600.0, 0.0, 7571.0 / 16695.0, 393.0 / 640.0, -92097.0 / 339200.0, 187.0 / 2100.0, 1.0 / 40.0], dtype=float)


def _rk_step(fun, t, y, h):
    k = []
    for i in range(7):
        ti = t + _DP_C[i] * h
        yi = y.copy()
        for j in range(i):
            yi += h * _DP_A[i][j] * k[j]
        k.append(np.asarray(fun(ti, yi), dtype=float))
    y5 = y + h * np.tensordot(_DP_B5, k, axes=1)
    y4 = y + h * np.tensordot(_DP_B4, k, axes=1)
    return y5, y4, k


def _error_norm(y5, y4, y, rtol, atol):
    scale = atol + rtol * np.maximum(np.abs(y), np.abs(y5))
    err = y5 - y4
    return np.sqrt(np.mean((err / scale) ** 2))


def _hermite(t, t_old, y_old, t_new, y_new, k_old, k_new):
    h = t_new - t_old
    if h == 0.0:
        return y_old.copy()
    s = (t - t_old) / h
    s2 = s * s
    s3 = s2 * s
    return (
        (2.0 * s3 - 3.0 * s2 + 1.0) * y_old
        + (-2.0 * s3 + 3.0 * s2) * y_new
        + (s3 - 2.0 * s2 + s) * h * k_old
        + (s3 - s2) * h * k_new
    )


def _crossing(g_old, g_new, direction):
    if direction == 0:
        return g_old * g_new < 0.0 or g_new == 0.0
    if direction == 1:
        return g_old < 0.0 and g_new >= 0.0
    if direction == -1:
        return g_old > 0.0 and g_new <= 0.0
    return False


def _event_root(ev, t_old, y_old, t_new, y_new, k_old, k_new, rtol, atol):
    a, b = t_old, t_new
    g_a = float(ev(t_old, y_old))
    g_b = float(ev(t_new, y_new))
    if g_b == 0.0:
        return t_new, y_new.copy()
    tol = max(rtol * max(abs(a), abs(b)), atol)
    fa, fb = g_a, g_b
    # Ensure fa has the opposite sign to fb for bisection.
    while abs(b - a) > tol:
        mid = (a + b) / 2.0
        y_mid = _hermite(mid, t_old, y_old, t_new, y_new, k_old, k_new)
        g_mid = float(ev(mid, y_mid))
        if g_mid == 0.0:
            return mid, y_mid
        if fa * g_mid <= 0.0:
            b, fb = mid, g_mid
        else:
            a, fa = mid, g_mid
    t_root = (a + b) / 2.0
    y_root = _hermite(t_root, t_old, y_old, t_new, y_new, k_old, k_new)
    return t_root, y_root


def integrate_rk45(
    fun: Callable[[float, np.ndarray], np.ndarray],
    t_span: tuple[float, float] | list[float] | np.ndarray,
    y0: np.ndarray,
    *,
    rtol: float = 1e-6,
    atol: float = 1e-9,
    max_step: float = float("inf"),
    events: list[Callable[[float, np.ndarray], float]] | None = None,
) -> OdeResult:
    """Integrate an ODE with Dormand-Prince 5(4) and event detection."""
    t0, tf = float(t_span[0]), float(t_span[1])
    y0_arr = np.atleast_1d(np.asarray(y0, dtype=float)).copy()
    if y0_arr.ndim != 1:
        raise ValueError("y0 must be a 1-D array or scalar")

    if not np.isfinite(rtol) or rtol < 0.0:
        raise ValueError("rtol must be finite and non-negative")
    if not np.isfinite(atol) or atol < 0.0:
        raise ValueError("atol must be finite and non-negative")
    if max_step <= 0.0:
        raise ValueError("max_step must be positive")

    direction = 1 if tf >= t0 else -1
    eps = np.finfo(float).eps

    rtol_arr = np.broadcast_to(np.asarray(rtol, dtype=float), y0_arr.shape)
    atol_arr = np.broadcast_to(np.asarray(atol, dtype=float), y0_arr.shape)

    event_funcs = []
    event_terminal = []
    event_direction = []
    if events is not None:
        for ev in events:
            if not callable(ev):
                raise ValueError("events must be callable")
            event_funcs.append(ev)
            event_terminal.append(bool(getattr(ev, "terminal", False)))
            event_direction.append(int(getattr(ev, "direction", 0)))

    t_events = [[] for _ in event_funcs]
    y_events = [[] for _ in event_funcs]

    t = t0
    y = y0_arr.copy()
    ts = [t]
    ys = [y.copy()]
    n_steps = 0
    n_rejected = 0

    # Initial step size.
    total_span = tf - t0
    if total_span == 0.0:
        return OdeResult(
            t=np.array(ts, dtype=float),
            y=np.column_stack(ys) if ys else np.empty((y0_arr.shape[0], 0)),
            status="finished",
            n_steps=0,
            n_rejected=0,
            t_events=[np.array(arr, dtype=float) for arr in t_events],
            y_events=[np.empty((y0_arr.shape[0], 0)) for _ in event_funcs],
            message="Zero-length integration interval",
        )
    h_abs = abs(total_span) / 100.0
    if max_step != float("inf"):
        h_abs = min(h_abs, max_step)
    h = h_abs * direction

    k_old = None

    max_steps = 1_000_000
    while (direction > 0 and t < tf) or (direction < 0 and t > tf):
        if n_steps + n_rejected > max_steps:
            return OdeResult(
                t=np.array(ts, dtype=float),
                y=np.column_stack(ys),
                status="failed",
                n_steps=n_steps,
                n_rejected=n_rejected,
                t_events=[np.array(arr, dtype=float) for arr in t_events],
                y_events=[np.column_stack(ev_ys) if ev_ys else np.empty((y0_arr.shape[0], 0)) for ev_ys in y_events],
                message="Maximum number of steps exceeded",
            )
        remaining = tf - t
        if direction > 0:
            h = min(h, remaining)
        else:
            h = max(h, remaining)
        if h == 0.0:
            break

        y5, y4, k = _rk_step(fun, t, y, h)
        err = _error_norm(y5, y4, y, rtol_arr, atol_arr)

        if err <= 1.0 or err == 0.0:
            # Accept step.
            t_new = t + h
            y_new = y5
            n_steps += 1

            k_new = k[6]
            if k_old is None:
                k_old = k[0]

            # Event detection on [t, t_new].
            roots = []
            for idx, ev in enumerate(event_funcs):
                g_old = float(ev(t, y))
                g_new = float(ev(t_new, y_new))
                if _crossing(g_old, g_new, event_direction[idx]):
                    t_root, y_root = _event_root(
                        ev, t, y, t_new, y_new, k_old, k_new, rtol, atol
                    )
                    roots.append((t_root, y_root, idx))

            if roots:
                roots.sort(key=lambda r: (direction * r[0], r[2]))
                for t_root, y_root, idx in roots:
                    t_events[idx].append(t_root)
                    y_events[idx].append(y_root)
                    if event_terminal[idx]:
                        ts.append(t_root)
                        ys.append(y_root)
                        return OdeResult(
                            t=np.array(ts, dtype=float),
                            y=np.column_stack(ys),
                            status="event",
                            n_steps=n_steps,
                            n_rejected=n_rejected,
                            t_events=[np.array(arr, dtype=float) for arr in t_events],
                            y_events=[np.column_stack(ev_ys) if ev_ys else np.empty((y0_arr.shape[0], 0)) for ev_ys in y_events],
                            message=f"Terminal event {idx} triggered",
                        )

            ts.append(t_new)
            ys.append(y_new.copy())
            t, y = t_new, y_new
            k_old = k_new

            if (direction > 0 and t >= tf) or (direction < 0 and t <= tf):
                break

            # Step-size growth for accepted step.
            if err == 0.0:
                factor = 5.0
            else:
                factor = min(5.0, max(0.2, 0.9 * (err ** (-1.0 / 5.0))))
            h_new = h * factor
        else:
            n_rejected += 1
            raw_factor = 0.9 * (err ** (-1.0 / 5.0))
            # If the error estimate demands a step below machine underflow,
            # the problem is too stiff for this explicit method.
            h_min = 100.0 * eps * max(abs(t), abs(t + h))
            if abs(h) * raw_factor < h_min:
                return OdeResult(
                    t=np.array(ts, dtype=float),
                    y=np.column_stack(ys),
                    status="failed",
                    n_steps=n_steps,
                    n_rejected=n_rejected,
                    t_events=[np.array(arr, dtype=float) for arr in t_events],
                    y_events=[np.column_stack(ev_ys) if ev_ys else np.empty((y0_arr.shape[0], 0)) for ev_ys in y_events],
                    message="Step size underflow",
                )
            factor = min(5.0, max(0.2, raw_factor))
            h_new = h * factor

        h = h_new
        if max_step != float("inf"):
            if direction > 0:
                h = min(h, max_step)
            else:
                h = max(h, -max_step)

        # Step underflow guard.
        if abs(h) < 100.0 * eps * max(abs(t), abs(t + h)):
            return OdeResult(
                t=np.array(ts, dtype=float),
                y=np.column_stack(ys),
                status="failed",
                n_steps=n_steps,
                n_rejected=n_rejected,
                t_events=[np.array(arr, dtype=float) for arr in t_events],
                y_events=[np.column_stack(ev_ys) if ev_ys else np.empty((y0_arr.shape[0], 0)) for ev_ys in y_events],
                message="Step size underflow",
            )

    return OdeResult(
        t=np.array(ts, dtype=float),
        y=np.column_stack(ys),
        status="finished",
        n_steps=n_steps,
        n_rejected=n_rejected,
        t_events=[np.array(arr, dtype=float) for arr in t_events],
        y_events=[np.column_stack(ev_ys) if ev_ys else np.empty((y0_arr.shape[0], 0)) for ev_ys in y_events],
        message="Integration finished successfully",
    )
'''


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    if not (workspace / "input.json").is_file():
        workspace = root / "workspace"
    (workspace / "ode.py").write_text(_REFERENCE, encoding="utf-8")
    sys.path.insert(0, str(workspace))
    old_cwd = Path.cwd()
    try:
        os.chdir(workspace)
        runpy.run_path(str(workspace / "run_ode.py"), run_name="__main__")
    finally:
        os.chdir(old_cwd)


if __name__ == "__main__":
    main()
