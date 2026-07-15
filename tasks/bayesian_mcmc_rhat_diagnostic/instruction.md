Workspace task. Implement rank-normalized split R-hat diagnostics in `diagnostics.py` and write `outputs/rhat.json`.

The workspace contains `chains.json`, mapping each parameter name to a list of MCMC chains. Implement `compute_rhat(chains_by_parameter)` using the rank-normalized split R-hat, bulk ESS, and tail ESS diagnostic described by Vehtari et al. (2021):

- Validate at least two chains and at least four draws per chain. Chains must have equal lengths and all draws must be finite real numbers. For an odd draw count, discard the final draw before splitting.
- Split every chain into two contiguous halves, rank-normalize all split draws together using average ranks for ties, and map rank probabilities `(rank - 0.5) / N` through the standard normal inverse CDF.
- Compute split R-hat from the rank-normalized chains using unbiased within-chain variances and the between-chain variance. A constant, identical parameter has `rhat = 1.0`; a constant parameter with differing chain locations has infinite R-hat.
- `ess_bulk` is the Geyer initial-positive-sequence effective sample size of the rank-normalized draws. `ess_tail` is the smaller ESS of indicators for the lower and upper 5% raw-draw tails. Values are bounded to `[1, number_of_split_draws]` and rounded to six decimal places.

Return one object per parameter with exactly these keys: `rhat`, `ess_bulk`, `ess_tail`, `n_chains`, and `draws_per_chain`. Running `python run_diagnostics.py` from the workspace must read `chains.json` and create `outputs/rhat.json`. Use only the Python standard library. Malformed inputs (wrong container types, too few chains/draws, unequal lengths, non-numeric/non-finite draws, or undefined empty data) must raise `ValueError`.
