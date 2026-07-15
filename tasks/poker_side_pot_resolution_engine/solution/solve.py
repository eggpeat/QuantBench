#!/usr/bin/env python3
"""Reference solution for the poker side pot resolution engine task."""

import json
import sys
from pathlib import Path

SIDE_POTS_SOURCE = '''"""Poker side pot resolution engine."""


def settle_hand(hand: dict) -> dict:
    """Settle a single poker hand, allocating pots, handling chops, folds, all-ins,
    and odd chips. Returns a dictionary with hand_id, payouts, and conservation info.
    """
    hand_id = hand["hand_id"]
    players = hand["players"]

    # Calculate total bets
    total_bets = sum(p["bet"] for p in players)

    # Initialize payouts dict
    payouts = {p["name"]: 0 for p in players}

    # Collect all non-zero bet amounts
    bet_amounts = sorted(list(set(p["bet"] for p in players if p["bet"] > 0)))

    last_level = 0
    for level in bet_amounts:
        increment = level - last_level
        if increment <= 0:
            continue

        # Pot contributed to this level
        pot_contributions = {}
        level_pot = 0
        for p in players:
            contrib = max(0, min(p["bet"], level) - last_level)
            if contrib > 0:
                pot_contributions[p["name"]] = contrib
                level_pot += contrib

        # Eligible active players for this level
        eligible = [p for p in players if not p.get("folded", False) and p["bet"] >= level]

        if eligible:
            # Find the winner(s) among eligible with the highest hand_strength
            max_strength = max(p.get("hand_strength") or 0 for p in eligible)
            winners = [p for p in eligible if (p.get("hand_strength") or 0) == max_strength]

            # Divide level_pot among winners
            base_share = level_pot // len(winners)
            remainder = level_pot % len(winners)

            # Sort winners by seat number ascending
            winners_sorted = sorted(winners, key=lambda p: p["seat"])
            for i, p in enumerate(winners_sorted):
                share = base_share
                if i < remainder:
                    share += 1
                payouts[p["name"]] += share
        else:
            # Refund level_pot to contributors at this level
            for name, contrib in pot_contributions.items():
                payouts[name] += contrib

        last_level = level

    total_payouts = sum(payouts.values())

    return {
        "hand_id": hand_id,
        "payouts": payouts,
        "conservation": {
            "total_bets": total_bets,
            "total_payouts": total_payouts,
            "is_conserved": total_bets == total_payouts
        }
    }


def settle_all(hands: list[dict]) -> list[dict]:
    """Settle a list of poker hands."""
    return [settle_hand(h) for h in hands]
'''

RUN_SIDE_POTS_SOURCE = '''"""Run the side pot evaluator against hands.json."""

import json
from pathlib import Path

from side_pots import settle_all


def main():
    workspace = Path.cwd()
    hands_path = workspace / "hands.json"
    output_path = workspace / "outputs" / "settlements.json"

    with hands_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    settled = settle_all(payload["hands"])

    result = {"settlements": settled}

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

    (workspace / "side_pots.py").write_text(SIDE_POTS_SOURCE, encoding="utf-8")
    (workspace / "run_side_pots.py").write_text(RUN_SIDE_POTS_SOURCE, encoding="utf-8")

    namespace = {}
    exec(SIDE_POTS_SOURCE, namespace)

    with (workspace / "hands.json").open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    result = {
        "settlements": namespace["settle_all"](payload["hands"])
    }

    output_path = workspace / "outputs" / "settlements.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
