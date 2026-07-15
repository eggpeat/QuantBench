#!/usr/bin/env python3
import sys
from pathlib import Path
import optimize_query

def main():
    workspace_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent

    # Make sure outputs directory exists
    output_dir = workspace_path / "outputs"
    output_dir.mkdir(exist_ok=True)

    db_path = workspace_path / "backtest.db"
    query_path = workspace_path / "query.sql"

    # Run the candidate's optimize_query logic
    print(f"Running query optimization on {db_path}...")
    optimize_query.optimize_query(db_path, query_path, output_dir)
    print("Done. Outputs written to outputs/")

if __name__ == "__main__":
    main()
