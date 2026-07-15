#!/usr/bin/env python3
import json
import sys
from pathlib import Path

MODULE_SOURCE = r'''
import sqlite3
import json
from pathlib import Path

def optimize_query(db_path: Path, query_path: Path, output_dir: Path):
    """
    Optimizes the execution of the query in query_path on the SQLite database at db_path.

    This function should:
    1. Create the necessary indexes on the SQLite database to optimize query performance.
    2. Execute the query found in query_path.
    3. Save the query results to output_dir / 'query_result.json' as a list of dicts.
    4. Save the EXPLAIN QUERY PLAN details to output_dir / 'query_plan.json' as a list of dicts.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create indexes to optimize the query plan
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_filter ON matches (sport, kickoff_time);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_odds_lookup ON odds (game_id, bookmaker, recorded_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_predictions_lookup ON predictions (game_id, model_name, generated_at);")
    conn.commit()

    # Read the query
    with open(query_path, "r", encoding="utf-8") as f:
        query = f.read()

    # Execute query
    cursor.execute(query)
    rows = cursor.fetchall()

    # Map results using columns
    keys = [col[0] for col in cursor.description]
    result_json = [dict(zip(keys, r)) for r in rows]

    # Write result
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "query_result.json", "w", encoding="utf-8") as f:
        json.dump(result_json, f, indent=2)

    # Run EXPLAIN QUERY PLAN
    cursor.execute("EXPLAIN QUERY PLAN " + query)
    plan_cols = [col[0] for col in cursor.description]
    plan_rows = [dict(zip(plan_cols, r)) for r in cursor.fetchall()]

    with open(output_dir / "query_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan_rows, f, indent=2)

    conn.close()
'''.lstrip()

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "optimize_query.py").write_text(MODULE_SOURCE, encoding="utf-8")

    # Import and run to generate outputs in the workspace
    sys.path.insert(0, str(workspace))
    import optimize_query

    db_path = workspace / "backtest.db"
    query_path = workspace / "query.sql"
    output_dir = workspace / "outputs"

    optimize_query.optimize_query(db_path, query_path, output_dir)

if __name__ == "__main__":
    main()
