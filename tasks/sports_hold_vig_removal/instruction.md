Read `markets.json` from the workspace and create `outputs/no_vig_kelly.json`.

You are auditing a small sportsbook slate. Implement the calculations in boring standard-library Python; do not use external services, live odds, credentials, or network access.

Starter files are provided in the workspace:
- `no_vig_kelly.py`: Contains stubs for your implementation.
- `run_no_vig_kelly.py`: A script that imports and runs your `no_vig_kelly.main()` function. You can run this using `python run_no_vig_kelly.py`.

Required implementation:

1. Complete the workspace module named `no_vig_kelly.py` exposing at least these functions:
   - `american_to_decimal(odds)`
   - `implied_probability(odds)`
   - `analyze_market(market, bankroll, fractional_kelly, high_hold_threshold)`
   - `main(workspace_path=None)`
2. Process every market in `markets.json`.
3. Write `outputs/no_vig_kelly.json` with this shape:

```json
{
  "bankroll": 1000.0,
  "fractional_kelly": 0.25,
  "markets": [
    {
      "market_id": "...",
      "sum_implied": 1.047619,
      "overround": 0.047619,
      "hold": 0.045455,
      "high_hold": false,
      "outcomes": [
        {
          "name": "...",
          "american_odds": -110,
          "decimal_odds": 1.909091,
          "implied_probability": 0.52381,
          "no_vig_probability": 0.5,
          "model_probability": 0.51,
          "ev_per_dollar": -0.026364,
          "full_kelly": 0.0,
          "recommended_stake": 0.0,
          "recommendation": "no_bet"
        }
      ]
    }
  ]
}
```

Calculation requirements:

- American odds to decimal odds:
  - positive odds: `1 + odds / 100`
  - negative odds: `1 + 100 / abs(odds)`
- American odds to implied probability:
  - positive odds: `100 / (odds + 100)`
  - negative odds: `abs(odds) / (abs(odds) + 100)`
- Market overround: `sum_implied - 1`.
- Balanced-book market hold percentage: `1 - 1 / sum_implied`.
- Proportional no-vig probability: `implied_probability / sum_implied`.
- Per-$1 EV at offered odds: `model_probability * (decimal_odds - 1) - (1 - model_probability)`.
- Full Kelly fraction: `max(0, (b * p - (1 - p)) / b)`, where `b = decimal_odds - 1` and `p = model_probability`.
- Recommended stake: `bankroll * fractional_kelly * full_kelly`, except force it to `0.00` for every outcome in a market whose hold is greater than or equal to `high_hold_threshold`.

Rounding requirements:

- Round probabilities, holds, overrounds, EVs, decimal odds, and Kelly fractions to exactly 6 decimal places in the JSON numeric values.
- Round stakes to exactly 2 decimal places.
- Use `recommendation = "bet"` only when the market is not high-hold and the rounded recommended stake is greater than 0; use `"no_bet_high_hold"` for all outcomes in high-hold markets; otherwise use `"no_bet"`.

The public fixture includes a normal two-way spread, a positive-edge two-way spread, and a high-hold three-way market. The three-way market must be flagged high-hold and must produce no bet recommendations even if an individual outcome has positive modeled EV.
