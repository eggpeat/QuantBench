#!/usr/bin/env python3
"""Reference solution for the poker range equity task."""

import json
import sys
from pathlib import Path

RANGE_EQUITY_SOURCE = '''"""Poker range equity engine implementation."""

import itertools
import random

RANK_MAP = {r: i for i, r in enumerate("23456789TJQKA", 2)}

def parse_card(card_str):
    """
    Parse a 2-character card string (e.g., 'Ah', 'Td') into a card representation.
    Returns a tuple (rank_int, suit_str).
    """
    if len(card_str) != 2:
        raise ValueError(f"Invalid card string length: {card_str}")
    rank_char, suit_char = card_str[0], card_str[1]
    if rank_char not in RANK_MAP:
        raise ValueError(f"Invalid card rank: {rank_char}")
    if suit_char not in "hdcs":
        raise ValueError(f"Invalid card suit: {suit_char}")
    return (RANK_MAP[rank_char], suit_char)

def evaluate_5_cards_parsed(parsed_cards):
    ranks = sorted([c[0] for c in parsed_cards], reverse=True)
    suits = [c[1] for c in parsed_cards]

    is_flush = len(set(suits)) == 1
    unique_ranks = sorted(list(set(ranks)), reverse=True)

    is_straight = False
    straight_high = 0
    if len(unique_ranks) == 5:
        if unique_ranks[0] - unique_ranks[4] == 4:
            is_straight = True
            straight_high = unique_ranks[0]
        elif unique_ranks == [14, 5, 4, 3, 2]:
            is_straight = True
            straight_high = 5

    rank_counts = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1

    sorted_by_freq = sorted(rank_counts.keys(), key=lambda r: (rank_counts[r], r), reverse=True)
    frequencies = [rank_counts[r] for r in sorted_by_freq]

    if is_flush and is_straight:
        return (8, straight_high)
    if frequencies == [4, 1]:
        return (7, sorted_by_freq[0], sorted_by_freq[1])
    if frequencies == [3, 2]:
        return (6, sorted_by_freq[0], sorted_by_freq[1])
    if is_flush:
        return (5, *sorted_by_freq)
    if is_straight:
        return (4, straight_high)
    if frequencies == [3, 1, 1]:
        return (3, sorted_by_freq[0], sorted_by_freq[1], sorted_by_freq[2])
    if frequencies == [2, 2, 1]:
        return (2, sorted_by_freq[0], sorted_by_freq[1], sorted_by_freq[2])
    if frequencies == [2, 1, 1, 1]:
        return (1, sorted_by_freq[0], sorted_by_freq[1], sorted_by_freq[2], sorted_by_freq[3])
    return (0, *sorted_by_freq)

def evaluate_hand(cards):
    parsed = [parse_card(c) for c in cards]
    best_score = None
    n = len(parsed)
    for combo in itertools.combinations(parsed, 5):
        score = evaluate_5_cards_parsed(combo)
        if best_score is None or score > best_score:
            best_score = score
    return best_score

DECK = [r + s for r in "23456789TJQKA" for s in "hdcs"]

def parse_range_hand(hand_str):
    if isinstance(hand_str, list):
        return hand_str
    if len(hand_str) != 4:
        raise ValueError(f"Hand string must be 4 characters: {hand_str}")
    return [hand_str[0:2], hand_str[2:4]]

def calculate_equity(p1_range, p2_range, board, num_samples=10000):
    p1_hands = [parse_range_hand(h) for h in p1_range]
    p2_hands = [parse_range_hand(h) for h in p2_range]

    total_p1_wins = 0.0
    total_p2_wins = 0.0
    total_ties = 0.0
    total_combos = 0

    for h1 in p1_hands:
        for h2 in p2_hands:
            combined = set(h1) | set(h2) | set(board)
            if len(combined) != len(h1) + len(h2) + len(board):
                continue

            total_combos += 1
            remaining_deck = [c for c in DECK if c not in combined]
            cards_needed = 5 - len(board)

            p1_wins = 0
            p2_wins = 0
            ties = 0

            if cards_needed == 0:
                s1 = evaluate_hand(h1 + board)
                s2 = evaluate_hand(h2 + board)
                if s1 > s2:
                    p1_wins += 1
                elif s2 > s1:
                    p2_wins += 1
                else:
                    ties += 1
                total_trials = 1
            elif cards_needed == 1:
                for c in remaining_deck:
                    s1 = evaluate_hand(h1 + board + [c])
                    s2 = evaluate_hand(h2 + board + [c])
                    if s1 > s2:
                        p1_wins += 1
                    elif s2 > s1:
                        p2_wins += 1
                    else:
                        ties += 1
                total_trials = len(remaining_deck)
            elif cards_needed == 2:
                for combo in itertools.combinations(remaining_deck, 2):
                    runout = list(combo)
                    s1 = evaluate_hand(h1 + board + runout)
                    s2 = evaluate_hand(h2 + board + runout)
                    if s1 > s2:
                        p1_wins += 1
                    elif s2 > s1:
                        p2_wins += 1
                    else:
                        ties += 1
                total_trials = len(remaining_deck) * (len(remaining_deck) - 1) // 2
            else:
                random.seed(42)
                for _ in range(num_samples):
                    runout = random.sample(remaining_deck, cards_needed)
                    s1 = evaluate_hand(h1 + board + runout)
                    s2 = evaluate_hand(h2 + board + runout)
                    if s1 > s2:
                        p1_wins += 1
                    elif s2 > s1:
                        p2_wins += 1
                    else:
                        ties += 1
                total_trials = num_samples

            total_p1_wins += (p1_wins / total_trials)
            total_p2_wins += (p2_wins / total_trials)
            total_ties += (ties / total_trials)

    if total_combos == 0:
        return 0.0, 0.0, 0.0

    p1_eq = (total_p1_wins + 0.5 * total_ties) / total_combos
    p2_eq = (total_p2_wins + 0.5 * total_ties) / total_combos
    tie_prob = total_ties / total_combos

    return p1_eq, p2_eq, tie_prob
'''

