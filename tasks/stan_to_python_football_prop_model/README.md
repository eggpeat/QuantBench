# stan_to_python_football_prop_model

## Overview

This Quant Bench task asks the agent to translate a quarterback passing touchdowns Poisson regression model from RStan (a Bayesian MCMC framework) to a deterministic Python-only implementation using Iteratively Reweighted Least Squares (IRLS).

The workspace contains historical player passing statistics in `data/passing_tds.csv`, upcoming prop bets in `data/prop_bets.csv`, and a reference RStan script `model_rstan.R`.

The candidate must complete the `football_prop_model.py` module in the workspace to fit the Poisson GLM, predict future game touchdown expectations ($\lambda$), compute tail probabilities (Over/Under), calculate fair American odds vs. market break-even, and determine the model's opinion. The verifier checks both the public snapshot and separate inline data/odds inputs to ensure a copied JSON file or hardcoded responses are not sufficient.

## Source Grounding & Provenance

- **Source**: *Football Analytics with Python & R: Learning Data Science Through the Lens of Sports* (Eric A. Eager and Richard A. Erickson, O'Reilly Media), Chapter 6: "Using Data Science for Sports Betting: Poisson Regression and Passing Touchdowns".
- **Task Behavior vs. Source**:
  - The task models player passing touchdowns per game via a Poisson Generalized Linear Model (GLM) with a log link, predicting game-level rate parameters ($\lambda$).
  - Expected outputs are converted to tail probabilities (exceeding a threshold) and compared to bookmaker odds to establish value opinions.
- **Verifier Risk**: None. Verifier and expected outputs are aligned with mathematically rigorous IRLS convergence and standard probability formulas.

## What It Tests

- Standard library numeric implementation of generalized linear models (IRLS algorithm for Poisson GLM with log link) without NumPy/SciPy.
- Numerical linear algebra (Gaussian elimination with partial pivoting) in pure Python.
- Exact calculation of Poisson cumulative distribution functions and tail probabilities ($P(Y > t)$).
- Conversion between probability, decimal odds, and positive/negative American betting odds.
- Value betting logic (identifying positive edges and outputting OVER, UNDER, or NO_BET opinions).
- Precise rounding and deterministic JSON schema formatting.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only (no numpy, scipy, pandas, or external packages allowed).
- No internet, credentials, or live database access.
- The verifier uses pytest-style assertions.

## Inputs

The workspace contains:

- `workspace/data/passing_tds.csv`: Historical game results containing quarterback name, opponent, home/away indicator, quarterback rating metric, opponent defense rating, and actual passing TDs.
- `workspace/data/prop_bets.csv`: Upcoming player prop options including market Over/Under odds and line thresholds.
- `workspace/model_rstan.R`: A reference script demonstrating the model structure in R and Stan.
- `workspace/football_prop_model.py`: Starter implementation file containing function stubs and docstrings.
- `workspace/run_model.py`: A wrapper script that imports and executes your `football_prop_model.py` module.

## Required Outputs

Create `outputs/prop_opinions.json` under the workspace with the following fields:

- `coefficients`: Dictionary of fitted model coefficients (`intercept`, `passer_rating`, `opp_defense_rating`, `is_home`).
- `prop_opinions`: List of dicts, each containing:
  - `prop_id`
  - `passer`
  - `opponent`
  - `line`
  - `lambda`
  - `model_prob_over`
  - `model_prob_under`
  - `market_be_over`
  - `market_be_under`
  - `fair_odds_over`
  - `fair_odds_under`
  - `edge_over`
  - `edge_under`
  - `opinion`

Round floats to 6 decimal places and American odds to the nearest integer.

## Verification

Candidates can run the calculations locally using:
```bash
python run_model.py
```
