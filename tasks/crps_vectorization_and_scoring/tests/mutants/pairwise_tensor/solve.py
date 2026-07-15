#!/usr/bin/env python3
"""Intentional O(M^2) CRPS mutant using a pairwise sample tensor."""
from pathlib import Path

_MUTANT = r'''from __future__ import annotations
import numpy as np

def _weights(w, n):
    if w is None:
        return np.ones(n, dtype=float)
    w = np.asarray(w, dtype=float).reshape(-1)
    if w.size != n or np.any(w < 0) or not np.any(w > 0):
        raise ValueError("invalid weights")
    return w

def gaussian_crps(mu, sigma, y, sample_weight=None):
    mu, sigma, y = np.broadcast_arrays(np.asarray(mu, float), np.asarray(sigma, float), np.asarray(y, float))
    if np.any(sigma < 0) or not np.isfinite(mu).all() or not np.isfinite(sigma).all() or not np.isfinite(y).all():
        raise ValueError("invalid inputs")
    from scipy.special import ndtr
    sigma = np.maximum(sigma, 1e-12)
    z = (y - mu) / sigma
    value = sigma * (z * (2 * ndtr(z) - 1) + 2 * np.exp(-z*z/2) / np.sqrt(2*np.pi) - 1/np.sqrt(np.pi))
    w = _weights(sample_weight, value.size).reshape(value.shape)
    return float(np.sum(w * value) / np.sum(w))

def empirical_crps(samples, y, sample_weight=None):
    x = np.asarray(samples, dtype=float)
    y = np.asarray(y, dtype=float).reshape(-1)
    if x.ndim != 2 or x.shape[1] != y.size:
        raise ValueError("expected members x observations")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("invalid inputs")
    pairwise = np.abs(x[:, None, :] - x[None, :, :])
    pointwise = np.mean(np.abs(x - y[None, :]), axis=0) - 0.5 * np.mean(pairwise, axis=(0, 1))
    w = _weights(sample_weight, y.size)
    return float(np.sum(w * pointwise) / np.sum(w))
'''
Path("scoring.py").write_text(_MUTANT, encoding="utf-8")
