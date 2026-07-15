# Bayesian MCMC Rank-Normalized Split R-hat Diagnostic

## Overview

This promoted Terminal-Bench-style task asks an agent to implement the modern rank-normalized split R-hat convergence diagnostic for Bayesian MCMC chains, including bulk and tail effective sample sizes. The workspace provides public chains in `chains.json`; the agent must implement `compute_rhat(chains_by_parameter)` in `diagnostics.py` and produce `outputs/rhat.json`.

Each parameter has at least two equal-length chains with at least four finite draws. Chains are split into contiguous halves (discarding one final draw for an odd length), all split draws are rank-normalized with average ties, and split R-hat uses unbiased within-chain and between-chain variances. Bulk ESS uses Geyer's initial-positive-sequence estimator on rank-normalized draws. Tail ESS is the minimum ESS of lower and upper five-percent indicators. Constant identical chains have R-hat 1.0 and full ESS.

## Source Grounding & Provenance

- **Source**: Vehtari, Gelman, Simpson, Carpenter, and Bürkner (2021), *Rank-normalization, folding, and localization: An improved R-hat for assessing convergence of MCMC*, Bayesian Analysis 16(2), 667–718.
- **Background**: Gelman, Carlin, Stern, and Rubin, *Bayesian Data Analysis* (Second Edition), equations 11.1–11.4 / p. 296.
- **Task behavior**: Modern split and rank normalization detect non-stationarity and remain meaningful for heavy-tailed or non-normal marginals; no third-party Bayesian package may be imported.

## What It Tests

- Correct split-chain rank normalization and tie handling.
- R-hat behavior for stationary, shifted, heavy-tailed, autocorrelated, and constant chains.
- Bulk and tail ESS bounds and deterministic six-decimal serialization.
- Exact output keys: `rhat`, `ess_bulk`, `ess_tail`, `n_chains`, and `draws_per_chain`.
- Validation of malformed MCMC inputs and too-few-draw errors.
- Dynamic inline cases so copying `expected.json` is insufficient.

## Environment

The task uses `python:3.13-slim-bookworm` pinned by digest. No internet access, credentials, external services, or third-party packages are required; pytest 8.4.2 is installed in the image.

## Inputs and Outputs

- `workspace/chains.json`: maps parameter names to lists of equal-length numeric chains.
- `workspace/diagnostics.py`: starter module containing the function to implement.
- `workspace/run_diagnostics.py`: command-line entry point that reads `chains.json` and writes `outputs/rhat.json`.
- `workspace/outputs/rhat.json`: JSON object keyed by parameter name, with exactly the five diagnostic keys above.

## Verification

Pytest tests import `diagnostics.py`, run the workspace script, compare `outputs/rhat.json` with `tests/expected.json`, exercise stationary and divergent cases, check constant-chain behavior, and verify malformed chain handling raises `ValueError`.
