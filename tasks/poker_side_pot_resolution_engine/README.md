# Poker Side Pot Resolution Engine

## Overview

This Quant Bench task asks an agent to implement a deterministic transactional allocation engine for no-limit poker side pots, chops, folds, all-in caps, and odd chips, then evaluate public fixture hands into `outputs/settlements.json`.

The source provenance is `source_books/392022285-No-Limit-Hold-em-Theory-and-Practice-David-Sklansky-Ed-Miller-pdf.pdf`. The task is fully grounded in standard rules of table stakes and no-limit hold'em side pots.

## Source Grounding & Provenance

- **Source**: *No-Limit Hold'em: Theory and Practice* by David Sklansky and Ed Miller.
- **Task Behavior vs. Source**:
  - The task operationalizes standard table stakes and side-pot rules, where a player cannot win more from an opponent than they have wagered.
  - This requires the pot to be divided into multiple pots when players go all-in with different amounts, which is a standard rule described in hold'em theory and practice.
  - The source is a scanned draft copy, which represents a scanned-PDF provenance limitation, but manual observation has verified that the task behavior is sufficiently supported, so there are no remaining promotion blockers.
- **Verifier Risk**: Low risk of analytical failure since the verifier strictly tests exact transactional conservation and pot allocation math.

## What It Tests

The task checks whether the agent can correctly implement a side-pot partitioning algorithm:

1. **Table Stakes & Pot Partitioning**:
   - Collect and sort all distinct non-zero player bets as level thresholds $L_1 < L_2 < \dots < L_k$.
   - For each level $j$, calculate the pot size by summing each player's contribution: $\max(0, \min(\text{bet}_p, L_j) - L_{j-1})$.
   - Track eligibility: only active players who bet $\ge L_j$ are eligible for pot $j$.
2. **Chops & Odd Chips**:
   - Split a level's pot equally among the eligible active players who share the highest hand strength.
   - Distribute the remainder (odd chips) 1 chip at a time to these tied winners in ascending order of their seat numbers.
3. **Refunds/Uncalled Bets**:
   - If a level has no eligible active players (e.g. because the highest bettors folded), refund the contributions of that level back to the contributors.
4. **Conservation of Chips**:
   - Sum of all payouts must equal the sum of all bet contributions.

## Environment

The environment is a small Python 3.13 workspace using only the standard library. Internet access is disabled and no credentials or external services are needed.

## Inputs

The workspace contains:

- `hands.json`: public hand scenarios.
- `side_pots.py`: starter implementation module.
- `run_side_pots.py`: small runner that should load hands and write results.

## Required Outputs

Create `outputs/settlements.json` containing the settlements for all hands in `hands.json`.

## Verification

Pytest-compatible tests compare `outputs/settlements.json` to `tests/expected.json` and import `side_pots.py` for inline edge cases, including an inline hidden hand with at least 3 all-in levels and a chop odd-chip case. The same file is directly executable with `python tests/test_outputs.py`.
