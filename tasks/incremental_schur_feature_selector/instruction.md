# Incremental Schur feature selector

Implement `selector.py` in the public workspace. It must expose:

```python
greedy_select(correlation, target_correlation, k, *, ridge=1e-8) -> list[int]
```

`correlation` is a finite `(p,p)` feature correlation/covariance matrix and `target_correlation` is a finite `(p,)` feature-target correlation vector. Select exactly `k` distinct feature indices, in greedy selection order. At each step maximize the ridge-regularized conditional target gain:

```
(r_j - R[j,S] @ inv(R[S,S] + ridge I) @ r[S])**2 /
(R[j,j] + ridge - R[j,S] @ inv(R[S,S] + ridge I) @ R[S,j])
```

The inverse block must be maintained with Schur/rank-one updates rather than recomputing a full inverse per candidate. Use float64 intermediates, clamp only a numerically non-positive Schur denominator, and choose the lowest original index on exact or numerical ties. `k=0` returns `[]`; malformed shapes, nonfinite values, negative ridge, or out-of-range `k` raise `ValueError`.

The workspace contains `selector_input.npz` and `selector_config.json`, generated with NumPy seed 100. Running `python selector.py` must write `outputs/selection.json` with key `selected_indices`. Do not add tests, solutions, answer files, or network calls to the workspace.
