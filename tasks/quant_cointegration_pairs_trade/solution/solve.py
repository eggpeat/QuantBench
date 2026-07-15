#!/usr/bin/env python3
"""Reference solution for the quant cointegration pairs trading task."""

import json
import math
import sys
import csv
from pathlib import Path

PAIRS_SOURCE = '''"""Cointegration and Pairs Trading analysis."""

import math


def fit_hedge_ratio(x, y):
    """
    Calculate the hedge ratio beta by regressing y on x without an intercept.
    """
    num = sum(xv * yv for xv, yv in zip(x, y))
    den = sum(xv * xv for xv in x)
    if den == 0:
        return 0.0
    return num / den


def adf_t_stat(residuals):
    """
    Calculate the Augmented Dickey-Fuller (no-lag, no-intercept) t-statistic for the residuals.
    """
    n = len(residuals)
    if n < 3:
        return 0.0

    dy = [residuals[i] - residuals[i-1] for i in range(1, n)]
    dx = [residuals[i-1] for i in range(1, n)]

    m = n - 1
    num = sum(dxv * dyv for dxv, dyv in zip(dx, dy))
    den = sum(dxv * dxv for dxv in dx)

    if den == 0:
        return 0.0

    rho = num / den
    u = [dyv - rho * dxv for dxv, dyv in zip(dx, dy)]
    rss = sum(uv * uv for uv in u)

    variance = rss / (n - 2)
    if variance <= 0:
        return 0.0

    se_rho = math.sqrt(variance / den)
    if se_rho == 0:
        return 0.0

    return rho / se_rho


def analyze_pair(rows, config):
    """
    Analyze a pair of assets from the rows of price data using the config settings.
    """
    x_col = config["x_col"]
    y_col = config["y_col"]
    adf_critical_value = config["adf_critical_value"]
    z_threshold = config["z_threshold"]

    x = [row[x_col] for row in rows]
    y = [row[y_col] for row in rows]

    hedge_ratio = fit_hedge_ratio(x, y)
    residuals = [y_val - hedge_ratio * x_val for x_val, y_val in zip(x, y)]

    n = len(residuals)
    res_mean = sum(residuals) / n
    res_var = sum((r - res_mean)**2 for r in residuals) / (n - 1)
    res_std = math.sqrt(res_var)

    last_res = residuals[-1]
    z_score = (last_res - res_mean) / res_std if res_std > 0 else 0.0
    t_stat = adf_t_stat(residuals)

    cointegrated = t_stat < adf_critical_value

    if z_score <= -z_threshold:
        signal = "BUY"
    elif z_score >= z_threshold:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "hedge_ratio": round(hedge_ratio, 6),
        "residual_mean": round(res_mean, 6),
        "residual_std": round(res_std, 6),
        "z_score": round(z_score, 6),
        "adf_t_stat": round(t_stat, 6),
        "cointegrated": cointegrated,
        "signal": signal
    }
'''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    workspace = Path(argv[0]) if argv else Path.cwd()

    # Write the solved code to workspace
    (workspace / "pairs.py").write_text(PAIRS_SOURCE, encoding="utf-8")

    # Load prices
    prices_path = workspace / "prices.csv"
    rows = []
    with prices_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed_row = {"date": row["date"]}
            for col in reader.fieldnames:
                if col != "date":
                    parsed_row[col] = float(row[col])
            rows.append(parsed_row)

    # Load config
    config_path = workspace / "config.json"
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    # Calculate metrics
    namespace = {}
    exec(PAIRS_SOURCE, namespace)

    result = namespace["analyze_pair"](rows, config)

    output_dir = workspace / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "pairs_signals.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    print(f"Pairs trading signals written to {output_path}")


if __name__ == "__main__":
    main()
