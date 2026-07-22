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

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from mlb_props.config import MODEL_DIR, PITCHER_TRAINING_PATH, ensure_output_directories
from mlb_props.features import TARGET, model_feature_names


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
    """Split rows chronologically 70/15/15 without shuffling."""
    first, second = int(len(frame) * 0.70), int(len(frame) * 0.85)
    return frame.iloc[:first], frame.iloc[first:second], frame.iloc[second:]


def build_model(name: str):
    """Construct a model; all learned preprocessing is fit on training rows."""
    if name == "lightgbm":
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
        return make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=1.0),
        )
    return DummyRegressor(strategy="mean")


def metrics(y_true: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    """Regression metrics for one chronological holdout."""
    return {
        "mae": float(mean_absolute_error(y_true, prediction)),
        "rmse": float(mean_squared_error(y_true, prediction) ** 0.5),
        "r2": float(r2_score(y_true, prediction)),
    }


def main(model_name: str) -> None:
    frame, features = load_frame()
    train, validation, test = chronological_split(frame)
    model = build_model(model_name)

    fit_kwargs = {}
    if model_name == "lightgbm":
        fit_kwargs = {
            "eval_set": [(validation[features], validation[TARGET])],
            "callbacks": [lgb.early_stopping(200), lgb.log_evaluation(50)],
        }
    model.fit(train[features], train[TARGET], **fit_kwargs)

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
            "validation_end": str(validation["game_date"].max().date()),
            "test_start": str(test["game_date"].min().date()),
        },
        "validation": metrics(
            validation[TARGET], np.clip(model.predict(validation[features]), 0, 1)
        ),
        "test": metrics(test[TARGET], np.clip(model.predict(test[features]), 0, 1)),
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
