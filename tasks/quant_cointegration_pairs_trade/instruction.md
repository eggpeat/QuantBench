# Cointegration and Pairs Trading Signals

Implement statistical pairs trading analysis based on Engle-Granger cointegration methodology in `pairs.py` and run the script to generate `outputs/pairs_signals.json`.

## Inputs

1. `prices.csv`: Contains the daily closing prices of two assets, with columns `date,Asset_A,Asset_B`.
2. `config.json`: Contains the configuration settings for the analysis. Format:
   ```json
   {
     "x_col": "Asset_A",
     "y_col": "Asset_B",
     "adf_critical_value": -2.76,
     "z_threshold": 2.0
   }
   ```

## Requirements

1. **Hedge Ratio Fitting**:
   Implement `fit_hedge_ratio(x, y)` to calculate the hedge ratio $\beta$ by regressing the dependent asset series $y$ on the independent asset series $x$ using ordinary least squares (OLS) without an intercept:
   $$y_t = \beta x_t + \epsilon_t$$
   The hedge ratio $\beta$ is computed as:
   $$\beta = \frac{\sum_{t=1}^N x_t y_t}{\sum_{t=1}^N x_t^2}$$
   where $N$ is the number of data points, and $x$, $y$ are lists of prices. If the denominator is 0, return `0.0`.

2. **Augmented Dickey-Fuller (ADF) t-statistic**:
   Implement `adf_t_stat(residuals)` to compute a simple no-lag, no-intercept Augmented Dickey-Fuller (Dickey-Fuller) t-statistic to test the stationarity of the residuals $e_t = y_t - \beta x_t$.
   The model is:
   $$\Delta e_t = \rho e_{t-1} + u_t \quad \text{for } t = 2, \dots, N$$
   where $\Delta e_t = e_t - e_{t-1}$ is the change in the residuals, and $e_{t-1}$ is the lagged level of the residuals.
   Let $Y_t = \Delta e_t$ and $X_t = e_{t-1}$ for $t = 2, \dots, N$.
   Let $M = N - 1$ be the number of observations in this regression.
   The OLS estimate of $\rho$ is:
   $$\hat{\rho} = \frac{\sum_{t=2}^N X_t Y_t}{\sum_{t=2}^N X_t^2}$$
   The residual sum of squares (RSS) is:
   $$\text{RSS} = \sum_{t=2}^N (Y_t - \hat{\rho} X_t)^2$$
   The regression error variance is estimated with $M-1 = N-2$ degrees of freedom:
   $$\hat{\sigma}^2 = \frac{\text{RSS}}{N - 2}$$
   The standard error of $\hat{\rho}$ is:
   $$\text{SE}(\hat{\rho}) = \sqrt{\frac{\hat{\sigma}^2}{\sum_{t=2}^N X_t^2}}$$
   The t-statistic is:
   $$t = \frac{\hat{\rho}}{\text{SE}(\hat{\rho})}$$
   If the denominator in any division (or standard error) is 0, return `0.0`. If $N < 3$, return `0.0`.

3. **Pair Analysis**:
   Implement `analyze_pair(rows, config)` to perform the full analysis.
   - Extract the independent series $x$ and dependent series $y$ from `rows` (using `x_col` and `y_col`).
   - Fit the hedge ratio $\beta$ using `fit_hedge_ratio(x, y)`.
   - Calculate the residuals: $\text{residuals}_t = y_t - \beta x_t$.
   - Calculate the sample mean ($\mu$) and sample standard deviation ($\sigma$) of the residuals:
     $$\mu = \frac{1}{N} \sum_{t=1}^N \text{residuals}_t$$
     $$\sigma = \sqrt{\frac{1}{N-1} \sum_{t=1}^N (\text{residuals}_t - \mu)^2}$$
   - Calculate the z-score of the last (most recent) residual $e_N$:
     $$z = \frac{e_N - \mu}{\sigma}$$
     If $\sigma = 0$, the z-score should be `0.0`.
   - Compute the ADF t-statistic using `adf_t_stat(residuals)`.
   - Determine if the pair is cointegrated: `cointegrated` is `true` if the ADF t-statistic is strictly less than `adf_critical_value` (from the config), else `false`.
   - Generate the trading signal based on the z-score and the `z_threshold` parameter:
     - If $z \le -\text{z\_threshold}$, signal is `"BUY"` (spread is cheap, buy Y and sell X).
     - If $z \ge \text{z\_threshold}$, signal is `"SELL"` (spread is rich, sell Y and buy X).
     - Otherwise, signal is `"HOLD"`.

4. **JSON Output**:
   The execution script `run_pairs.py` should save the results of `analyze_pair` in `outputs/pairs_signals.json` with the following keys:
   - `hedge_ratio`: float (rounded to 6 decimals)
   - `residual_mean`: float (rounded to 6 decimals)
   - `residual_std`: float (rounded to 6 decimals)
   - `z_score`: float (rounded to 6 decimals)
   - `adf_t_stat`: float (rounded to 6 decimals)
   - `cointegrated`: boolean
   - `signal`: string (`"BUY"`, `"SELL"`, or `"HOLD"`)

Use only Python's standard library. Do not use external libraries like pandas, numpy, scipy, statsmodels, etc.
