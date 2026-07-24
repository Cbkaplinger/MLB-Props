"""Train leakage-safe pitcher strikeout-rate models from the Level 3 artifact.

Examples:
    python Models/Strikeout-Model/train.py --model lightgbm
    python Models/Strikeout-Model/train.py --model ridge
    python Models/Strikeout-Model/train.py --model mean
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from Python.config import MODEL_DIR, PITCHER_TRAINING_PATH, ensure_output_directories
from Python.features import TARGET, model_feature_names

try:
    import lightgbm as lgb
except ImportError:  # Base/dev installs can still audit splits and non-LGBM models.
    lgb = None


def load_frame() -> tuple[pd.DataFrame, list[str]]:
    """Load Level 3 and return chronologically sorted rows plus safe features."""
    if not PITCHER_TRAINING_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PITCHER_TRAINING_PATH}. Run all three pipeline stages first."
        )
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    return frame, list(model_feature_names(frame))


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


def build_model(name: str):
    """Construct a model; all learned preprocessing is fit on training rows."""
    if name == "lightgbm":
        if lgb is None:
            raise ImportError(
                "LightGBM requires the research dependencies: "
                'pip install -e ".[research]"'
            )
        return lgb.LGBMRegressor(
            objective="regression",
            n_estimators=5_000,
            learning_rate=0.03,
            num_leaves=31,
            min_child_samples=50,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.1,
            reg_lambda=2.0,
            random_state=42,
        )
    if name == "ridge":
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=1.0),
        )
    from sklearn.dummy import DummyRegressor

    return DummyRegressor(strategy="mean")


def metrics(y_true: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    """Regression metrics for one chronological holdout."""
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    return {
        "mae": float(mean_absolute_error(y_true, prediction)),
        "rmse": float(mean_squared_error(y_true, prediction) ** 0.5),
        "r2": float(r2_score(y_true, prediction)),
    }


def lightgbm_matrix(frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Return a stable numeric matrix for LightGBM's Windows native library."""
    return np.ascontiguousarray(frame[features].to_numpy(dtype=np.float64))


def main(model_name: str) -> None:
    frame, features = load_frame()
    train, validation, test = chronological_split(frame)
    model = build_model(model_name)

    fit_kwargs = {}
    fit_target: pd.Series | np.ndarray = train[TARGET]
    fit_features: pd.DataFrame | np.ndarray = train[features]
    if model_name == "lightgbm":
        assert lgb is not None  # build_model already raises a clear dependency error.
        fit_features = lightgbm_matrix(train, features)
        fit_target = np.ascontiguousarray(train[TARGET].to_numpy(dtype=np.float64))
        fit_kwargs = {
            "eval_X": lightgbm_matrix(validation, features),
            "eval_y": np.ascontiguousarray(
                validation[TARGET].to_numpy(dtype=np.float64)
            ),
            "callbacks": [lgb.early_stopping(200), lgb.log_evaluation(50)],
        }
    model.fit(fit_features, fit_target, **fit_kwargs)

    validation_features = (
        lightgbm_matrix(validation, features)
        if model_name == "lightgbm"
        else validation[features]
    )
    test_features = (
        lightgbm_matrix(test, features)
        if model_name == "lightgbm"
        else test[features]
    )

    report = {
        "model": model_name,
        "features": len(features),
        "rows": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
        "cutoffs": {
            "train_end": str(train["game_date"].max().date()),
            "validation_start": str(validation["game_date"].min().date()),
            "validation_end": str(validation["game_date"].max().date()),
            "test_start": str(test["game_date"].min().date()),
        },
        "validation": metrics(
            validation[TARGET], np.clip(model.predict(validation_features), 0, 1)
        ),
        "test": metrics(test[TARGET], np.clip(model.predict(test_features), 0, 1)),
    }
    print(json.dumps(report, indent=2))

    if model_name == "lightgbm":
        ensure_output_directories()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        model_path = MODEL_DIR / f"lightgbm_krate_{stamp}.txt"
        model.booster_.save_model(model_path)
        model_path.with_suffix(".json").write_text(
            json.dumps({"features": features, "evaluation": report}, indent=2),
            encoding="utf-8",
        )
        print(f"Saved model and metadata to {model_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        choices=("lightgbm", "ridge", "mean"),
        default="lightgbm",
    )
    main(parser.parse_args().model)
