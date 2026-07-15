# Historical Value at Risk (VaR) and Expected Shortfall (ES)

Implement historical simulation for portfolio risk metrics in `risk_metrics.py` and run the script to generate `outputs/risk_report.json`.

## Inputs

1. `returns.csv`: Contains the daily returns of several assets, with columns `date,asset_a,asset_b,asset_c,...`.
2. `config.json`: Contains portfolio weights and the confidence levels at which risk metrics should be computed. Format:
   ```json
   {
     "weights": {
       "asset_a": 0.4,
       "asset_b": 0.3,
       "asset_c": 0.3
     },
     "confidence_levels": [0.95, 0.99]
   }
   ```

## Requirements

1. **Portfolio Returns**:
   Compute the portfolio return for each day as the weighted sum of the individual asset returns:
   $$\text{portfolio\_return} = \sum_{j} w_j \times r_j$$
   where $w_j$ is the weight of asset $j$ and $r_j$ is the return of asset $j$ for that day.

2. **Historical Loss**:
   Define daily historical loss as the negative of the portfolio return:
   $$\text{loss} = -\text{portfolio\_return}$$
   Sort the losses in ascending order: $L_{(1)} \le L_{(2)} \le \dots \le L_{(n)}$, where $n$ is the total number of days/observations.

3. **Value at Risk (VaR)**:
   For a given confidence level $c \in (0, 1)$, compute VaR using the nearest-rank method:
   - Calculate the 0-based index $i = \lceil c \times n \rceil - 1$.
   - Clamp the index $i$ to be within the valid range $[0, n-1]$ (i.e. $0 \le i \le n-1$).
   - The VaR value is the loss at index $i$: $\text{VaR} = L_{(i+1)}$ (the sorted loss value at that 0-based index).
   - If the confidence level is not strictly between 0 and 1, raise a `ValueError`.

4. **Expected Shortfall (ES)**:
   Based on the theoretical concepts of coherent risk measures (Acerbi & Tasche 2002 / arXiv:cond-mat/0104295), Expected Shortfall is the expectation of losses in the tail exceeding the VaR threshold.
   For the purpose of this task and the verifier's deterministic test suite, you must use a discrete historical ES approximation. This finite-sample contract is defined as the arithmetic mean of all losses in the dataset that are greater than or equal to the calculated VaR threshold (the nearest-rank value at index $i$).
   Specifically, select all historical losses $L_j$ such that $L_j \ge \text{VaR}$, and calculate their arithmetic mean.
5. **JSON Report Output**:
   Write the outputs to `outputs/risk_report.json` with the following structure:
   - `portfolio_returns`: List of float portfolio returns (rounded to 6 decimals).
   - `metrics`: Dictionary mapping each confidence level string (e.g. `"0.95"`, `"0.99"`) to its corresponding `"var"` and `"expected_shortfall"` (each rounded to 6 decimals).

Use only Python's standard library. Do not use external libraries like pandas, numpy, scipy, etc.
