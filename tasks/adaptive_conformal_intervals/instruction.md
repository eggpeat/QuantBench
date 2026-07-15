# Adaptive conformal intervals

Implement `conformal.py` in the workspace without network access. It must expose:

```python
calibration_split(n_samples, *, groups=None, times=None,
                  calibration_fraction=0.2, random_state=0)
conformal_quantile(scores, alpha, sample_weight=None)
normalized_intervals(mu, scale, q, *, scale_floor=1e-12)
```

`calibration_split` returns `(train_indices, calibration_indices)` as integer NumPy arrays. Validate that `n_samples` is a positive integer, `0 < calibration_fraction < 1`, and both resulting partitions are non-empty. `groups` and `times` are mutually exclusive and, when given, must have length `n_samples`. Ordinary mode uses a seeded shuffled permutation of row indices and takes the first `ceil(n_samples * calibration_fraction)` rows for calibration. It must not make an unseeded/global RNG call. Group mode uses a seeded shuffle of unique group labels, takes whole groups until at least that target number of rows is reached, and returns indices in original row order. Time mode stably sorts the supplied times and takes the last `ceil(n_samples * calibration_fraction)` sorted rows as calibration; the remaining sorted rows are training. Time mode never randomly permutes rows. Reject non-finite numeric times and malformed labels.

`conformal_quantile` accepts a non-empty finite one-dimensional score array and `0 < alpha < 1`. Without weights, sort ascending and return the 1-based order statistic at rank `min(ceil((n+1)*(1-alpha)), n)`. With frequency weights, require a matching finite one-dimensional non-negative array with positive sum. Sort scores and weights together and return the first score whose cumulative weight divided by total weight is at least `min((1-alpha)*(1 + 1/sum(weights)), 1)`. Do not interpolate or silently clip invalid data.

`normalized_intervals` accepts finite, broadcast-compatible `mu`, `scale`, and scalar/array `q`. Require finite non-negative `q` and positive finite `scale_floor`; use `effective_scale = maximum(scale, scale_floor)` (the documented scale-floor exception), returning fresh `(lower, upper)` arrays equal to `mu - q*effective_scale` and `mu + q*effective_scale`.

Also provide a small CLI `run_task.py` that reads `fixture.json` and writes `outputs/conformal.json` with deterministic split indices, quantile, and interval arrays. Keep the workspace free of tests, solutions, and precomputed answer files. Use only the pinned dependencies in `environment/requirements.txt`.