RUN_EQUITY_SOURCE = '''#!/usr/bin/env python3
"""Runner script to evaluate range equity scenarios."""

import json
import os
from pathlib import Path
import range_equity

def main():
    workspace_dir = Path(__file__).parent
    scenarios_path = workspace_dir / "scenarios.json"
    output_dir = workspace_dir / "outputs"
    output_path = output_dir / "equity.json"

    if not scenarios_path.exists():
        print(f"Error: scenarios.json not found in {workspace_dir}")
        return

    with open(scenarios_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    results = []
    for scenario in data.get("scenarios", []):
        scenario_id = scenario["scenario_id"]
        p1_range = scenario["p1_range"]
        p2_range = scenario["p2_range"]
        board = scenario.get("board", [])

        print(f"Evaluating scenario: {scenario_id}...")
        p1_eq, p2_eq, tie_prob = range_equity.calculate_equity(p1_range, p2_range, board)

        results.append({
            "scenario_id": scenario_id,
            "p1_equity": round(p1_eq, 5),
            "p2_equity": round(p2_eq, 5),
            "tie_probability": round(tie_prob, 5)
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump({"scenarios": results}, fh, indent=2)
    print(f"Saved results to {output_path}")

if __name__ == "__main__":
    main()
'''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    workspace = Path(argv[0]) if argv else Path.cwd()

    (workspace / "range_equity.py").write_text(RANGE_EQUITY_SOURCE, encoding="utf-8")
    (workspace / "run_equity.py").write_text(RUN_EQUITY_SOURCE, encoding="utf-8")

    namespace = {}
    exec(RANGE_EQUITY_SOURCE, namespace)

    with (workspace / "scenarios.json").open("r", encoding="utf-8") as fh:
        payload = json.load(fh)

    results = []
    for scenario in payload.get("scenarios", []):
        p1_eq, p2_eq, tie_prob = namespace["calculate_equity"](
            scenario["p1_range"],
            scenario["p2_range"],
            scenario["board"]
        )
        results.append({
            "scenario_id": scenario["scenario_id"],
            "p1_equity": round(p1_eq, 5),
            "p2_equity": round(p2_eq, 5),
            "tie_probability": round(tie_prob, 5)
        })

    output_path = workspace / "outputs" / "equity.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump({"scenarios": results}, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
