#!/usr/bin/env python3
"""Run the public mixed-type linear residual fixture."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import linear_residual


def main() -> None:
    root = Path(__file__).resolve().parent
    data = json.loads((root / "input.json").read_text(encoding="utf-8"))
    estimator = linear_residual.LinearResidualRegressor(
        alpha=data["alpha"],
        max_depth=data["max_depth"],
        min_samples_leaf=data["min_samples_leaf"],
        random_state=data["seed"],
    )
    X = np.asarray(data["X"], dtype=object)
    y = np.asarray(data["y"], dtype=np.float64)
    w = np.asarray(data["sample_weight"], dtype=np.float64)
    estimator.fit(X, y, sample_weight=w)
    prediction = estimator.predict(X)
    roundtrip = root / "outputs" / "fixture_model.npz"
    roundtrip.parent.mkdir(parents=True, exist_ok=True)
    estimator.save_model(roundtrip)
    loaded = linear_residual.LinearResidualRegressor.load_model(roundtrip)
    report = {
        "seed": data["seed"],
        "n_rows": int(len(y)),
        "predictions": prediction.tolist(),
        "trend_active": bool(estimator.linear_residual_active_),
        "max_reload_error": float(np.max(np.abs(prediction - loaded.predict(X)))),
    }
    (root / "outputs" / "linear_residual.json").write_text(
        json.dumps(report, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
