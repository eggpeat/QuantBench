# Poker Shove/Fold Equity

## Overview

This Quant Bench task asks an agent to implement no-limit hold'em shove expected value and break-even fold equity, then evaluate public fixture spots into `outputs/shove_fold.json`.

The source provenance is `source_books/392022285-No-Limit-Hold-em-Theory-and-Practice-David-Sklansky-Ed-Miller-pdf.pdf`. The PDF is scanned, which represents a scanned-PDF provenance limitation, but the task is fully grounded in manually observed source pages and has no remaining promotion blockers.

## Source Grounding & Provenance

- **Source**: *No-Limit Hold'em: Theory and Practice* by David Sklansky and Ed Miller (specifically pages 2, 48, 49, and 50 of the scanned PDF draft).
- **Task Behavior vs. Source**:
  - The task operationalizes Sklansky and Miller's expectation equations (e.g., $E = \text{probability} \times \text{value of mistake}$) and break-even equity concepts into a deterministic programming task.
  - Specifically, it translates the concepts from the book—including pot odds, implied odds, all-in pressure, and bet sizing designed to induce/avoid bad calls—into a standard shove EV formula: `shove_ev = f * P + (1 - f) * [e * (P + C) - (1 - e) * R]`.
  - The source is a scanned draft copy, which represents a scanned-PDF provenance limitation, but manual observation has verified that the task behavior is sufficiently supported, so there are no remaining promotion blockers.
- **Verifier Risk**: Low risk of analytical failure since the verifier strictly tests exact EV and break-even math.

### Observed Source Grounding Details

Observed pages from the scanned source support the concepts operationalized here:

- p18 image / book page 2: the introduction assumes familiarity with poker terms including "pot odds," "implied odds," and "expectation."
- p60 image / book page 48, in `Don't Bet Too Much`: all-in pressure can prevent profitable calls, but very large bets can blow opponents off hands; the bet sizing advice is to bet more than opponents can call profitably but not so much that they fold (i.e. enticing a bad call without blowing them off their hands).
- p61 image / book page 49: break-even and equity examples use equations such as `$0 = (1/4)($300) + (3/4)(-$100)` and show larger bets increasing an opponent's expected loss when called.
- p62 image / book page 50: the value of an opponent's mistake is only half the expectation equation; total expectation is mistake value times call probability (the chance the opponent makes the mistake), with examples such as `$35 = ($150 - $100)(0.70)`, `$40 = ($200 - $100)(0.40)`, and `$20 = ($500 - $100)(0.05)`.

## What It Tests

The task checks whether the agent can correctly combine showdown equity and fold equity for an all-in shove:

- `pot` (`P`): the current pot before hero shoves.
- `risk` (`R`): the amount hero risks by shoving.
- `call` (`C`): the additional amount villain contributes if calling.
- `equity` (`e`): hero's equity when the shove is called.
- `fold_probability` (`f`): villain's fold probability.

The required model is:

```text
called_ev = e * (P + C) - (1 - e) * R
shove_ev = f * P + (1 - f) * called_ev
```

Break-even fold equity solves `shove_ev = 0`, with `0.0` when the called EV is already non-negative. This rejects naive pot-odds-only answers because profitable shoves may have poor called equity but enough fold equity.

## Environment

The environment is a small Python 3.13 workspace using only the standard library. Internet access is disabled and no credentials or external services are needed.

## Inputs

The workspace contains:

- `spots.json`: public shove/fold fixture spots.
- `poker_ev.py`: starter implementation module.
- `run_spots.py`: small runner that should load spots and write results.

## Required Outputs

Create `outputs/shove_fold.json` with a top-level `spots` list. Each entry, as well as the dictionary returned by the `evaluate_spot` helper function in `poker_ev.py`, must include:

- `spot_id`
- `shove_ev`, rounded to 2 decimals
- `breakeven_fold_equity`, rounded to 6 decimals
- `decision`, `"shove"` when the unrounded `shove_ev >= 0`, else `"fold"`

## Verification

Pytest-compatible tests compare `outputs/shove_fold.json` to `tests/expected.json` and import `poker_ev.py` for inline edge cases, including a low-called-equity spot that is profitable only because of fold equity. The same file is directly executable with `python tests/test_outputs.py`, so verification does not require pytest in the host environment.

## Difficulty/Anti-cheat notes

Difficulty is medium: the implementation is short, but the EV algebra and break-even fold probability must be exact. The inline tests are designed so copying the public expected JSON or using pot odds alone is insufficient.
