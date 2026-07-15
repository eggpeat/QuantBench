# Adaptive ODE Integration with Events

## Summary

Implement `workspace/ode.py::integrate_rk45` and the `OdeResult` dataclass for adaptive Dormand--Prince 5(4) integration, forward or reverse, with directional event detection and root localization. The public runner is `workspace/run_ode.py`.

## Required outputs

Running `python run_ode.py` must create `outputs/ode_report.json` with the deterministic fixture seed and per-problem status, final time/state, accepted/rejected step counts, message, and event times when applicable.

## Verifier-facing success contract

- Validate `fun`, two-element `t_span`, state shape, tolerances, and step controls. Combine scalar/array tolerances as documented and accept forward or reverse integration.
- Use the Dormand--Prince embedded pair, accept only RMS error `<= 1`, bound steps by `max_step` and remaining interval, and return a clear failed status when the step underflows.
- Detect only sign crossings matching each event's `direction`; localize accepted-step roots to `max(rtol*abs(t), atol)` using dense output. Resolve multiple roots by root time then event-list order, and stop at terminal events.
- Return exactly the documented `OdeResult` fields and array shapes: accepted-step times including the initial time, state columns, status, counts, per-event trigger arrays, and a human-readable message.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 2 GiB memory, no network, and the pinned NumPy, SciPy, and pytest dependencies in `environment/requirements.txt`.