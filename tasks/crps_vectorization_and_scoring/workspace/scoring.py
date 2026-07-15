"""Distributional scoring exercise.

Implement Gaussian and empirical continuous ranked probability scores with
broadcasting, validation, and observation weights.
"""
from __future__ import annotations

import numpy as np


def gaussian_crps(mu, sigma, y, sample_weight=None) -> float:
    raise NotImplementedError("implement gaussian_crps")


def empirical_crps(samples, y, sample_weight=None) -> float:
    raise NotImplementedError("implement empirical_crps")
