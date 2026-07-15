# Constrained Minimum-Variance Portfolio

Implement `portfolio.py::min_variance_portfolio` and the accompanying `OptimizationResult` dataclass. The function must solve a minimum-variance portfolio with scipy using the following contract:

```python
min_variance_portfolio(
    covariance,
    expected_returns=None,
    *,
    target_return=None,
    bounds=None,
    sector_labels=None,
    sector_bounds=None,
    previous_weights=None,
    turnover_limit=None,
    ridge=1e-8,
) -> OptimizationResult
```

`covariance` is a finite, square numeric matrix. Symmetrize it as `(covariance + covariance.T) / 2`, then use `covariance + ridge * I` only for the solver objective. The returned `objective` (also exposed as `variance`) must be the un-ridged variance `weights @ covariance_sym @ weights`. `ridge` is finite and non-negative.

Weights satisfy `sum(weights) == 1` and default to bounds `(0, 1)` for every asset. A caller may provide one `(low, high)` pair or one pair per asset. `target_return` imposes `expected_returns @ weights == target_return`; expected returns are required when a target is supplied. `sector_bounds` is a mapping (or one pair per distinct sector in label order) of inclusive `(minimum, maximum)` aggregate weights and requires one `sector_labels` value per asset. A turnover limit requires `previous_weights` and imposes `sum(abs(weights - previous_weights)) <= turnover_limit`.

Inputs with invalid shape, non-numeric or non-finite values, contradictory options, or invalid intervals must raise `ValueError`. A valid but infeasible optimization must return an explicit result with `success=False`, `status="infeasible"`, `weights=None`, and `objective=None`; do not return a failed solver iterate. A successful result has `success=True`, `status="optimal"`, finite weights, and the un-ridged objective. The result also records realized `expected_return`, `turnover` (when previous weights are supplied), and a diagnostic message.

Run the self-contained public check with:

```bash
python run_portfolio.py
python -m pytest -q /tests/test_outputs.py
```

The visible fixture is deterministic (`seed=100`). Hidden checks exercise nonsymmetric covariance and ridge reporting, default and custom bounds, target-return and sector intervals, exact turnover boundaries, invalid input and infeasible schemas, no input mutation, and the named `ignore_turnover` mutant.
