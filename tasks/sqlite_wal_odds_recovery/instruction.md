Read `odds.db` and `odds_transactions.jsonl` from the workspace and create `outputs/recovered_ticks.json`.

You are auditing a crashed sports betting odds processor database. Implement the recovery calculations in boring standard-library Python; do not use external services, third-party libraries, or network access.

Starter files are provided in the workspace:
- `recover.py`: Contains stubs for your implementation.
- `run_recovery.py`: A script that imports and runs your `recover.main()` function. You can run this using `python run_recovery.py`.

Required implementation:

1. Complete the workspace module named `recover.py` exposing at least this function:
   - `recover_database(workspace: str | Path) -> dict`
2. Process the log sidecar file `odds_transactions.jsonl` in the workspace and recover the state of `odds.db`.
3. Write `outputs/recovered_ticks.json` with the recovery summary.

### Schema of the SQLite Database `odds.db`

The database contains the following tables:
- `markets`:
  - `market_id` (TEXT PRIMARY KEY)
  - `home_team` (TEXT)
  - `away_team` (TEXT)
  - `sport` (TEXT)
- `ticks_log`:
  - `tick_id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `timestamp` (TEXT)
  - `sportsbook` (TEXT)
  - `market_id` (TEXT)
  - `outcome` (TEXT)
  - `price` (REAL)
  - `tx_id` (INTEGER)
- `live_odds`:
  - `market_id` (TEXT)
  - `outcome` (TEXT)
  - `sportsbook` (TEXT)
  - `price` (REAL)
  - `last_updated` (TEXT)
  - `tx_id` (INTEGER)
  - Primary Key is `(market_id, outcome, sportsbook)`
- `applied_transactions`:
  - `tx_id` (INTEGER PRIMARY KEY)
  - `tx_hash` (TEXT)
- `recovery_metadata`:
  - `name` (TEXT PRIMARY KEY)
  - `value` (TEXT)

### Format of the Log Sidecar `odds_transactions.jsonl`

`odds_transactions.jsonl` is a line-by-line JSON Lines (JSONL) file representing transactions containing tick updates. Every line is a JSON object. There are three types of records:
- **START**:
  `{"type": "START", "tx_id": <int>, "prev_hash": <hex_str>}`
  Marks the start of a transaction.
- **OP**:
  `{"type": "OP", "sportsbook": <str>, "market_id": <str>, "outcome": <str>, "price": <float>, "timestamp": <str>}`
  An operation updating live odds and appending to the ticks log.
- **COMMIT**:
  `{"type": "COMMIT", "tx_id": <int>, "hash": <hex_str>}`
  Commits the transaction.

### Transaction Validation Rules

1. Transactions must be parsed and processed sequentially.
2. The transaction IDs (`tx_id`) in the log must form a contiguous sequence of increasing integers (e.g. `T, T+1, ..., T+k`).
3. For the first transaction `T` in the log:
   - If `T = 1`, its `prev_hash` must be `"0000000000000000000000000000000000000000000000000000000000000000"`.
   - If `T > 1`, its `prev_hash` must match the transaction hash of transaction `T - 1` stored in the `applied_transactions` table in the database. If transaction `T - 1` does not exist in the database, the log is corrupted.
4. For all subsequent transactions in the log, the `prev_hash` of transaction `T` must match the computed hash of the preceding transaction `T - 1` in the log.
5. The `hash` in the `COMMIT` record of transaction `T` must match the computed SHA-256 hash of its payload.
   - **Payload construction**:
     - Start with the `prev_hash` of the transaction (a 64-character lowercase hex string).
     - Append `
`.
     - For each `OP` record in the transaction in the order they appear in the WAL:
       - Construct the string representation of the operation:
         `f"{sportsbook}|{market_id}|{outcome}|{price:.4f}|{timestamp}"`
       - Append this string followed by `
` to the payload.
     - Compute the SHA-256 hex digest of the payload.
6. A transaction is corrupted/malformed if it lacks a `COMMIT` record before another `START` or EOF, has sequence gaps, has mismatched hashes, or has mismatching `tx_id` values between its `START` and `COMMIT` records.

### Database Recovery Procedure

- Scan the WAL file sequentially.
- If a transaction is valid and `tx_id <= last_applied_tx_id` (obtained from `recovery_metadata`'s `"last_applied_tx_id"` key), skip applying it (it is already checkpointed).
- If a transaction is valid and `tx_id > last_applied_tx_id`, apply it to the database:
  - For each `OP` in the transaction:
    - Insert a row into `ticks_log`.
    - Insert or replace a row in `live_odds`.
  - Insert a row into `applied_transactions` with `(tx_id, tx_hash)`.
  - Update `recovery_metadata` setting `"last_applied_tx_id"` to `tx_id`.
  - Commit these updates to the database.
- If you encounter any invalid transaction (mismatched hash, missing commit, non-sequential `tx_id` sequence, or missing parent hash linkage), **stop recovery immediately, rollback the current uncommitted transaction, and do not process any further logs**. Set `corruption_encountered = true` in the output.

### Output JSON Format (`outputs/recovered_ticks.json`)

The output must contain:
- `status`: `"recovered"`
- `initial_tx_id`: `<int>` (last applied transaction ID before recovery)
- `final_tx_id`: `<int>` (last applied transaction ID after recovery)
- `applied_transactions`: `[<int>, ...]` (list of newly applied transaction IDs)
- `ticks_inserted`: `<int>` (count of ticks newly inserted into ticks_log)
- `corruption_encountered`: `<bool>` (whether recovery stopped early due to an invalid/incomplete transaction)
- `database_state`:
  - `total_ticks`: `<int>` (total number of rows in `ticks_log` after recovery)
  - `live_odds`: A list of all live odds rows in the database after recovery, sorted by `market_id` ASC, `outcome` ASC, `sportsbook` ASC. Each row contains:
    - `market_id` (TEXT)
    - `outcome` (TEXT)
    - `sportsbook` (TEXT)
    - `price` (REAL)
    - `timestamp` (TEXT)
    - `tx_id` (INTEGER)
