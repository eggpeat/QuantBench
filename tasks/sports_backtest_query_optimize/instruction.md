Optimize the execution of the SQL query in `query.sql` on the historical backtest database `backtest.db`.

## Context
You are auditing historical backtest data for a sports modeling/trading pipeline. The SQLite database `backtest.db` contains matches, odds, and predictions. The backtest query evaluated in `query.sql` calculates average odds and average predicted probabilities for positive-edge bets, grouped by sport and bookmaker, over a specific date range.

Currently, the database has no user-defined indexes. Running the query requires full table scans (`SCAN TABLE`) and forces SQLite to create automatic temporary indexes on the fly, making the query extremely slow and inefficient.

## Requirements

1. Complete the stub function `optimize_query(db_path, query_path, output_dir)` in `optimize_query.py`:
   - Create appropriate indexes in `backtest.db` (e.g. using `CREATE INDEX IF NOT EXISTS ...`) to speed up the query execution.
   - Execute the query in `query.sql` (or a logically equivalent optimized version).
   - Save the query results to `outputs/query_result.json` as a JSON array of objects with keys: `"sport"`, `"bookmaker"`, `"total_bets"`, `"avg_odds"`, `"avg_pred"`.
   - Save the `EXPLAIN QUERY PLAN` explanation of your optimized query to `outputs/query_plan.json` as a JSON array of objects. Each object must contain the query plan columns returned by the SQLite cursor (`id`, `parent`, `notused`, `detail`).

2. The optimized query plan must:
   - Not contain any table scans (`SCAN TABLE` / `SCAN` on the database tables).
   - Not cause any automatic index creation (`AUTOMATIC COVERING INDEX`, etc.).
   - Utilize the indexes you created to perform fast searches (`SEARCH TABLE ... USING INDEX ...`).
   - Produce the exact same result rows as the original query.

3. Boring standard-library Python only. Do not use external libraries, and do not access the internet.
