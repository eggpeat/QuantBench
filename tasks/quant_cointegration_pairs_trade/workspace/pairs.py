def fit_hedge_ratio(x, y):
    """
    Calculate the hedge ratio beta by regressing y on x without an intercept.

    Parameters:
    - x: A list of floats (independent variable series, e.g. prices of Asset A).
    - y: A list of floats (dependent variable series, e.g. prices of Asset B).

    Returns:
    - A float: the hedge ratio beta.

    Formula:
      beta = sum(x_t * y_t) / sum(x_t^2)
    """
    raise NotImplementedError("Calculate hedge ratio.")


def adf_t_stat(residuals):
    """
    Calculate the Augmented Dickey-Fuller (no-lag, no-intercept) t-statistic
    for the residuals.

    Parameters:
    - residuals: A list of floats.

    Returns:
    - A float: the t-statistic of the lag-1 regression of the differences
      on the lagged levels.

    Model:
      Delta e_t = rho * e_{t-1} + u_t  (for t = 2...N)
      where Delta e_t = e_t - e_{t-1} and e_{t-1} is the lagged residual.

    Returns:
      t_stat = rho_hat / SE(rho_hat)
      where:
        rho_hat = sum(e_{t-1} * Delta e_t) / sum(e_{t-1}^2)
        RSS = sum((Delta e_t - rho_hat * e_{t-1})^2)
        variance = RSS / (N - 2)
        SE(rho_hat) = sqrt(variance / sum(e_{t-1}^2))
    """
    raise NotImplementedError("Calculate ADF t-statistic.")


def analyze_pair(rows, config):
    """
    Analyze a pair of assets from the rows of price data using the config settings.

    Parameters:
    - rows: A list of dicts, where each dict has keys corresponding to asset names
            mapping to float prices (e.g., {'date': '2025-01-01', 'Asset_A': 100.0, 'Asset_B': 120.0}).
    - config: A dict containing:
      - 'x_col': Name of the independent asset column (str)
      - 'y_col': Name of the dependent asset column (str)
      - 'adf_critical_value': Critical value for the cointegration decision (float)
      - 'z_threshold': Threshold for z-score signals (float)

    Returns:
    - A dict containing:
      - 'hedge_ratio': float (rounded to 6 decimal places)
      - 'residual_mean': float (rounded to 6 decimal places)
      - 'residual_std': float (rounded to 6 decimal places)
      - 'z_score': float (rounded to 6 decimal places)
      - 'adf_t_stat': float (rounded to 6 decimal places)
      - 'cointegrated': bool
      - 'signal': str ("BUY", "SELL", or "HOLD")
    """
    raise NotImplementedError("Analyze pair.")
