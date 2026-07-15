# Cointegration Pairs Trading Analysis

## Overview

This Quant Bench task requires the candidate to implement statistical pairs trading analysis by fitting an OLS hedge ratio and computing a simple Augmented Dickey-Fuller (ADF) t-statistic to determine cointegration.

## Source Grounding & Provenance
 - **Source**: *Mastering R for Quantitative Finance* pages 27-31: defines cointegration, details simulation of cointegrating series, and describes the Engle-Granger two-step method of testing cointegration (fitting a regression of one series on the other and testing residuals for unit root).
 - **Task Behavior vs. Source**:
  - The OLS hedge ratio and Engle-Granger two-step method map directly to the description in *Mastering R for Quantitative Finance* (pages 30-31).
  - To keep the task stdlib-only compatible and self-contained in Python, we simplify the Augmented Dickey-Fuller test to a no-lag, no-intercept Dickey-Fuller t-statistic on residuals.
  - The decision boundary for cointegration uses a critical value of -2.76, representing the 5% critical value of the DF test statistic on residuals without drift or trend.
 - **Verifier Risk**: Low risk of verification failure since the verifier strictly checks compliance with this discrete approximation and specific OLS/ADF formulations.

## What It Tests

This task verifies:
1. Parsing daily asset prices from a CSV file.
2. Fitting an OLS regression slope without intercept to calculate a hedge ratio $\beta = \frac{\sum x_t y_t}{\sum x_t^2}$.
3. Implementing a no-lag, no-intercept ADF t-statistic for residuals.
4. Correct mathematical calculation of residual sample mean, sample standard deviation, z-score, and signal.
5. Correct identification of cointegrated pairs based on critical values, rejecting merely correlated non-cointegrated pairs.
6. Writing results to a formatted JSON report with rounding to 6 decimal places.

## Environment

Python 3.13 standard library only. No external dependencies.

## Inputs

- `workspace/prices.csv`: Daily price history containing cointegrated Asset_A and Asset_B.
- `workspace/config.json`: Column names, ADF critical value, and z-score threshold.

## Required Outputs

- `workspace/outputs/pairs_signals.json`: Contains the fitted hedge ratio, residual stats, ADF t-stat, cointegrated decision, and signals.
