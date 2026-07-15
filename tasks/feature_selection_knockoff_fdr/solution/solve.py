#!/usr/bin/env python3
"""General oracle: materialize Gaussian-copula knockoff selection and CLI."""
from pathlib import Path
import sys

KNOCKOFFS = r'''"""Deterministic Gaussian-copula Model-X knockoffs."""
from dataclasses import dataclass
from typing import Sequence
import numpy as np
from scipy.special import ndtr, ndtri


@dataclass
class SelectionResult:
    selected_indices: list[int]
    selection_frequency: np.ndarray
    draw_thresholds: np.ndarray
    group_selected: list[object]


def _as_finite_X(X):
    try:
        a = np.asarray(X)
    except Exception as exc:
        raise ValueError("X must be numeric array-like") from exc
    if a.ndim != 2 or a.shape[0] < 2 or a.shape[1] < 1 or a.dtype.kind in "bOUSV":
        raise ValueError("X must be a finite numeric matrix with at least two rows")
    try:
        a = a.astype(float, copy=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("X must be numeric") from exc
    if not np.isfinite(a).all():
        raise ValueError("X must be finite")
    return a


def _as_finite_y(y, n):
    try:
        a = np.asarray(y)
    except Exception as exc:
        raise ValueError("y must be numeric array-like") from exc
    if a.ndim != 1 or len(a) != n or a.dtype.kind in "bOUSV":
        raise ValueError("y must be a numeric vector matching X rows")
    try:
        a = a.astype(float, copy=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("y must be numeric") from exc
    if not np.isfinite(a).all():
        raise ValueError("y must be finite")
    return a


def _rank_normalize(x):
    n, p = x.shape
    z = np.empty((n, p), dtype=float)
    eps = 0.5 / n
    for j in range(p):
        order = np.argsort(x[:, j], kind="stable")
        vals = x[order, j]
        ranks = np.empty(n, dtype=float)
        i = 0
        while i < n:
            k = i + 1
            while k < n and vals[k] == vals[i]:
                k += 1
            ranks[i:k] = 0.5 * (i + 1 + k)
            i = k
        u = np.clip((ranks - 0.5) / n, eps, 1.0 - eps)
        z[order, j] = ndtri(u)
    return z


def _correlation(z):
    n, p = z.shape
    centered = z - np.mean(z, axis=0)
    norm = np.sqrt(np.sum(centered * centered, axis=0))
    out = np.zeros((p, p), dtype=float)
    nonconstant = norm > 0
    if np.any(nonconstant):
        q = centered[:, nonconstant] / norm[nonconstant]
        out[np.ix_(nonconstant, nonconstant)] = q.T @ q
    np.fill_diagonal(out, 1.0)
    return (out + out.T) * 0.5


def _groups(labels, p):
    if labels is None:
        return None, None
    try:
        a = np.asarray(labels, dtype=object)
    except Exception as exc:
        raise ValueError("feature_groups must be a one-dimensional sequence") from exc
    if a.ndim != 1 or len(a) != p:
        raise ValueError("feature_groups must have one label per feature")
    unique, index = [], {}
    for j, label in enumerate(a.tolist()):
        try:
            hash(label)
        except Exception as exc:
            raise ValueError("feature group labels must be hashable") from exc
        if isinstance(label, (float, np.floating)) and not np.isfinite(label):
            raise ValueError("feature group labels must be finite")
        if label not in index:
            index[label] = len(unique)
            unique.append(label)
    membership = np.array([index[x] for x in a.tolist()], dtype=np.int64)
    return unique, membership


def _pearson(x, y):
    xc = x - np.mean(x)
    yc = y - np.mean(y)
    den = float(np.sqrt(np.dot(xc, xc) * np.dot(yc, yc)))
    return 0.0 if den == 0.0 else float(np.dot(xc, yc) / den)


def _inverse_empirical(ztilde, x):
    n, p = x.shape
    u = np.clip(ndtr(ztilde), 0.5 / n, 1.0 - 0.5 / n)
    grid = (np.arange(n, dtype=float) + 0.5) / n
    out = np.empty_like(ztilde)
    for j in range(p):
        vals = np.sort(x[:, j], kind="stable")
        if vals[0] == vals[-1]:
            out[:, j] = vals[0]
        else:
            out[:, j] = np.interp(u[:, j], grid, vals)
    return out


def _threshold(stat, q):
    candidates = np.unique(stat[stat > 0])
    candidates.sort()
    for t in candidates:
        numer = 1.0 + float(np.count_nonzero(stat <= -t))
        denom = max(int(np.count_nonzero(stat >= t)), 1)
        if numer / denom <= q:
            return float(t)
    return float("inf")


def select_fdr(X, y, *, q=0.1, n_draws=10, random_state=0,
               feature_groups: Sequence[object] | None = None) -> SelectionResult:
    x = _as_finite_X(X)
    yy = _as_finite_y(y, x.shape[0])
    try:
        qq = float(q)
    except (TypeError, ValueError) as exc:
        raise ValueError("q must lie strictly between zero and one") from exc
    if not np.isfinite(qq) or not 0.0 < qq < 1.0:
        raise ValueError("q must lie strictly between zero and one")
    if isinstance(n_draws, bool) or not isinstance(n_draws, (int, np.integer)) or n_draws <= 0:
        raise ValueError("n_draws must be a positive integer")
    unique, membership = _groups(feature_groups, x.shape[1])
    z = _rank_normalize(x)
    R = _correlation(z)
    vals, vecs = np.linalg.eigh((R + R.T) * 0.5)
    vals = np.maximum(vals, 1e-3)
    R = (vecs * vals) @ vecs.T
    R = (R + R.T) * 0.5
    lam = float(np.min(np.linalg.eigvalsh(R)))
    s = min(2.0 * lam, 1.0)
    p = x.shape[1]
    S = s * np.eye(p)
    rinv = np.linalg.inv(R)
    A = np.eye(p) - rinv @ S
    C = 2.0 * S - S @ rinv @ S
    cvals, cvecs = np.linalg.eigh((C + C.T) * 0.5)
    L = (cvecs * np.sqrt(np.maximum(cvals, 0.0))) @ cvecs.T
    try:
        rng = np.random.default_rng(random_state)
    except (TypeError, ValueError) as exc:
        raise ValueError("random_state must be a valid seed") from exc
    frequencies = np.zeros(p, dtype=float)
    thresholds = np.full(int(n_draws), np.inf, dtype=float)
    for draw in range(int(n_draws)):
        noise = rng.standard_normal((x.shape[0], p))
        ztilde = z @ A.T + noise @ L.T
        xtilde = _inverse_empirical(ztilde, x)
        stat = np.array([abs(_pearson(x[:, j], yy)) - abs(_pearson(xtilde[:, j], yy)) for j in range(p)])
        if membership is None:
            t = _threshold(stat, qq)
            if np.isfinite(t):
                selected = stat >= t
                thresholds[draw] = t
            else:
                selected = np.zeros(p, dtype=bool)
        else:
            grouped = np.full(len(unique), -np.inf, dtype=float)
            for g in range(len(unique)):
                grouped[g] = np.max(stat[membership == g])
            t = _threshold(grouped, qq)
            if np.isfinite(t):
                selected_group = grouped >= t
                selected = selected_group[membership]
                thresholds[draw] = t
            else:
                selected = np.zeros(p, dtype=bool)
        frequencies += selected
    frequencies /= float(n_draws)
    selected_indices = np.flatnonzero(frequencies >= 0.5).astype(int).tolist()
    group_selected = []
    if unique is not None:
        chosen = {int(membership[j]) for j in selected_indices}
        group_selected = [unique[g] for g in range(len(unique)) if g in chosen]
    return SelectionResult(selected_indices, frequencies, thresholds, group_selected)
'''

