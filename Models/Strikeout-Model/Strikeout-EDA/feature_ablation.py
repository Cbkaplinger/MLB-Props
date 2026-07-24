"""Protected 2023-to-2024 screening of plate-discipline feature families.

This is feature research, not final model training. It never reads 2025 rows.
The fixed Ridge and LightGBM estimators compare candidate families against a
common core while correlation outputs quantify within-family redundancy.
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from Python import config
from Python.features import TARGET, model_feature_names


def _metrics(actual: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    prediction = np.clip(prediction, 0, 1)
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "rmse": float(mean_squared_error(actual, prediction) ** 0.5),
        "r2": float(r2_score(actual, prediction)),
    }


def _families(features: list[str]) -> dict[str, list[str]]:
    definitions = {
        "pitcher_whiff": ("whiff_rate_",),
        "pitcher_swstr": ("swstr_rate_",),
        "pitcher_ball": ("ball_rate_",),
        "pitcher_gb": ("gb_rate_",),
        "batter_whiff": ("opp_lineup_whiff",),
        "batter_swstr": ("opp_lineup_swstr",),
    }
    return {
        name: [
            feature
            for feature in features
            if any(
                feature == prefix or feature.startswith(prefix)
                for prefix in prefixes
            )
        ]
        for name, prefixes in definitions.items()
    }


def _configurations(
    features: list[str],
    families: dict[str, list[str]],
) -> dict[str, list[str]]:
    candidate_columns = {
        feature for family in families.values() for feature in family
    }
    core = [feature for feature in features if feature not in candidate_columns]

    def with_families(*names: str) -> list[str]:
        selected = [feature for name in names for feature in families[name]]
        return [*core, *selected]

    compact = [
        feature
        for name in ("pitcher_whiff", "pitcher_swstr", "pitcher_ball")
        for feature in families[name]
        if feature.endswith("_P20")
    ]
    compact.extend(families["batter_whiff"])
    compact.extend(families["batter_swstr"])

    return {
        "core": core,
        "pitcher_whiff": with_families("pitcher_whiff"),
        "pitcher_swstr": with_families("pitcher_swstr"),
        "pitcher_both": with_families("pitcher_whiff", "pitcher_swstr"),
        "batter_whiff": with_families("batter_whiff"),
        "batter_swstr": with_families("batter_swstr"),
        "batter_both": with_families("batter_whiff", "batter_swstr"),
        "pitcher_ball": with_families("pitcher_ball"),
        "pitcher_gb": with_families("pitcher_gb"),
        "preferred_raw": with_families(
            "pitcher_swstr",
            "batter_whiff",
            "pitcher_ball",
            "pitcher_gb",
        ),
        "compact_candidate": [*core, *compact],
        "all_candidates": features,
    }


def _models() -> dict[str, object]:
    return {
        "ridge": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=1.0),
        ),
        "lightgbm": lgb.LGBMRegressor(
            objective="regression",
            n_estimators=800,
            learning_rate=0.03,
            num_leaves=31,
            min_child_samples=50,
            subsample=0.8,
            colsample_bytree=0.7,
            reg_alpha=0.1,
            reg_lambda=2.0,
            random_state=42,
            verbosity=-1,
            n_jobs=-1,
        ),
    }


def _correlation_report(
    frame: pd.DataFrame,
    families: dict[str, list[str]],
) -> pd.DataFrame:
    candidates = [feature for group in families.values() for feature in group]
    correlation = frame[candidates].corr(min_periods=100)
    rows = []
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            value = correlation.loc[left, right]
            rows.append(
                {
                    "left": left,
                    "right": right,
                    "correlation": float(value) if pd.notna(value) else np.nan,
                    "abs_correlation": (
                        float(abs(value)) if pd.notna(value) else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(
        "abs_correlation",
        ascending=False,
        na_position="last",
    )


def _research_folds(
    frame: pd.DataFrame,
) -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    """Return expanding, date-disjoint folds contained entirely in dev data."""
    july_2023 = pd.Timestamp("2023-07-01")
    start_2024 = pd.Timestamp("2024-01-01")
    july_2024 = pd.Timestamp("2024-07-01")
    folds = {
        "2023_h2": (
            frame[frame["game_date"] < july_2023],
            frame[
                (frame["game_date"] >= july_2023)
                & (frame["game_date"] < start_2024)
            ],
        ),
        "2024_h1": (
            frame[frame["game_date"] < start_2024],
            frame[
                (frame["game_date"] >= start_2024)
                & (frame["game_date"] < july_2024)
            ],
        ),
        "2024_h2": (
            frame[frame["game_date"] < july_2024],
            frame[frame["game_date"] >= july_2024],
        ),
    }
    for name, (train, validation) in folds.items():
        if train.empty or validation.empty:
            raise ValueError(f"research fold {name} produced an empty partition")
        if train["game_date"].max() >= validation["game_date"].min():
            raise ValueError(f"research fold {name} has overlapping dates")
    return folds


def main() -> None:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = frame.dropna(subset=[TARGET, "game_date"]).sort_values("game_date")
    frame = frame[frame["season"].isin(config.FEATURE_RESEARCH_SEASONS)].copy()
    observed_seasons = tuple(sorted(frame["season"].unique()))
    if observed_seasons != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected {config.FEATURE_RESEARCH_SEASONS}, got {observed_seasons}"
        )

    folds = _research_folds(frame)

    features = list(model_feature_names(frame))
    families = _families(features)
    missing = [name for name, columns in families.items() if not columns]
    if missing:
        raise ValueError(f"candidate feature families are empty: {missing}")
    configurations = _configurations(features, families)

    output_dir = config.OUTPUT_DIR / "feature_research"
    output_dir.mkdir(parents=True, exist_ok=True)
    correlations = _correlation_report(frame, families)
    correlations.to_csv(output_dir / "candidate_correlations.csv", index=False)

    rows: list[dict[str, object]] = []
    for fold, (train, validation) in folds.items():
        for model_name in _models():
            for configuration, selected in configurations.items():
                # Estimators are rebuilt each iteration to avoid fitted-state reuse.
                model = _models()[model_name]
                model.fit(train[selected], train[TARGET])
                result = _metrics(
                    validation[TARGET],
                    model.predict(validation[selected]),
                )
                rows.append(
                    {
                        "fold": fold,
                        "model": model_name,
                        "configuration": configuration,
                        "n_features": len(selected),
                        "train_rows": len(train),
                        "validation_rows": len(validation),
                        **result,
                    }
                )
                print(fold, model_name, configuration, result)

    results = pd.DataFrame(rows)
    core = (
        results[results["configuration"] == "core"]
        .set_index(["fold", "model"])[["mae", "rmse", "r2"]]
        .rename(columns=lambda column: f"core_{column}")
    )
    results = results.join(core, on=["fold", "model"])
    results["mae_improvement_vs_core"] = results["core_mae"] - results["mae"]
    results["rmse_improvement_vs_core"] = (
        results["core_rmse"] - results["rmse"]
    )
    results["r2_improvement_vs_core"] = results["r2"] - results["core_r2"]
    results = results.drop(columns=["core_mae", "core_rmse", "core_r2"])
    results.to_csv(output_dir / "candidate_ablation_results.csv", index=False)
    aggregate = (
        results.groupby(["model", "configuration"], as_index=False)
        .agg(
            n_features=("n_features", "first"),
            folds=("fold", "nunique"),
            mean_mae=("mae", "mean"),
            mean_rmse=("rmse", "mean"),
            mean_r2=("r2", "mean"),
            mean_mae_improvement=("mae_improvement_vs_core", "mean"),
            mean_rmse_improvement=("rmse_improvement_vs_core", "mean"),
            mean_r2_improvement=("r2_improvement_vs_core", "mean"),
            positive_mae_folds=(
                "mae_improvement_vs_core",
                lambda values: int((values > 0).sum()),
            ),
        )
        .sort_values(["model", "mean_mae"])
    )
    aggregate.to_csv(
        output_dir / "candidate_ablation_aggregate.csv",
        index=False,
    )

    metadata = {
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "folds": {
            name: {
                "train_range": [
                    str(train["game_date"].min().date()),
                    str(train["game_date"].max().date()),
                ],
                "validation_range": [
                    str(validation["game_date"].min().date()),
                    str(validation["game_date"].max().date()),
                ],
            }
            for name, (train, validation) in folds.items()
        },
        "families": families,
        "configurations": {
            name: len(selected) for name, selected in configurations.items()
        },
    }
    (output_dir / "candidate_ablation_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(aggregate.to_string(index=False))
    print(correlations.head(20).to_string(index=False))
    print(f"Wrote feature research outputs to {output_dir}")


if __name__ == "__main__":
    main()
