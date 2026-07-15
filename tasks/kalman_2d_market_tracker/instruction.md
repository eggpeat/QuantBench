Workspace task. Implement a 2D state-space Kalman filter with Mahalanobis-based anomaly detection and covariance inflation in `kalman2d.py` and write `outputs/filtered_states.json`.

The workspace contains:
1. `config.json` with parameters:
   - `initial_state`: a list of length 2 `[price, velocity]`
   - `initial_covariance`: a $2 \times 2$ matrix (nested list of lists)
   - `transition_matrix`: a $2 \times 2$ matrix `F` (nested list of lists)
   - `process_noise`: a $2 \times 2$ matrix `Q` (nested list of lists)
   - `measurement_matrix`: a $1 \times 2$ matrix `H` (nested list of lists)
   - `measurement_noise`: a $1 \times 1$ matrix `R` (nested list of lists)
   - `anomaly_threshold`: Mahalanobis distance threshold for anomaly/structural-break detection (float)
   - `inflation_factor`: scale factor to multiply predicted covariance matrix `P_pred` if anomaly is detected (float)

2. `observations.csv` containing time series observations with headers `time` and `price`.

Implement the following functions in `kalman2d.py`:

- `predict(x, P, F, Q)`:
  Performs the state-space prediction step:
  $$x_{pred} = F x$$
  $$P_{pred} = F P F^T + Q$$
  Returns `(x_pred, P_pred)` where `x_pred` is a list of length 2, and `P_pred` is a $2 \times 2$ matrix as a list of lists.
  Raise a `ValueError` if `P[0][0]` or `P[1][1]` is negative, or if `Q[0][0]` or `Q[1][1]` is negative.

- `update(x_pred, P_pred, z, H, R, anomaly_threshold, inflation_factor)`:
  Performs the measurement update step with anomaly detection and covariance inflation:
  1. Compute innovation/residual:
     $$y = z - H x_{pred}$$
  2. Compute innovation covariance:
     $$S = H P_{pred} H^T + R$$
  3. Compute Mahalanobis distance:
     $$D_M = \sqrt{y^T S^{-1} y}$$
  4. Determine if the step is an anomaly:
     `anomaly = D_M > anomaly_threshold`
  5. If `anomaly` is True:
     - Inflate predicted covariance:
       $$P_{pred\_inflated} = \text{inflation\_factor} \times P_{pred}$$
     - Recalculate innovation covariance:
       $$S = H P_{pred\_inflated} H^T + R$$
     - Use $P_{pred\_inflated}$ as the predicted covariance for the update.
  6. Compute Kalman Gain:
     $$K = P_{pred} H^T S^{-1}$$  (using $P_{pred\_inflated}$ if anomaly is True)
  7. Compute updated state estimate and covariance:
     $$x_{opt} = x_{pred} + K y$$
     $$P_{opt} = P_{pred} - K H P_{pred}$$ (standard update equation)
  Returns `(x_opt, P_opt, anomaly, D_M)`.
  Raise a `ValueError` if any diagonal element of `R` is negative, or if `anomaly_threshold` or `inflation_factor` is negative.
  Raise a `ValueError` if $S$ (for a 1x1 measurement) is zero or less, or if $S$ is singular or non-invertible.

  *Matrix operations helper details:*
  Since $M = 1$ in this task (scalar observations, so $z$ is a 1-element list `[price_value]`), $H$ is a $1 \times 2$ matrix `[[H0, H1]]`, $R$ is a $1 \times 1$ matrix `[[R00]]`, $y$ is a 1-element vector `[y0]`, and $S$ is a $1 \times 1$ matrix `[[S00]]`.
  Thus, $S^{-1} = [[1.0 / S00]]$.
  Mahalanobis distance $D_M = \sqrt{y_0^2 / S00} = \frac{|y_0|}{\sqrt{S00}}$.
  Kalman Gain $K$ is a $2 \times 1$ matrix: `[[K0], [K1]]`, where $K_i = (P_{pred} H^T)_i / S00$.
  If you implement general matrix operations, support at least these dimensions.

- `filter_series(rows, config)`:
  Runs the Kalman filter over the rows of observations.
  `rows` is a list of dicts, where each dict has keys `time` and `price`.
  Returns a dictionary with:
  - `"steps"`: a list of dicts, each containing:
    - `"time"`: float or int from row
    - `"state"`: list of float `[price_estimate, velocity_estimate]`
    - `"covariance"`: $2 \times 2$ matrix as list of lists
    - `"anomaly"`: bool
    - `"mahalanobis"`: float (Mahalanobis distance)
  - `"final_state"`: list of float `[price_estimate, velocity_estimate]`
  - `"final_covariance"`: $2 \times 2$ matrix as list of lists

Required behavior:
1. Running `python run_kalman2d.py` from the workspace must read `config.json` and `observations.csv`, filter the series, and create `outputs/filtered_states.json`.
2. All numeric values in the written JSON must be rounded to 6 decimal places.
3. Use only the Python standard library.
