"""Nested chronological comparison of unweighted vs PA-weighted k_rate fits.

Step 5 diagnostic: same features and nested_research_folds, only the sample-
weight mode changes. Always scores both unweighted and PA-weighted metrics so
arms can be compared on either rule. Does not use 2025 rows.

Examples:
    python Models/Strikeout-Model/Strikeout-EDA/pa_weight_nested_compare.py
    python Models/Strikeout-Model/Strikeout-EDA/pa_weight_nested_compare.py --models ridge
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from Python import config
from Python.features import TARGET, model_feature_names
from Python.training import (
    SAMPLE_WEIGHT_MODES,
    assert_pa_not_in_features,
    build_model,
    fit_regressor,
    lightgbm_matrix,
    partition_metrics,
    predict_clipped,
    resolve_sample_weights,
)

EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from nested_cv import fold_metadata, nested_research_folds  # noqa: E402


def _flatten_metrics(block: dict[str, dict[str, float]]) -> dict[str, float]:
    flat: dict[str, float] = {}
    for scoring, values in block.items():
        for name, value in values.items():
            flat[f"{scoring}_{name}"] = value
    return flat


def _fit_fold_model(
    model_name: str,
    train: pd.DataFrame,
    features: list[str],
    sample_weight_mode: str,
) -> object:
    model = build_model(
        model_name,
        lightgbm_n_estimators=800,
        lightgbm_verbosity=-1,
    )
    train_weight = resolve_sample_weights(train, sample_weight_mode)
    if model_name == "lightgbm":
        fit_regressor(
            model,
            model_name,
            lightgbm_matrix(train, features),
            train[TARGET],
            train_weight=train_weight,
        )
    else:
        fit_regressor(
            model,
            model_name,
            train[features],
            train[TARGET],
            train_weight=train_weight,
        )
    return model


def _evaluate(
    model,
    model_name: str,
    frame: pd.DataFrame,
    features: list[str],
) -> dict[str, dict[str, float]]:
    prediction = predict_clipped(model, model_name, frame, features)
    pa_weights = resolve_sample_weights(frame, "pa")
    return partition_metrics(
        frame[TARGET],
        prediction,
        pa_weights=pa_weights,
        include_pa_weighted=True,
    )


def main(models: tuple[str, ...]) -> None:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date", "PA"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    frame = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )

    features = list(model_feature_names(frame))
    assert_pa_not_in_features(features)
    folds = nested_research_folds(frame)

    output_dir = config.OUTPUT_DIR / "feature_research" / "step5_pa_weight"
    output_dir.mkdir(parents=True, exist_ok=True)

    outer_rows: list[dict[str, object]] = []
    inner_rows: list[dict[str, object]] = []

    for outer_name, nested in folds.items():
        for model_name in models:
            for weight_mode in SAMPLE_WEIGHT_MODES:
                # Inner folds: score each selection fold for transparency.
                for inner_name, inner in nested.inner.items():
                    model = _fit_fold_model(
                        model_name, inner.train, features, weight_mode
                    )
                    scored = _evaluate(
                        model, model_name, inner.validation, features
                    )
                    inner_rows.append(
                        {
                            "outer_fold": outer_name,
                            "inner_fold": inner_name,
                            "model": model_name,
                            "sample_weight": weight_mode,
                            "n_features": len(features),
                            "train_rows": len(inner.train),
                            "validation_rows": len(inner.validation),
                            **_flatten_metrics(scored),
                        }
                    )
                    print(
                        "inner",
                        outer_name,
                        inner_name,
                        model_name,
                        weight_mode,
                        scored["unweighted"],
                    )

                # Outer confirmation: refit on outer train, score outer val.
                model = _fit_fold_model(
                    model_name, nested.outer.train, features, weight_mode
                )
                scored = _evaluate(
                    model, model_name, nested.outer.validation, features
                )
                outer_rows.append(
                    {
                        "outer_fold": outer_name,
                        "model": model_name,
                        "sample_weight": weight_mode,
                        "n_features": len(features),
                        "train_rows": len(nested.outer.train),
                        "validation_rows": len(nested.outer.validation),
                        **_flatten_metrics(scored),
                    }
                )
                print(
                    "outer",
                    outer_name,
                    model_name,
                    weight_mode,
                    scored["unweighted"],
                )

    inner_results = pd.DataFrame(inner_rows)
    outer_results = pd.DataFrame(outer_rows)
    inner_results.to_csv(output_dir / "inner_results.csv", index=False)
    outer_results.to_csv(output_dir / "outer_results.csv", index=False)

    # Prefer lower unweighted MAE for the headline aggregate; PA-weighted
    # columns remain available for likelihood-oriented inspection.
    aggregate = (
        outer_results.groupby(["model", "sample_weight"], as_index=False)
        .agg(
            outer_folds=("outer_fold", "nunique"),
            mean_unweighted_mae=("unweighted_mae", "mean"),
            mean_unweighted_rmse=("unweighted_rmse", "mean"),
            mean_unweighted_r2=("unweighted_r2", "mean"),
            mean_pa_weighted_mae=("pa_weighted_mae", "mean"),
            mean_pa_weighted_rmse=("pa_weighted_rmse", "mean"),
            mean_pa_weighted_r2=("pa_weighted_r2", "mean"),
        )
        .sort_values(["model", "mean_unweighted_mae", "sample_weight"])
    )
    aggregate.to_csv(output_dir / "aggregate.csv", index=False)

    # Pairwise delta: pa arm minus none arm on each outer fold / model.
    none = outer_results[outer_results["sample_weight"] == "none"].set_index(
        ["outer_fold", "model"]
    )
    pa = outer_results[outer_results["sample_weight"] == "pa"].set_index(
        ["outer_fold", "model"]
    )
    delta_rows: list[dict[str, object]] = []
    for key in none.index.intersection(pa.index):
        delta_rows.append(
            {
                "outer_fold": key[0],
                "model": key[1],
                "delta_unweighted_mae": (
                    pa.loc[key, "unweighted_mae"] - none.loc[key, "unweighted_mae"]
                ),
                "delta_unweighted_rmse": (
                    pa.loc[key, "unweighted_rmse"]
                    - none.loc[key, "unweighted_rmse"]
                ),
                "delta_unweighted_r2": (
                    pa.loc[key, "unweighted_r2"] - none.loc[key, "unweighted_r2"]
                ),
                "delta_pa_weighted_mae": (
                    pa.loc[key, "pa_weighted_mae"]
                    - none.loc[key, "pa_weighted_mae"]
                ),
                "delta_pa_weighted_rmse": (
                    pa.loc[key, "pa_weighted_rmse"]
                    - none.loc[key, "pa_weighted_rmse"]
                ),
                "delta_pa_weighted_r2": (
                    pa.loc[key, "pa_weighted_r2"] - none.loc[key, "pa_weighted_r2"]
                ),
            }
        )
    deltas = pd.DataFrame(delta_rows)
    deltas.to_csv(output_dir / "pa_minus_none_deltas.csv", index=False)

    metadata = {
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "sample_weight_modes": list(SAMPLE_WEIGHT_MODES),
        "models": list(models),
        "n_features": len(features),
        "feature_gate": "model_feature_names(include_experimental=False)",
        "lightgbm_n_estimators": 800,
        "early_stopping": False,
        "selection_note": (
            "No configuration search; compares sample-weight modes only on the "
            "production feature allow-list and nested_research_folds."
        ),
        "folds": fold_metadata(folds),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(aggregate.to_string(index=False))
    if not deltas.empty:
        print(deltas.to_string(index=False))
    print(f"Wrote Step 5 PA-weight nested comparison to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--models",
        nargs="+",
        choices=("ridge", "lightgbm", "mean"),
        default=["ridge", "lightgbm"],
    )
    args = parser.parse_args()
    main(tuple(args.models))
