Workspace task. Implement a scalar Kalman filter with outlier gating/rejection in `market_filter.py` and write `outputs/filtered_market.json`.

The workspace contains:
1. `config.json` with parameters:
   - `initial_mean`: initial posterior state estimate mean
   - `initial_variance`: initial posterior state estimate variance
   - `process_variance`: process noise variance (Q)
   - `measurement_variance`: measurement noise variance (R)
   - `outlier_z`: z-score threshold for outlier rejection

2. `observations.json` containing a list of objects with `time`, `measurement`, and optionally `label`.

Implement the following functions in `market_filter.py`:

- `kalman_step(mean, variance, measurement, process_variance, measurement_variance, outlier_z)`:
  1. Predict:
     - predicted_mean = mean
     - predicted_variance = variance + process_variance
  2. Evaluate Outlier Gating:
     - Compute the innovation variance (the scalar Kalman predictive measurement variance, i.e., $S = P + R$):
       `innovation_variance = predicted_variance + measurement_variance`
     - `std_innovation = sqrt(innovation_variance)`
     - `threshold = outlier_z * std_innovation`
     - `abs_diff = abs(measurement - predicted_mean)`
     - `accepted = abs_diff <= threshold` (this is the deliberate verifier contract for gating outliers)
  3. Update:
     - If `accepted` is True:
       - kalman_gain = predicted_variance / innovation_variance
       - updated_mean = predicted_mean + kalman_gain * (measurement - predicted_mean)
       - updated_variance = (1.0 - kalman_gain) * predicted_variance
     - If `accepted` is False (i.e. outlier):
       - Preserve the predicted state:
         - updated_mean = predicted_mean
         - updated_variance = predicted_variance
  4. Returns `(updated_mean, updated_variance, accepted)`.
  5. Validation:
     - If `variance` is negative, raise a `ValueError`.
     - If `process_variance` or `measurement_variance` or `outlier_z` is negative, raise a `ValueError`.
     - If `variance` is zero, we proceed normally, but if `innovation_variance` is zero or less, raise `ValueError`.

- `filter_series(config, observations)`:
  Run the Kalman filter over the observations sequentially starting from `initial_mean` and `initial_variance` as the initial posterior state.
  Returns:
  - `steps`: a list of steps, each containing `time`, posterior `mean`, posterior `variance`, and `accepted` (boolean).
  - `final_state`: a dictionary containing `mean` and `variance`.

Required behavior:
1. Running `python run_filter.py` from the workspace must read `config.json` and `observations.json` and create `outputs/filtered_market.json`.
2. All numeric values in the written JSON must be rounded to 6 decimal places.
3. Use only the Python standard library.
