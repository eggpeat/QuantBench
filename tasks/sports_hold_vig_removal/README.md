# sports_hold_vig_removal

## Overview

This Quant Bench task asks the agent to turn a small sportsbook slate into a no-vig and Kelly sizing report. The workspace contains `markets.json` with bankroll settings, a fractional Kelly multiplier, a high-hold cutoff, and three public markets: a normal two-way spread, a positive-edge two-way spread, and an intentionally expensive three-way/tie market.

The candidate must create `outputs/no_vig_kelly.json` and a reusable `no_vig_kelly.py` module in the workspace. The verifier checks both the public snapshot and separate inline American-odds edge cases so a copied JSON file is not sufficient.

## Source Grounding & Provenance

- **Source**: *The Logic of Sports Betting* read-extracted lines 305-361 (break-even percentages and American odds conversion), 397-435 (sportsbook hold calculation), and 447-461 (decimal odds and reciprocal break-even probability); *Winning Sports Betting* (Masaru Kanemoto) read-extracted lines 1193-1231 (dynamic/fractional Kelly sizing and quarter-Kelly/fractional risk discipline).
- **Task Behavior vs. Source**:
  - The task matches the source books. It reports both `overround = sum_implied - 1` and `hold = 1 - 1 / sum_implied` as defined in *The Logic of Sports Betting*.
  - Dynamic fractional Kelly bet sizing matches *Winning Sports Betting* risk discipline.
- **Verifier Risk**: None. Verifier and expected outputs are aligned with source-defined formulas.
## What It Tests

- Correct conversion between American odds, decimal odds, and implied break-even probability.
- Separating bookmaker hold from proportional no-vig fair probabilities.
- EV calculation at the offered sportsbook price, not at the no-vig fair price.
- Fractional Kelly bet sizing with non-negative full Kelly fractions.
- High-hold risk control: a three-way market above the hold threshold must be flagged and must not produce bet recommendations.
- Deterministic JSON output with precise rounding discipline.

## Environment

- Docker image: `python:3.13-slim-bookworm`
- Standard-library Python only.
- No internet, credentials, live sportsbook access, trading, or betting.
- The verifier uses pytest-style tests with plain asserts.

## Inputs

The workspace contains:

- `workspace/markets.json`: Includes:
  - `bankroll`: bankroll used for stake sizing.
  - `fractional_kelly`: multiplier applied to full Kelly.
  - `high_hold_threshold`: market hold cutoff for forced no-bet behavior.
  - `markets`: each market has a `market_id`, descriptive fields, and outcomes with `name`, `american_odds`, and `model_probability`.
- `workspace/no_vig_kelly.py`: Starter implementation file containing function stubs and docstrings.
- `workspace/run_no_vig_kelly.py`: A starter script that imports and executes your `no_vig_kelly.py` module.

## Required Outputs

Create `outputs/no_vig_kelly.json` under the workspace. For each market include:

- `market_id`
- `sum_implied`
- `overround`
- `hold`
- `high_hold`
- `outcomes`

For each outcome include:

- `name`
- `american_odds`
- `decimal_odds`
- `implied_probability`
- `no_vig_probability`
- `model_probability`
- `ev_per_dollar`
- `full_kelly`
- `recommended_stake`
- `recommendation`

Round probability-like fields, EVs, decimal odds, and Kelly fractions to 6 decimals; round stakes to 2 decimals.

## Verification

The public verifier loads `TASK_WORKSPACE` if set, otherwise `/workspace`. It checks that:

1. `outputs/no_vig_kelly.json` exactly matches `tests/expected.json` for the public fixture.
2. The candidate module exposes odds-conversion and market-analysis functions.
3. Inline edge cases cover plus-money, minus-money, even-money, high-hold no-bet forcing, and Kelly stake sizing.

Candidates can run the calculations locally using:
```bash
python run_no_vig_kelly.py
```
## Difficulty/Anti-cheat Notes

Difficulty is medium. The arithmetic is small, but the task is designed to catch common sports-betting mistakes: treating hold as edge, sizing from no-vig odds instead of offered odds, mishandling plus/minus American prices, and recommending bets in a high-hold three-way market. Inline tests make a static expected-output copy insufficient.
