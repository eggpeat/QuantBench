# Kalman 2D Market Tracker

## Overview

This Quant Bench task asks an agent to implement a multivariate 2D Kalman filter with structural break (anomaly) detection and covariance inflation to track a market's price and trend (velocity), producing `outputs/filtered_states.json`.

## Source Grounding & Provenance

 - **Source**: *Kalman and Bayesian Filters in Python* by Roger R. Labbe (Ch. 6 for multivariate Kalman equations; Ch. 8, Sec. 8.6 for outlier/anomaly detection using Mahalanobis distance).
 - **Task Behavior vs. Source**:
  - The implementation uses a 2D state-space representation with state vector $x = [p, v]^T$ representing price and velocity.
  - The transition model is $x_k = F x_{k-1} + w_k$, where $F = \begin{bmatrix} 1 & dt \\ 0 & 1 \end{bmatrix}$ (with $dt$ configurable or defaulting to $1.0$).
  - Anomaly detection is based on the Mahalanobis distance $D_M = \sqrt{y^T S^{-1} y}$ of the measurement innovation $y = z - H x_{pred}$.
  - When $D_M$ exceeds a configured `anomaly_threshold`, the step is flagged as an anomaly (`anomaly = True`).
  - To adapt to structural breaks/regime changes, the predicted state covariance matrix $P_{pred}$ is inflated by multiplying it by a factor `inflation_factor` (e.g., $10.0$) before running the measurement update. This represents the deliberate verifier contract.
 - **Verifier Risk**: None. The 2D Kalman filter and Mahalanobis gating implementation fully aligns with standard multivariate Kalman filtering and regime-shift detection principles, and the verifier strictly checks compliance with this specific contract.

## What It Tests

- Correct implementation of predict and update equations in a 2D Kalman filter (including matrix multiplication, transposition, addition, subtraction, and inversion in pure Python).
- Mathematical logic for multivariate innovation covariance $S = H P_{pred} H^T + R$ and Mahalanobis distance calculation.
- Handling covariance inflation when $D_M > \text{threshold}$ before updating state and covariance.
- Input validation (e.g. raising `ValueError` on negative values/matrices containing negative variance on diagonals).
- Correct formatting of floating-point numbers in the output JSON (rounded to 6 decimal places).

## Environment

The task uses `python:3.13-slim-bookworm`. No internet access, credentials, external services, or third-party packages are required. The implementation must use only the Python standard library.

## Inputs

- `workspace/observations.csv`: a CSV containing the time series observations with headers `time` and `price`.
- `workspace/config.json`: configuration with the filter matrices (as nested lists), `anomaly_threshold`, and `inflation_factor`.
- `workspace/kalman2d.py`: starter module containing the functions to implement.
- `workspace/run_kalman2d.py`: command-line entry point that reads the configuration and observations, runs the filter, and writes the filtered outputs.

## Required Outputs

- `workspace/outputs/filtered_states.json` formatted as a JSON object containing:
  - `"steps"`: array of per-step records with `"time"`, `"state"` (list of length 2), `"covariance"` (nested list representing $2 \times 2$ matrix), `"anomaly"` (boolean), and `"mahalanobis"` (float). All rounded to 6 decimal places.
  - `"final_state"`: list of length 2 representing the final posterior state.
  - `"final_covariance"`: nested list representing the final $2 \times 2$ posterior covariance.

## Verification

Pytest tests import `kalman2d.py`, run the workspace script, compare `outputs/filtered_states.json` with `tests/expected.json`, exercise specific test cases for accepted updates, anomaly/structural break handling, and error handling of invalid values.
