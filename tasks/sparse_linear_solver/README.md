# Sparse Linear Solver

## Summary

Implement `workspace/sparse_solver.py::pcg` and the `SolverResult` dataclass for preconditioned conjugate gradients over CSR matrices. The public runner is `workspace/run_sparse.py`.

## Required outputs

Running `python run_sparse.py` must create `outputs/sparse_report.json` describing the deterministic solve, including the solver result fields.

## Verifier-facing success contract

- Validate CSR `indptr`, `indices`, and `data`, infer a square matrix from `len(indptr)-1`, and validate the length and finiteness of `b`; malformed or object inputs raise `ValueError` with reason `invalid_input`.
- Use Hestenes--Stiefel preconditioned conjugate gradients with Jacobi by default (or the optional identity preconditioner). A zero diagonal returns `singular_preconditioner`; a non-positive search-direction curvature returns `non_spd`; an exhausted iteration limit returns `max_iter`.
- Stop at `||r|| <= tol * max(||b||, 1)`, defaulting `max_iter` to `10*n`. Return exactly `x`, `converged`, `iterations`, `residual_norm`, and the documented reason, including the best iterate when unconverged.
- Never construct a dense `n x n` matrix. The large sparse verifier enforces the documented runtime and memory bounds.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 2 GiB memory, no network, and the pinned NumPy, SciPy, and pytest dependencies in `environment/requirements.txt`.