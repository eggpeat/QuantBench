# Stability-Selection Resampling

## Summary

Implement `workspace/stability.py` with deterministic stability selection, local per-resample preprocessing, weighted Pearson scoring, and row, group, or contiguous-time resampling.

## Required outputs

Running `python stability.py` with `stability_input.npz` and `stability_config.json` must write `outputs/stability.json` describing the `StabilityResult`: selected indices/features, frequencies, threshold, and resample count.

## Verifier-facing success contract

- Expose the frozen `StabilityResult` dataclass and `stability_select(...)` with the documented parameters.
- For each seeded resample, median-impute and standardize using that resample only, score absolute weighted Pearson correlations with `y`, and mark the top `k` features with original-order tie handling. Frequencies are counts divided by `n_resamples`; selected indices/features are sorted by original order.
- Ordinary mode samples rows without replacement; group mode samples whole groups until the target count; time mode samples one stable contiguous block. Group and time modes are mutually exclusive, and positive `n_jobs` values must match the single-job result.
- Validate matrix and feature-name shapes, finite `y`, valid positive integer controls, sample fraction/threshold ranges, nonnegative finite weights with positive mass, and one group/time value per row. Reject duplicate feature names.
- The public workspace must contain no tests, solution, or precomputed answer files.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 2 GiB memory, no network, and the pinned NumPy and pytest dependencies in `environment/requirements.txt`.