#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys
_REFERENCE = r'''
"""Leakage-safe linear residual regression estimator."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
try:
    from sklearn.base import BaseEstimator, RegressorMixin
except Exception:  # pragma: no cover - the task image provides sklearn
    class BaseEstimator: pass
    class RegressorMixin: pass


def _rows_and_names(X):
    columns = getattr(X, "columns", None)
    if columns is not None:
        names = [str(c) for c in list(columns)]
        if len(set(names)) != len(names):
            raise ValueError("input column names must be unique")
        if hasattr(X, "to_numpy"):
            arr = np.asarray(X.to_numpy(dtype=object), dtype=object)
        elif hasattr(X, "values"):
            arr = np.asarray(X.values, dtype=object)
        else:
            arr = np.asarray(X, dtype=object)
    else:
        names = None
        arr = np.asarray(X, dtype=object)
    if arr.ndim != 2:
        raise ValueError("X must be a two-dimensional array")
    return arr, names


def _align_rows(X, expected_names, expected_n):
    arr, names = _rows_and_names(X)
    if expected_names is None:
        if names is not None:
            raise ValueError("a named DataFrame cannot replace unnamed training input")
        if arr.shape[1] != expected_n:
            raise ValueError("X has an incompatible number of columns")
        return arr
    if names is None:
        raise ValueError("prediction input must provide the fitted column names")
    if len(names) != expected_n or set(names) != set(expected_names):
        raise ValueError("prediction columns must match the fitted columns")
    order = [names.index(name) for name in expected_names]
    return arr[:, order]


def _missing(value):
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "null", "<na>"}:
        return True
    try:
        return bool(np.isscalar(value) and not np.isfinite(float(value)))
    except (TypeError, ValueError, OverflowError):
        return False


def _numeric_column(values):
    out = np.empty(len(values), dtype=np.float64)
    for i, value in enumerate(values):
        if _missing(value):
            out[i] = np.nan
            continue
        try:
            out[i] = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
    return out


def _category_key(value):
    return "__MISSING__" if _missing(value) else type(value).__name__ + ":" + repr(value)


def _weights(sample_weight, n):
    if sample_weight is None:
        w = np.ones(n, dtype=np.float64)
    else:
        w = np.asarray(sample_weight, dtype=np.float64)
        if w.ndim != 1 or w.shape[0] != n:
            raise ValueError("sample_weight must have shape (n_samples,)")
        if not np.all(np.isfinite(w)) or np.any(w < 0):
            raise ValueError("sample_weight must be finite and nonnegative")
    w = np.where(w > 0, w, 1.0)
    positive = np.ones(n, dtype=bool)
    if not np.any(positive):
        raise ValueError("sample_weight must have positive total weight")
    return w, positive


def _weighted_mean(values, weights):
    return float(np.dot(values, weights) / np.sum(weights))


def _weighted_sse(y, w):
    if np.sum(w) <= 0:
        return 0.0
    mean = _weighted_mean(y, w)
    return float(np.dot(w, (y - mean) ** 2))


class _ResidualTree:
    """Small deterministic weighted squared-error regression tree."""
    def __init__(self, max_depth=3, min_samples_leaf=1):
        self.max_depth = max_depth
        self.min_samples_leaf = int(min_samples_leaf)

    def fit(self, X, y, sample_weight):
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        w = np.asarray(sample_weight, dtype=np.float64)
        keep = w > 0
        X, y, w = X[keep], y[keep], w[keep]
        if X.shape[0] == 0:
            raise ValueError("residual tree received no positive-weight rows")
        lefts, rights, features, thresholds, values = [], [], [], [], []
        def grow(rows, depth):
            node = len(values)
            lefts.append(-1); rights.append(-1); features.append(-2); thresholds.append(-2.0)
            value = _weighted_mean(y[rows], w[rows])
            values.append(value)
            if self.max_depth is not None and depth >= self.max_depth:
                return node
            if rows.size < 2 * self.min_samples_leaf:
                return node
            base = _weighted_sse(y[rows], w[rows])
            if base <= 1e-15:
                return node
            best = None
            for feature in range(X.shape[1]):
                order = rows[np.argsort(X[rows, feature], kind="mergesort")]
                xs = X[order, feature]
                for cut in range(self.min_samples_leaf, order.size - self.min_samples_leaf + 1):
                    if cut >= order.size or xs[cut - 1] == xs[cut]:
                        continue
                    lrows, rrows = order[:cut], order[cut:]
                    lw, rw = w[lrows], w[rrows]
                    if np.sum(lw) <= 0 or np.sum(rw) <= 0:
                        continue
                    score = _weighted_sse(y[lrows], lw) + _weighted_sse(y[rrows], rw)
                    threshold = float((xs[cut - 1] + xs[cut]) / 2.0)
                    candidate = (float(score), int(feature), threshold, lrows, rrows)
                    if best is None or candidate[:3] < best[:3]:
                        best = candidate
            if best is None or best[0] >= base - 1e-12:
                return node
            _, feature, threshold, lrows, rrows = best
            features[node] = feature; thresholds[node] = threshold
            lefts[node] = grow(lrows, depth + 1)
            rights[node] = grow(rrows, depth + 1)
            return node
        grow(np.arange(X.shape[0], dtype=np.int64), 0)
        self.children_left_ = np.asarray(lefts, dtype=np.int64)
        self.children_right_ = np.asarray(rights, dtype=np.int64)
        self.feature_ = np.asarray(features, dtype=np.int64)
        self.threshold_ = np.asarray(thresholds, dtype=np.float64)
        self.value_ = np.asarray(values, dtype=np.float64)
        self.n_features_in_ = int(X.shape[1])
        return self

    def predict(self, X):
        X = np.asarray(X, dtype=np.float64)
        out = np.empty(X.shape[0], dtype=np.float64)
        for i, row in enumerate(X):
            node = 0
            while self.children_left_[node] >= 0:
                node = self.children_left_[node] if row[self.feature_[node]] <= self.threshold_[node] else self.children_right_[node]
            out[i] = self.value_[node]
        return out

    def arrays(self):
        return {
            "tree_children_left": self.children_left_,
            "tree_children_right": self.children_right_,
            "tree_feature": self.feature_,
            "tree_threshold": self.threshold_,
            "tree_value": self.value_,
        }

    @classmethod
    def from_arrays(cls, arrays, max_depth, min_samples_leaf):
        names = ("tree_children_left", "tree_children_right", "tree_feature", "tree_threshold", "tree_value")
        if any(name not in arrays for name in names):
            raise ValueError("model archive is missing residual-tree arrays")
        tree = cls(max_depth, min_samples_leaf)
        tree.children_left_ = np.asarray(arrays[names[0]], dtype=np.int64)
        tree.children_right_ = np.asarray(arrays[names[1]], dtype=np.int64)
        tree.feature_ = np.asarray(arrays[names[2]], dtype=np.int64)
        tree.threshold_ = np.asarray(arrays[names[3]], dtype=np.float64)
        tree.value_ = np.asarray(arrays[names[4]], dtype=np.float64)
        n = tree.value_.shape
        if tree.value_.ndim != 1 or any(np.asarray(arrays[k]).shape != n for k in names):
            raise ValueError("invalid residual-tree array shapes")
        if not np.all(np.isfinite(tree.threshold_)) or not np.all(np.isfinite(tree.value_)):
            raise ValueError("residual-tree arrays must be finite")
        if tree.value_.size == 0 or tree.children_left_[0] < -1:
            raise ValueError("invalid residual-tree structure")
        tree.n_features_in_ = int(np.max(tree.feature_) + 1) if np.any(tree.feature_ >= 0) else 0
        return tree


class LinearResidualRegressor(BaseEstimator, RegressorMixin):
    """Weighted ridge trend plus a deterministic residual regression tree."""
    def __init__(self, *, alpha=1.0, max_depth=3, min_samples_leaf=1, random_state=100,
                 features="auto", fit_intercept=True, standardize=True):
        self.alpha = alpha
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.random_state = random_state
        self.features = features
        self.fit_intercept = fit_intercept
        self.standardize = standardize

    def _validate_params(self):
        alpha = float(self.alpha)
        if not np.isfinite(alpha) or alpha < 0:
            raise ValueError("alpha must be a finite nonnegative number")
        if self.max_depth is not None and (isinstance(self.max_depth, (bool, np.bool_)) or int(self.max_depth) != self.max_depth or int(self.max_depth) < 1):
            raise ValueError("max_depth must be None or a positive integer")
        if isinstance(self.min_samples_leaf, (bool, np.bool_)) or int(self.min_samples_leaf) != self.min_samples_leaf or int(self.min_samples_leaf) < 1:
            raise ValueError("min_samples_leaf must be a positive integer")
        return alpha

    def _selector(self, kinds, names):
        p = len(kinds)
        value = self.features
        explicit = not (value is None or (isinstance(value, str) and value == "auto"))
        if not explicit:
            return [i for i, kind in enumerate(kinds) if kind == "numeric"], False
        if isinstance(value, (str, bytes)):
            raw = [value]
        else:
            arr = np.asarray(value)
            if arr.ndim == 1 and arr.dtype == bool:
                if arr.shape != (p,):
                    raise ValueError("features boolean mask has wrong length")
                raw = np.flatnonzero(arr).tolist()
            elif arr.ndim == 0:
                raw = [arr.item()]
            else:
                raw = list(value)
        if not raw:
            raise ValueError("features must select at least one column")
        if all(isinstance(v, str) for v in raw):
            if names is None:
                raise ValueError("string features require named input")
            indices = []
            for v in raw:
                if names.count(v) != 1:
                    raise ValueError("feature name was not found uniquely")
                indices.append(names.index(v))
        else:
            try:
                indices = [int(v) for v in raw]
            except (TypeError, ValueError) as exc:
                raise ValueError("features must be names, indices, a mask, or auto") from exc
            if any(int(v) != v or v < 0 or v >= p for v in indices):
                raise ValueError("feature index is out of bounds")
        if len(set(indices)) != len(indices):
            raise ValueError("features contains duplicate columns")
        bad = [i for i in indices if kinds[i] != "numeric"]
        if bad:
            raise ValueError("features cannot include categorical columns")
        return indices, True

    def _detect(self, arr):
        kinds, nums = [], []
        for j in range(arr.shape[1]):
            col = _numeric_column(arr[:, j])
            if col is None:
                kinds.append("categorical"); nums.append(None)
            else:
                kinds.append("numeric"); nums.append(col)
        return kinds, nums

    def _fit_trend(self, nums, kinds, y, w, positive, indices, names, explicit):
        wp = w[positive]; columns = []; selected = []; centers = []; scales = []; impute = []; dropped = []
        for j in indices:
            col = nums[j]
            finite_pos = np.isfinite(col) & positive
            if not np.any(finite_pos):
                if explicit:
                    raise ValueError("explicit feature has no finite positive-weight values")
                dropped.append({"index": int(j), "reason": "all_missing"}); continue
            imp = _weighted_mean(col[finite_pos], w[finite_pos])
            filled = np.where(np.isfinite(col), col, imp)
            mean = _weighted_mean(filled[positive], wp)
            var = float(np.dot(wp, (filled[positive] - mean) ** 2) / np.sum(wp))
            if var <= np.finfo(np.float64).eps:
                dropped.append({"index": int(j), "reason": "constant"}); continue
            center = mean if bool(self.fit_intercept) else 0.0
            scale = float(np.sqrt(var)) if bool(self.standardize) else 1.0
            columns.append((filled - center) / scale); selected.append(j); centers.append(center); scales.append(scale); impute.append(imp)
        if not selected:
            if explicit:
                raise ValueError("features did not leave any usable numeric columns")
            self.linear_residual_active_ = False
            self.linear_residual_inactive_reason_ = "no_usable_auto_features"
            self.linear_residual_feature_indices_ = np.empty(0, dtype=np.int64)
            self.linear_residual_coef_ = np.empty(0, dtype=np.float64)
            self.linear_residual_intercept_ = 0.0
            self.linear_residual_center_ = np.empty(0); self.linear_residual_scale_ = np.empty(0); self.linear_residual_impute_values_ = np.empty(0)
            self.dropped_features_ = dropped
            return
        Z = np.column_stack(columns); zp = Z[positive]; yp = y[positive]
        ymean = _weighted_mean(yp, wp) if bool(self.fit_intercept) else 0.0
        sw = np.sqrt(wp); zw = zp * sw[:, None]; yw = (yp - ymean) * sw
        U, singular, Vt = np.linalg.svd(zw, full_matrices=False)
        rhs = U.T @ yw
        if float(self.alpha) == 0:
            cutoff = max(len(wp), len(selected)) * np.finfo(np.float64).eps * (float(np.max(singular)) if singular.size else 0.0)
            factors = np.where(singular > cutoff, 1.0 / singular, 0.0)
        else:
            factors = singular / (singular * singular + float(self.alpha) * len(wp))
        transformed = Vt.T @ (factors * rhs)
        centers = np.asarray(centers, dtype=np.float64); scales = np.asarray(scales, dtype=np.float64)
        coef = transformed / scales
        intercept = float(ymean - np.dot(centers, coef)) if bool(self.fit_intercept) else 0.0
        self.linear_residual_active_ = True; self.linear_residual_inactive_reason_ = None
        self.linear_residual_feature_indices_ = np.asarray(selected, dtype=np.int64)
        self.linear_residual_feature_names_ = None if names is None else [names[j] for j in selected]
        self.linear_residual_coef_ = coef; self.linear_residual_transformed_coef_ = transformed
        self.linear_residual_intercept_ = intercept; self.linear_residual_center_ = centers; self.linear_residual_scale_ = scales; self.linear_residual_impute_values_ = np.asarray(impute, dtype=np.float64)
        self.linear_residual_singular_values_ = singular; self.linear_residual_rank_ = int(np.sum(singular > max(len(wp), len(selected)) * np.finfo(np.float64).eps * np.max(singular)))
        self.dropped_features_ = dropped; self.linear_residual_weight_sum_ = float(np.sum(wp)); self.linear_residual_positive_weight_n_ = int(len(wp)); self.linear_residual_target_mean_ = float(ymean)

    def _fit_tree_preprocess(self, arr, kinds, nums, w, positive):
        self._tree_kinds_ = list(kinds); self._tree_impute_ = []; self._tree_categories_ = []
        for j, kind in enumerate(kinds):
            if kind == "numeric":
                col = nums[j]; ok = np.isfinite(col) & positive
                value = _weighted_mean(col[ok], w[ok]) if np.any(ok) else 0.0
                self._tree_impute_.append(float(value)); self._tree_categories_.append(None)
            else:
                mapping = {};
                for val in arr[positive, j]:
                    key = _category_key(val)
                    if key not in mapping: mapping[key] = len(mapping)
                self._tree_impute_.append(0.0); self._tree_categories_.append(mapping)
        return self._encode_tree(arr, nums)

    def _encode_tree(self, arr, nums=None):
        if nums is None:
            kinds, nums = self._detect(arr)
        out = np.empty(arr.shape, dtype=np.float64)
        for j, kind in enumerate(self._tree_kinds_):
            if kind == "numeric":
                col = nums[j] if nums[j] is not None else _numeric_column(arr[:, j])
                if col is None: raise ValueError("numeric column is nonnumeric at predict time")
                out[:, j] = np.where(np.isfinite(col), col, self._tree_impute_[j])
            else:
                mapping = self._tree_categories_[j]
                out[:, j] = [mapping.get(_category_key(value), -1.0) for value in arr[:, j]]
        return out

    def _trend_predict(self, arr):
        if not self.linear_residual_active_:
            return np.zeros(arr.shape[0], dtype=np.float64)
        cols = []
        for off, j in enumerate(self.linear_residual_feature_indices_):
            col = _numeric_column(arr[:, int(j)])
            if col is None: raise ValueError("a fitted numeric feature is nonnumeric at predict time")
            cols.append(np.where(np.isfinite(col), col, self.linear_residual_impute_values_[off]))
        return self.linear_residual_intercept_ + np.column_stack(cols) @ self.linear_residual_coef_

    def fit(self, X, y, sample_weight=None):
        self._validate_params(); arr, names = _rows_and_names(X)
        n, p = arr.shape; yy = np.asarray(y, dtype=np.float64)
        if yy.ndim != 1 or yy.shape[0] != n or not np.all(np.isfinite(yy)):
            raise ValueError("y must be a finite one-dimensional vector aligned with X")
        w, positive = _weights(sample_weight, n)
        kinds, nums = self._detect(arr); indices, explicit = self._selector(kinds, names)
        self.n_features_in_ = int(p); self.feature_names_in_ = None if names is None else np.asarray(names, dtype=object)
        self._fit_trend(nums, kinds, yy, w, positive, indices, names, explicit)
        tree_X = self._fit_tree_preprocess(arr, kinds, nums, w, positive)
        residual = yy - self._trend_predict(arr)
        self.residual_tree_ = _ResidualTree(self.max_depth, self.min_samples_leaf).fit(tree_X, residual, w)
        self.is_fitted_ = True
        return self

    def predict(self, X):
        if not getattr(self, "is_fitted_", False): raise ValueError("estimator is not fitted")
        arr = _align_rows(X, None if self.feature_names_in_ is None else list(self.feature_names_in_), self.n_features_in_)
        kinds, nums = self._detect(arr)
        return np.asarray(self._trend_predict(arr) + self.residual_tree_.predict(self._encode_tree(arr, nums)), dtype=np.float64)

    def save_model(self, path):
        if not getattr(self, "is_fitted_", False): raise ValueError("estimator is not fitted")
        meta = {"format": "linear-residual-regressor-1", "params": {"alpha": self.alpha, "max_depth": self.max_depth, "min_samples_leaf": self.min_samples_leaf, "random_state": self.random_state, "features": self.features.tolist() if isinstance(self.features, np.ndarray) else self.features, "fit_intercept": self.fit_intercept, "standardize": self.standardize}, "n_features_in": self.n_features_in_, "feature_names_in": None if self.feature_names_in_ is None else [str(v) for v in self.feature_names_in_], "tree_kinds": self._tree_kinds_, "tree_impute": self._tree_impute_, "tree_categories": self._tree_categories_, "active": self.linear_residual_active_, "inactive_reason": self.linear_residual_inactive_reason_, "dropped_features": self.dropped_features_, "trend_feature_names": getattr(self, "linear_residual_feature_names_", None), "trend_intercept": float(self.linear_residual_intercept_), "trend_rank": int(getattr(self, "linear_residual_rank_", 0)), "trend_weight_sum": float(getattr(self, "linear_residual_weight_sum_", 0.0)), "trend_positive_n": int(getattr(self, "linear_residual_positive_weight_n_", 0)), "trend_target_mean": float(getattr(self, "linear_residual_target_mean_", 0.0))}
        arrays = {"trend_indices": self.linear_residual_feature_indices_, "trend_coef": self.linear_residual_coef_, "trend_transformed_coef": getattr(self, "linear_residual_transformed_coef_", np.empty(0)), "trend_center": self.linear_residual_center_, "trend_scale": self.linear_residual_scale_, "trend_impute": self.linear_residual_impute_values_, **self.residual_tree_.arrays()}
        with Path(path).open("wb") as handle:
            np.savez_compressed(handle, metadata=np.asarray(json.dumps(meta), dtype=np.str_), **arrays)

    @classmethod
    def load_model(cls, path):
        try:
            with np.load(Path(path), allow_pickle=False) as data:
                meta = json.loads(str(data["metadata"].item()))
                if meta.get("format") != "linear-residual-regressor-1": raise ValueError("unsupported model format")
                params = dict(meta["params"]); obj = cls(**params)
                obj.n_features_in_ = int(meta["n_features_in"]); obj.feature_names_in_ = None if meta.get("feature_names_in") is None else np.asarray(meta["feature_names_in"], dtype=object)
                if obj.n_features_in_ < 1: raise ValueError("invalid feature count")
                obj._tree_kinds_ = list(meta["tree_kinds"]); obj._tree_impute_ = [float(v) for v in meta["tree_impute"]]; obj._tree_categories_ = [None if v is None else {str(k): int(x) for k, x in v.items()} for v in meta["tree_categories"]]
                if len(obj._tree_kinds_) != obj.n_features_in_: raise ValueError("invalid preprocessing state")
                obj.linear_residual_active_ = bool(meta["active"]); obj.linear_residual_inactive_reason_ = meta.get("inactive_reason"); obj.dropped_features_ = list(meta.get("dropped_features", [])); obj.linear_residual_feature_indices_ = np.asarray(data["trend_indices"], dtype=np.int64); obj.linear_residual_coef_ = np.asarray(data["trend_coef"], dtype=np.float64); obj.linear_residual_transformed_coef_ = np.asarray(data["trend_transformed_coef"], dtype=np.float64); obj.linear_residual_center_ = np.asarray(data["trend_center"], dtype=np.float64); obj.linear_residual_scale_ = np.asarray(data["trend_scale"], dtype=np.float64); obj.linear_residual_impute_values_ = np.asarray(data["trend_impute"], dtype=np.float64); obj.linear_residual_intercept_ = float(meta["trend_intercept"]); obj.linear_residual_feature_names_ = meta.get("trend_feature_names"); obj.linear_residual_rank_ = int(meta.get("trend_rank", 0)); obj.linear_residual_weight_sum_ = float(meta.get("trend_weight_sum", 0)); obj.linear_residual_positive_weight_n_ = int(meta.get("trend_positive_n", 0)); obj.linear_residual_target_mean_ = float(meta.get("trend_target_mean", 0))
                p = len(obj.linear_residual_feature_indices_)
                for a in (obj.linear_residual_coef_, obj.linear_residual_transformed_coef_, obj.linear_residual_center_, obj.linear_residual_scale_, obj.linear_residual_impute_values_):
                    if a.ndim != 1 or a.shape[0] != p or not np.all(np.isfinite(a)): raise ValueError("invalid trend arrays")
                if np.any(obj.linear_residual_scale_ <= 0): raise ValueError("invalid trend scales")
                obj.residual_tree_ = _ResidualTree.from_arrays({k: data[k] for k in ("tree_children_left", "tree_children_right", "tree_feature", "tree_threshold", "tree_value")}, obj.max_depth, obj.min_samples_leaf)
                obj.is_fitted_ = True
                return obj
        except KeyError as exc:
            raise ValueError("model archive is missing required fields") from exc
'''
def main():
    workspace = Path.cwd()
    if not (workspace / "input.json").is_file(): workspace = Path(__file__).resolve().parents[3] / "workspace"
    (workspace / "linear_residual.py").write_text(_REFERENCE, encoding="utf-8")
    sys.path.insert(0, str(workspace))
    runpy.run_path(str(workspace / "run_linear_residual.py"), run_name="__main__")
if __name__ == "__main__": main()
