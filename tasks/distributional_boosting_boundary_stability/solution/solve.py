#!/usr/bin/env python3
"""General oracle for stable negative-binomial natural gradients."""
from __future__ import annotations

from pathlib import Path

SOURCE = r'''"""Numerically stable negative-binomial gradient and diagonal hessian."""
from __future__ import annotations

import numpy as np
from scipy.special import digamma, expit

MIN_EXPONENT = float(np.log(np.float32(1e-32)))
MAX_EXPONENT = float(np.log(np.finfo("float32").max) - 1.0)
DIAG_FLOOR = np.float32(1e-30)


def gradient_and_hessian(y, log_n, logit_p, *, natural_gradient=True):
    """Return float32 natural gradients and the constant boosting hessian."""
    if not natural_gradient:
        raise NotImplementedError("standard gradients are not supported; use natural_gradient=True")
    yy = np.asarray(y, dtype=np.float64)
    aa = np.asarray(log_n, dtype=np.float64)
    bb = np.asarray(logit_p, dtype=np.float64)
    if yy.ndim != 1 or aa.ndim != 1 or bb.ndim != 1 or not (yy.shape == aa.shape == bb.shape):
        raise ValueError("y, log_n, and logit_p must be matching one-dimensional arrays")
    if yy.size == 0 or not (np.all(np.isfinite(yy)) and np.all(np.isfinite(aa)) and np.all(np.isfinite(bb))):
        raise ValueError("inputs must be nonempty and finite")
    if np.any(yy < 0) or np.any(yy != np.floor(yy)):
        raise ValueError("y must contain nonnegative integer counts")
    aa = np.clip(aa, MIN_EXPONENT, MAX_EXPONENT)
    bb = np.clip(bb, MIN_EXPONENT, MAX_EXPONENT)
    n = np.exp(aa)
    p = expit(bb)
    # Keep all score and information arithmetic in float64.  In particular,
    # the second score avoids an intermediate division by p at p ~= 0.
    raw_n = -n * (digamma(yy + n) - digamma(n) + np.log(p))
    raw_p = p * yy - n * (1.0 - p)
    fisher_n = np.maximum(np.asarray((n * p) / (p + 1.0), dtype=np.float32), DIAG_FLOOR).astype(np.float64)
    fisher_p = np.maximum(np.asarray(n * (1.0 - p), dtype=np.float32), DIAG_FLOOR).astype(np.float64)
    grad = np.column_stack([raw_n / fisher_n, raw_p / fisher_p]).astype(np.float32)
    hess = np.ones((yy.size, 2), dtype=np.float32)
    if not np.all(np.isfinite(grad)):
        raise FloatingPointError("natural gradient became non-finite")
    return grad, hess
'''


def main() -> None:
    Path("negative_binomial.py").write_text(SOURCE, encoding="utf-8")
    runner = Path("run_negative_binomial.py")
    if runner.exists():
        import subprocess, sys
        subprocess.run([sys.executable, str(runner)], check=True)


if __name__ == "__main__":
    main()
