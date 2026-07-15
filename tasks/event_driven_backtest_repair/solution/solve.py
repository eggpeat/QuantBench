#!/usr/bin/env python3
"""Install the reference event-driven backtester and run the public fixture."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

_REFERENCE = r'''"""Reference event-driven CSV accounting implementation."""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
_EPS = 1e-12


def _utc(value: Any) -> tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid timestamp: {value!r}") from exc
    else:
        raise ValueError(f"invalid timestamp: {value!r}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware ISO-8601 values")
    parsed = parsed.astimezone(UTC)
    text = parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if text.endswith(".000000Z"):
        text = text[:-8] + "Z"
    return parsed, text


def _number(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _rows(path: str | Path, required: tuple[str, ...], *, allow_empty: bool = False) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{path} has no CSV header")
        missing = [column for column in required if column not in reader.fieldnames]
        if missing:
            raise ValueError(f"{path} missing columns: {', '.join(missing)}")
        result = []
        for row in reader:
            if row and any((value or "").strip() for value in row.values()):
                result.append({key: (value or "").strip() for key, value in row.items()})
    if not result and not allow_empty:
        raise ValueError(f"{path} contains no rows")
    return result


def _load_prices(path: str | Path) -> list[dict[str, Any]]:
    fields = ("open", "high", "low", "close", "volume")
    seen: dict[tuple[datetime, str], tuple[float, ...]] = {}
    result = []
    for row in _rows(path, ("timestamp", "asset", *fields)):
        dt, text = _utc(row["timestamp"])
        asset = row["asset"].strip()
        if not asset:
            raise ValueError("asset must be nonempty")
        values = tuple(_number(row[field], field) for field in fields)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("price values must be finite")
        if any(value <= 0 for value in values):
            raise ValueError("OHLC and volume must be positive")
        key = (dt, asset)
        previous = seen.get(key)
        if previous is not None:
            if previous != values:
                raise ValueError(f"conflicting duplicate price for {asset} at {text}")
            continue
        seen[key] = values
        result.append({"dt": dt, "timestamp": text, "asset": asset, **dict(zip(fields, values))})
    result.sort(key=lambda row: (row["dt"], row["asset"]))
    return result


def _load_signals(path: str | Path) -> list[dict[str, Any]]:
    seen: dict[tuple[datetime, str], float] = {}
    result = []
    for row in _rows(path, ("timestamp", "asset", "target_position"), allow_empty=True):
        dt, text = _utc(row["timestamp"])
        asset = row["asset"].strip()
        target = _number(row["target_position"], "target_position")
        key = (dt, asset)
        previous = seen.get(key)
        if previous is not None:
            if previous != target:
                raise ValueError(f"conflicting duplicate signal for {asset} at {text}")
            continue
        seen[key] = target
        result.append({"dt": dt, "timestamp": text, "asset": asset, "target_position": target})
    result.sort(key=lambda row: (row["dt"], row["asset"]))
    return result


def _optional_number(raw: str | None, default: float, name: str) -> float:
    if raw is None or raw.strip().lower() in {"", "null", "none"}:
        return default
    return _number(raw, name)


def _load_actions(path: str | Path) -> list[dict[str, Any]]:
    seen: dict[tuple[datetime, str], tuple[float, float]] = {}
    result = []
    for row in _rows(path, ("timestamp", "asset", "split_ratio", "cash_dividend"), allow_empty=True):
        dt, text = _utc(row["timestamp"])
        asset = row["asset"].strip()
        ratio = _optional_number(row.get("split_ratio"), 1.0, "split_ratio")
        dividend = _optional_number(row.get("cash_dividend"), 0.0, "cash_dividend")
        if ratio <= 0 or dividend < 0:
            raise ValueError("split_ratio must be positive and cash_dividend nonnegative")
        key = (dt, asset)
        value = (ratio, dividend)
        previous = seen.get(key)
        if previous is not None:
            if previous != value:
                raise ValueError(f"conflicting duplicate action for {asset} at {text}")
            continue
        seen[key] = value
        result.append({"dt": dt, "timestamp": text, "asset": asset, "split_ratio": ratio, "cash_dividend": dividend})
    result.sort(key=lambda row: (row["dt"], row["asset"]))
    return result


def _load_config(config_path: str | Path | None, config: dict[str, Any] | None) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    if config_path is not None:
        with Path(config_path).open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, dict):
            raise ValueError("config must be a JSON object")
    if config:
        loaded.update(config)
    defaults = {"initial_cash": 100000.0, "commission_bps": 5.0, "slippage_bps": 0.0, "max_participation": 0.10, "allow_short": False}
    defaults.update(loaded)
    initial_cash = _number(defaults["initial_cash"], "initial_cash")
    commission_bps = _number(defaults["commission_bps"], "commission_bps")
    slippage_bps = _number(defaults["slippage_bps"], "slippage_bps")
    participation = _number(defaults["max_participation"], "max_participation")
    allow_short = defaults["allow_short"]
    if not isinstance(allow_short, bool):
        raise ValueError("allow_short must be boolean")
    if initial_cash <= 0 or commission_bps < 0 or slippage_bps < 0 or participation <= 0 or participation > 1:
        raise ValueError("invalid backtest configuration")
    if slippage_bps >= 10000:
        raise ValueError("slippage_bps makes sell prices nonpositive")
    return {"initial_cash": initial_cash, "commission_bps": commission_bps, "slippage_bps": slippage_bps, "max_participation": participation, "allow_short": allow_short}


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run_backtest(
    prices_path: str | Path,
    signals_path: str | Path,
    actions_path: str | Path,
    output_dir: str | Path,
    *,
    config_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
    seed: int = 100,
) -> dict[str, float | int]:
    if actions_path is None:
        raise ValueError("--actions is required")
    settings = _load_config(config_path, config)
    prices = _load_prices(prices_path)
    signals = _load_signals(signals_path)
    actions = _load_actions(actions_path)
    if not settings["allow_short"] and any(row["target_position"] < 0 for row in signals):
        raise ValueError("negative target_position requires allow_short=true")
    cash = float(settings["initial_cash"])
    positions: dict[str, float] = {}
    last_close: dict[str, float] = {}
    targets: dict[str, float] = {}
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    fees_total = 0.0
    gross_total = 0.0
    dividends_total = 0.0
    split_count = 0
    price_times = sorted({row["dt"] for row in prices})
    action_index = 0
    signal_index = 0
    running_max = float(settings["initial_cash"])
    drawdown_max = 0.0
    by_time: dict[datetime, list[dict[str, Any]]] = {}
    for row in prices:
        by_time.setdefault(row["dt"], []).append(row)

    def marked_value() -> float:
        return sum(quantity * last_close[asset] for asset, quantity in positions.items() if asset in last_close)

    for event_time in price_times:
        group = by_time[event_time]
        for row in group:
            last_close[row["asset"]] = row["close"]
        # Corporate actions happen before any fill at this timestamp.
        while action_index < len(actions) and actions[action_index]["dt"] <= event_time:
            action = actions[action_index]
            asset = action["asset"]
            pre_action_shares = positions.get(asset, 0.0)
            credit = pre_action_shares * action["cash_dividend"]
            cash += credit
            dividends_total += credit
            positions[asset] = pre_action_shares * action["split_ratio"]
            if action["split_ratio"] != 1.0:
                split_count += 1
            action_index += 1
        # Strictly earlier signals only: equal-time signals wait for a later bar.
        while signal_index < len(signals) and signals[signal_index]["dt"] < event_time:
            signal = signals[signal_index]
            targets[signal["asset"]] = signal["target_position"]
            signal_index += 1
        for row in group:
            asset = row["asset"]
            if asset not in targets:
                continue
            current = positions.get(asset, 0.0)
            delta = targets[asset] - current
            cap = math.floor(row["volume"] * settings["max_participation"])
            if cap <= 0 or abs(delta) <= _EPS:
                continue
            signed_quantity = math.copysign(min(abs(delta), cap), delta)
            if signed_quantity < 0 and not settings["allow_short"] and current + signed_quantity < -_EPS:
                raise ValueError("short position requires allow_short=true")
            slippage = settings["slippage_bps"] / 10000.0
            fill_price = row["open"] * (1.0 + slippage if signed_quantity > 0 else 1.0 - slippage)
            gross_value = abs(signed_quantity * fill_price)
            fee = gross_value * settings["commission_bps"] / 10000.0
            cash -= signed_quantity * fill_price + fee
            positions[asset] = current + signed_quantity
            fees_total += fee
            gross_total += gross_value
            trades.append({"timestamp": _utc(event_time)[1], "asset": asset, "side": "buy" if signed_quantity > 0 else "sell", "quantity": abs(signed_quantity), "price": fill_price, "gross_value": gross_value, "fees": fee, "cash_after": cash})
        positions_value = marked_value()
        equity = cash + positions_value
        running_max = max(running_max, equity)
        drawdown_max = max(drawdown_max, 1.0 - equity / running_max)
        equity_rows.append({"timestamp": _utc(event_time)[1], "cash": cash, "positions_value": positions_value, "equity": equity})
    if not equity_rows:
        raise ValueError("prices contains no rows")
    mean_equity = sum(row["equity"] for row in equity_rows) / len(equity_rows)
    final_equity = equity_rows[-1]["equity"]
    metrics = {"total_return": final_equity / settings["initial_cash"] - 1.0, "max_drawdown": drawdown_max, "turnover": gross_total / mean_equity if mean_equity else 0.0, "total_fees": fees_total, "n_trades": len(trades)}
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    _write_csv(destination / "trades.csv", ["timestamp", "asset", "side", "quantity", "price", "gross_value", "fees", "cash_after"], trades)
    _write_csv(destination / "equity.csv", ["timestamp", "cash", "positions_value", "equity"], equity_rows)
    (destination / "metrics.json").write_text(json.dumps(metrics, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return metrics
'''


def main() -> None:
    workspace = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "backtester.py").write_text(_REFERENCE, encoding="utf-8")
    old_cwd, old_argv = Path.cwd(), sys.argv
    try:
        os.chdir(workspace)
        sys.path.insert(0, str(workspace))
        sys.argv = [str(workspace / "run_backtest.py"), "--prices", str(workspace / "prices.csv"), "--signals", str(workspace / "signals.csv"), "--actions", str(workspace / "actions.csv"), "--config", str(workspace / "config.json"), "--output-dir", str(workspace / "outputs"), "--seed", "100"]
        runpy.run_path(str(workspace / "run_backtest.py"), run_name="__main__")
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
        try:
            sys.path.remove(str(workspace))
        except ValueError:
            pass


if __name__ == "__main__":
    main()
