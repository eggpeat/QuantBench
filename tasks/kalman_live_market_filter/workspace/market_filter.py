"""Kalman filtering for noisy market observations."""

from __future__ import annotations
import math

def kalman_step(
    mean: float,
    variance: float,
    measurement: float,
    process_variance: float,
    measurement_variance: float,
    outlier_z: float,
) -> tuple[float, float, bool]:
    """Perform one step of the Kalman filter, with outlier rejection.

    If variance, process_variance, measurement_variance, or outlier_z is negative,
    raise ValueError.
    """
    raise NotImplementedError("To be implemented")


def filter_series(config: dict, observations: list[dict]) -> dict:
    """Run the Kalman filter over a series of observations.

    Returns a dictionary of steps and final state.
    """
    raise NotImplementedError("To be implemented")
