from __future__ import annotations

import csv
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TASK_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = Path(os.environ.get("TASK_WORKSPACE", str(TASK_DIR / "workspace")))


def _module():
    spec = importlib.util.spec_from_file_location("candidate_backtester", WORKSPACE / "backtester.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _run_cli(prices: Path, signals: Path, actions: Path, output: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(WORKSPACE / "run_backtest.py"), "--prices", str(prices), "--signals", str(signals), "--actions", str(actions), "--config", str(WORKSPACE / "config.json"), "--output-dir", str(output), *extra], cwd=WORKSPACE, text=True, capture_output=True)


def test_public_seed_fixture_outputs_exact_schema():
    output = WORKSPACE / "outputs"
    result = _run_cli(WORKSPACE / "prices.csv", WORKSPACE / "signals.csv", WORKSPACE / "actions.csv", output)
    assert result.returncode == 0, result.stderr
    metrics = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics) == {"total_return", "max_drawdown", "turnover", "total_fees", "n_trades"}
    assert metrics["n_trades"] > 0 and metrics["total_fees"] > 0
    assert metrics["total_return"] == pytest.approx(float(metrics["total_return"]))
    with (output / "trades.csv").open(newline="", encoding="utf-8") as handle:
        trades = list(csv.DictReader(handle))
    with (output / "equity.csv").open(newline="", encoding="utf-8") as handle:
        equity = list(csv.DictReader(handle))
    assert trades and equity
    assert set(trades[0]) == {"timestamp", "asset", "side", "quantity", "price", "gross_value", "fees", "cash_after"}
    assert set(equity[0]) == {"timestamp", "cash", "positions_value", "equity"}
    assert [row["timestamp"] for row in equity] == sorted(row["timestamp"] for row in equity)


def test_actions_before_fill_and_mark_with_split_and_dividend(tmp_path: Path):
    prices = tmp_path / "prices.csv"
    signals = tmp_path / "signals.csv"
    actions = tmp_path / "actions.csv"
    _write_csv(prices, "timestamp,asset,open,high,low,close,volume", [
        "2024-01-01T09:30:00Z,A,100,101,99,100,1000",
        "2024-01-02T09:30:00Z,A,50,51,49,50,1000",
    ])
    _write_csv(signals, "timestamp,asset,target_position", ["2024-01-01T09:29:00Z,A,10"])
    actions.write_text("timestamp,asset,split_ratio,cash_dividend\n2024-01-02T09:30:00+00:00,A,2,1\n2024-01-02T04:30:00-05:00,A,2,1\n", encoding="utf-8")
    output = tmp_path / "out"
    metrics = _module().run_backtest(prices, signals, actions, output, config={"initial_cash": 1000, "commission_bps": 0, "slippage_bps": 0, "max_participation": 1, "allow_short": False})
    assert metrics["n_trades"] == 2
    rows = list(csv.DictReader((output / "equity.csv").open(newline="", encoding="utf-8")))
    assert float(rows[-1]["equity"]) == pytest.approx(1010.0)
    assert float(rows[-1]["positions_value"]) == pytest.approx(500.0)
    trades = list(csv.DictReader((output / "trades.csv").open(newline="", encoding="utf-8")))
    assert trades[0]["side"] == "buy" and float(trades[0]["quantity"]) == pytest.approx(10)
    assert trades[1]["side"] == "sell" and float(trades[1]["quantity"]) == pytest.approx(10)

def test_participation_slippage_fee_and_turnover(tmp_path: Path):
    prices = tmp_path / "prices.csv"
    signals = tmp_path / "signals.csv"
    actions = tmp_path / "actions.csv"
    _write_csv(prices, "timestamp,asset,open,high,low,close,volume", [
        "2024-01-01T00:00:00Z,A,100,101,99,100,3",
    ])
    _write_csv(signals, "timestamp,asset,target_position", ["2023-12-31T23:00:00Z,A,10"])
    _write_csv(actions, "timestamp,asset,split_ratio,cash_dividend", ["2024-01-01T00:00:00Z,A,,"])
    output = tmp_path / "out"
    metrics = _module().run_backtest(prices, signals, actions, output, config={"initial_cash": 1000, "commission_bps": 100, "slippage_bps": 100, "max_participation": 0.5, "allow_short": False})
    assert metrics["n_trades"] == 1
    trade = next(csv.DictReader((output / "trades.csv").open(newline="", encoding="utf-8")))
    assert float(trade["quantity"]) == pytest.approx(1)  # floor(3 * .5)
    assert float(trade["price"]) == pytest.approx(101)
    assert float(trade["fees"]) == pytest.approx(1.01)
    assert float(trade["cash_after"]) == pytest.approx(897.99)
    assert metrics["total_fees"] == pytest.approx(1.01)
    assert metrics["turnover"] > 0


