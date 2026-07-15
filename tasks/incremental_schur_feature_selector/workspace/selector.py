"""Starter module for the incremental Schur feature selector task."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def greedy_select(correlation, target_correlation, k, *, ridge=1e-8) -> list[int]:
    """Return ``k`` feature indices using incremental Schur updates."""
    raise NotImplementedError("implement greedy_select")


def _cli(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("selector_input.npz"))
    parser.add_argument("--output", type=Path, default=Path("outputs/selection.json"))
    parser.parse_args(argv)
    raise NotImplementedError("implement selector CLI")


if __name__ == "__main__":
    _cli()
