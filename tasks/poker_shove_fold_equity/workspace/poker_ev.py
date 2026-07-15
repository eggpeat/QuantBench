"""Poker shove/fold EV helpers.

Implement these functions using the formula in instruction.md.
"""


def called_ev(pot, risk, call, equity):
    """Return EV when villain calls the shove."""
    raise NotImplementedError("called_ev must be implemented")


def shove_ev(pot, risk, call, equity, fold_probability):
    """Return total shove EV including fold equity."""
    raise NotImplementedError("shove_ev must be implemented")


def breakeven_fold_equity(pot, risk, call, equity):
    """Return fold probability needed for zero shove EV."""
    raise NotImplementedError("breakeven_fold_equity must be implemented")


def evaluate_spot(spot):
    """Return the output record for one spot."""
    raise NotImplementedError("evaluate_spot must be implemented")


def evaluate_spots(payload):
    """Return {'spots': [...]} for a loaded spots.json payload."""
    raise NotImplementedError("evaluate_spots must be implemented")
