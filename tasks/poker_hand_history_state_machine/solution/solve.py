#!/usr/bin/env python3
"""Reference solution for the poker hand history state machine parser task."""

import json
import sys
from pathlib import Path

HAND_PARSER_SOURCE = """\"\"\"Poker Hand History State Machine Parser.\"\"\"

import re

def parse_hands(text: str) -> list[dict]:
    hands = []
    hand_blocks = []
    current_block = []
    for line in text.splitlines():
        if line.startswith("PokerStars Hand #"):
            if current_block:
                hand_blocks.append(current_block)
            current_block = [line]
        elif current_block:
            current_block.append(line)
    if current_block:
        hand_blocks.append(current_block)

    for block in hand_blocks:
        hand_id = None
        table_name = ""
        button_seat = 0
        small_blind = 0.0
        big_blind = 0.0
        seats = []
        player_to_seat = {}
        player_stacks = {}
        blinds_posted = []
        actions = []
        uncalled_bet_returned = None
        total_pot = 0.0
        rake = 0.0
        winners = []
        valid = True
        errors = []

        # Stateful tracking
        current_street = ""
        street_contributions = {}
        current_bet = 0.0
        folded_players = set()
        all_in_players = set()
        showed_players = set()

        header_line = block[0]
        header_match = re.search(r"PokerStars Hand #(\\d+): Hold'em No Limit \\((?:[^\\d]*)([\\d\\.]+)/(?:[^\\d]*)([\\d\\.]+)", header_line)
        if header_match:
            hand_id = header_match.group(1)
            small_blind = float(header_match.group(2))
            big_blind = float(header_match.group(3))
        else:
            continue

        for line in block[1:]:
            line = line.strip()
            if not line:
                continue

            # Check street headers
            if line == "*** HOLE CARDS ***":
                current_street = "preflop"
                street_contributions = {}
                for post in blinds_posted:
                    name = post["player_name"]
                    amt = post["amount"]
                    street_contributions[name] = street_contributions.get(name, 0.0) + amt
                current_bet = max([post["amount"] for post in blinds_posted] + [0.0])
                continue
            elif line.startswith("*** FLOP ***"):
                current_street = "flop"
                street_contributions = {}
                current_bet = 0.0
                continue
            elif line.startswith("*** TURN ***"):
                current_street = "turn"
                street_contributions = {}
                current_bet = 0.0
                continue
            elif line.startswith("*** RIVER ***"):
                current_street = "river"
                street_contributions = {}
                current_bet = 0.0
                continue
            elif line.startswith("*** SHOW DOWN ***"):
                current_street = "showdown"
                continue
            elif line.startswith("*** SUMMARY ***"):
                current_street = "summary"
                continue

            # Table line
            table_match = re.search(r"Table '([^']+)' .* Seat #(\\d+) is the button", line)
            if table_match:
                table_name = table_match.group(1)
                button_seat = int(table_match.group(2))
                continue

            # Seat line
            seat_match = re.search(r"^Seat (\\d+): (.+?) \\(\\$?([\\d\\.]+) in chips\\)", line)
            if seat_match:
                s_num = int(seat_match.group(1))
                p_name = seat_match.group(2).strip()
                chips = float(seat_match.group(3))
                seats.append({
                    "seat_number": s_num,
                    "player_name": p_name,
                    "chips": chips
                })
                player_to_seat[p_name] = s_num
                player_stacks[p_name] = chips
                continue

            # Blinds posting (before HOLE CARDS)
            if current_street == "":
                post_match = re.search(r"^([^:]+): posts (small|big) blind \\$?([\\d\\.]+)", line)
                if post_match:
                    p_name = post_match.group(1).strip()
                    b_type = post_match.group(2)
                    amt = float(post_match.group(3))

                    if p_name not in player_stacks:
                        valid = False
                        errors.append("Player acting is not seated")
                    else:
                        if player_stacks[p_name] < amt:
                            valid = False
                            errors.append("Insufficient stack")
                        player_stacks[p_name] -= amt
                        if player_stacks[p_name] == 0.0:
                            all_in_players.add(p_name)

                    blinds_posted.append({
                        "player_name": p_name,
                        "type": b_type,
                        "amount": amt
                    })
                    continue

            # Actions
            if current_street in ["preflop", "flop", "turn", "river"]:
                if ":" in line:
                    parts = line.split(":", 1)
                    p_name = parts[0].strip()
                    action_text = parts[1].strip()

                    is_action_format = False
                    for act in ["folds", "checks", "calls", "bets", "raises"]:
                        if action_text.startswith(act):
                            if not (action_text.startswith('"') and action_text.endswith('"')):
                                is_action_format = True
                                break

                    if is_action_format:
                        if p_name not in player_to_seat:
                            valid = False
                            errors.append("Player acting is not seated")
                            continue

                        action_type = None
                        amt = 0.0
                        to_amt_target = 0.0

                        if action_text.startswith("folds"):
                            action_type = "fold"
                        elif action_text.startswith("checks"):
                            action_type = "check"
                        elif action_text.startswith("calls"):
                            action_type = "call"
                            match = re.search(r"calls \\$?([\\d\\.]+)", action_text)
                            if match:
                                amt = float(match.group(1))
                        elif action_text.startswith("bets"):
                            action_type = "bet"
                            match = re.search(r"bets \\$?([\\d\\.]+)", action_text)
                            if match:
                                amt = float(match.group(1))
                        elif action_text.startswith("raises"):
                            action_type = "raise"
                            match = re.search(r"raises \\$?([\\d\\.]+) to \\$?([\\d\\.]+)", action_text)
                            if match:
                                to_amt_target = float(match.group(2))

                        if action_type is not None:
                            if p_name in folded_players:
                                valid = False
                                errors.append("Player acting has already folded")

                            if action_type in ["call", "bet", "raise"]:
                                needed_chips = 0.0
                                if action_type == "call":
                                    needed_chips = amt
                                    to_amt_target = street_contributions.get(p_name, 0.0) + amt
                                elif action_type == "bet":
                                    needed_chips = amt
                                    to_amt_target = amt
                                elif action_type == "raise":
                                    needed_chips = to_amt_target - street_contributions.get(p_name, 0.0)
                                    amt = needed_chips

                                if player_stacks[p_name] < needed_chips:
                                    valid = False
                                    errors.append("Insufficient stack")

                                player_stacks[p_name] -= needed_chips
                                street_contributions[p_name] = to_amt_target
                                current_bet = max(current_bet, to_amt_target)
                                if player_stacks[p_name] == 0.0:
                                    all_in_players.add(p_name)
                            elif action_type == "check":
                                my_contrib = street_contributions.get(p_name, 0.0)
                                if current_bet > my_contrib:
                                    valid = False
                                    errors.append("Player checking when facing a bet")
                                to_amt_target = my_contrib
                            elif action_type == "fold":
                                folded_players.add(p_name)
                                to_amt_target = street_contributions.get(p_name, 0.0)

                            actions.append({
                                "street": current_street,
                                "player_name": p_name,
                                "action_type": action_type,
                                "amount": amt,
                                "to_amount": to_amt_target
                            })
                            continue

            # Showdown/Summary parsing
            show_match = re.search(r"^([^:]+): shows \\[^\\]+\\]", line)
            if show_match:
                p_name = show_match.group(1).strip()
                if p_name in player_to_seat:
                    showed_players.add(p_name)
                continue

            uncalled_match = re.search(r"Uncalled bet \\(\\$?([\\d\\.]+)\\) returned to (.+)", line)
            if uncalled_match:
                amt = float(uncalled_match.group(1))
                p_name = uncalled_match.group(2).strip()
                uncalled_bet_returned = {
                    "player_name": p_name,
                    "amount": amt
                }
                if p_name in player_stacks:
                    player_stacks[p_name] += amt
                continue

            collect_match = re.search(r"^(.+?) collected \\$?([\\d\\.]+) from pot", line)
            if collect_match:
                p_name = collect_match.group(1).strip()
                amt = float(collect_match.group(2))
                winners.append({
                    "player_name": p_name,
                    "amount": amt,
                    "showed": p_name in showed_players
                })
                continue

            pot_match = re.search(r"Total pot \\$?([\\d\\.]+)(?: \\| Rake \\$?([\\d\\.]+))?", line)
            if pot_match:
                total_pot = float(pot_match.group(1))
                if pot_match.group(2):
                    rake = float(pot_match.group(2))
                continue

        for line in block:
            if "showed [" in line:
                for p_name in player_to_seat:
                    if p_name in line:
                        showed_players.add(p_name)

        for w in winners:
            w["showed"] = w["player_name"] in showed_players

        hands.append({
            "hand_id": hand_id,
            "table_name": table_name,
            "button_seat": button_seat,
            "small_blind": small_blind,
            "big_blind": big_blind,
            "seats": seats,
            "blinds_posted": blinds_posted,
            "actions": actions,
            "uncalled_bet_returned": uncalled_bet_returned,
            "total_pot": total_pot,
            "rake": rake,
            "winners": winners,
            "valid": valid,
            "errors": list(set(errors))
        })
    return hands
"""

RUN_PARSER_SOURCE = """#!/usr/bin/env python3
\"\"\"Run the hand history parser and write the output.\"\"\"

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
        fh.write("\\n")

    print(f"Successfully parsed hands and wrote output to {output_file}")

if __name__ == "__main__":
    main()
"""

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    (workspace / "hand_parser.py").write_text(HAND_PARSER_SOURCE, encoding="utf-8")
    (workspace / "run_parser.py").write_text(RUN_PARSER_SOURCE, encoding="utf-8")

    # Execute the parse_hands function locally to produce the expected output
    namespace = {}
    exec(HAND_PARSER_SOURCE, namespace)

    input_file = workspace / "hand_histories.txt"
    if input_file.exists():
        text = input_file.read_text(encoding="utf-8")
        parsed = namespace["parse_hands"](text)

        output_dir = workspace / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "parsed_hands.json"

        with output_file.open("w", encoding="utf-8") as fh:
            json.dump(parsed, fh, indent=2)
            fh.write("\n")


if __name__ == "__main__":
    main()
