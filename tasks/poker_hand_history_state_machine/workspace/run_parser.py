#!/usr/bin/env python3
"""Run the hand history parser and write the output."""

import json
from pathlib import Path
from hand_parser import parse_hands


def main():
    workspace = Path(__file__).parent
    input_file = workspace / "hand_histories.txt"
    output_dir = workspace / "outputs"
    output_file = output_dir / "parsed_hands.json"

    if not input_file.exists():
        print(f"Error: input file {input_file} not found.")
        return

    text = input_file.read_text(encoding="utf-8")
    parsed = parse_hands(text)

    output_dir.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as fh:
        json.dump(parsed, fh, indent=2)
        fh.write("\n")

    print(f"Successfully parsed hands and wrote output to {output_file}")


if __name__ == "__main__":
    main()
