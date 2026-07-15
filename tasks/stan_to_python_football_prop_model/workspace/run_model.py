#!/usr/bin/env python3
import sys
from pathlib import Path

# Add current workspace to path
sys.path.insert(0, str(Path(__file__).parent))
import football_prop_model


def main():
    workspace_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent

    data_csv = workspace_dir / "data" / "passing_tds.csv"
    props_csv = workspace_dir / "data" / "prop_bets.csv"

    # Ensure outputs directory exists
    outputs_dir = workspace_dir / "outputs"
    outputs_dir.mkdir(exist_ok=True)

    print(f"Running prop analysis in workspace: {workspace_dir}")
    football_prop_model.analyze_props(str(data_csv), str(props_csv))
    print("Done!")


if __name__ == "__main__":
    main()
