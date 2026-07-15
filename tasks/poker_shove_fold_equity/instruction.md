# Poker shove/fold equity task

Implement the starter module `poker_ev.py` in the workspace and produce `outputs/shove_fold.json` from `spots.json`.

Each spot has:

- `pot` (`P`): current pot before hero shoves.
- `risk` (`R`): chips hero risks by shoving.
- `call` (`C`): chips villain contributes when calling the shove.
- `equity` (`e`): hero's chance to win when called, as a decimal.
- `fold_probability` (`f`): probability villain folds.

Use this model exactly:

```text
called_ev = e * (P + C) - (1 - e) * R
shove_ev = f * P + (1 - f) * called_ev
```

Break-even fold equity is the fold probability that makes `shove_ev = 0`. Clamp it to `[0, 1]` when meaningful; if `called_ev` is already non-negative, return `0.0`.

Required output file: `outputs/shove_fold.json` (containing a top-level `"spots"` key with a list of spot records).

For every spot in the output file and in the `evaluate_spot` helper return dictionary, include the following fields:

- `spot_id`
- `shove_ev`, rounded to 2 decimals
- `breakeven_fold_equity`, rounded to 6 decimals
- `decision`, `"shove"` when the unrounded `shove_ev >= 0`, else `"fold"`
Use only Python's standard library. Do not use external services, credentials, live betting, or trading APIs.

### Source Grounding
This task operationalizes the mathematical expectation and fold equity concepts from David Sklansky and Ed Miller's *No-Limit Hold'em: Theory and Practice* (specifically pages 2, 48, 49, and 50). All formulas and decision criteria are directly derived from the book's break-even and total expectation rules.
