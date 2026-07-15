#!/usr/bin/env python3
"""Intentional mutant: silently discards all observation weights."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import gammaln, ive, log_ndtr, logsumexp

_FAMILIES = {"probit", "logit", "poisson", "skellam"}


def fit_temporal_states(times: Any, outcomes: Any, weights: Any, *, likelihood: str,
                        process_var: float, initial_mean: float = 0.0,
                        initial_var: float = 1.0, quadrature_order: int = 20) -> dict[str, Any]:
    t = np.asarray(times, dtype=float).reshape(-1)
    y = np.asarray(outcomes, dtype=float).reshape(-1)
    w = np.asarray(weights, dtype=float).reshape(-1)
    if t.size == 0 or t.size != y.size or t.size != w.size or not np.all(np.isfinite(np.r_[t, y, w])):
        raise ValueError("invalid inputs")
    family = likelihood.lower() if isinstance(likelihood, str) else ""
    if family not in _FAMILIES or np.any(w <= 0) or process_var <= 0 or initial_var <= 0:
        raise ValueError("invalid likelihood or parameters")
    if family in {"probit", "logit"} and np.any(~np.isin(y, [-1.0, 1.0])):
        raise ValueError("binary outcomes must be -1 or +1")
    if family == "poisson" and (np.any(y < 0) or np.any(y != np.floor(y))):
        raise ValueError("invalid Poisson outcome")
    if family == "skellam" and np.any(y != np.floor(y)):
        raise ValueError("invalid Skellam outcome")
    # MUTATION: every observation has unit power regardless of its supplied weight.
    w = np.ones_like(w)
    idx = np.argsort(t, kind="mergesort")
    t, y, w = t[idx], y[idx], w[idx]
    starts = np.r_[0, np.flatnonzero(np.diff(t) > 0) + 1]
    ends = np.r_[starts[1:], t.size]
    ut = t[starts]
    nodes, qw = np.polynomial.hermite.hermgauss(int(quadrature_order))
    qw /= math.sqrt(math.pi)
    fm = np.empty(ut.size); fv = np.empty(ut.size); pm = np.empty(ut.size); pv = np.empty(ut.size); logs = np.empty(ut.size)
    taus = np.zeros(t.size); etas = np.zeros(t.size)
    prev_m, prev_v = float(initial_mean), float(initial_var)
    for s, (a, b) in enumerate(zip(starts, ends)):
        dt = 0 if s == 0 else ut[s] - ut[s - 1]
        base_m, base_v = prev_m, prev_v + float(process_var) * dt
        pm[s], pv[s] = base_m, base_v
        bp, bn = 1 / base_v, base_m / base_v
        rt = re = total = 0.0
        for j in range(a, b):
            cp = bp + rt - taus[j]; cn = bn + re - etas[j]
            if cp <= 0 or not np.isfinite(cp): cp, cn = max(bp, 1e-12), bn
            cv, cm = 1 / cp, cn / cp
            x = cm + math.sqrt(2 * cv) * nodes
            if family == "probit": obs_ll = log_ndtr(y[j] * x)
            elif family == "logit": obs_ll = -np.logaddexp(0, -y[j] * x)
            elif family == "poisson": obs_ll = y[j] * x - np.exp(np.clip(x, -50, 50)) - gammaln(y[j] + 1)
            else:
                rs = np.exp(np.clip(x, -50, 50)) + np.exp(np.clip(-x, -50, 50))
                obs_ll = -rs + y[j] * x + math.log(float(ive(abs(int(y[j])), 2))) + 2
            terms = np.log(qw) + obs_ll
            lz = float(logsumexp(terms)); p = np.exp(terms - lz)
            tm = float(np.dot(p, x)); tv = max(float(np.dot(p, (x - tm) ** 2)), 1e-12)
            tau, eta = 1 / tv - cp, tm / tv - cm * cp
            rt += tau - taus[j]; re += eta - etas[j]; taus[j], etas[j] = tau, eta; total += lz
        pp = bp + rt
        prev_m, prev_v = (bn + re) / pp, max(1 / pp, 1e-12)
        fm[s], fv[s], logs[s] = prev_m, prev_v, total
    sm, sv = fm.copy(), fv.copy()
    for s in range(ut.size - 2, -1, -1):
        g = fv[s] / pv[s + 1]
        sm[s] = fm[s] + g * (sm[s + 1] - pm[s + 1]); sv[s] = max(fv[s] + g * g * (sv[s + 1] - pv[s + 1]), 1e-12)
    return {"times": ut, "filtered_mean": fm, "filtered_var": fv,
            "smoothed_mean": sm, "smoothed_var": sv, "log_likelihood": logs}


if __name__ == "__main__":
    # Mutant protocol: materialize the candidate module in the current workspace.
    Path("temporal_ep.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
