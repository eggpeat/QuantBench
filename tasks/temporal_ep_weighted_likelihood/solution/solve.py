"""Reference solution for the temporal EP benchmark."""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import gammaln, ive, log_ndtr, logsumexp

_LIKELIHOODS = {"probit", "logit", "poisson", "skellam"}


def _as_vector(value: Any, name: str) -> np.ndarray:
    try:
        arr = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if arr.ndim != 1 or arr.size == 0 or not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be a finite nonempty one-dimensional array")
    return arr


def _log_likelihood(x: np.ndarray, y: float, family: str) -> np.ndarray:
    if family == "probit":
        return log_ndtr(y * x)
    if family == "logit":
        return -np.logaddexp(0.0, -y * x)
    if family == "poisson":
        return y * x - np.exp(np.clip(x, -50.0, 50.0)) - gammaln(y + 1.0)
    rate_sum = np.exp(np.clip(x, -50.0, 50.0)) + np.exp(np.clip(-x, -50.0, 50.0))
    bessel_scaled = ive(abs(int(y)), 2.0)
    if not np.isfinite(bessel_scaled) or bessel_scaled <= 0.0:
        raise ValueError("Skellam normalizer is not representable")
    return -rate_sum + y * x + math.log(float(bessel_scaled)) + 2.0


def _validate_outcomes(y: np.ndarray, family: str) -> None:
    if family in {"probit", "logit"} and np.any((y != -1.0) & (y != 1.0)):
        raise ValueError("binary outcomes must be -1 or +1")
    if family == "poisson" and (np.any(y < 0.0) or np.any(y != np.floor(y))):
        raise ValueError("Poisson outcomes must be nonnegative integers")
    if family == "skellam" and np.any(y != np.floor(y)):
        raise ValueError("Skellam outcomes must be integers")


def fit_temporal_states(
    times: Any,
    outcomes: Any,
    weights: Any,
    *,
    likelihood: str,
    process_var: float,
    initial_mean: float = 0.0,
    initial_var: float = 1.0,
    quadrature_order: int = 20,
) -> dict[str, Any]:
    """Fit weighted scalar random-walk states using normalized GH EP."""
    t, y, w = _as_vector(times, "times"), _as_vector(outcomes, "outcomes"), _as_vector(weights, "weights")
    if t.size != y.size or t.size != w.size:
        raise ValueError("times, outcomes, and weights must have equal length")
    if not isinstance(likelihood, str) or likelihood.lower() not in _LIKELIHOODS:
        raise ValueError("unknown likelihood")
    family = likelihood.lower()
    _validate_outcomes(y, family)
    if np.any(w <= 0.0):
        raise ValueError("weights must be positive")
    q, m0, v0 = float(process_var), float(initial_mean), float(initial_var)
    if not (math.isfinite(q) and q > 0 and math.isfinite(m0) and math.isfinite(v0) and v0 > 0):
        raise ValueError("invalid process or initial variance")
    if isinstance(quadrature_order, bool) or int(quadrature_order) != quadrature_order or int(quadrature_order) <= 0:
        raise ValueError("quadrature_order must be a positive integer")
    nodes, qw = np.polynomial.hermite.hermgauss(int(quadrature_order))
    qw = qw / math.sqrt(math.pi)
    idx = np.argsort(t, kind="mergesort")
    st, sy, sw = t[idx], y[idx], w[idx]
    starts = np.r_[0, np.flatnonzero(np.diff(st) > 0) + 1]
    ends = np.r_[starts[1:], st.size]
    ut = st[starts]
    n = ut.size
    fm, fv, pm, pv, ll_out = (np.empty(n) for _ in range(5))
    taus, etas = np.zeros(st.size), np.zeros(st.size)
    prev_m, prev_v = m0, v0
    for state, (start, end) in enumerate(zip(starts, ends)):
        dt = 0.0 if state == 0 else float(ut[state] - ut[state - 1])
        if dt < 0 or not math.isfinite(dt):
            raise ValueError("times must not decrease")
        base_v, base_m = prev_v + q * dt, prev_m
        pm[state], pv[state] = base_m, base_v
        bp, bn = 1.0 / base_v, base_m / base_v
        rt, re, logz_total = 0.0, 0.0, 0.0
        for event in range(start, end):
            cp = bp + rt - taus[event]
            cn = bn + re - etas[event]
            if cp <= 0 or not math.isfinite(cp):
                cp, cn = max(bp, 1e-12), bn
            cv, cm = 1.0 / cp, cn / cp
            x = cm + math.sqrt(2.0 * cv) * nodes
            if family == "probit":
                obs_ll = log_ndtr(float(sy[event]) * x)
            elif family == "logit":
                obs_ll = -np.logaddexp(0.0, -float(sy[event]) * x)
            elif family == "poisson":
                obs_ll = float(sy[event]) * x - np.exp(np.clip(x, -50.0, 50.0)) - gammaln(float(sy[event]) + 1.0)
            else:
                rate_sum = np.exp(np.clip(x, -50.0, 50.0)) + np.exp(np.clip(-x, -50.0, 50.0))
                b = ive(abs(int(sy[event])), 2.0)
                obs_ll = -rate_sum + float(sy[event]) * x + math.log(float(b)) + 2.0
            zterms = np.log(qw) + float(sw[event]) * obs_ll
            logz = float(logsumexp(zterms))
            p = np.exp(zterms - logz)
            tm = float(np.dot(p, x))
            tv = max(float(np.dot(p, (x - tm) ** 2)), 1e-12)
            tau, eta = 1.0 / tv - cp, tm / tv - cm * cp
            rt += tau - taus[event]
            re += eta - etas[event]
            taus[event], etas[event] = tau, eta
            logz_total += logz
        pp = bp + rt
        if pp <= 0 or not math.isfinite(pp):
            raise ValueError("EP posterior precision is invalid")
        prev_m, prev_v = (bn + re) / pp, max(1.0 / pp, 1e-12)
        fm[state], fv[state], ll_out[state] = prev_m, prev_v, logz_total
    sm, sv = fm.copy(), fv.copy()
    for state in range(n - 2, -1, -1):
        gain = fv[state] / pv[state + 1]
        sm[state] = fm[state] + gain * (sm[state + 1] - pm[state + 1])
        sv[state] = max(fv[state] + gain * gain * (sv[state + 1] - pv[state + 1]), 1e-12)
    return {
        "times": ut,
        "filtered_mean": fm,
        "filtered_var": fv,
        "smoothed_mean": sm,
        "smoothed_var": sv,
        "log_likelihood": ll_out,
    }
if __name__ == "__main__":
    # Oracle protocol: materialize this reference module in the clean
    # workspace mounted by the verifier.
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    target.mkdir(parents=True, exist_ok=True)
    (target / "temporal_ep.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
