# Adaptive Conformal Intervals

## Summary

Implement `workspace/conformal.py` for deterministic split-conformal calibration with ordinary, grouped, and temporal splits, weighted quantiles, and normalized prediction intervals. The task also requires `workspace/run_task.py`.

## Required outputs

The runner reads `fixture.json` and writes `outputs/conformal.json` containing deterministic split indices, the conformal quantile, and lower/upper interval arrays.

## Verifier-facing success contract

- Expose `calibration_split`, `conformal_quantile`, and `normalized_intervals` with the documented signatures.
- Validate positive integer sample counts, a calibration fraction strictly between zero and one, non-empty partitions, mutually exclusive group/time inputs, matching lengths, finite values, and valid domains. Ordinary splits use a seeded local permutation; group splits take whole groups and return original row order; time splits stably use the latest rows.
- Unweighted quantiles use the specified finite-sample order statistic. Weighted quantiles sort scores with nonnegative finite frequency weights and use the documented cumulative-mass threshold without interpolation or silent clipping.
- Intervals use `maximum(scale, scale_floor)` and return fresh arrays for `mu - q*effective_scale` and `mu + q*effective_scale`; require finite non-negative `q` and a positive finite floor.
- Keep the workspace free of tests, solutions, and precomputed answer files, and make output deterministic.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 2 GiB memory, no network, and only the pinned NumPy, SciPy, and pytest dependencies in `environment/requirements.txt`.