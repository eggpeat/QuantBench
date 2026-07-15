# Gaussian-Copula Knockoff FDR Selection

## Summary

Implement `workspace/knockoffs.py` to select features with finite-sample Knockoff+ control using seeded Gaussian-copula knockoffs. The task also requires `workspace/run_task.py`.

## Required outputs

The runner reads `fixture.json` and writes `outputs/knockoffs.json` containing selected indices, selection frequencies, per-draw thresholds, and selected group labels.

## Verifier-facing success contract

- Expose the frozen `SelectionResult` dataclass and `select_fdr(X, y, *, q=0.1, n_draws=10, random_state=0, feature_groups=None)`.
- Validate finite `(n, p)` `X`, finite `(n,)` `y`, `n >= 2`, `p >= 1`, `0 < q < 1`, positive integer draw count, and valid feature-group labels. Invalid shapes, non-finite values, and malformed groups raise `ValueError`.
- Rank-normalize columns with stable average ties, build the symmetrized/floored Gaussian-copula covariance, and compute signed knockoff statistics with constant-column correlations equal to zero.
- Apply the exact Knockoff+ threshold. Draws without a threshold select nothing; features or whole groups selected in at least half the draws are returned in original order, with reproducible frequencies, thresholds, and group labels.
- Keep the workspace free of tests, solutions, and precomputed answer files; identical inputs and seed must produce bitwise-reproducible results.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 4 GiB memory, no network, and only the pinned NumPy, SciPy, and pytest dependencies in `environment/requirements.txt`.