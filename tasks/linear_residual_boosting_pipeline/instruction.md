# Linear Residual Boosting Pipeline

Implement `linear_residual.py::LinearResidualRegressor`, a sklearn-compatible additive regressor. The estimator fits a weighted ridge trend on eligible numeric input columns and a deterministic residual regression tree, then adds the trend and tree predictions.

## API

```python
class LinearResidualRegressor:
    def __init__(self, *, alpha=1.0, max_depth=3, min_samples_leaf=1,
                 random_state=100, features="auto", fit_intercept=True,
                 standardize=True): ...
    def fit(self, X, y, sample_weight=None) -> "LinearResidualRegressor": ...
    def predict(self, X) -> numpy.ndarray: ...
    def save_model(self, path) -> None: ...
    @classmethod
    def load_model(cls, path) -> "LinearResidualRegressor": ...
```

Constructor parameters are immutable: `fit` must not change their values, and `sklearn.base.clone` must reproduce an unfitted estimator. `alpha` is finite and nonnegative; `max_depth` is `None` or a positive integer; `min_samples_leaf` is a positive integer; `random_state` is retained for deterministic sklearn compatibility; `features` is `"auto"`/`None`, a sequence of integer column indices, a boolean mask, or a sequence of column names when named input is supplied.

`X` may be a NumPy array, an array-like object, or a pandas-like DataFrame exposing `.columns` and `.iloc`. Numeric columns are float-coercible columns (missing values are `NaN`, infinities, or `None`); nonnumeric columns are categorical. On named input, prediction may reorder columns, but must contain the same unique names. Numeric columns are encoded as floats and categorical columns use deterministic train-category codes; unknown prediction categories have a fixed fallback code.

The trend's eligible columns exclude categorical columns. For `"auto"`, nonnumeric, all-missing, and constant columns are dropped. Explicit categorical/non-numeric selections raise `ValueError`; explicit constant columns may be dropped only when another selected column remains. Missing-value imputation, centering, scaling, and constant detection use only rows with strictly positive training weights. `sample_weight` is one-dimensional, finite, nonnegative, and must have positive total weight. Zero-weight rows are accepted as validation/hold-out rows and must not influence any trend statistic or residual-tree fit. The ridge solve uses positive rows with weights normalized to mean one and an unpenalized intercept; use a stable SVD solve. Prediction accepts missing values and applies the training imputation values.

Fit the residual tree only on `y - trend(X)` and pass the positive training weights. Predictions are `trend(X) + residual_tree(X)`, are finite float64, and preserve input row order. Fitted state should expose useful sklearn-style attributes including `n_features_in_`, `feature_names_in_` (for named input), `linear_residual_active_`, `linear_residual_feature_indices_`, `linear_residual_coef_`, `linear_residual_intercept_`, and train-only imputation/scale arrays.

`save_model`/`load_model` must use JSON metadata and plain numeric arrays only (for example, a compressed NumPy archive). Pickle/joblib/cloudpickle and refitting on load are forbidden. Loaded predictions on the same and reordered named inputs must match the saved estimator within `1e-12`; malformed/nonfinite archives should raise `ValueError`.

Run the public deterministic fixture and focused checks:

```bash
python run_linear_residual.py
python -m pytest -q /tests/test_outputs.py
```

The visible fixture uses seed `100`. Hidden fixtures use seeds `1101`–`1105` and cover weights scaled by a positive constant, zero-weight validation rows with extreme values, categoricals and missing values, named-column reordering, cloneability, serialization, and a named `validation_leak` mutant that incorrectly includes zero-weight validation rows in preprocessing.
