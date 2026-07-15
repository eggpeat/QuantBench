"""Starter module for the linear residual boosting exercise."""
from __future__ import annotations


class LinearResidualRegressor:
    """Implement the estimator described in instruction.md."""
    def __init__(self, *, alpha=1.0, max_depth=3, min_samples_leaf=1, random_state=100, features="auto", fit_intercept=True, standardize=True):
        self.alpha = alpha
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.features = features
        self.fit_intercept = fit_intercept
        self.standardize = standardize

    def fit(self, X, y, sample_weight=None):
        raise NotImplementedError("implement LinearResidualRegressor.fit")

    def predict(self, X):
        raise NotImplementedError("implement LinearResidualRegressor.predict")

    def save_model(self, path):
        raise NotImplementedError("implement LinearResidualRegressor.save_model")

    @classmethod
    def load_model(cls, path):
        raise NotImplementedError("implement LinearResidualRegressor.load_model")
