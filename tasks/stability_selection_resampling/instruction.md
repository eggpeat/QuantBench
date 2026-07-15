# Stability-selection resampling

Implement `stability.py` in the public workspace with:

```python
@dataclass(frozen=True)
class StabilityResult:
    selected_indices: list[int]
    selected_features: list[str]
    frequencies: np.ndarray       # shape (p,)
    threshold: float
    n_resamples: int

def stability_select(X, y, *, k, n_resamples=100, sample_fraction=0.5,
                     threshold=0.8, sample_weight=None, groups=None,
                     times=None, feature_names=None, random_state=0,
                     n_jobs=1) -> StabilityResult
```

For each seeded resample, first median-impute missing values and then standardize every feature using only that resample. Compute absolute weighted Pearson correlations with `y`, and mark the top `k` features; ties preserve original column order. Frequencies are counts divided by `n_resamples`; return indices/features sorted by original order. Default feature names are stringified indices. `groups` and `times` are mutually exclusive: group mode samples whole groups until at least `ceil(n*sample_fraction)` rows, while time mode stable-sorts by time and samples one contiguous block of that many rows. Ordinary mode samples rows without replacement. `n_jobs=1` and any positive `n_jobs` must produce byte-for-byte equivalent values and identical selected output for the same seed.

Validate finite `y`, valid matrix shapes, positive integer `k`/`n_resamples`/`n_jobs`, `0 < sample_fraction <= 1`, `0 <= threshold <= 1`, nonnegative finite weights with positive mass, one group/time value per row, and unique feature names. Running `python stability.py` reads the seeded-100 `stability_input.npz` and `stability_config.json`, then writes `outputs/stability.json`. The public workspace must contain no tests, solution, or precomputed answer files.
