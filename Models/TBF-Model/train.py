"""Train leakage-safe projected-TBF (PA) models from the Level 3 artifact.

Examples:
    python Models/TBF-Model/train.py --model lightgbm
    python Models/TBF-Model/train.py --model ridge --feature-set workload
    python Models/TBF-Model/train.py --model ridge --tune-alpha --persist
    python Models/TBF-Model/train.py --model mean
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from Python.config import (
    MODEL_DIR,
    OUTPUT_DIR,
    PITCHER_TRAINING_PATH,
    TRAIN_SEASONS,
    ensure_output_directories,
)
from Python.tbf import (
    TBF_DEFAULT_FEATURE_SET,
    TBF_FEATURE_SETS,
    TBF_TARGET,
    assert_tbf_label_not_in_features,
    tbf_feature_names,
)
from Python.training import (
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_nonnegative,
)

# Phase 11.A: log-spaced Ridge alpha grid (chrono val, not shuffled CV).
RIDGE_ALPHA_GRID = tuple(float(x) for x in np.logspace(-2, 3, 12))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frame(
    feature_set: str = TBF_DEFAULT_FEATURE_SET,
) -> tuple[pd.DataFrame, list[str]]:
    """Load Level 3 rows restricted to train seasons plus TBF features."""
    if not PITCHER_TRAINING_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PITCHER_TRAINING_PATH}. Run all three pipeline stages first."
        )
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.loc[frame["season"].isin(TRAIN_SEASONS)]
        .dropna(subset=[TBF_TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    observed = tuple(sorted(frame["season"].unique()))
    if observed != TRAIN_SEASONS:
        raise ValueError(f"expected {TRAIN_SEASONS}, got {observed}")
    return frame, list(tbf_feature_names(frame, feature_set))


def fit_model(
    model,
    model_name: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> None:
    """Fit one TBF model; LightGBM uses early stopping on validation MAE proxy."""
    if model_name == "lightgbm":
        fit_regressor(
            model,
            model_name,
            lightgbm_matrix(train, features),
            train[TBF_TARGET],
            validation_features=lightgbm_matrix(validation, features),
            validation_target=validation[TBF_TARGET],
            early_stopping_rounds=200,
            log_evaluation_period=50,
        )
        return
    fit_regressor(
        model,
        model_name,
        train[features],
        train[TBF_TARGET],
    )


def _select_ridge_alpha(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
    alphas: tuple[float, ...] = RIDGE_ALPHA_GRID,
) -> tuple[float, list[dict[str, float]]]:
    """Pick Ridge alpha by chronological validation MAE (never shuffled CV)."""
    rows: list[dict[str, float]] = []
    best_alpha = alphas[0]
    best_mae = float("inf")
    for alpha in alphas:
        model = build_model("ridge", ridge_alpha=alpha)
        fit_model(model, "ridge", train, validation, features)
        pred = predict_nonnegative(model, "ridge", validation, features)
        mae = metrics(
            validation[TBF_TARGET], pred, clip_to_unit_interval=False
        )["mae"]
        rows.append({"alpha": float(alpha), "validation_mae": float(mae)})
        if mae < best_mae:
            best_mae = float(mae)
            best_alpha = float(alpha)
    return best_alpha, rows


def main(
    model_name: str,
    feature_set: str = TBF_DEFAULT_FEATURE_SET,
    *,
    tune_alpha: bool = False,
    persist: bool = False,
    ridge_alpha: float = 1.0,
) -> None:
    if feature_set not in TBF_FEATURE_SETS:
        raise ValueError(
            f"unsupported feature set {feature_set!r}; expected {TBF_FEATURE_SETS}"
        )

    frame, features = load_frame(feature_set=feature_set)
    assert_tbf_label_not_in_features(features)

    train, validation, test = chronological_split(frame)
    alpha_grid_rows: list[dict[str, float]] | None = None
    selected_alpha = ridge_alpha
    if model_name == "ridge" and tune_alpha:
        selected_alpha, alpha_grid_rows = _select_ridge_alpha(
            train, validation, features
        )

    if model_name == "ridge":
        model = build_model(model_name, ridge_alpha=selected_alpha)
    else:
        model = build_model(model_name)
    fit_model(model, model_name, train, validation, features)

    # Starter PA rarely exceeds ~40; clip wild extrapolations without forcing [0,1].
    upper = float(train[TBF_TARGET].quantile(0.999))
    validation_pred = predict_nonnegative(
        model, model_name, validation, features, upper=upper
    )
    test_pred = predict_nonnegative(
        model, model_name, test, features, upper=upper
    )

    report = {
        "model": model_name,
        "target": TBF_TARGET,
        "feature_set": feature_set,
        "features": len(features),
        "feature_names": features,
        "prediction_upper_clip": upper,
        "ridge_alpha": selected_alpha if model_name == "ridge" else None,
        "tune_alpha": tune_alpha if model_name == "ridge" else False,
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
        "target_summary": {
            "train_mean": float(train[TBF_TARGET].mean()),
            "validation_mean": float(validation[TBF_TARGET].mean()),
            "test_mean": float(test[TBF_TARGET].mean()),
        },
        "validation": metrics(
            validation[TBF_TARGET], validation_pred, clip_to_unit_interval=False
        ),
        "test": metrics(
            test[TBF_TARGET], test_pred, clip_to_unit_interval=False
        ),
    }
    if alpha_grid_rows is not None:
        report["alpha_grid"] = alpha_grid_rows
    print(json.dumps(report, indent=2))

    ensure_output_directories()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = MODEL_DIR / f"tbf_pa_{model_name}_{feature_set}_{stamp}"
    quality_dir = OUTPUT_DIR / "model_quality" / "phase11a_tbf_ridge"
    quality_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "evaluation": report,
        "training_artifact": str(PITCHER_TRAINING_PATH),
        "training_artifact_sha256": _sha256(PITCHER_TRAINING_PATH),
        "approved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": (
            "Frozen projected-TBF spine: Ridge + thin bullpen "
            "(workload_context_bullpen). Same-game PA is the label only. "
            "Population remains PA>=9 starter cohort (opener bias unresolved)."
        ),
    }
    if model_name == "lightgbm":
        model.booster_.save_model(stem.with_suffix(".txt"))
        stem.with_suffix(".json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        print(f"Saved model and metadata to {stem.with_suffix('.txt')}")
    else:
        stem.with_suffix(".json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        print(f"Saved evaluation metadata to {stem.with_suffix('.json')}")
        if persist and model_name == "ridge":
            import joblib

            joblib_path = stem.with_suffix(".joblib")
            joblib.dump(
                {
                    "model": model,
                    "features": features,
                    "feature_set": feature_set,
                    "ridge_alpha": selected_alpha,
                    "prediction_upper_clip": upper,
                    "target": TBF_TARGET,
                },
                joblib_path,
            )
            payload["joblib_path"] = str(joblib_path)
            stem.with_suffix(".json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            (quality_dir / "latest_ridge.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
            print(f"Persisted Ridge pipeline to {joblib_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        choices=("lightgbm", "ridge", "elasticnet", "poisson", "mean"),
        default="ridge",
    )
    parser.add_argument(
        "--feature-set",
        choices=TBF_FEATURE_SETS,
        default=TBF_DEFAULT_FEATURE_SET,
        help=(
            "Frozen default: workload_context_bullpen (thin pen). "
            "workload_context_bullpen_rich keeps L/R/B2B/max enrichment for ablation."
        ),
    )
    parser.add_argument(
        "--tune-alpha",
        action="store_true",
        help="Phase 11.A: select Ridge alpha on chronological validation MAE.",
    )
    parser.add_argument(
        "--ridge-alpha",
        type=float,
        default=1.0,
        help="Fixed Ridge alpha when --tune-alpha is not set.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Write Ridge sklearn pipeline to joblib (required for reproducible backtests).",
    )
    args = parser.parse_args()
    main(
        args.model,
        feature_set=args.feature_set,
        tune_alpha=args.tune_alpha,
        persist=args.persist,
        ridge_alpha=args.ridge_alpha,
    )
