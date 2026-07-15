# Empirical Bayes CTR Shrinkage

## Overview

This Quant Bench task asks an agent to implement Beta-binomial empirical Bayes shrinkage on ad click-through rates (CTR) to shrink noisy, low-volume ad performance toward a global prior. The agent must load raw CSV fixtures, parse settings from `config.json`, compute posterior distributions, and output a ranked JSON report.

## Source Grounding & Provenance

 - **Source**: *Introduction to Empirical Bayes: Examples and Methods in R* by David Robinson (Chapter 3, pp. 21-25).
 - **Task Behavior vs. Source**:
  - The task is intentionally scoped as a posterior update and shrinkage task rather than full prior hyperparameter estimation. It tests conjugate beta-binomial shrinkage using an empirical global mean and a configured prior strength $K$ (to compute $\alpha_0$ and $\beta_0$), rather than prior-MLE fitting.
  - Robinson lines 543-579 describe empirical Bayes estimation and success/total data including ad click rates. Lines 669-671 discuss estimating a beta prior from data. Lines 537-538 detail the standard Bayesian update of adding successes to $\alpha_0$ and failures to $\beta_0$, which is the core contract tested by this task.
  - This simplification reduces mathematical implementation complexity for the solver by using a configured prior strength instead of full MLE or Method of Moments beta-binomial parameter fitting on the raw click/impression dataset.
 - **Verifier Risk**: None. The verifier assumes fixed, configured prior strength $K$ and empirical global mean $\text{global\_ctr}$ calculated from the dataset. Solver agents must perform the posterior update using these parameters, which avoids complex fitting algorithms.

## What It Tests

The task checks whether the agent can correctly implement Beta-binomial shrinkage math and handle low-volume/noisy samples correctly:
- Validation: Negative impressions, negative clicks, or clicks exceeding impressions must raise a `ValueError` in `posterior_summary`.
- Return rounding: Helper return floats must be rounded to exactly 6 decimals.
- Division by Zero: 0 impressions must be handled correctly, returning the prior mean.
- Shrinkage logic: The agent must verify that a low-volume ad (e.g. 2 clicks out of 2 impressions) is shrunk below a high-volume, high-performing ad (e.g. 500 clicks out of 10,000 impressions) even though the low-volume ad has a raw CTR of 100%.

## Environment

The environment is a small Python 3.13 workspace using only the standard library. Internet access is disabled and no credentials or external services are needed.

## Inputs

The workspace contains:
- `ad_clicks.csv`: CSV file with `ad_id,impressions,clicks`.
- `config.json`: Configuration file with `prior_strength` and `top_k`.
- `ctr_shrinkage.py`: Starter implementation module.
- `run_ctr.py`: Runner that executes the shrinkage model and writes results.

## Required Outputs

Create `outputs/ctr_report.json` with the structure:
- `prior`: `global_ctr`, `prior_strength`, `alpha0`, `beta0`
- `ranking`: List of top `top_k` ads sorted by `posterior_mean` in descending order.

All floats in the JSON must be rounded to exactly 6 decimals.

## Verification

Pytest-compatible tests compare `outputs/ctr_report.json` to `tests/expected.json` and import `ctr_shrinkage.py` to test edge cases:
- 2/2 low-volume ad is shrunk below a large-sample strong performer.
- 0 impressions is handled using prior mean.
- Negative clicks or impressions raises a `ValueError`.

The tests are executable via `python tests/test_outputs.py`.
