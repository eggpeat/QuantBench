# CRPS Vectorization and Scoring

Implement `scoring.py` with these exact APIs:

```python
gaussian_crps(mu, sigma, y, sample_weight=None) -> float
empirical_crps(samples, y, sample_weight=None) -> float
```

`gaussian_crps` uses the closed form for a normal forecast. For `z=(y-mu)/sigma`,

```text
CRPS = sigma * ( z * (2 Phi(z) - 1) + 2 phi(z) - 1/sqrt(pi) )
```

where `phi` and `Phi` are the standard normal density and CDF. Inputs may be scalar or broadcast-compatible numeric arrays. `sigma` must be finite and strictly positive; zero and negative scales, non-finite/object inputs, or incompatible shapes raise `ValueError`. Tiny positive scales are accepted in float64.

`empirical_crps` accepts a one-dimensional `samples` array as one forecast distribution when `y` is scalar (or length one), or a two-dimensional ensemble in either member-first shape `(M, N)` or observation-first shape `(N, M)`, with unambiguous observation matching. For an empirical distribution, use

```text
E|X-y| - 1/2 E|X-X'|
```

and compute the pair term from sorted order statistics; do not materialize a `(M, M, N)` pairwise tensor. `sample_weight` contains nonnegative finite observation weights and must have positive total. Both functions return the weighted mean score as a finite Python float, preserve caller arrays, and reject malformed domains/shapes.

The empirical implementation is benchmarked with `(M, N)=(100, 100000)`: candidate time must be at most 0.20 times the pairwise reference and peak RSS must remain below 2 GB. The verifier checks analytical parity, weighting, tiny scales, float32/64, orientation, memory, and the named `pairwise_tensor` mutant.

Run the self-contained public check with:

```bash
python run_scoring.py
python -m pytest -q /tests/test_outputs.py
```

The fixture is deterministic (seed 100), and no expected-answer file is present in the public workspace.
