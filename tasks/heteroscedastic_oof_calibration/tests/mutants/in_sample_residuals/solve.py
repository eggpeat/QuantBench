#!/usr/bin/env python3
"""Intentional mutant: calibrates residuals from a model fit on every row."""
from pathlib import Path

SOURCE = '''import numpy as np

def make_oof_predictions(estimator_factory, X, y, *, n_splits=5, groups=None, times=None, sample_weight=None, random_state=0):
    if groups is not None and times is not None:
        raise ValueError("groups and times are mutually exclusive")
    yy = np.asarray(y, dtype=float)
    if yy.ndim != 1 or len(X) != yy.size:
        raise ValueError("bad input")
    model = estimator_factory()
    kwargs = {} if sample_weight is None else {"sample_weight": np.asarray(sample_weight, dtype=float)}
    model.fit(X, yy, **kwargs)
    return np.asarray(model.predict(X), dtype=float)

def fit_variance_scale(y, mu, var_raw, *, sample_weight=None, eps=1e-12):
    yy, mm, vv = (np.asarray(a, dtype=float) for a in (y, mu, var_raw))
    if yy.ndim != 1 or yy.shape != mm.shape or yy.shape != vv.shape:
        raise ValueError("bad shape")
    ratio = (yy - mm) ** 2 / np.maximum(vv, eps)
    return float(np.average(ratio, weights=sample_weight)) if sample_weight is not None else float(np.mean(ratio))
'''

def main():
    Path("hetero.py").write_text(SOURCE, encoding="utf-8")
    import subprocess, sys
    if Path("run_calibration.py").exists():
        subprocess.run([sys.executable, "run_calibration.py"], check=True)

if __name__ == "__main__":
    main()
