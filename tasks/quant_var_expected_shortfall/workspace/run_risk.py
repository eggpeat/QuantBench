import os
import sys
import json
import csv
from pathlib import Path

# Try importing risk_metrics from local workspace or from system path
try:
    import risk_metrics
except ImportError:
    # Fallback to local import if run from a sibling directory
    sys.path.append(str(Path(__file__).parent))
    import risk_metrics


def main():
    workspace_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    returns_path = workspace_dir / "returns.csv"
    config_path = workspace_dir / "config.json"
    output_dir = workspace_dir / "outputs"
    output_path = output_dir / "risk_report.json"

    # Load return data
    if not returns_path.exists():
        print(f"Error: {returns_path} not found.", file=sys.stderr)
        sys.exit(1)

    rows = []
    with returns_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parsed_row = {"date": row["date"]}
            for col in reader.fieldnames:
                if col != "date":
                    parsed_row[col] = float(row[col])
            rows.append(parsed_row)

    # Load configuration
    if not config_path.exists():
        print(f"Error: {config_path} not found.", file=sys.stderr)
        sys.exit(1)

    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    weights = config["weights"]
    confidence_levels = config["confidence_levels"]

    # Calculate portfolio returns
    p_returns = risk_metrics.portfolio_returns(rows, weights)

    # Calculate metrics for each confidence level
    metrics = {}
    for conf in confidence_levels:
        var_val, es_val = risk_metrics.historical_var_es(p_returns, conf)
        # Format confidence level as string for json key (e.g. "0.95")
        metrics[str(conf)] = {
            "var": round(var_val, 6),
            "expected_shortfall": round(es_val, 6)
        }

    report = {
        "portfolio_returns": [round(r, 6) for r in p_returns],
        "metrics": metrics
    }

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    print(f"Risk report written to {output_path}")


if __name__ == "__main__":
    main()
