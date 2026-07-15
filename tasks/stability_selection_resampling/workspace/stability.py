"""Starter module for deterministic stability selection."""
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class StabilityResult:
    selected_indices: list[int]
    selected_features: list[str]
    frequencies: np.ndarray
    threshold: float
    n_resamples: int


def stability_select(
    X,
    y,
    *,
    k,
    n_resamples=100,
    sample_fraction=0.5,
    threshold=0.8,
    sample_weight=None,
    groups=None,
    times=None,
    feature_names: Sequence[str] | None = None,
    random_state=0,
    n_jobs=1,
) -> StabilityResult:
    """Implement local preprocessing and deterministic resampling."""
    raise NotImplementedError("implement stability_select")


def _cli(argv=None) -> None:
    raise NotImplementedError("implement stability CLI")


if __name__ == "__main__":
    _cli()
