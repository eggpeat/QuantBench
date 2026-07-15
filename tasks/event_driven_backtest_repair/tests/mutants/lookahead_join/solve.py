#!/usr/bin/env python3
"""Intentional mutant: joins each bar to a signal from the future."""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    source = r'''from __future__ import annotations
import csv, json, math
from datetime import datetime, timezone
from pathlib import Path

def _ts(value):
    if value.endswith("Z"): value=value[:-1]+"+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)

def run_backtest(prices_path, signals_path, actions_path, output_dir, *, config_path=None, config=None, seed=100):
    cfg={"initial_cash":100000.0,"commission_bps":5.0,"slippage_bps":0.0,"max_participation":0.1,"allow_short":False}
    if config_path:
        cfg.update(json.loads(Path(config_path).read_text()))
    if config: cfg.update(config)
    with open(prices_path,newline="",encoding="utf-8") as h: prices=list(csv.DictReader(h))
    with open(signals_path,newline="",encoding="utf-8") as h: signals=list(csv.DictReader(h))
    prices.sort(key=lambda r:(_ts(r["timestamp"]),r["asset"]))
    signals.sort(key=lambda r:(_ts(r["timestamp"]),r["asset"]))
    # BUG: selects the first signal at or after the current bar (lookahead).
    cash=float(cfg["initial_cash"]); positions={}; trades=[]; equity=[]; gross=fees=0.0
    for row in prices:
        now=_ts(row["timestamp"]); future=next((s for s in signals if s["asset"]==row["asset"] and _ts(s["timestamp"])>=now),None)
        if future is not None:
            target=float(future["target_position"]); current=positions.get(row["asset"],0.0); delta=target-current; cap=math.floor(float(row["volume"])*float(cfg["max_participation"]))
            if cap and abs(delta)>1e-12:
                q=math.copysign(min(abs(delta),cap),delta); slip=float(cfg["slippage_bps"])/10000; price=float(row["open"])*(1+slip if q>0 else 1-slip); g=abs(q*price); f=g*float(cfg["commission_bps"])/10000; cash-=q*price+f; positions[row["asset"]]=current+q; gross+=g; fees+=f
                trades.append({"timestamp":now.isoformat().replace("+00:00","Z"),"asset":row["asset"],"side":"buy" if q>0 else "sell","quantity":abs(q),"price":price,"gross_value":g,"fees":f,"cash_after":cash})
        value=sum(q*float(r["close"]) for a,q in positions.items() for r in [row] if a==r["asset"]); equity.append({"timestamp":now.isoformat().replace("+00:00","Z"),"cash":cash,"positions_value":value,"equity":cash+value})
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    fields=["timestamp","asset","side","quantity","price","gross_value","fees","cash_after"]
    with (out/"trades.csv").open("w",newline="",encoding="utf-8") as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(trades)
    fields=["timestamp","cash","positions_value","equity"]
    with (out/"equity.csv").open("w",newline="",encoding="utf-8") as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(equity)
    mean=sum(r["equity"] for r in equity)/len(equity) if equity else 1
    metrics={"total_return":(equity[-1]["equity"]/float(cfg["initial_cash"])-1) if equity else 0,"max_drawdown":0.0,"turnover":gross/mean,"total_fees":fees,"n_trades":len(trades)}
    (out/"metrics.json").write_text(json.dumps(metrics,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return metrics
'''
    (workspace / "backtester.py").write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
