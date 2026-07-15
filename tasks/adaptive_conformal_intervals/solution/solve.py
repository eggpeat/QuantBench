#!/usr/bin/env python3
"""General oracle: materialize the conformal API and deterministic CLI."""
from pathlib import Path
import sys

CONFORMAL = r'''"""Finite-sample split conformal utilities."""
from __future__ import annotations
import math
from typing import Any
import numpy as np


def _numeric_array(value, name, *, ndim=None):
    try:
        a = np.asarray(value)
    except Exception as exc:
        raise ValueError(f"{name} is not array-like") from exc
    if a.dtype.kind in "bOUSV":
        raise ValueError(f"{name} must have a numeric, non-object dtype")
    if ndim is not None and a.ndim != ndim:
        raise ValueError(f"{name} must be {ndim}-dimensional")
    try:
        a = a.astype(float, copy=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not np.isfinite(a).all():
        raise ValueError(f"{name} must be finite")
    return a


def _labels(value, n, name):
    a = np.asarray(value, dtype=object)
    if a.ndim != 1 or len(a) != n:
        raise ValueError(f"{name} must have length n_samples")
    for x in a:
        try:
            hash(x)
        except Exception as exc:
            raise ValueError(f"{name} labels must be hashable") from exc
        if isinstance(x, (float, np.floating)) and not np.isfinite(x):
            raise ValueError(f"{name} labels must be finite")
    return a


def calibration_split(n_samples: int, *, groups=None, times=None,
                      calibration_fraction: float = 0.2,
                      random_state: int = 0):
    if isinstance(n_samples, bool) or not isinstance(n_samples, (int, np.integer)) or n_samples <= 1:
        raise ValueError("n_samples must be an integer greater than one")
    try:
        fraction = float(calibration_fraction)
    except (TypeError, ValueError) as exc:
        raise ValueError("calibration_fraction must be finite") from exc
    if not np.isfinite(fraction) or not 0.0 < fraction < 1.0:
        raise ValueError("calibration_fraction must lie strictly between zero and one")
    if groups is not None and times is not None:
        raise ValueError("groups and times are mutually exclusive")
    target = int(math.ceil(n_samples * fraction))
    if target <= 0 or target >= n_samples:
        raise ValueError("calibration split must leave non-empty partitions")
    try:
        rng = np.random.default_rng(random_state)
    except (TypeError, ValueError) as exc:
        raise ValueError("random_state must be a valid seed") from exc
    if groups is None and times is None:
        perm = rng.permutation(n_samples)
        return perm[target:].astype(np.int64), perm[:target].astype(np.int64)
    if groups is not None:
        labels = _labels(groups, n_samples, "groups")
        unique = []
        seen = set()
        for x in labels.tolist():
            if x not in seen:
                seen.add(x)
                unique.append(x)
        if len(unique) < 2:
            raise ValueError("groups must contain at least two groups")
        order = rng.permutation(len(unique))
        chosen = set()
        count = 0
        for pos in order:
            chosen.add(unique[int(pos)])
            count += int(np.sum(labels == unique[int(pos)]))
            if count >= target:
                break
        cal = np.array([i for i, x in enumerate(labels.tolist()) if x in chosen], dtype=np.int64)
        train = np.array([i for i, x in enumerate(labels.tolist()) if x not in chosen], dtype=np.int64)
        if len(train) == 0 or len(cal) == 0:
            raise ValueError("group split must leave non-empty partitions")
        return train, cal
    t = np.asarray(times)
    if t.ndim != 1 or len(t) != n_samples:
        raise ValueError("times must have length n_samples")
    if t.dtype.kind in "bOUSV":
        raise ValueError("times must have an ordered numeric or datetime dtype")
    if t.dtype.kind == "M":
        if np.isnat(t).any():
            raise ValueError("times must not contain NaT")
    elif t.dtype.kind in "if":
        if not np.isfinite(t.astype(float)).all():
            raise ValueError("times must be finite")
    try:
        order = np.argsort(t, kind="stable")
    except Exception as exc:
        raise ValueError("times must be stably sortable") from exc
    return order[:-target].astype(np.int64), order[-target:].astype(np.int64)


def conformal_quantile(scores, alpha: float, sample_weight=None) -> float:
    s = _numeric_array(scores, "scores", ndim=1)
    n = len(s)
    if n == 0:
        raise ValueError("scores must be non-empty")
    try:
        a = float(alpha)
    except (TypeError, ValueError) as exc:
        raise ValueError("alpha must be finite") from exc
    if not np.isfinite(a) or not 0.0 < a < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    if sample_weight is None:
        rank = min(int(math.ceil((n + 1) * (1.0 - a))), n)
        return float(np.sort(s)[rank - 1])
    w = _numeric_array(sample_weight, "sample_weight", ndim=1)
    if len(w) != n or np.any(w < 0):
        raise ValueError("sample_weight must be non-negative and match scores")
    total = float(np.sum(w))
    if not np.isfinite(total) or total <= 0:
        raise ValueError("sample_weight must have positive finite sum")
    idx = np.argsort(s, kind="stable")
    ss, ww = s[idx], w[idx]
    level = min((1.0 - a) * (1.0 + 1.0 / total), 1.0)
    pos = int(np.searchsorted(np.cumsum(ww), level * total, side="left"))
    return float(ss[min(pos, n - 1)])


def normalized_intervals(mu, scale, q, *, scale_floor: float = 1e-12):
    try:
        floor = float(scale_floor)
    except (TypeError, ValueError) as exc:
        raise ValueError("scale_floor must be finite and positive") from exc
    if not np.isfinite(floor) or floor <= 0:
        raise ValueError("scale_floor must be finite and positive")
    m = _numeric_array(mu, "mu")
    s = _numeric_array(scale, "scale")
    qq = _numeric_array(q, "q")
    if np.any(qq < 0):
        raise ValueError("q must be non-negative")
    try:
        m, s, qq = np.broadcast_arrays(m, s, qq)
    except ValueError as exc:
        raise ValueError("mu, scale and q are not broadcast-compatible") from exc
    effective = np.maximum(s, floor)
    return np.array(m - qq * effective, copy=True), np.array(m + qq * effective, copy=True)
'''

RUN_TASK = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
import conformal

def main(root):
    root = Path(root)
    f = json.loads((root / "fixture.json").read_text())
    train, cal = conformal.calibration_split(
        f["n_samples"], groups=f.get("groups"), times=None,
        calibration_fraction=f["calibration_fraction"], random_state=f["random_state"])
    q = conformal.conformal_quantile(f["scores"], f["alpha"])
    lo, hi = conformal.normalized_intervals(f["mu"], f["scale"], f["q"])
    out = {"train_indices": train.tolist(), "calibration_indices": cal.tolist(),
           "quantile": q, "lower": lo.tolist(), "upper": hi.tolist()}
    (root / "outputs").mkdir(exist_ok=True)
    (root / "outputs" / "conformal.json").write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
'''

def main(workspace):
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    (root / "conformal.py").write_text(CONFORMAL)
    (root / "run_task.py").write_text(RUN_TASK)
    import os
    os.chmod(root / "run_task.py", 0o755)
    sys.path.insert(0, str(root))
    ns = {"__file__": str(root / "run_task.py"), "__name__": "oracle_run_task"}
    exec(compile(RUN_TASK, str(root / "run_task.py"), "exec"), ns)
    ns["main"](root)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
