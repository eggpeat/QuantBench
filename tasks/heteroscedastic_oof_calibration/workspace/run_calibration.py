#!/usr/bin/env python3
"""Run the deterministic public calibration example."""
from __future__ import annotations

import json
import math
from pathlib import Path
import numpy as np
import hetero


class WeightedLinear:
    def fit(self, X, y, sample_weight=None):
        x = np.asarray(X, dtype=float).reshape(len(y), -1)
        yy = np.asarray(y, dtype=float)
        z = np.column_stack([np.ones(len(x)), x])
        if sample_weight is None:
            ww = np.ones(len(x))
        else:
            ww = np.asarray(sample_weight, dtype=float)
        self.coef_ = np.linalg.lstsq(z * np.sqrt(ww)[:, None], yy * np.sqrt(ww), rcond=None)[0]
        return self

    def predict(self, X):
        x = np.asarray(X, dtype=float).reshape(len(X), -1)
        return np.column_stack([np.ones(len(x)), x]) @ self.coef_


def main() -> None:
    root = Path(__file__).resolve().parent
    with (root / "input.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    X = np.asarray(data["X"], dtype=float)
    y = np.asarray(data["y"], dtype=float)
    w = np.asarray(data["sample_weight"], dtype=float)
    mu = np.asarray(hetero.make_oof_predictions(lambda: WeightedLinear(), X, y, n_splits=6, sample_weight=w, random_state=100), dtype=float)
    mask = np.isfinite(mu)
    if not np.any(mask):
        raise ValueError("OOF procedure produced no calibration rows")
    # A deliberately misscaled but positive variance shape; the scalar fit repairs it.
    var_raw = 0.35 + 0.18 * X[:, 0] ** 2
    yy, mm, vv, ww = y[mask], mu[mask], var_raw[mask], w[mask]
    scale = float(hetero.fit_variance_scale(yy, mm, vv, sample_weight=ww))
    def nll(var):
        return float(np.average(0.5 * (np.log(2.0 * math.pi * var) + (yy - mm) ** 2 / var), weights=ww))
    payload = {
        "scale": scale,
        "nll_before": nll(vv),
        "nll_after": nll(scale * vv),
        "n_calibration_rows": int(mask.sum()),
    }
    out = root / "outputs" / "calibration.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
