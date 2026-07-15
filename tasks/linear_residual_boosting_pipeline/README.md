# Linear Residual Boosting Pipeline

## Summary

Implement the sklearn-compatible `workspace/linear_residual.py::LinearResidualRegressor`: a weighted ridge trend plus deterministic residual regression tree with leakage-safe preprocessing and portable persistence. The public runner is `workspace/run_linear_residual.py`.

## Required outputs

Running `python run_linear_residual.py` must create `outputs/linear_residual.json` and the round-trip model archive `outputs/fixture_model.npz`.

## Verifier-facing success contract

- Expose the documented constructor, `fit`, `predict`, `save_model`, and `load_model` APIs. Constructor parameters remain immutable and an unfitted estimator remains sklearn-cloneable.
- Support NumPy/array-like or pandas-like named inputs, deterministic numeric/categorical encoding, named-column reordering, explicit feature selection, and the documented handling of missing, all-missing, constant, and categorical columns.
- Use only strictly positive training-weight rows for imputation, centering, scaling, constant detection, ridge fitting, and residual-tree fitting. Accept nonnegative finite weights with positive total; zero-weight rows must not influence fitted statistics.
- Predictions are finite float64 values in input order and equal trend plus residual-tree predictions. Expose the required fitted sklearn-style attributes.
- Save/load uses JSON metadata and plain numeric arrays only; no pickle-family format or refitting on load. Loaded predictions, including reordered named inputs, match within `1e-12`; malformed/non-finite archives raise `ValueError`.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 4 GiB memory, no network, and the pinned NumPy, SciPy, scikit-learn, and pytest dependencies in `environment/requirements.txt`.