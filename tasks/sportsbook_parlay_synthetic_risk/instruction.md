Read `tickets.json` from the workspace and create `outputs/parlay_risk.json`.

You are auditing sportsbook parlay ticket exposure. Implement the calculations in boring standard-library Python; do not use external libraries, databases, or network access.

Starter files are provided in the workspace:
- `parlay_risk.py`: Contains stubs for your implementation.
- `run_parlay_risk.py`: A script that imports and runs your `parlay_risk.main()` function. You can run this using `python run_parlay_risk.py`.

Required implementation:

1. Complete the workspace module named `parlay_risk.py` exposing at least these functions:
   - `american_to_decimal(odds)`
   - `evaluate_ticket(ticket)`
   - `evaluate_tickets(tickets)`
   - `main(workspace_path=None)`
2. Process every ticket in `tickets.json`.
3. Write `outputs/parlay_risk.json` with this shape:

```json
{
  "tickets": [
    {
      "ticket_id": "...",
      "true_rollover_decimal": 12.345678,
      "offered_decimal": 11.0,
      "short_pay_margin": 0.108996,
      "expected_synthetic_handle": 150.25,
      "expected_return": 85.5,
      "hold_on_stake": 0.145,
      "hold_on_synthetic_handle": 0.096505
    }
  ]
}
```

Calculation requirements:

- American odds to decimal odds:
  - positive odds (odds >= 100): `1 + odds / 100`
  - negative odds (odds <= -100): `1 + 100 / abs(odds)`
- True rollover decimal odds:
  - `true_rollover_decimal = product(decimal_odds_i)` for all legs $i = 1 \dots N$.
- Offered decimal odds:
  - If `offered_payout` is specified in the ticket, `offered_decimal = offered_payout / stake`.
  - If not specified, it defaults to `true_rollover_decimal`.
- Short-pay margin:
  - `short_pay_margin = 1.0 - (offered_decimal / true_rollover_decimal)`.
- Expected synthetic handle:
  - `expected_synthetic_handle = S * sum_{k=0}^{N-1} (product_{i=1}^{k} (decimal_odds_i * true_win_prob_i))`
  - Note that for $k=0$, the product is empty and equals `1.0`.
- Expected return:
  - `expected_return = S * offered_decimal * product(true_win_prob_i)` for all legs $i = 1 \dots N$.
- Hold on stake:
  - `hold_on_stake = 1.0 - offered_decimal * product(true_win_prob_i)` for all legs $i = 1 \dots N$.
- Hold on synthetic handle:
  - `hold_on_synthetic_handle = (S - expected_return) / expected_synthetic_handle`.

Rounding requirements:

- Round decimal odds, margins, handles, returns, and holds to exactly 6 decimal places in the JSON numeric values.
- If a calculation result has no decimal parts (e.g. 100.0), outputting it with a trailing `.0` or `.00` is acceptable as long as it matches python float conversion, but rounding via `round(val, 6)` is required.
