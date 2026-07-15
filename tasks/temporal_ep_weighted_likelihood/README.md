# Temporal EP Weighted Likelihood

## Summary

Implement `workspace/temporal_ep.py::fit_temporal_states` for a scalar Gaussian random walk with powered likelihood sites, normalized Gauss-Hermite expectation propagation, and Rauch--Tung--Striebel smoothing. The public runner is `workspace/run_temporal.py`.

## Required outputs

Running `python run_temporal.py` must create `outputs/temporal_report.json` representing exactly the result keys `times`, `filtered_mean`, `filtered_var`, `smoothed_mean`, `smoothed_var`, and `log_likelihood`.

## Verifier-facing success contract

- Validate finite, equal-length, non-empty one-dimensional `times`, `outcomes`, and strictly positive observation `weights`; validate positive finite process/initial variances, finite initial mean, positive integer quadrature order, and known likelihood names.
- Stably sort observations by time, preserve equal-time input order, apply process variance proportional to elapsed time between unique times, and process duplicate-time observations sequentially.
- Support the documented probit, logit, Poisson, and Skellam likelihood domains. Each powered likelihood must include its observation weight.
- Normalize all Gauss--Hermite weights in cavity moment matching, run the scalar forward pass and RTS smoother, and return NumPy arrays at unique sorted times. `log_likelihood` groups and sums duplicate-time contributions.
- Invalid shapes, non-finite values, unknown likelihoods, and invalid domains raise `ValueError`.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 2 GiB memory, no network, and the pinned NumPy, SciPy, and pytest dependencies in `environment/requirements.txt`.