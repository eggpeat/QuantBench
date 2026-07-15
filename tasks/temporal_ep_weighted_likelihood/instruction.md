# Temporal EP Weighted Likelihood

Implement `temporal_ep.py` with this exact API:

```python
fit_temporal_states(
    times, outcomes, weights, *, likelihood, process_var,
    initial_mean=0.0, initial_var=1.0, quadrature_order=20,
) -> dict
```

`times`, `outcomes`, and `weights` are finite one-dimensional arrays of equal,
nonzero length. Every observation weight is finite and strictly positive.
`process_var` and `initial_var` must be finite and positive; `initial_mean` must
be finite. `quadrature_order` is a positive integer. Unknown likelihood names,
non-finite values, malformed shapes, or invalid domains raise `ValueError`.

The scalar latent state follows a Gaussian random walk. Between unique sorted
times `t[i-1]` and `t[i]`, process variance is
`process_var * (t[i] - t[i-1])`. Inputs are stably sorted by time (equal-time
observations retain original order), then equal times are processed as
sequential updates at one state. The four likelihood names and domains are:

* `probit`, with outcome `y` in `{-1,+1}` and `log p(y|x) = log Phi(y*x)`;
* `logit`, with outcome `y` in `{-1,+1}` and
  `log p(y|x) = -log(1 + exp(-y*x))`;
* `poisson`, with nonnegative integer `y`, rate `exp(x)`, and
  `log p(y|x) = y*x - exp(x) - log(y!)`;
* `skellam`, with integer score difference `y`, symmetric rates
  `mu_1=exp(x)`, `mu_2=exp(-x)`, and
  `log p(y|x) = -(exp(x)+exp(-x)) + y*x + log(I_|y|(2))`.

Each observation is an EP site whose powered likelihood is `p(y|x)**weight`.
Moment matching must use a *normalized* Gauss--Hermite rule under the Gaussian
cavity; all quadrature weights must be included in the normalized partition and
first two moments. Use a scalar Gaussian forward pass followed by
Rauch--Tung--Striebel smoothing. The result must contain exactly these keys:

```text
times, filtered_mean, filtered_var, smoothed_mean, smoothed_var, log_likelihood
```

`times` is a NumPy array of unique sorted times. The four state arrays are
NumPy float arrays with one entry per unique time. `log_likelihood` is the
NumPy array of forward EP log partition contributions, grouped by unique time
and summing duplicate-time contributions (each contribution includes its
observation weight).

Run the self-contained public check with:

```bash
python run_temporal.py
python -m pytest -q ../tests/test_outputs.py
```

The public fixture is deterministic (`seed=100`) and has no expected-answer
file. The verifier also exercises all four likelihood domains, weighted-vs-
unweighted behavior, stable duplicate updates, smoothing variance reduction,
quadrature normalization, finite boundary cases, and the named
`unweighted_updates` mutant.
