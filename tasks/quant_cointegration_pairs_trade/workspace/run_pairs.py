import os
import sys
import json
import csv
from pathlib import Path

# Try importing pairs from local workspace or from system path
try:
    import pairs
except ImportError:
    # Fallback to local import if run from a sibling directory
    sys.path.append(str(Path(__file__).parent))
    import pairs


def main():
    workspace_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/workspace")
    prices_path = workspace_dir / "prices.csv"
    config_path = workspace_dir / "config.json"
    output_dir = workspace_dir / "outputs"
    output_path = output_dir / "pairs_signals.json"

    # Load price data
    if not prices_path.exists():
        print(f"Error: {prices_path} not found.", file=sys.stderr)
        sys.exit(1)

    rows = []
    with prices_path.open("r", encoding="utf-8") as f:
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

    # Analyze pair
    result = pairs.analyze_pair(rows, config)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    print(f"Pairs analysis report written to {output_path}")


if __name__ == "__main__":
    main()
