# Heteroscedastic OOF Calibration

## Summary

Implement leakage-safe two-stage calibration in `workspace/hetero.py`: produce out-of-fold mean predictions and fit a weighted Gaussian variance multiplier. The public runner is `workspace/run_calibration.py`.

## Required outputs

Running `python run_calibration.py` from the workspace must create `outputs/calibration.json` with exactly `scale`, weighted `nll_before`, weighted `nll_after`, and `n_calibration_rows`.

## Verifier-facing success contract

- Expose `make_oof_predictions(...)` and `fit_variance_scale(...)` with the documented signatures.
- Ordinary OOF uses seeded shuffled folds; group mode keeps each group wholly in one fold; time mode uses stable expanding-window folds and leaves the initial training-only block as `NaN`. Group and time modes are mutually exclusive, and returned predictions preserve input order.
- Fit each fold's fresh estimator only on training rows. If weights are supplied, pass only the training slice to `fit`; validation weights must not affect fitting.
- Reject malformed, non-finite, non-positive, or impossible inputs with `ValueError`; estimator predictions must be one-dimensional and finite.
- `fit_variance_scale` returns the weighted mean of `(y - mu)**2 / max(var_raw, eps)`, floored at `eps`, using a Python `float`. NLL calculations use the stated Gaussian formula and finite OOF rows.
- Keep calculations deterministic with float64 intermediates.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 1 GiB memory, no network, and the pinned NumPy, SciPy, scikit-learn, and pytest dependencies in `environment/requirements.txt`.