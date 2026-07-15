# Event-driven CSV backtest repair

Implement the stub in `workspace/backtester.py`. The CLI in
`workspace/run_backtest.py` has a required `--actions PATH` argument (there is
no implicit actions file). `--prices`, `--signals`, `--config`, and
`--output-dir` default to files in the current workspace, so the short form
`run_backtest.py --actions actions.csv` is valid. Use only the Python standard
library.

## Input and validation

* `prices.csv` columns are `timestamp,asset,open,high,low,close,volume`.
  `signals.csv` columns are `timestamp,asset,target_position` where the target
  is a signed desired number of shares. `actions.csv` columns are
  `timestamp,asset,split_ratio,cash_dividend`; a null split ratio means 1 and
  a null cash dividend means 0. `config.json` contains
  `initial_cash,commission_bps,slippage_bps,max_participation,allow_short`.
* Timestamps are timezone-aware ISO-8601 values (a trailing `Z` means UTC).
  Normalize to UTC before sorting or comparing. Naive or malformed timestamps,
  nonfinite prices/targets, nonpositive open/close/volume, nonpositive split
  ratios, negative rates, or an invalid participation are errors.
* Exact duplicate rows are collapsed. Rows with the same normalized
  `(timestamp,asset)` key but different values are conflicts and must raise
  `ValueError`, never be selected by input order. When `allow_short` is false,
  negative target positions are rejected.

## Accounting contract

For every UTC price timestamp, first credit
`pre_action_shares * cash_dividend`, then multiply shares by `split_ratio`.
Actions are applied before execution. Fill toward the latest **strictly earlier**
signal at the current bar's open; a same-timestamp signal cannot use that bar.
Quantity is signed and capped by `floor(volume * max_participation)`. A
positive quantity buys and a negative quantity sells. Buy/sell fill price is
open times
`1 +/- slippage_bps/10000`; fee is
`abs(quantity * fill_price) * commission_bps/10000`; cash changes by
`-quantity * fill_price - fee`. Mark all positions at the bar close after the
fill. Short targets are allowed only when `allow_short` is true.

Write deterministic UTC-ordered `outputs/trades.csv`, `outputs/equity.csv`,
and `outputs/metrics.json`. Trades contain exactly
`timestamp,asset,side,quantity,price,gross_value,fees,cash_after`; quantity is
the absolute filled amount and side is `buy` or `sell`. Equity contains
exactly `timestamp,cash,positions_value,equity`. Metrics contain exactly
`total_return,max_drawdown,turnover,total_fees,n_trades`. `total_return =
final_equity / initial_cash - 1`; `max_drawdown` is the maximum `1 -
equity/running_max_equity`, with running max initialised to initial cash;
`turnover` is absolute traded gross value divided by the mean recorded equity.
The public fixture is deterministic seed 100; do not put generated outputs or
a solution in `workspace`.
