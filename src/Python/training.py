"""Shared training helpers for strikeout-rate fits and PA sample weights.

`PA` may be used as a training/eval weight (likelihood information) but must
never enter the prediction feature matrix. Feature exclusion remains the job of
`Python.features.model_feature_names`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from Python.features import TARGET

try:
    import lightgbm as lgb
except ImportError:  # Base/dev installs can still audit non-LGBM models.
    lgb = None

SAMPLE_WEIGHT_MODES = ("none", "pa")


def resolve_sample_weights(
    frame: pd.DataFrame, mode: str
) -> np.ndarray | None:
    """Return fit/eval sample weights, or None for the unweighted baseline."""
    if mode == "none":
        return None
    if mode != "pa":
        raise ValueError(
            f"unsupported sample-weight mode {mode!r}; "
            f"expected one of {SAMPLE_WEIGHT_MODES}"
        )
    if "PA" not in frame.columns:
        raise ValueError("sample-weight mode 'pa' requires a PA column")
    weights = np.ascontiguousarray(frame["PA"].to_numpy(dtype=np.float64))
    if weights.size == 0:
        raise ValueError("sample-weight mode 'pa' received an empty frame")
    if not np.isfinite(weights).all():
        raise ValueError("PA sample weights must be finite")
    if (weights <= 0).any():
        raise ValueError("PA sample weights must be strictly positive")
    return weights


def metrics(
    y_true: pd.Series | np.ndarray,
    prediction: np.ndarray,
    sample_weight: np.ndarray | None = None,
    *,
    clip_to_unit_interval: bool = True,
) -> dict[str, float]:
    """Regression metrics for one chronological holdout."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    kwargs: dict[str, np.ndarray] = {}
    if sample_weight is not None:
        kwargs["sample_weight"] = sample_weight
    scored = (
        np.clip(prediction, 0, 1)
        if clip_to_unit_interval
        else np.asarray(prediction, dtype=float)
    )
    return {
        "mae": float(mean_absolute_error(y_true, scored, **kwargs)),
        "rmse": float(mean_squared_error(y_true, scored, **kwargs) ** 0.5),
        "r2": float(r2_score(y_true, scored, **kwargs)),
    }


def partition_metrics(
    y_true: pd.Series | np.ndarray,
    prediction: np.ndarray,
    *,
    pa_weights: np.ndarray | None = None,
    include_pa_weighted: bool | None = None,
) -> dict[str, dict[str, float]]:
    """Report unweighted game-level metrics and optional PA-weighted metrics.

    When ``include_pa_weighted`` is None, PA-weighted metrics are included iff
    ``pa_weights`` is provided.
    """
    report = {"unweighted": metrics(y_true, prediction)}
    should_include = (
        include_pa_weighted
        if include_pa_weighted is not None
        else pa_weights is not None
    )
    if should_include:
        if pa_weights is None:
            raise ValueError("pa_weights required when include_pa_weighted=True")
        report["pa_weighted"] = metrics(y_true, prediction, pa_weights)
    return report


