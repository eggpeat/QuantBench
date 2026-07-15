# Adaptive ODE Integration with Events

Implement `ode.py::integrate_rk45` and the `OdeResult` dataclass.

```python
def integrate_rk45(
    fun,
    t_span,
    y0,
    *,
    rtol: float = 1e-6,
    atol: float = 1e-9,
    max_step: float = np.inf,
    events=None,
) -> OdeResult
```

`fun(t, y)` returns the derivative as a NumPy array. `t_span` is a two-element
sequence `(t0, tf)`; integration proceeds forward if `tf > t0` and in reverse if
`tf < t0`. `y0` is the initial state. `rtol` and `atol` may be scalars or arrays
and are combined as `atol + rtol * max(|y|, |y_next|)`.

Use the Dormand-Prince 5(4) embedded pair with adaptive step-size control:
accept a step only when the RMS error estimate is `<= 1`, otherwise reject it
and retry with a smaller step. Bound the next step by `max_step` and by the
remaining integration interval. If a step size collapses below the underflow
tolerance (`100 * eps * max(|t|, |t+h|)`), return `status="failed"` with a
nonempty `message`.

`events` is an iterable of callables `event(t, y) -> float`. Each event may have
optional Boolean attributes `terminal` (stop integration when triggered) and
`direction` (`-1`, `0`, or `1`). Detect a crossing only when the sign change
matches `direction`:

* `direction == 0`: any sign change or exact zero at the right endpoint.
* `direction == 1`: negative to non-negative crossing.
* `direction == -1`: positive to non-negative crossing.

When a crossing is detected on an accepted step, localize the root inside that
step to `max(rtol * |t|, atol)` using dense output. If multiple events trigger
inside one step, resolve them sorted by root time, breaking ties by list order.
For a terminal event stop at the event time and return `status="event"`;
otherwise continue integration.

Return an `OdeResult` dataclass with exactly these fields:

* `t`: 1-D `np.ndarray` of times at accepted steps (including the initial time).
* `y`: `np.ndarray` shaped `(state_dim, len(t))`.
* `status`: one of `"finished"`, `"event"`, `"failed"`.
* `n_steps`: integer number of accepted steps.
* `n_rejected`: integer number of rejected steps.
* `t_events`: list of `np.ndarray`, one per event, containing trigger times.
* `y_events`: list of `np.ndarray`, one per event, containing trigger states as columns.
* `message`: human-readable status string.

Run the self-contained public check with:

```bash
python run_ode.py
python -m pytest -q /tests/test_outputs.py
```

The visible fixture is deterministic (`seed=100`). Hidden tests exercise
exponential decay, an oscillator, vector states, tolerance scaling, forward and
reverse integration, terminal and directional events, discontinuous event
boundaries, and a stiff problem that must fail clearly rather than hang. The
named `fixed_step` mutant ignores adaptive error control.
