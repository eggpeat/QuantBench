# sportsbook_parlay_synthetic_risk

## Overview

This Quant Bench task asks the agent to calculate parlay synthetic risk and handle metrics over a series of betting tickets. The workspace contains `tickets.json` with stake, ordered legs, American odds, true win probabilities, and optional offered parlay payouts.

The candidate must create `outputs/parlay_risk.json` and a reusable `parlay_risk.py` module in the workspace. The verifier checks both the public snapshot and separate inline test cases (one-leg degeneracy, fair rollover, short-pays, and edge-compounding handle) so a static expected-output copy is insufficient.

## Source Grounding & Provenance

- **Source**: *The Logic of Sports Betting* read-extracted lines 607-789 (parlay-as-rolled-singles, off-board payouts, short-pay schedules, and betting volume/handle explosion).
- **Task Behavior vs. Source**:
  - The task matches the source book. It models a parlay as a sequence of rolled-over single wagers.
  - The true rollover decimal odds are computed as the product of the legs' decimal odds.
  - Short-pay margins represent the extra vig introduced by fixed-odds parlay tables or payout caps below true rollover.
  - Expected synthetic handle tracks the total expected volume of money wagered as legs win and roll over chronologically.
- **Verifier Risk**: None. Verifier and expected outputs are aligned with source-defined formulas.

## What It Tests

- Correct conversion of American odds to decimal odds.
- Compound true rollover odds calculation.
- Short-pay margin calculation given capped offered payouts.
- Chronological expected synthetic handle calculation: $S \times \sum_{k=0}^{N-1} \prod_{i=1}^k (d_i \times p_i)$.
- Expected ticket return and hold metrics under true win probabilities.
- Compounded edge behavior (e.g. how a positive edge compounds the expected handle and keeps hold on synthetic handle constant while hold on stake grows).
- Robust path and file handling via workspace path parameter.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No internet, credentials, or third-party packages.
- The verifier uses pytest-style tests with plain asserts.

## Inputs

The workspace contains:

- `workspace/tickets.json`: A JSON list of tickets, each containing:
  - `ticket_id`: Unique identifier.
  - `stake`: The initial wager amount.
  - `legs`: A list of ordered legs, where each leg contains `leg_id`, `american_odds`, and `true_win_prob`.
  - `offered_payout`: (Optional) The total return (stake + win) offered by the sportsbook for the parlay.
- `workspace/parlay_risk.py`: Starter implementation file containing function stubs and docstrings.
- `workspace/run_parlay_risk.py`: A starter script that imports and executes your `parlay_risk.py` module.

## Required Outputs

Create `outputs/parlay_risk.json` under the workspace. For each ticket include:

- `ticket_id`
- `true_rollover_decimal`
- `offered_decimal`
- `short_pay_margin`
- `expected_synthetic_handle`
- `expected_return`
- `hold_on_stake`
- `hold_on_synthetic_handle`

Round all metrics to 6 decimal places.

## Verification

The public verifier loads `TASK_WORKSPACE` if set, otherwise `/workspace`. It checks that:

1. `outputs/parlay_risk.json` exactly matches `tests/expected.json` for the public fixture.
2. The candidate module exposes the required API functions.
3. Inline edge cases cover one-leg degeneracy, fair off-board parlays, short-pays, and compounding edge wagers.

Candidates can run the calculations locally using:
```bash
python run_parlay_risk.py
```

## Difficulty/Anti-cheat Notes

Difficulty is medium. The math is simple but requires precise order-of-settlement modeling for expected synthetic handle. A static copy of the expected JSON will fail the dynamic inline checks in the verifier.
