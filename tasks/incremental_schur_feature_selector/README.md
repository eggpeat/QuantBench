# Incremental Schur Feature Selector

## Summary

Implement `workspace/selector.py::greedy_select` for greedy conditional-correlation feature selection using incremental Schur-complement inverse updates.

## Required outputs

Running `python selector.py` with the supplied `selector_input.npz` and `selector_config.json` must write `outputs/selection.json` with the key `selected_indices`.

## Verifier-facing success contract

- Accept finite square feature correlation/covariance `correlation`, finite matching `target_correlation`, and valid integer `k`; `k=0` returns `[]`.
- At each step select exactly one unused feature maximizing the documented ridge-regularized conditional target gain. Maintain the inverse block with Schur/rank-one updates, use float64 intermediates, clamp only a numerically non-positive Schur denominator, and choose the lowest original index on exact or numerical ties.
- Reject malformed shapes, non-finite values, negative ridge, or out-of-range `k` with `ValueError`; return indices in greedy selection order.
- Do not add tests, solutions, answer files, or network calls to the workspace.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 2 GiB memory, no network, and the pinned NumPy and pytest dependencies in `environment/requirements.txt`.