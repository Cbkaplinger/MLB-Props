"""Train leakage-safe pitcher strikeout-rate models from the Level 3 artifact.

Examples:
    python models/Strikeout-Model/train.py --model lightgbm
    python models/Strikeout-Model/train.py --model ridge
    python models/Strikeout-Model/train.py --model mean
    python models/Strikeout-Model/train.py --model ridge --sample-weight pa
    python models/Strikeout-Model/train.py --model ridge --feature-set ridge_vif
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from Python.config import (
    MODEL_DIR,
    PITCHER_TRAINING_PATH,
    TRAIN_SEASONS,
    ensure_output_directories,
)
from Python.features import TARGET, model_feature_names
from Python.registries import FEATURE_SETS, resolve_feature_names
from Python.training import (
    SAMPLE_WEIGHT_MODES,
    assert_pa_not_in_features,
    build_model,
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    partition_metrics,
    predict_clipped,
    resolve_sample_weights,
)

_MONO_POSITIVE_STEMS = (
    "opp_lineup_k",
    "opp_lineup_k_vs_hand",
    "opp_lineup_whiff",
    "opp_lineup_swstr",
    "opp_lineup_chase",
    "park_k_factor",
)
_MONO_NEGATIVE_STEMS = (
    "xERA",
    "ERA",
    "BB_per_9",
    "xwOBA",
    "xBA",
    "wOBA",
    "xSLG",
    "avg_exit_velocity",
    "barrel_batted_rate",
    "hard_hit_percent",
)


def _feature_constraints(features: list[str]) -> list[int]:
    out: list[int] = []
    for feature in features:
        if any(feature == stem or feature.startswith(stem) for stem in _MONO_POSITIVE_STEMS):
            out.append(1)
        elif any(feature == stem or feature.startswith(stem) for stem in _MONO_NEGATIVE_STEMS):
            out.append(-1)
        else:
            out.append(0)
    return out


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_frame(
    feature_set: str = "production",
) -> tuple[pd.DataFrame, list[str]]:
    """Load Level 3 and return chronologically sorted rows plus safe features."""
    if not PITCHER_TRAINING_PATH.exists():
        raise FileNotFoundError(
            f"Missing {PITCHER_TRAINING_PATH}. Run all three pipeline stages first."
        )
    frame = pd.read_parquet(PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.loc[frame["season"].isin(TRAIN_SEASONS)]
        .dropna(subset=[TARGET, "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    observed_seasons = tuple(sorted(frame["season"].unique()))
    if observed_seasons != TRAIN_SEASONS:
        raise ValueError(
            f"expected configured training seasons {TRAIN_SEASONS}, "
            f"got {observed_seasons}"
        )
    return frame, list(resolve_feature_names(frame, feature_set))


def fit_model(
    model,
    model_name: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
    train_weight,
    validation_weight,
) -> None:
    """Fit one production model with optional PA weights and early stopping."""
    if model_name == "lightgbm":
        fit_regressor(
            model,
            model_name,
            lightgbm_matrix(train, features),
            train[TARGET],
            train_weight=train_weight,
            validation_features=lightgbm_matrix(validation, features),
            validation_target=validation[TARGET],
            validation_weight=validation_weight,
            early_stopping_rounds=200,
            log_evaluation_period=50,
        )
        return
    fit_regressor(
        model,
        model_name,
        train[features],
        train[TARGET],
        train_weight=train_weight,
    )


def main(
    model_name: str,
    sample_weight: str = "none",
    feature_set: str = "production",
    monotone: bool = False,
) -> None:
    if sample_weight not in SAMPLE_WEIGHT_MODES:
        raise ValueError(
            f"unsupported sample-weight mode {sample_weight!r}; "
            f"expected one of {SAMPLE_WEIGHT_MODES}"
        )
    if feature_set not in FEATURE_SETS:
        raise ValueError(
            f"unsupported feature set {feature_set!r}; "
            f"expected one of {FEATURE_SETS}"
        )

    frame, features = load_frame(feature_set=feature_set)
    assert_pa_not_in_features(features)

    train, validation, test = chronological_split(frame)
    train_weight = resolve_sample_weights(train, sample_weight)
    validation_weight = resolve_sample_weights(validation, sample_weight)
    test_weight = resolve_sample_weights(test, sample_weight)

    lightgbm_params: dict[str, object] | None = None
    if model_name == "lightgbm" and monotone:
        lightgbm_params = {
            "monotone_constraints": _feature_constraints(features),
            "monotone_constraints_method": "advanced",
        }
    model = build_model(model_name, lightgbm_params=lightgbm_params)
    fit_model(
        model,
        model_name,
        train,
        validation,
        features,
        train_weight,
        validation_weight,
    )

    validation_pred = predict_clipped(model, model_name, validation, features)
    test_pred = predict_clipped(model, model_name, test, features)
    # Always score PA-weighted metrics when PA is present so arms are comparable.
    validation_pa = resolve_sample_weights(validation, "pa")
    test_pa = resolve_sample_weights(test, "pa")

    report = {
        "model": model_name,
        "sample_weight": sample_weight,
        "feature_set": feature_set,
        "monotone_constraints": bool(monotone),
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
        "validation": partition_metrics(
            validation[TARGET],
            validation_pred,
            pa_weights=validation_pa,
            include_pa_weighted=True,
        ),
        "test": partition_metrics(
            test[TARGET],
            test_pred,
            pa_weights=test_pa,
            include_pa_weighted=True,
        ),
    }
    if train_weight is not None:
        report["weight_summary"] = {
            "train_pa_sum": float(train_weight.sum()),
            "train_pa_mean": float(train_weight.mean()),
            "validation_pa_mean": float(validation_weight.mean()),
            "test_pa_mean": float(test_weight.mean()),
        }
    print(json.dumps(report, indent=2))

    if model_name == "lightgbm":
        ensure_output_directories()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        weight_tag = "" if sample_weight == "none" else f"_{sample_weight}w"
        mono_tag = "_mono" if monotone else ""
        model_path = MODEL_DIR / f"lightgbm_krate{weight_tag}{mono_tag}_{stamp}.txt"
        model.booster_.save_model(model_path)
        metadata = {
            "features": features,
            "evaluation": report,
            "registry_freeze": {
                "status": "frozen" if feature_set == "production" else "not_frozen",
                "feature_set": feature_set,
                "n_features": len(features),
                "approved_utc": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "training_artifact": str(PITCHER_TRAINING_PATH),
                "training_artifact_sha256": _sha256(PITCHER_TRAINING_PATH),
                "train_seasons": list(TRAIN_SEASONS),
                "sample_weight": sample_weight,
                "monotone_constraints": bool(monotone),
                "mean_window_policy": (
                    "P3/P5 for pitch_physics, pitch_usage, mechanics, fip_xfip "
                    "(P10 dropped at feature selection; Level 2 may still store P10)"
                    if feature_set == "production"
                    else "unchanged for this feature_set"
                ),
                "post_freeze_evaluation_policy": (
                    "Do not use previously scored 2025 rows as a pristine test; "
                    "reserve genuinely future post-freeze games."
                ),
            },
        }
        model_path.with_suffix(".json").write_text(
            json.dumps(metadata, indent=2),
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
    parser.add_argument(
        "--sample-weight",
        choices=SAMPLE_WEIGHT_MODES,
        default="none",
        help=(
            "Training-row weights. 'none' is the unweighted baseline; "
            "'pa' passes same-game PA as sample_weight (never as a feature)."
        ),
    )
    parser.add_argument(
        "--feature-set",
        choices=FEATURE_SETS,
        default="production",
        help=(
            "Feature registry. 'production' is Step 10 P1 spine + Step 11 "
            "discipline lift (184 features); 'step10_180' is the prior freeze; "
            "'step7_185' is the pre-P1 freeze; 'pre_freeze_248' is the prior "
            "full allow-list; 'ridge_vif' is the Step 1 Ridge research registry."
        ),
    )
    parser.add_argument(
        "--monotone",
        action="store_true",
        help="Apply monotone constraints for LightGBM features.",
    )
    args = parser.parse_args()
    main(
        args.model,
        sample_weight=args.sample_weight,
        feature_set=args.feature_set,
        monotone=args.monotone,
    )
