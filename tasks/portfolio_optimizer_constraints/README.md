# Constrained Minimum-Variance Portfolio

## Summary

Implement `workspace/portfolio.py::min_variance_portfolio` and its `OptimizationResult` dataclass for constrained minimum-variance portfolios. The public runner is `workspace/run_portfolio.py`.

## Required outputs

Running `python run_portfolio.py` must create `outputs/portfolio_report.json`, serializing the optimization result fields including weights, objective/variance, status, success, message, expected return, and turnover.

## Verifier-facing success contract

- Symmetrize the covariance matrix for the solver, add ridge only to the solver objective, and report un-ridged variance `weights @ covariance_sym @ weights` as both objective and variance.
- Enforce weights summing to one, default nonnegative `(0, 1)` bounds, optional target return, inclusive sector bounds, and turnover limits against previous weights. Validate all shapes, finite values, intervals, and option combinations with `ValueError`.
- A valid but infeasible problem returns `success=False`, `status="infeasible"`, `weights=None`, and `objective=None`, rather than a failed solver iterate. A successful result has finite weights, `status="optimal"`, and records realized expected return, turnover when applicable, and a diagnostic message.
- Preserve caller inputs and use the documented SciPy constrained optimization behavior.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 2 GiB memory, no network, and the pinned NumPy, SciPy, and pytest dependencies in `environment/requirements.txt`.