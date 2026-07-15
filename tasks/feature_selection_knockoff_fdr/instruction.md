# Gaussian-copula knockoff FDR selection

Implement `knockoffs.py` in the workspace without network access. It must expose:

```python
@dataclass
class SelectionResult:
    selected_indices: list[int]
    selection_frequency: np.ndarray
    draw_thresholds: np.ndarray
    group_selected: list[object]

select_fdr(X, y, *, q=0.1, n_draws=10, random_state=0,
           feature_groups=None) -> SelectionResult
```

Validate finite `X` with shape `(n,p)`, finite `y` with shape `(n,)`, `n >= 2`, `p >= 1`, `0 < q < 1`, positive integer `n_draws`, and valid `feature_groups` of length `p` (groups are labels; equal labels identify a group). Invalid shapes, non-finite values, and malformed groups raise `ValueError`.

Rank-normalize each feature column to Gaussian scores using stable average ranks (ties get their average rank). Estimate the Gaussian-copula correlation, symmetrize it, floor eigenvalues at `1e-3`, and use equicorrelated `S = min(2*lambda_min, 1)*I`. For each seeded draw construct a valid Model-X Gaussian knockoff from this latent covariance, map it back to the observed feature marginals, and compute `W_j = abs(corr(X_j,y)) - abs(corr(Xtilde_j,y))`. Constant columns have correlation zero and must never produce NaNs. If groups are provided, replace feature statistics by the maximum signed `W` in each group for thresholding and select whole groups.

Use the exact Knockoff+ threshold:
`min { t > 0 : (1 + count(W <= -t)) / max(count(W >= t), 1) <= q }`.
If no threshold exists, the draw threshold is `inf` and that draw selects nothing. A feature (or whole group) is selected when it is selected in at least half the draws. Return selection frequencies in original feature order, selected indices sorted in original order, thresholds of shape `(n_draws,)`, and selected group labels sorted by first original feature position. With no groups, `group_selected` is an empty list. Every call with the same inputs and `random_state` must be bitwise reproducible.

Also provide `run_task.py` that reads `fixture.json` and writes `outputs/knockoffs.json` containing selected indices, selection frequencies, draw thresholds, and group labels. Keep the workspace free of tests, solutions, and precomputed answer files. Use only the pinned dependencies in `environment/requirements.txt`.
