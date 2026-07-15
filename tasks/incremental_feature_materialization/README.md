# Incremental Feature Materialization

## Summary

Implement `workspace/materialize.py --events PATH --output PATH` for crash-safe incremental feature materialization over append-only JSONL events with fields `event_id`, `entity_id`, `event_time`, and `value`.

## Required outputs

Each successful commit makes one generation under `OUTPUT/.generations/<uuid>/` containing `partitions/YYYY-MM-DD.jsonl` and `state.json`, then atomically replaces `OUTPUT/CURRENT` and fsyncs the output directory. `state.json` must contain exactly `version`, `last_event_offset`, `input_prefix_sha256`, `event_ids`, `dirty_start_date`, and `completed_at`.

## Verifier-facing success contract

- Materialize one row per entity seen on each UTC calendar date. Choose `value_last` by maximal `(event_time, event_id)`, deduplicate event IDs, reject conflicting duplicates, and recompute from the earliest dirty date when late events arrive.
- Track the consumed byte prefix and reject source mutation when its SHA-256 no longer matches. Store version `1`, the zero-based offset after the final consumed newline, lexicographically sorted event IDs, and `dirty_start_date: null` after a successful commit.
- Hard-link byte-identical unchanged partitions from the previous generation. At invocation start remove generations not named by `CURRENT`; readers resolve only `CURRENT`.
- A crash before replacing `CURRENT` leaves the prior generation authoritative. Serialization is deterministic, input/domain errors fail nonzero, the source is never mutated, and no network or writes outside the requested output directory are allowed.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 1 GiB memory, 2 GiB storage, no network, and the Python standard library (no additional runtime requirements).