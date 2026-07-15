# Kalman Live Market Filter

## Overview

This Quant Bench task asks an agent to implement a scalar (1D) Kalman filter with outlier gating to track a noisy market fair-value, then produce `outputs/filtered_market.json`.

## Source Grounding & Provenance

 - **Source**: *Kalman and Bayesian Filters in Python* by Roger R. Labbe (Ch. 4 for 1D predict/update/Kalman gain; Ch. 8, Sec. 8.6 for detecting/rejecting bad measurements).
 - **Task Behavior vs. Source**:
  - The Kalman filter implementation uses the 1D predict/update equations from Chapter 4 of Labbe.
  - The outlier gating rejects measurements if their absolute innovation exceeds $z \times \sqrt{S}$, where $S = P + R$ is the innovation covariance (the scalar Kalman predictive measurement variance, where $P$ is the predicted state variance and $R$ is the measurement noise covariance). This is the deliberate contract checked by the verifier.
  - For rejected measurements, the update step is bypassed and the predicted state mean and variance ($P$) are preserved directly as the posterior state for that step.
 - **Verifier Risk**: None. The 1D predictive gating implementation fully aligns with standard Kalman filter outlier rejection principles, and the verifier strictly checks compliance with this specific scalar contract.

## What It Tests

- Correct implementation of predict and update equations in a 1D Kalman filter.
- Mathematical logic for outlier gating using standard deviation of innovation and a z-score threshold.
- Correct handling of state preservation (using predicted state as next state) when outliers are rejected.
- Input validation (e.g. raising `ValueError` on invalid negative variance).
- Formatting outputs correctly to 6 decimal places in JSON.

## Environment

The task uses `python:3.13-slim-bookworm`. No internet access, credentials, external services, or third-party packages are required. The implementation should use only the Python standard library.

## Inputs

- `workspace/observations.json`: a time series of noisy market fair-value observations.
- `workspace/config.json`: initial state prior, process noise variance, measurement noise variance, and outlier z-threshold.
- `workspace/market_filter.py`: starter module containing the functions to implement.
- `workspace/run_filter.py`: command-line entry point that reads the configuration and observations and writes the filtered outputs.

## Required Outputs

- `workspace/outputs/filtered_market.json` formatted as a JSON object containing:
  - `"steps"`: array of per-step records with `"time"`, `"mean"`, `"variance"`, and `"accepted"`.
  - `"final_state"`: dict with final posterior `"mean"` and `"variance"`.

## Verification

Pytest tests import `market_filter.py`, run the workspace script, compare `outputs/filtered_market.json` with `tests/expected.json`, exercise specific test cases for accepted updates, outlier rejection, and error handling of invalid values.
