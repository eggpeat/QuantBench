# Vectorized Fisher Preconditioner

## Summary

Implement `workspace/fisher.py::precondition_diagonal` as a memory-bounded diagonal Fisher linear solve for batched gradients. The public runner is `workspace/run_fisher.py`.

## Required outputs

Running `python run_fisher.py` must create `outputs/fisher_report.json`, reporting the fixture seed, result shape, preconditioned values, and L1 summary.

## Verifier-facing success contract

- Accept a finite `(N, P)` gradient or one-dimensional `(P,)` gradient. The Fisher diagonal may match the gradient shape, be a shared `(P,)` diagonal, or be a scalar for a one-dimensional gradient.
- Return a fresh float64 array with each entry `raw_grad / max(fisher_diag, floor)`. `floor` must be finite and strictly positive; reject object, non-finite, and incompatible inputs with `ValueError`.
- Preserve both inputs without mutation. Zero or small negative diagonal values use the documented floor.
- Vectorize the operation without constructing an `(N, P, P)` tensor. The large-fixture verifier also enforces the documented time and incremental-memory limits.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b`), one CPU, 2 GiB memory, no network, and the pinned NumPy and pytest dependencies in `environment/requirements.txt`.