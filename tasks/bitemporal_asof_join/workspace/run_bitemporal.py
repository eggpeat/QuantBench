#!/usr/bin/env python3
"""Run the public bitemporal fixture and write a JSON report."""
from __future__ import annotations

import json
from pathlib import Path

import bitemporal


def main() -> None:
    root = Path(__file__).resolve().parent
    data = json.loads((root / "input.json").read_text(encoding="utf-8"))
    entity_key = data["entity_key"]
    fact_time = data["fact_time"]
    valid_from = data["valid_from"]
    valid_to = data["valid_to"]
    system_from = data["system_from"]
    as_of = data["as_of_system_time"]

    facts = [
        {entity_key: "A", fact_time: "2023-06-10T00:00:00Z"},
        {entity_key: "A", fact_time: "2023-06-14T00:00:00Z"},
        {entity_key: "B", fact_time: "2023-06-12T00:00:00Z"},
        {entity_key: "B", fact_time: "2023-06-20T00:00:00Z"},
    ]
    revisions = [
        {entity_key: "A", valid_from: "2023-06-01T00:00:00Z", valid_to: "2023-06-13T00:00:00Z", system_from: "2023-06-01T00:00:00Z", "revision_id": "rA1"},
        {entity_key: "A", valid_from: "2023-06-13T00:00:00Z", valid_to: None, system_from: "2023-06-13T00:00:00Z", "revision_id": "rA2"},
        {entity_key: "B", valid_from: "2023-06-01T00:00:00Z", valid_to: "2023-06-15T00:00:00Z", system_from: "2023-06-01T00:00:00Z", "revision_id": "rB1"},
        {entity_key: "B", valid_from: "2023-06-10T00:00:00Z", valid_to: "2023-06-15T00:00:00Z", system_from: "2023-06-12T00:00:00Z", "revision_id": "rB2"},
    ]

    result = bitemporal.asof_join(
        facts,
        revisions,
        entity_key=entity_key,
        fact_time=fact_time,
        valid_from=valid_from,
        valid_to=valid_to,
        system_from=system_from,
        as_of_system_time=as_of,
    )

    report = {
        "seed": data["seed"],
        "n_facts": len(result),
        "matches": [
            {entity_key: row[entity_key], "revision_id": (row["revision"] or {}).get("revision_id")}
            for row in result
        ],
    }
    output = root / "outputs" / "bitemporal_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
