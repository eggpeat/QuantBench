# Incremental feature materialization

Implement `workspace/materialize.py --events PATH --output PATH` for append-only JSONL events with exact fields `event_id`, `entity_id`, `event_time`, and `value`.

Each committed generation lives at `OUTPUT/.generations/<uuid>/`, contains `partitions/YYYY-MM-DD.jsonl` and `state.json`, and becomes visible only when `OUTPUT/CURRENT` is atomically replaced and the output directory is fsynced. Readers resolve only `CURRENT`. Hard-link byte-identical unchanged partitions from the prior generation. At the beginning of the next successful invocation, remove generations not named by `CURRENT`.

For each UTC calendar date, serialize one row per entity seen by that date. `value_last` is selected by maximal `(event_time, event_id)`. Late appended events require recomputation from the earliest dirty date. Deduplicate `event_id`; conflicting duplicates are invalid. Reject a source file when the bytes covered by the stored consumed prefix no longer match `input_prefix_sha256`.

`state.json` has exactly these keys: `version`, `last_event_offset`, `input_prefix_sha256`, `event_ids`, `dirty_start_date`, and `completed_at`. `version` is `1`; `last_event_offset` is the zero-based byte position after the final consumed newline; event IDs sort lexicographically; successful commit sets `dirty_start_date` to `null`. JSON output must be deterministic. A crash before replacing `CURRENT` must leave the prior generation authoritative.

Input/domain errors raise or exit nonzero. Do not mutate the event source, use the network, or write outside the requested output directory.
