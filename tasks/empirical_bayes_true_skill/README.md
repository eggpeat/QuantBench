# Empirical Bayes True Skill

## Overview

This Quant Bench task asks an agent to implement Beta-binomial empirical Bayes shrinkage on player success/attempt counts (skills) to shrink noisy, low-volume player performance toward a global prior fitted from the data. The agent must load a raw CSV of player records, fit a Beta prior using the Method of Moments, compute posterior parameters, means, and Normal approximation credible intervals, and output a ranked JSON report.

## Source Grounding & Provenance

 - **Source**: *Introduction to Empirical Bayes: Examples and Methods in R* by David Robinson (Chapter 3, pp. 21-25; Chapter 4, pp. 28-34).
 - **Task Behavior vs. Source**:
  - The task implements empirical Bayes estimation and posterior updating using success/total data (corresponding to R chapters 3 & 4).
  - While Robinson uses Maximum Likelihood Estimation (MLE) in R via the VGAM package to fit the prior, this task requires implementing the Method of Moments (MoM) with a robust fallback for prior parameter estimation. This enables a standard-library-only implementation without external optimization library dependencies.
  - The task also uses a Normal approximation to calculate 95% credible intervals for each player's posterior Beta distribution in Python, matching the conceptual behavior of qbeta discussed in Chapter 4 of the book.
 - **Verifier Risk**: None. The verifier checks exact output matching on a public dataset and runs programmatic test cases.

## What It Tests

The task checks whether the agent can correctly implement Beta-binomial shrinkage math, Method of Moments fitting, and handle edge cases and outliers:
- Validation: Negative success or attempt counts, or successes exceeding attempts, must raise a `ValueError`.
- Division by Zero: Players with 0 attempts must return the prior mean and be handled gracefully.
- Fallback logic: Method of Moments must handle zero-variance or high-variance cases using a fallback prior strength.
- Shrinkage logic: Noisy, low-volume performers (e.g. 2 successes out of 2 attempts) must shrink toward the global mean, ranking below a strong high-volume performer (e.g. 700 successes out of 1000 attempts) despite having a 100% raw success rate.

## Environment

The environment is a small Python 3.13 workspace using only the standard library. Internet access is disabled.

## Inputs

The workspace contains:
- `players.csv`: CSV file with columns `player_id,successes,attempts`.
- `eb_skill.py`: Starter implementation module.
- `run_eb_skill.py`: Runner that executes the model and writes results.

## Required Outputs

Create `outputs/skill_rankings.json` with the structure:
- `prior`: `alpha`, `beta`, `mean`
- `rankings`: Sorted list of players with `rank`, `player_id`, successes/attempts, raw/posterior statistics, and credible interval bounds.

All floats in the JSON must be rounded to exactly 6 decimals.

## Verification

Pytest-compatible tests compare `outputs/skill_rankings.json` to `tests/expected.json` and import `eb_skill.py` to test edge cases:
- 2/2 low-volume players shrink below the 700/1000 player.
- 0 attempts handles correctly.
- Negative counts or invalid inputs raise `ValueError`.

The tests are executable via `python tests/test_outputs.py`.
