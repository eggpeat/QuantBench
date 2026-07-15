#!/usr/bin/env python3
"""Intentional matrix-solve mutant: constructs one dense diagonal matrix per row."""
from pathlib import Path

_MUTANT = r'''from __future__ import annotations
import numpy as np

def precondition_diagonal(raw_grad, fisher_diag, *, floor=1e-30):
    g = np.asarray(raw_grad, dtype=np.float64)
    f = np.asarray(fisher_diag, dtype=np.float64)
    if f.ndim == 1 and g.ndim > 1:
        f = np.broadcast_to(f, g.shape)
    if g.shape != f.shape:
        raise ValueError("shape mismatch")
    eye = np.eye(g.shape[-1], dtype=np.float64)
    matrices = f[..., :, None] * eye
    # Deliberately slow and memory-hungry reference implementation.
    return np.linalg.solve(matrices, g[..., None])[..., 0]
'''

Path("fisher.py").write_text(_MUTANT, encoding="utf-8")
