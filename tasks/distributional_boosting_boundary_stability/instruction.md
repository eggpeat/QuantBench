# Distributional boosting boundary stability

Implement `negative_binomial.py::gradient_and_hessian` for a negative-binomial distribution parameterized by `log_n` and `logit_p`. The verifier imports this module from the public workspace and executes `run_negative_binomial.py`; keep tests and the oracle out of `workspace/`.

## Required API

```python
gradient_and_hessian(
    y, log_n, logit_p, *, natural_gradient=True
) -> tuple[numpy.ndarray, numpy.ndarray]
```

Inputs are broadcast-free, matching one-dimensional arrays (array-like values are accepted). `y` contains finite nonnegative integer counts. `log_n` and `logit_p` are finite real values. Raise `ValueError` for shape/domain violations. `natural_gradient=False` is intentionally unsupported and must raise `NotImplementedError`.

Clip `log_n` and `logit_p` to the float32-safe exponent range used by the upstream distribution (`log(1e-32)` through `log(float32_max)-1`). Let `n=exp(log_n_clipped)` and `p=expit(logit_p_clipped)`. Compute all raw arithmetic in float64. The raw score of the negative log PMF is

* `g_n = -n * (digamma(y+n) - digamma(n) + log(p))`
* `g_p = p*y - n*(1-p)`

The second expression is algebraically deliberate: do not form `p * (y - n*(1-p)/p)`, whose intermediate can overflow at the lower-probability boundary. For natural gradients divide by the corrected diagonal Fisher entries

* `F_n = n*p/(p+1)`
* `F_p = n*(1-p)`

Floor each diagonal to `1e-30` before division. Return `(gradient, hessian)` as finite `float32` arrays of shape `(n_rows, 2)`, with the hessian equal to ones (the boosting interface uses a constant diagonal hessian). The floor is the only permitted clipping of a computed numeric result; do not turn nonfinite values into zeros.

The command `python run_negative_binomial.py` reads `input.json` and writes `outputs/gradients.json` containing `gradient`, `hessian`, and `finite`. Preserve deterministic input order and JSON-serializable numbers.
