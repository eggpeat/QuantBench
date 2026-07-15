# Heteroscedastic OOF calibration

Implement leakage-safe two-stage calibration in `hetero.py`. The verifier imports the module from the public workspace and also executes `run_calibration.py`; do not add tests, solutions, or precomputed answers to `workspace/`.

## Required API

```python
make_oof_predictions(
    estimator_factory, X, y, *, n_splits=5, groups=None, times=None,
    sample_weight=None, random_state=0
) -> numpy.ndarray
fit_variance_scale(y, mu, var_raw, *, sample_weight=None, eps=1e-12) -> float
```

`make_oof_predictions` constructs a fresh estimator for every fold, fits only on that fold's training rows, and returns one prediction per row. Ordinary mode is seeded shuffled K-fold. With `groups`, shuffle unique groups using `random_state` and assign whole groups to folds; no group may occur in both train and validation. With `times`, stably sort by time and use expanding-window folds: every validation block is predicted by a model trained on strictly earlier rows, while the initial training-only block remains `NaN`. `groups` and `times` are mutually exclusive. If weights are provided, pass only the training slice to `fit(..., sample_weight=...)`; never use validation weights for fitting. Preserve input row order in the returned array.

Validate one-dimensional finite `y`, matching row counts and valid positive integer `n_splits`; reject non-finite or non-positive sample weights, invalid groups/times, impossible folds, and a factory that does not produce a fit/predict estimator. Raise `ValueError` for contract violations rather than silently dropping data. Estimator predictions must be one-dimensional and finite on assigned validation rows.

`fit_variance_scale` fits a **variance multiplier**, not a standard-deviation multiplier. Its closed-form solution is the weighted mean of `(y - mu)**2 / max(var_raw, eps)`, clipped below by `eps`. Validate shapes, finiteness, positive finite `eps`, and positive finite total weight. The function returns a Python `float`.

The command `python run_calibration.py` reads `input.json` and writes `outputs/calibration.json` with exactly these keys: `scale`, weighted `nll_before`, weighted `nll_after`, and `n_calibration_rows`. Calibration rows are the finite OOF rows (time mode's initial `NaN` block is excluded). Gaussian NLL uses `0.5 * (log(2*pi*variance) + residual**2/variance)` and the supplied frequency weights. Keep all arithmetic deterministic and use float64 intermediates.
