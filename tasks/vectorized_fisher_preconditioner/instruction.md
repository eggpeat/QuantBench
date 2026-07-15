# Vectorized Fisher Preconditioner

Implement `fisher.py::precondition_diagonal(raw_grad, fisher_diag, *, floor=1e-30) -> numpy.ndarray`.

`raw_grad` is a finite numeric array shaped `(N, P)` (a one-dimensional `(P,)` input is also valid). `fisher_diag` is either the same shape or one shared diagonal of shape `(P,)`; a scalar diagonal is allowed for a one-dimensional gradient. The result is the diagonal Fisher linear solve, element by element:

```text
result[i, j] = raw_grad[i, j] / max(fisher_diag[i, j], floor)
```

Use float64 intermediates and return a fresh float64 array. `floor` must be finite and strictly positive. Reject object, non-finite, or incompatible-shape inputs with `ValueError`; reject negative floors. Never mutate either input. A Fisher diagonal can contain zero (or a small negative round-off value), which is handled by the documented floor rather than by clipping the gradient.

The implementation must be vectorized and must not construct or solve an `(N, P, P)` tensor. It is benchmarked against an explicit matrix-solve reference at `N=500_000, P=3`: candidate time must be at most 0.10 times the reference and incremental RSS must remain at most 128 MB.

Run the self-contained public check with:

```bash
python run_fisher.py
python -m pytest -q /tests/test_outputs.py
```

The fixture is deterministic (seed 100). The verifier also exercises hidden random fixtures, broadcast diagonals, floor corners, no-input-mutation, and the named `matrix_solve` mutant.
