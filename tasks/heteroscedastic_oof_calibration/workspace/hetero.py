"""Starter module for leakage-safe out-of-fold calibration.

Implement the public functions described in instruction.md.
"""


def make_oof_predictions(estimator_factory, X, y, *, n_splits=5, groups=None,
                         times=None, sample_weight=None, random_state=0):
    raise NotImplementedError("implement make_oof_predictions")


def fit_variance_scale(y, mu, var_raw, *, sample_weight=None, eps=1e-12):
    raise NotImplementedError("implement fit_variance_scale")