def test_utc_dedup_conflicts_and_short_rejection(tmp_path: Path):
    prices = tmp_path / "prices.csv"
    signals = tmp_path / "signals.csv"
    actions = tmp_path / "actions.csv"
    config = {"initial_cash": 1000, "commission_bps": 0, "slippage_bps": 0, "max_participation": 1, "allow_short": False}
    _write_csv(prices, "timestamp,asset,open,high,low,close,volume", [
        "2024-01-01T00:00:00Z,A,100,101,99,100,10",
        "2023-12-31T19:00:00-05:00,A,100,101,99,100,10",
    ])
    _write_csv(signals, "timestamp,asset,target_position", ["2024-01-01T00:00:00Z,A,0"])
    _write_csv(actions, "timestamp,asset,split_ratio,cash_dividend", ["2024-01-01T00:00:00Z,A,,0"])
    _module().run_backtest(prices, signals, actions, tmp_path / "out", config=config)
    _write_csv(prices, "timestamp,asset,open,high,low,close,volume", [
        "2024-01-01T00:00:00Z,A,100,101,99,100,10",
        "2023-12-31T19:00:00-05:00,A,101,102,100,101,10",
    ])
    with pytest.raises(ValueError, match="conflict"):
        _module().run_backtest(prices, signals, actions, tmp_path / "conflict", config=config)
    _write_csv(prices, "timestamp,asset,open,high,low,close,volume", ["2024-01-01T00:00:00,A,100,101,99,100,10"])
    with pytest.raises(ValueError, match="timezone-aware"):
        _module().run_backtest(prices, signals, actions, tmp_path / "naive", config=config)
    _write_csv(prices, "timestamp,asset,open,high,low,close,volume", ["2024-01-01T00:00:00Z,A,100,101,99,100,10"])
    _write_csv(signals, "timestamp,asset,target_position", ["2023-12-31T23:00:00Z,A,-1"])
    with pytest.raises(ValueError, match="allow_short"):
        _module().run_backtest(prices, signals, actions, tmp_path / "short", config=config)


def test_strict_no_lookahead_and_required_actions(tmp_path: Path):
    prices = tmp_path / "prices.csv"
    signals = tmp_path / "signals.csv"
    actions = tmp_path / "actions.csv"
    _write_csv(prices, "timestamp,asset,open,high,low,close,volume", ["2024-01-01T00:00:00Z,A,100,101,99,100,100", "2024-01-02T00:00:00Z,A,110,111,109,110,100"])
    _write_csv(signals, "timestamp,asset,target_position", ["2024-01-03T00:00:00Z,A,1"])
    _write_csv(actions, "timestamp,asset,split_ratio,cash_dividend", ["2024-01-01T00:00:00Z,A,,0"])
    metrics = _module().run_backtest(prices, signals, actions, tmp_path / "out", config={"initial_cash": 1000, "commission_bps": 0, "slippage_bps": 0, "max_participation": 1, "allow_short": False})
    assert metrics["n_trades"] == 0
    missing_actions = subprocess.run([sys.executable, str(WORKSPACE / "run_backtest.py"), "--prices", str(prices), "--signals", str(signals)], cwd=WORKSPACE, text=True, capture_output=True)
    assert missing_actions.returncode != 0


def test_noop_candidate_is_rejected(tmp_path: Path):
    fake = tmp_path / "workspace"
    shutil.copytree(WORKSPACE, fake)
    (fake / "backtester.py").write_text("def run_backtest(*args, **kwargs):\n    raise NotImplementedError('no-op')\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(fake / "run_backtest.py"), "--actions", str(fake / "actions.csv")], cwd=fake, text=True, capture_output=True)
    assert result.returncode != 0
