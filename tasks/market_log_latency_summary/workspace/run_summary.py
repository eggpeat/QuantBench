import json
import os
import sys
from pathlib import Path

# Ensure log_summary can be imported from workspace directory
sys.path.insert(0, str(Path(__file__).parent))
try:
    from log_summary import parse_records, summarize
finally:
    try:
        sys.path.remove(str(Path(__file__).parent))
    except ValueError:
        pass

def main():
    workspace = Path(os.environ.get("TASK_WORKSPACE", Path(__file__).parent))
    log_path = workspace / "logs" / "market_api.jsonl"
    output_path = workspace / "outputs" / "latency_summary.json"

    # Ensure outputs directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = parse_records(log_path)
    summary = summarize(records)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")

if __name__ == "__main__":
    main()
