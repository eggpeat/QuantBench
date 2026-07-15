#!/usr/bin/env python3
"""Reference solution for the poker shove/fold equity task."""

import json
import sys
from pathlib import Path


POKER_EV_SOURCE = '''"""Poker shove/fold EV helpers."""


def called_ev(pot, risk, call, equity):
    """Return EV when villain calls the shove."""
    pot = float(pot)
    risk = float(risk)
    call = float(call)
    equity = float(equity)
    return equity * (pot + call) - (1.0 - equity) * risk


def shove_ev(pot, risk, call, equity, fold_probability):
    """Return total shove EV including fold equity."""
    fold_probability = float(fold_probability)
    when_called = called_ev(pot, risk, call, equity)
    return fold_probability * float(pot) + (1.0 - fold_probability) * when_called


def breakeven_fold_equity(pot, risk, call, equity):
    """Return fold probability needed for zero shove EV."""
    pot = float(pot)
    when_called = called_ev(pot, risk, call, equity)
    if when_called >= 0.0:
        return 0.0
    denominator = pot - when_called
    if denominator <= 0.0:
        return 1.0
    needed = -when_called / denominator
    return min(1.0, max(0.0, needed))


def evaluate_spot(spot):
    """Return the output record for one spot."""
    ev = shove_ev(
        spot["pot"],
        spot["risk"],
        spot["call"],
        spot["equity"],
        spot["fold_probability"],
    )
    breakeven = breakeven_fold_equity(
        spot["pot"], spot["risk"], spot["call"], spot["equity"]
    )
    return {
        "spot_id": spot["spot_id"],
        "shove_ev": round(ev, 2),
        "breakeven_fold_equity": round(breakeven, 6),
        "decision": "shove" if ev >= 0.0 else "fold",
    }


def evaluate_spots(payload):
    """Return {'spots': [...]} for a loaded spots.json payload."""
    return {"spots": [evaluate_spot(spot) for spot in payload["spots"]]}
'''


RUN_SPOTS_SOURCE = '''"""Run the shove/fold evaluator against spots.json."""

import json
from pathlib import Path

from poker_ev import evaluate_spots


def main():
    workspace = Path.cwd()
    spots_path = workspace / "spots.json"
    output_path = workspace / "outputs" / "shove_fold.json"

    with spots_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    result = evaluate_spots(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\\n")


if __name__ == "__main__":
    main()
'''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    workspace = Path(argv[0]) if argv else Path.cwd()

    (workspace / "poker_ev.py").write_text(POKER_EV_SOURCE, encoding="utf-8")
    (workspace / "run_spots.py").write_text(RUN_SPOTS_SOURCE, encoding="utf-8")

    namespace = {}
    exec(POKER_EV_SOURCE, namespace)

    with (workspace / "spots.json").open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    result = namespace["evaluate_spots"](payload)
    output_path = workspace / "outputs" / "shove_fold.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