RUN_TASK = r'''#!/usr/bin/env python3
import json, sys
from pathlib import Path
import knockoffs

def main(root):
    root = Path(root)
    f = json.loads((root / "fixture.json").read_text())
    result = knockoffs.select_fdr(f["X"], f["y"], q=f["q"], n_draws=f["n_draws"],
                                  random_state=f["random_state"], feature_groups=f.get("feature_groups"))
    out = {"selected_indices": result.selected_indices,
           "selection_frequency": result.selection_frequency.tolist(),
           "draw_thresholds": result.draw_thresholds.tolist(),
           "group_selected": result.group_selected}
    (root / "outputs").mkdir(exist_ok=True)
    (root / "outputs" / "knockoffs.json").write_text(json.dumps(out, sort_keys=True, indent=2) + "\n")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
'''

def main(workspace):
    root = Path(workspace)
    root.mkdir(parents=True, exist_ok=True)
    (root / "knockoffs.py").write_text(KNOCKOFFS)
    (root / "run_task.py").write_text(RUN_TASK)
    import os
    os.chmod(root / "run_task.py", 0o755)
    sys.path.insert(0, str(root))
    ns = {"__file__": str(root / "run_task.py"), "__name__": "oracle_run_task"}
    exec(compile(RUN_TASK, str(root / "run_task.py"), "exec"), ns)
    ns["main"](root)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
