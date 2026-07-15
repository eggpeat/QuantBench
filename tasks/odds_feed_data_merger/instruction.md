Workspace task: implement the functions in `merge_odds.py` and run the merge process via `python run_merge.py`.

Merge the heterogeneous odds feeds under `feeds/` and write two deterministic JSON files:

- `outputs/merged_odds.json`
- `outputs/conflicts.json`

Implementation Requirements:
You must implement the following functions in `merge_odds.py`:
- `canonical_name(value, aliases)`: Canonicalizes a team name or outcome label using aliases.
- `canonical_market(value)`: Canonicalizes market names.
- `normalize_record(raw, source_file, row_number, aliases)`: Normalizes a raw record from any feed into a standard dictionary shape.
- `load_records(workspace_path)`: Loads all records from JSON, CSV, and JSONL feeds, and normalizes them.
- `merge_records(records)`: Merges normalized records, resolving conflicts and identifying winners.
- `write_outputs(merged, conflicts, workspace_path)`: Writes the merged odds and conflicts to JSON files in the outputs directory.
- `main(workspace_path=None)`: Main entry point to merge odds data.

Once implemented, running `python run_merge.py` will invoke `merge_odds.main()` to run the whole process and generate the JSON outputs.

Inputs:

- `feeds/json_feed.json`: JSON object with a `records` array.
- `feeds/csv_feed.csv`: CSV file with a header row.
- `feeds/jsonl_feed.jsonl`: one JSON object per line.
- `team_aliases.json`: maps noncanonical team names and outcome labels to canonical team names.

Each feed record describes one event outcome with these logical fields: `event_id`, `home_team`, `away_team`, `market`, `book`, `outcome`, `odds`, `line`, `timestamp`, and `source_priority`. Field names may vary by format.

Canonicalization rules:

1. Trim string values before comparing or writing them.
2. Team names and team outcome labels must be mapped through `team_aliases.json`; unmapped values remain trimmed as-is.
3. Market names are case-insensitive and canonicalized as:
   - `moneyline`, `ml`, `h2h` -> `moneyline`
   - `spread`, `point_spread`, `point spread` -> `spread`
   - `total`, `totals`, `over_under`, `over/under` -> `total`
4. `odds` and `source_priority` are integers.
5. Empty `line` values become JSON `null`; otherwise write `line` as a number.
6. The canonical record key is `(event_id, canonical home_team, canonical away_team, canonical market, book, canonical outcome)`.

Merge rules:

1. Group records by the canonical key.
2. If records for the same key have different `odds` or `line`, this is a conflict and every non-winning conflicting record must be listed in `outputs/conflicts.json`.
3. The winner for a key is the record with the highest `source_priority`.
4. If `source_priority` ties, the newer ISO-8601 `timestamp` wins.
5. If both priority and timestamp tie, choose deterministically by source file name and original row number so repeated runs produce the same output.
6. Exact duplicate rows for the same key, odds, line, timestamp, priority, and source file may be ignored rather than reported as conflicts.

Output shape:

`outputs/merged_odds.json` must be a JSON array of winner records. Each record must contain exactly:

`event_id`, `home_team`, `away_team`, `market`, `book`, `outcome`, `odds`, `line`, `timestamp`, `source_priority`, `source_file`.

`outputs/conflicts.json` must be a JSON array. Each conflict object must contain exactly:

`event_id`, `home_team`, `away_team`, `market`, `book`, `outcome`, `winning`, `rejected`, `reason`.

For this task, every reported conflict is a rejected lower-priority or older record for the same canonical key. Set `reason` exactly to the string `"lower_priority_or_older_timestamp"`.

`winning` and `rejected` must each contain `odds`, `line`, `timestamp`, `source_priority`, and `source_file`.

Sort both output arrays deterministically by event id, home team, away team, market, book, and outcome. Sort conflicts with the same canonical key by rejected source file, rejected timestamp, rejected priority, rejected odds, and rejected line. Use pretty JSON with sorted object keys.
