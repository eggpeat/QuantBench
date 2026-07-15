# Distributional Boosting Boundary Stability

## Summary

Implement `workspace/negative_binomial.py::gradient_and_hessian` for a negative-binomial distribution parameterized by `log_n` and `logit_p`. The public runner is `workspace/run_negative_binomial.py`.

## Required outputs

Running `python run_negative_binomial.py` must create `outputs/gradients.json` containing `gradient`, `hessian`, and `finite`, preserving input order with JSON-serializable values.

## Verifier-facing success contract

- Accept matching one-dimensional arrays of finite nonnegative integer counts, `log_n`, and `logit_p`; reject shape/domain violations with `ValueError`.
- `natural_gradient=False` is unsupported and must raise `NotImplementedError`.
- Clip both parameters to the documented float32-safe exponent range, perform raw arithmetic in float64, and use the stable raw scores `g_n = -n * (digamma(y+n) - digamma(n) + log(p))` and `g_p = p*y - n*(1-p)`.
- Natural gradients divide by the corrected diagonal Fisher terms `F_n = n*p/(p+1)` and `F_p = n*(1-p)`, each floored at `1e-30`. Return finite float32 arrays shaped `(n_rows, 2)`; the hessian is all ones.
- The floor is the only clipping of computed results; do not replace non-finite results with zeros.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 1 GiB memory, no network, and the pinned NumPy, SciPy, scikit-learn, and pytest dependencies in `environment/requirements.txt`.