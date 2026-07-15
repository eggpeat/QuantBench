"""Oracle solution for the Kalman market filter task."""

from __future__ import annotations
import sys
from pathlib import Path

SOLVED_SOURCE = '''"""Kalman filtering for noisy market observations."""

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
    """Perform one step of the Kalman filter, with outlier rejection."""
    if variance < 0:
        raise ValueError("Variance cannot be negative")
    if process_variance < 0:
        raise ValueError("Process variance cannot be negative")
    if measurement_variance < 0:
        raise ValueError("Measurement variance cannot be negative")
    if outlier_z < 0:
        raise ValueError("Outlier Z-threshold cannot be negative")

    # Predict
    pred_mean = mean
    pred_variance = variance + process_variance

    # Outlier evaluation
    innovation_variance = pred_variance + measurement_variance
    if innovation_variance <= 0:
        raise ValueError("Innovation variance must be positive")

    std_innovation = math.sqrt(innovation_variance)
    threshold = outlier_z * std_innovation
    diff = abs(measurement - pred_mean)

    accepted = diff <= threshold
    if accepted:
        # Update step
        k = pred_variance / innovation_variance
        updated_mean = pred_mean + k * (measurement - pred_mean)
        updated_variance = (1.0 - k) * pred_variance
    else:
        # Reject: preserve predicted state
        updated_mean = pred_mean
        updated_variance = pred_variance

    return updated_mean, updated_variance, accepted


def filter_series(config: dict, observations: list[dict]) -> dict:
    """Run the Kalman filter over a series of observations."""
    mean = config["initial_mean"]
    variance = config["initial_variance"]
    process_variance = config["process_variance"]
    measurement_variance = config["measurement_variance"]
    outlier_z = config["outlier_z"]

    steps = []
    for obs in observations:
        t = obs["time"]
        val = obs["measurement"]
        mean, variance, accepted = kalman_step(
            mean, variance, val, process_variance, measurement_variance, outlier_z
        )
        steps.append({
            "time": t,
            "mean": mean,
            "variance": variance,
            "accepted": accepted
        })

    return {
        "steps": steps,
        "final_state": {
            "mean": mean,
            "variance": variance
        }
    }
'''

def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    (workspace / "market_filter.py").write_text(SOLVED_SOURCE, encoding="utf-8")

    # Run the filtering script
    sys.path.insert(0, str(workspace))
    import run_filter
    run_filter.main()

if __name__ == "__main__":
    main()
