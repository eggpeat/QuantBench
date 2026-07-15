# odds_feed_data_merger

## Overview

Merge sportsbook odds records from JSON, CSV, and JSONL feeds into canonical, deterministic JSON outputs. The task simulates a small data-engineering reconciliation job with inconsistent labels, repeated rows, and conflicting prices.

## Source Grounding & Provenance

- **Source Task**: Direct adaptation of the Terminal-Bench 2.1 `multi-source-data-merger` task.
- **Parent Behavior Preserved**:
  - Parsing and combining heterogeneous file formats (JSON, CSV, JSONL).
  - Normalizing variant schemas/keys into a standard, clean representation.
  - De-duplicating and resolving record-level conflicts using strict, deterministic priority rules (source priority, then newer timestamp, then file/row order).
  - Producing a final clean merged output alongside a detailed conflict/rejection log.
- **Domain Translation Added**:
  - Translates the domain from general customer/user record linking to sports betting odds feeds.
  - Utilizes a sports-themed alias map (`team_aliases.json`) for team and outcome label canonicalization.
  - Normalizes variant market names case-insensitively (e.g., `ML` or `h2h` to `moneyline`, `spread` or `point spread` to `spread`, `total` or `over/under` to `total`).
- **Verifier Anti-Cheat & Robustness**:
  - The verifier is designed to resist static-output copying. In addition to verifying that the output files (`merged_odds.json` and `conflicts.json`) match the static expected test fixtures, it dynamically imports and tests the candidate's core functions (`canonical_name`, `canonical_market`, `normalize_record`, `merge_records`) on a separate inline test case. This ensures that the actual code logic must be implemented correctly, rather than just hardcoding the output files.
- **Promotion Readiness**:
  - All blockers are cleared. The domain-specific sports odds feeds and metadata alias matching have been validated as structurally complete, correct, and sufficient for testing this ETL pattern.

## What It Tests

- Parsing multiple common data formats with the Python standard library.
- Canonicalizing team aliases, outcome labels, and market names.
- Building stable compound keys for record linkage.
- Resolving duplicate/conflicting rows with explicit priority and timestamp rules.
- Producing deterministic, audit-friendly JSON outputs.

## Environment

The environment is `python:3.13-slim-bookworm` with no internet access. Use only the Python standard library.

## Inputs

The workspace contains:

- `feeds/json_feed.json` with a `records` array.
- `feeds/csv_feed.csv` with headered rows.
- `feeds/jsonl_feed.jsonl` with one JSON object per line.
- `team_aliases.json` mapping variant team/outcome names to canonical names.

Records contain event ids, teams, markets, books, outcomes, odds, optional lines, timestamps, and source priorities. Field names intentionally vary across formats.

## Implementation & Required Outputs

Implement the following importable functions in `workspace/merge_odds.py`:
- `canonical_name`
- `canonical_market`
- `normalize_record`
- `load_records`
- `merge_records`
- `write_outputs`
- `main`

Then, execute the process by running:

```bash
python run_merge.py
```

This will invoke `merge_odds.main()` to run the whole process and write:

- `outputs/merged_odds.json`: sorted array of winning canonical odds records.
- `outputs/conflicts.json`: sorted array of rejected conflicting records paired with the final winner for their canonical key.

The winner is selected by higher `source_priority`, then newer timestamp, then deterministic source-file/row ordering. Exact duplicates may be ignored. Conflict records use the fixed reason string `"lower_priority_or_older_timestamp"` because this task's conflicts are all rejected lower-priority or older records for the same canonical key.
## Verification

The pytest verifier loads the workspace from `TASK_WORKSPACE` when set, otherwise `/workspace`, and compares both output files to `tests/expected.json`. It also includes an inline edge-case check for canonical market/team normalization and conflict-winner selection semantics.

## Difficulty / Anti-cheat Notes

Difficulty: medium. The fixtures are public, but tests check exact deterministic output and include an inline semantic edge case so copying an output snapshot alone does not demonstrate the required normalization and conflict-resolution behavior.
