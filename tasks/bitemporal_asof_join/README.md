# Bitemporal As-Of Join

## Summary

Implement `workspace/bitemporal.py::asof_join` to select the revision known at a system cutoff and valid at each fact time. The public runner is `workspace/run_bitemporal.py`.

## Required outputs

Running `python run_bitemporal.py` must create `outputs/bitemporal_report.json` for the deterministic fixture, preserving the returned fact rows and selected revision data.

## Verifier-facing success contract

- Accept fact and revision iterables of mappings with caller-supplied field names. For each fact, match entity, require `system_from <= as_of_system_time` and `valid_from <= fact_time < valid_to`, treating missing/`None` `valid_to` as positive infinity.
- When multiple revisions match, select maximal `(system_from, valid_from, revision_id)` lexicographically. Use a supplied `revision_id` or a deterministic stable identifier derived from revision contents; result selection is input-order invariant.
- Identical duplicate revision keys `(entity, system_from, valid_from, valid_to, revision_id)` raise `ValueError`.
- Parse timezone-aware datetime values and ISO-8601 strings; interpret naive timestamps as UTC and reject malformed timestamps.
- Return one shallow copy per fact in input order, augmented with `revision` set to the selected revision mapping or `None`.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 1 GiB memory, no network, and the pinned NumPy and pytest dependencies in `environment/requirements.txt`.