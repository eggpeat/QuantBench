# Bitemporal As-Of Join

Implement `bitemporal.py::asof_join`.

```python
def asof_join(
    facts,
    revisions,
    *,
    entity_key: str,
    fact_time: str,
    valid_from: str,
    valid_to: str,
    system_from: str,
    as_of_system_time,
) -> list[dict]
```

`facts` and `revisions` are iterables of mappings (e.g., dicts). Each fact has
`entity_key` and `fact_time`; each revision has `entity_key`, `valid_from`,
`valid_to`, and `system_from`. The column names are passed as string arguments.

For each fact, select the revision that:

* belongs to the same entity;
* is known at the system cutoff: `system_from <= as_of_system_time`;
* is valid at the fact time: `valid_from <= fact_time < valid_to`;
* a `None` / missing `valid_to` means positive infinity.

If several revisions satisfy the above, choose the one with the maximal tuple
`(system_from, valid_from, revision_id)` lexicographically. `revision_id` is
taken from a `revision_id` field if present; otherwise a deterministic
stable identifier derived from the revision's contents is used. The result is
input-order invariant.

If two revisions have identical duplicate keys
`(entity, system_from, valid_from, valid_to, revision_id)`, raise `ValueError`.

Timestamps may be timezone-aware `datetime` objects or ISO-8601 strings. Naive
timestamps are interpreted as UTC. Malformed timestamps raise `ValueError`.

Return a list of dicts: one shallow copy of each fact, in the same order,
augmented with a `revision` key set to the selected revision dict or `None`.

Run the self-contained public check with:

```bash
python run_bitemporal.py
python -m pytest -q /tests/test_outputs.py
```

The visible fixture is deterministic (`seed=100`). Hidden tests exercise
future leakage, corrections, overlapping validity intervals, missing matches,
duplicate revisions, timezones, input-order invariance, and the named
`latest_revision` mutant.
