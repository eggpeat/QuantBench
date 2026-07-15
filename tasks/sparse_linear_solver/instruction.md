# Sparse Linear Solver

Implement `sparse_solver.py::pcg` and the `SolverResult` dataclass.

```python
def pcg(
    indptr,
    indices,
    data,
    b,
    *,
    x0=None,
    tol: float = 1e-8,
    max_iter: int | None = None,
    preconditioner: str = "jacobi",
) -> SolverResult
```

The matrix is given in Compressed Sparse Row (CSR) format: `indptr`
has length `n+1`, `indices` and `data` have equal length, and row `i`
occupies `indices[indptr[i]:indptr[i+1]]` with values
`data[indptr[i]:indptr[i+1]]`. Infer `n = len(indptr) - 1`. The matrix
must be square and valid CSR; `b` must have length `n`. Reject
non-matching shapes or object/non-finite inputs with `ValueError`
(reason `"invalid_input"`).

Use Hestenes-Stiefel preconditioned conjugate gradients with the chosen
preconditioner:

* `"jacobi"`: diagonal preconditioner using the matrix diagonal. If any
diagonal entry is zero, return `reason="singular_preconditioner"`.
* (optional) `"none"`: identity preconditioner.

Default `max_iter = 10 * n`. Stop when
`||r||_2 <= tol * max(||b||_2, 1)`. If the search direction violates
positive definiteness (`p @ A @ p <= 0`), return
`reason="non_spd"`. If the iteration limit is reached first, return
`reason="max_iter"`.

Return a `SolverResult` dataclass with exactly these fields:

* `x`: `np.ndarray` of length `n` (best iterate even when not converged).
* `converged`: `bool`.
* `iterations`: `int`.
* `residual_norm`: `float`.
* `reason`: one of `"converged"`, `"max_iter"`, `"non_spd"`, `"singular_preconditioner"`, `"invalid_input"`.

Do not construct a dense `n x n` matrix at any point. The implementation
must be fast enough and memory-bounded for a 250,000-row seven-nonzero-per-row
SPD fixture (under 30 seconds and 512 MB peak RSS).

Run the self-contained public check with:

```bash
python run_sparse.py
python -m pytest -q /tests/test_outputs.py
```

The visible fixture is deterministic (`seed=100`). Hidden tests exercise
residual norms, diagonally dominant and ill-conditioned systems, zero RHS,
singular/non-SPD rejection, large sparse memory limits, iteration reporting,
and the named `densify` mutant.
