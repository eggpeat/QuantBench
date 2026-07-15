"""Bitemporal as-of join."""
from typing import Any


def asof_join(
    facts: list[dict[str, Any]],
    revisions: list[dict[str, Any]],
    *,
    entity_key: str,
    fact_time: str,
    valid_from: str,
    valid_to: str,
    system_from: str,
    as_of_system_time: Any,
) -> list[dict[str, Any]]:
    """Return facts augmented with the revision valid and known at the requested time."""
    raise NotImplementedError("implement asof_join")
