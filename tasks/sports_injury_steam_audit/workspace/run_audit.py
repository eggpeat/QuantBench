import json
import os
from pathlib import Path
import sys

# Ensure candidate module is importable
sys.path.insert(0, str(Path(__file__).parent.resolve()))

import injury_audit


def main():
    workspace = Path(__file__).parent.resolve()
    events_path = workspace / "events.json"
    output_dir = workspace / "outputs"
    output_path = output_dir / "injury_steam_audit.json"

    if not events_path.exists():
        print(f"Error: {events_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(events_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    games = data.get("games", [])
    results = injury_audit.audit_slate(games)

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"games": results}, f, indent=2)

    print(f"Successfully wrote audited slate to {output_path}")


if __name__ == "__main__":
    main()
