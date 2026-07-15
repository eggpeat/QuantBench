# Poker Hand History State Machine Parser

## Overview

This Terminal-Bench-style task asks an agent to implement a state-machine parser that converts raw-text poker hand histories into a canonical structured JSON format. The parser must process metadata, track player chips/stacks, handle street transitions, compute pot contributions, and statefully validate the rules of the hand.

The source provenance is standard poker rules and hand history formats, utilizing *No-Limit Hold'em: Theory and Practice* by David Sklansky and Ed Miller as the theoretical foundation for betting street transitions, action order, blind posting, and showdown evaluation.

## Source Grounding & Provenance

- **Source**: *No-Limit Hold'em: Theory and Practice* by David Sklansky and Ed Miller.
- **Task Behavior vs. Source**:
  - The task operationalizes standard No-Limit Hold'em rules—specifically blinds, seats, chip stacks, betting street progression (preflop, flop, turn, river), actions (fold, check, call, bet, raise), uncalled bets returned, and pot collections—into a state-machine parser.
  - The verifier validates both standard PokerStars-formatted histories and edge cases designed to defeat simple regular expressions (e.g. players named with action verbs, chat lines mimicking actions, stateful rule violations like checking when facing a bet, acting out of turn, or betting more than one's stack).
- **Verifier Risk**: Low risk of analytical failure since the verifier runs tests with deterministic outputs.

## What It Tests

The task checks whether the agent can correctly design and implement a state-machine parser:

- **Metadata Parsing**: Extract hand ID, table name, button seat, and blinds.
- **Seat/Stack Tracking**: Initialize starting stacks from seat info, deduct posts/bets, refund uncalled bets, and add collections.
- **Street Action Invariants**: Process actions sequentially, tracking incremental `amount` (chips added) and `to_amount` (total street bet size).
- **State Machine Validation**: Return `valid: false` with descriptive `errors` for:
  - Unseated player acting.
  - Folded player acting.
  - Player checking when facing an outstanding bet.
  - Insufficient stack to bet/call.
- **Adversarial Input Handling**: Avoid false positives on chat lines, or player names matching action verbs.

## Workspace Structure

- `hand_histories.txt`: Text file with multiple public hand histories (both valid and invalid).
- `hand_parser.py`: Starter implementation module with a `parse_hands(text)` stub.
- `run_parser.py`: Run script that reads `hand_histories.txt` and writes `outputs/parsed_hands.json`.

## Required Outputs

- `outputs/parsed_hands.json`: JSON output containing the structured list of parsed hand history dicts.

## Verifier Verification

Tests check that the output matches the expected JSON and verify candidate functions against hidden, inline test cases (e.g. stack limits, players named `folds`, chat lines, and invalid check sequences).
