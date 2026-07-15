# CRPS Vectorization and Scoring

## Summary

Implement `workspace/scoring.py` with Gaussian and empirical continuous ranked probability score functions, including weighted observation reductions. The public runner is `workspace/run_scoring.py`.

## Required outputs

Running `python run_scoring.py` must create `outputs/scoring_report.json` with the fixture seed, `gaussian_crps`, and `empirical_crps` values.

## Verifier-facing success contract

- Expose `gaussian_crps(mu, sigma, y, sample_weight=None)` and `empirical_crps(samples, y, sample_weight=None)`, returning finite Python floats.
- Gaussian CRPS uses the stated normal closed form and accepts scalar or broadcast-compatible numeric arrays. Require finite, strictly positive `sigma`; reject zero/negative scales, object or non-finite values, and incompatible shapes.
- Empirical CRPS uses `E|X-y| - 1/2 E|X-X'|`. Support a one-dimensional forecast for scalar (or length-one) observations and unambiguously oriented two-dimensional ensembles; obtain the pair term from sorted order statistics rather than a pairwise tensor.
- Observation weights must be finite, nonnegative, matching, and have positive total. Preserve caller arrays and reject malformed domains or shapes.
- The verifier enforces the documented vectorization, runtime, and memory bounds on the large ensemble fixture.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b`), one CPU, 2 GiB memory, no network, and the pinned NumPy, SciPy, and pytest dependencies in `environment/requirements.txt`.