def lightgbm_matrix(frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Return a stable numeric matrix for LightGBM's Windows native library.

    Coerces to float64, forces a contiguous copy, and maps ±inf → NaN. Jupyter
    on Windows has historically AV'd inside ``LGBM_BoosterPredictForMat`` when
    fed non-contiguous / object-tainted blocks.
    """
    block = frame.loc[:, list(features)].apply(pd.to_numeric, errors="coerce")
    mat = np.ascontiguousarray(block.to_numpy(dtype=np.float64, copy=True))
    if mat.ndim != 2 or mat.shape[1] != len(features):
        raise ValueError(
            f"lightgbm_matrix shape {mat.shape} does not match "
            f"{len(frame)} rows × {len(features)} features"
        )
    np.nan_to_num(mat, copy=False, nan=np.nan, posinf=np.nan, neginf=np.nan)
    return mat


def fit_kwargs_for_weights(
    model_name: str,
    train_weight: np.ndarray | None,
) -> dict:
    """Keyword args that route sample weights to Ridge / ElasticNet / Poisson / LightGBM / Dummy."""
    if train_weight is None:
        return {}
    if model_name == "ridge":
        # make_pipeline names the final step "ridge".
        return {"ridge__sample_weight": train_weight}
    if model_name == "elasticnet":
        return {"elasticnetcv__sample_weight": train_weight}
    if model_name == "poisson":
        return {"poissonregressor__sample_weight": train_weight}
    return {"sample_weight": train_weight}


def fit_regressor(
    model,
    model_name: str,
    train_features: pd.DataFrame | np.ndarray,
    train_target: pd.Series | np.ndarray,
    *,
    train_weight: np.ndarray | None = None,
    validation_features: pd.DataFrame | np.ndarray | None = None,
    validation_target: pd.Series | np.ndarray | None = None,
    validation_weight: np.ndarray | None = None,
    early_stopping_rounds: int | None = None,
    log_evaluation_period: int | None = 50,
) -> None:
    """Fit one estimator, optionally with PA weights and LightGBM early stop."""
    fit_kwargs = fit_kwargs_for_weights(model_name, train_weight)

    if model_name == "lightgbm":
        if lgb is None:
            raise ImportError(
                "LightGBM requires the research dependencies: "
                'pip install -e ".[research]"'
            )
        if not isinstance(train_features, np.ndarray):
            raise TypeError("lightgbm fits expect a numeric ndarray feature matrix")
        train_target = np.ascontiguousarray(
            np.asarray(train_target, dtype=np.float64)
        )
        if early_stopping_rounds is not None:
            if validation_features is None or validation_target is None:
                raise ValueError(
                    "LightGBM early stopping requires validation features/target"
                )
            fit_kwargs["eval_X"] = validation_features
            fit_kwargs["eval_y"] = np.ascontiguousarray(
                np.asarray(validation_target, dtype=np.float64)
            )
            callbacks = [lgb.early_stopping(early_stopping_rounds)]
            if log_evaluation_period is not None and log_evaluation_period > 0:
                callbacks.append(lgb.log_evaluation(log_evaluation_period))
            fit_kwargs["callbacks"] = callbacks
            if train_weight is not None:
                fit_kwargs["eval_sample_weight"] = [validation_weight]

    model.fit(train_features, train_target, **fit_kwargs)


def build_model(
    name: str,
    *,
    lightgbm_n_estimators: int = 5_000,
    lightgbm_verbosity: int = 1,
    lightgbm_params: dict | None = None,
    ridge_alpha: float = 1.0,
):
    """Construct a model; learned preprocessing is fit on training rows only."""
    if name == "lightgbm":
        if lgb is None:
            raise ImportError(
                "LightGBM requires the research dependencies: "
                'pip install -e ".[research]"'
            )
        params = {
            "objective": "regression",
            "n_estimators": lightgbm_n_estimators,
            "learning_rate": 0.03,
            "num_leaves": 31,
            "min_child_samples": 50,
            "subsample": 0.8,
            "colsample_bytree": 0.7,
            "reg_alpha": 0.1,
            "reg_lambda": 2.0,
            "random_state": 42,
            "verbosity": lightgbm_verbosity,
            "n_jobs": -1,
        }
        if lightgbm_params:
            params.update(lightgbm_params)
        return lgb.LGBMRegressor(**params)
    if name == "ridge":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=ridge_alpha),
        )
    if name == "elasticnet":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import ElasticNetCV
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        # CV folds stay inside the training partition only (caller fits on train).
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            ElasticNetCV(
                l1_ratio=[0.1, 0.5, 0.9, 1.0],
                cv=5,
                max_iter=20_000,
                random_state=42,
                n_jobs=-1,
            ),
        )
    if name == "poisson":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import PoissonRegressor
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            PoissonRegressor(alpha=1.0, max_iter=1_000),
        )
    if name == "mean":
        from sklearn.dummy import DummyRegressor

        return DummyRegressor(strategy="mean")
    raise ValueError(f"unsupported model {name!r}")


def chronological_split(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split approximately 70/15/15 without dividing a calendar date.

    Every game on a boundary date is assigned to the later partition. This
    keeps train, validation, and test date ranges strictly disjoint.
    """
    if len(frame) < 3 or frame["game_date"].nunique() < 3:
        raise ValueError("chronological split requires at least three distinct dates")
    if not frame["game_date"].is_monotonic_increasing:
        raise ValueError("chronological split requires rows sorted by game_date")

    first, second = int(len(frame) * 0.70), int(len(frame) * 0.85)
    validation_start = frame.iloc[first]["game_date"]
    test_start = frame.iloc[second]["game_date"]

    train = frame[frame["game_date"] < validation_start]
    validation = frame[
        (frame["game_date"] >= validation_start)
        & (frame["game_date"] < test_start)
    ]
    test = frame[frame["game_date"] >= test_start]
    if train.empty or validation.empty or test.empty:
        raise ValueError("chronological split produced an empty partition")
    return train, validation, test


def predict_clipped(
    model,
    model_name: str,
    frame: pd.DataFrame,
    features: list[str],
) -> np.ndarray:
    """Predict k_rate and clip to the valid [0, 1] interval."""
    matrix: pd.DataFrame | np.ndarray
    if model_name == "lightgbm":
        matrix = lightgbm_matrix(frame, features)
    else:
        matrix = frame[features]
    return np.clip(model.predict(matrix), 0, 1)


def predict_nonnegative(
    model,
    model_name: str,
    frame: pd.DataFrame,
    features: list[str],
    *,
    upper: float | None = None,
) -> np.ndarray:
    """Predict a count-like target and clip to a non-negative range."""
    matrix: pd.DataFrame | np.ndarray
    if model_name == "lightgbm":
        matrix = lightgbm_matrix(frame, features)
    else:
        matrix = frame[features]
    prediction = np.asarray(model.predict(matrix), dtype=float)
    if upper is None:
        return np.maximum(prediction, 0.0)
    return np.clip(prediction, 0.0, upper)


def assert_pa_not_in_features(features: list[str]) -> None:
    """Fail loudly if same-game PA leaked into the feature list."""
    if "PA" in features:
        raise RuntimeError(
            "PA leaked into model features; refuse to train. "
            "PA may be used only as a sample weight / label."
        )


# Re-export target for callers that import training helpers together.
__all__ = [
    "SAMPLE_WEIGHT_MODES",
    "TARGET",
    "assert_pa_not_in_features",
    "build_model",
    "chronological_split",
    "fit_kwargs_for_weights",
    "fit_regressor",
    "lightgbm_matrix",
    "metrics",
    "partition_metrics",
    "predict_clipped",
    "predict_nonnegative",
    "resolve_sample_weights",
]
