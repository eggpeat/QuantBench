# Quantitative Portfolio Risk: Historical VaR and Expected Shortfall

## Overview

This Quant Bench task requires the candidate to implement historical portfolio Value at Risk (VaR) and Expected Shortfall (ES) calculations from a CSV of asset returns and a JSON configuration file.

## Source Grounding & Provenance
 - **Source**: *Mastering R for Quantitative Finance* read-extracted lines 9995-10001 and 10035-10055 for VaR and historical simulation; read-extracted lines 10080-10095 for Expected Shortfall as a tail expectation beyond VaR, with the book noting that full ES treatment is beyond its scope and referring to Acerbi and Tasche (2002).
 - **Task Behavior vs. Source**:
  - The historical VaR calculation maps to the historical simulation guidelines in *Mastering R for Quantitative Finance* (lines 10035-10055).
  - Expected Shortfall (ES) calculation is defined theoretically in *Mastering R for Quantitative Finance* as a tail expectation beyond VaR, citing Carlo Acerbi and Dirk Tasche (2002), "Expected Shortfall for Coherent Risk Measures" (also arXiv:cond-mat/0104295) for coherence properties.
  - For this coding task, the verifier expects a simplified discrete historical ES approximation calculated as `mean(losses >= VaR nearest-rank threshold)`. This finite-sample discrete approximation is an intentional verifier contract rather than an analytical continuous or interpolated tail-distribution expectation.
 - **Verifier Risk**: Low risk of verification failure since the verifier strictly checks compliance with this discrete approximation. A solver must implement the specific discrete averaging contract (`losses >= VaR`) rather than any alternative continuous or strictly greater-than formula to pass verification.
## What It Tests

This task verifies:
1. Parsing daily asset returns from a CSV file.
2. Computing weighted portfolio returns from asset returns and weights.
3. Sorting historical losses ($loss = -return$) and finding Value at Risk (VaR) via the nearest-rank index method with proper clamping.
4. Correct mathematical calculation of Expected Shortfall (ES) as the mean of all losses $\ge$ VaR.
5. Raising a `ValueError` for confidence levels outside $(0, 1)$.
6. Writing results to a formatted JSON report with rounding to 6 decimal places.

## Environment

Python 3.13 standard library only. No external dependencies.

## Inputs

- `workspace/returns.csv`: Deterministic return sequence containing positive and negative returns across three assets.
- `workspace/config.json`: Portfolio weights and target confidence levels.

## Required Outputs

- `workspace/outputs/risk_report.json`: Contains portfolio returns and risk metrics for each confidence level.
