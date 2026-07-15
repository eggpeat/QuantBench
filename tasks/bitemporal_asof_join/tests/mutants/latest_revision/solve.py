#!/usr/bin/env python3
from pathlib import Path
import os
import sys

BROKEN = '''def asof_join(facts, revisions, *, entity_key, fact_time, valid_from, valid_to, system_from, as_of_system_time):
    out = []
    for fact in facts:
        matches = [r for r in revisions if r.get(entity_key) == fact.get(entity_key) and r.get(valid_from) <= fact.get(fact_time) and (r.get(valid_to) is None or fact.get(fact_time) < r.get(valid_to))]
        row = dict(fact)
        row["revision"] = dict(max(matches, key=lambda r: (r.get(system_from), r.get(valid_from), r.get("revision_id")))) if matches else None
        out.append(row)
    return out
'''

workspace = Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve()
(workspace / "bitemporal.py").write_text(BROKEN, encoding="utf-8")
os.chdir(workspace)
sys.path.insert(0, str(workspace))
from run_bitemporal import main
main()
