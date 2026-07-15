#!/usr/bin/env python3
"""Reference solution for the quant VaR and Expected Shortfall task."""

import json
import math
import sys
import csv
from pathlib import Path

RISK_METRICS_SOURCE = '''"""Historical Value at Risk (VaR) and Expected Shortfall (ES) metrics."""

import math


def portfolio_returns(rows, weights):
    """
    Calculate portfolio returns for each row.
    """
    p_returns = []
    for row in rows:
        ret = 0.0
        for asset, weight in weights.items():
            ret += float(row[asset]) * weight
        p_returns.append(ret)
    return p_returns


def historical_var_es(returns, confidence):
    """
    Calculate historical Value at Risk (VaR) and Expected Shortfall (ES) at a given confidence level.
    """
    if not (0.0 < confidence < 1.0):
        raise ValueError("Confidence level must be strictly between 0 and 1.")

    losses = [-r for r in returns]
    losses.sort()
    n = len(losses)
    if n == 0:
        return 0.0, 0.0

    # nearest-rank index
    idx = math.ceil(confidence * n) - 1
    # clamp index to [0, n - 1]
    idx = max(0, min(idx, n - 1))

    var_val = losses[idx]

    # ES is the arithmetic mean of losses greater than or equal to VaR
    es_losses = [x for x in losses if x >= var_val]
    es_val = sum(es_losses) / len(es_losses) if es_losses else var_val

    return var_val, es_val
'''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    workspace = Path(argv[0]) if argv else Path.cwd()

    # Write the solved code to workspace
    (workspace / "risk_metrics.py").write_text(RISK_METRICS_SOURCE, encoding="utf-8")

    # Load returns
    returns_path = workspace / "returns.csv"
    rows = []
    with returns_path.open("r", encoding="utf-8") as f:
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

    weights = config["weights"]
    confidence_levels = config["confidence_levels"]

    # Calculate metrics
    namespace = {}
    exec(RISK_METRICS_SOURCE, namespace)

    p_returns = namespace["portfolio_returns"](rows, weights)

    metrics = {}
    for conf in confidence_levels:
        var_val, es_val = namespace["historical_var_es"](p_returns, conf)
        metrics[str(conf)] = {
            "var": round(var_val, 6),
            "expected_shortfall": round(es_val, 6)
        }

    report = {
        "portfolio_returns": [round(r, 6) for r in p_returns],
        "metrics": metrics
    }

    output_dir = workspace / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "risk_report.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"Risk report written to {output_path}")


if __name__ == "__main__":
    main()
