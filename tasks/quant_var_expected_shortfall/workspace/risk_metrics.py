def portfolio_returns(rows, weights):
    """
    Calculate portfolio returns for each row.

    Parameters:
    - rows: A list of dicts, where each dict has keys corresponding to asset names
            mapping to float returns (e.g., {'asset_a': 0.005, 'asset_b': -0.012, 'asset_c': 0.008}).
    - weights: A dict mapping asset names to float weights (e.g., {'asset_a': 0.4, 'asset_b': 0.3, 'asset_c': 0.3}).

    Returns:
    - A list of float portfolio returns.
    """
    raise NotImplementedError("Calculate portfolio returns.")


def historical_var_es(returns, confidence):
    """
    Calculate historical Value at Risk (VaR) and Expected Shortfall (ES) at a given confidence level.

    Parameters:
    - returns: A list of float portfolio returns.
    - confidence: A float confidence level (e.g., 0.95 or 0.99).

    Returns:
    - A tuple of (var, expected_shortfall) as floats.
    """
    raise NotImplementedError("Calculate historical VaR and Expected Shortfall.")
