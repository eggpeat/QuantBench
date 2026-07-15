# Event-Driven CSV Backtest Repair

## Summary

Repair `workspace/backtester.py` and run it through `workspace/run_backtest.py`, which consumes normalized CSV price, signal, and corporate-action events plus a JSON configuration. The CLI requires `--actions PATH`; other input paths and the output directory have workspace defaults.

## Required outputs

Create deterministic UTC-ordered `outputs/trades.csv`, `outputs/equity.csv`, and `outputs/metrics.json`. Trades contain exactly `timestamp,asset,side,quantity,price,gross_value,fees,cash_after`; equity contains `timestamp,cash,positions_value,equity`; metrics contain `total_return,max_drawdown,turnover,total_fees,n_trades`.

## Verifier-facing success contract

- Validate required CSV fields, timezone-aware ISO-8601 timestamps, finite positive market data, valid rates/participation, split/dividend domains, and short-position rules. Normalize timestamps to UTC before sorting or comparison; naive or malformed timestamps are errors.
- Collapse exact duplicate rows. Same normalized `(timestamp, asset)` rows with conflicting values raise `ValueError` rather than relying on input order.
- At each UTC price timestamp, credit pre-action dividends, apply split ratios, then fill toward the latest strictly earlier signal. Apply participation caps, signed quantities, slippage, commission fees, cash accounting, and close marking exactly as specified; same-timestamp signals cannot fill that bar.
- Compute the stated total return, running-maximum drawdown, gross-value turnover, fees, and trade count. Use only standard-library Python and do not generate outputs or a solution in the workspace source tree.

## Environment and runtime constraints

Use the pinned `python:3.12-slim-bookworm` image (`sha256:db8e83a44af476c636a6a753adace39ad37863b63c0afd2862db7bbafeeb3944`), one CPU, 1 GiB memory, no network, and only the pinned pytest dependency in `environment/requirements.txt`; implementation code uses the Python standard library.