# Poker Range Equity Engine

## Overview

This Quant Bench task asks an agent to implement a probabilistic card/range equity engine in Python using only the standard library. The agent must parse card representations, implement a Texas Hold'em hand evaluator supporting 5 to 7 cards, and compute equity for player ranges over specific board states.

## Source Grounding & Provenance

- **Source**: *No-Limit Hold'em: Theory and Practice* by David Sklansky and Ed Miller (specifically page 2, where expectation and poker terms are introduced).
- **Task Behavior vs. Source**:
  - The task operationalizes the concepts of showdown equity, card combinations, and range vs. range comparison discussed throughout Sklansky and Miller's work.
  - It translates these principles into a clean computational engine that calculates exact equities for small combination spaces and Monte Carlo simulated equities for larger spaces.
- **Verifier Risk**: Low risk of analytical failure since the verifier strictly tests exact equities and known made-hand comparisons on deterministic scenarios.

## What It Tests

- Card representation parsing.
- Texas Hold'em hand strength evaluation (5 to 7 cards) with proper tie-breaking.
- Range vs. Range equity computation under card removal constraints.
- Exact enumeration over remaining deck combinations for turn and flop boards.

## Inputs

- `scenarios.json`: contains the test scenarios with `scenario_id`, `p1_range`, `p2_range`, and `board`.
- `range_equity.py`: stub implementation file.
- `run_equity.py`: entrypoint to read the inputs, run the calculations, and output results.

## Required Outputs

Create `outputs/equity.json` containing:
- `scenario_id`
- `p1_equity`, rounded to 5 decimal places
- `p2_equity`, rounded to 5 decimal places
- `tie_probability`, rounded to 5 decimal places

## Verification

Pytest-compatible tests compare `outputs/equity.json` to `tests/expected.json` and import `range_equity.py` for inline edge cases, including exact turn and flop boards. The same file is directly executable with `python tests/test_outputs.py`.
