#!/usr/bin/env python3
from pathlib import Path
import os
import sys

BROKEN = '''#!/usr/bin/env python3
import argparse, hashlib, json, uuid
from datetime import datetime, timezone
from pathlib import Path

def materialize(events_path, output_path):
    raw = Path(events_path).read_bytes()
    events = [json.loads(line) for line in raw.splitlines()]
    output = Path(output_path); output.mkdir(parents=True, exist_ok=True)
    generation_id = uuid.uuid4().hex
    generation = output / ".generations" / generation_id
    generation.mkdir(parents=True); (generation / "partitions").mkdir()
    # Broken: materializes only newly appended rows, never recomputing prior dates or carry-forward values.
    for event in events:
        day = event["event_time"][:10]
        with (generation / "partitions" / (day + ".jsonl")).open("a") as handle:
            handle.write(json.dumps({"date": day, "entity_id": event["entity_id"], "event_id": event["event_id"], "event_time": event["event_time"], "value_last": event["value"]}, sort_keys=True) + "\\n")
    state = {"version":1,"last_event_offset":len(raw),"input_prefix_sha256":hashlib.sha256(raw).hexdigest(),"event_ids":sorted({e["event_id"] for e in events}),"dirty_start_date":None,"completed_at":datetime.now(timezone.utc).isoformat()}
    (generation / "state.json").write_text(json.dumps(state))
    (output / "CURRENT").write_text(generation_id + "\\n")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--events",required=True); p.add_argument("--output",required=True); a=p.parse_args(); materialize(a.events,a.output)
if __name__ == "__main__": main()
'''
workspace = Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve()
path = workspace / "materialize.py"
path.write_text(BROKEN, encoding="utf-8"); path.chmod(0o755)
