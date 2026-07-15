#!/usr/bin/env python3
"""Run the public ODE fixture and write a JSON report."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import ode


def exponential(t: float, y: np.ndarray) -> np.ndarray:
    return -y


def damped_oscillator(t: float, y: np.ndarray) -> np.ndarray:
    return np.array([y[1], -4.0 * y[0] - 0.1 * y[1]], dtype=float)


def main() -> None:
    root = Path(__file__).resolve().parent
    data = json.loads((root / "input.json").read_text(encoding="utf-8"))
    report = {"seed": data["seed"], "results": []}
    for problem in data["problems"]:
        t_span = tuple(problem["t_span"])
        y0 = np.array(problem["y0"], dtype=float)
        events = None
        if "event_threshold" in problem:
            threshold = problem["event_threshold"]

            def make_event(th):
                def event(t, y):
                    return float(y[0] - th)

                event.terminal = True
                event.direction = -1
                return event

            events = [make_event(threshold)]
        result = ode.integrate_rk45(
            exponential if problem["name"] == "exponential_decay" else damped_oscillator,
            t_span,
            y0,
            rtol=problem["rtol"],
            atol=problem["atol"],
            max_step=problem.get("max_step", float("inf")),
            events=events,
        )
        entry = {
            "name": problem["name"],
            "status": result.status,
            "final_t": float(result.t[-1]),
            "final_y": result.y[:, -1].tolist(),
            "n_steps": result.n_steps,
            "n_rejected": result.n_rejected,
            "message": result.message,
        }
        if events:
            entry["t_events"] = [arr.tolist() for arr in result.t_events]
        report["results"].append(entry)

    output = root / "outputs" / "ode_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
