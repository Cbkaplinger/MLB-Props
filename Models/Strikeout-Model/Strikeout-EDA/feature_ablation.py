"""Protected 2023-to-2024 screening of plate-discipline feature families.

This is feature research, not final model training. It never uses 2025 rows.
Inner chronological folds select among fixed Ridge/LightGBM configurations;
distinct outer folds report confirmation against a common core.
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

from nested_cv import fold_metadata, nested_research_folds


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
        "batted_ball": ("bip_rate_", "babip_"),
        "count_state": (
            "first_pitch_strike_rate_",
            "ahead_rate_",
            "behind_rate_",
            "two_strike_reach_rate_",
            "putaway_rate_",
        ),
        "siera": ("siera_mlb_",),
        "arm_angle": ("arm_angle_",),
        "run_value": ("rv_per_100_",),
    }
    families = {
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
    families["p2_arsenal"] = [
        feature
        for feature in features
        if feature.startswith("has_thrown_")
        or (feature.endswith("_usage_P2") and "_v" not in feature)
    ]
    return families


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

    revised_compact = [
        feature
        for feature in families["pitcher_ball"]
        if feature.endswith("_P5")
    ]
    revised_compact.extend(
        feature
        for feature in families["pitcher_swstr"]
        if feature.endswith("_P20")
    )
    revised_compact.extend(families["batter_whiff"])
    revised_compact.extend(families["batter_swstr"])

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
        "revised_compact": [*core, *revised_compact],
        "p2_arsenal": with_families("p2_arsenal"),
        "batted_ball": with_families("batted_ball"),
        "count_state": with_families("count_state"),
        "siera": with_families("siera"),
        "arm_angle": with_families("arm_angle"),
        "run_value": with_families("run_value"),
        "expanded_all": with_families(
            "p2_arsenal",
            "batted_ball",
            "count_state",
            "siera",
            "arm_angle",
            "run_value",
        ),
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


def _select_from_inner_results(results: pd.DataFrame) -> pd.DataFrame:
    """Select one configuration per outer fold/model using inner MAE only."""
    aggregate = (
        results.groupby(
            ["outer_fold", "model", "configuration"],
            as_index=False,
        )
        .agg(
            n_features=("n_features", "first"),
            inner_folds=("inner_fold", "nunique"),
            inner_mean_mae=("mae", "mean"),
            inner_mean_rmse=("rmse", "mean"),
            inner_mean_r2=("r2", "mean"),
        )
        .sort_values(
            [
                "outer_fold",
                "model",
                "inner_mean_mae",
                "n_features",
                "configuration",
            ]
        )
    )
    return aggregate.drop_duplicates(["outer_fold", "model"], keep="first")


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

    folds = nested_research_folds(frame)

    features = list(model_feature_names(frame, include_experimental=True))
    families = _families(features)
    missing = [name for name, columns in families.items() if not columns]
    if missing:
        raise ValueError(f"candidate feature families are empty: {missing}")
    configurations = _configurations(features, families)

    output_dir = config.OUTPUT_DIR / "feature_research" / "expanded"
    output_dir.mkdir(parents=True, exist_ok=True)

    inner_rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        for inner_name, inner in nested.inner.items():
            for model_name in _models():
                for configuration, selected in configurations.items():
                    model = _models()[model_name]
                    model.fit(inner.train[selected], inner.train[TARGET])
                    result = _metrics(
                        inner.validation[TARGET],
                        model.predict(inner.validation[selected]),
                    )
                    inner_rows.append(
                        {
                            "outer_fold": outer_name,
                            "inner_fold": inner_name,
                            "model": model_name,
                            "configuration": configuration,
                            "n_features": len(selected),
                            "train_rows": len(inner.train),
                            "validation_rows": len(inner.validation),
                            **result,
                        }
                    )
                    print(
                        "inner",
                        outer_name,
                        inner_name,
                        model_name,
                        configuration,
                        result,
                    )

    inner_results = pd.DataFrame(inner_rows)
    inner_results.to_csv(
        output_dir / "candidate_ablation_inner_results.csv",
        index=False,
    )
    selections = _select_from_inner_results(inner_results)
    selections.to_csv(
        output_dir / "candidate_ablation_inner_selection.csv",
        index=False,
    )

    outer_rows: list[dict[str, object]] = []
    for selection in selections.itertuples(index=False):
        nested = folds[selection.outer_fold]
        outer = nested.outer
        selected = configurations[selection.configuration]
        selected_model = _models()[selection.model]
        selected_model.fit(outer.train[selected], outer.train[TARGET])
        selected_metrics = _metrics(
            outer.validation[TARGET],
            selected_model.predict(outer.validation[selected]),
        )

        core_features = configurations["core"]
        core_model = _models()[selection.model]
        core_model.fit(outer.train[core_features], outer.train[TARGET])
        core_metrics = _metrics(
            outer.validation[TARGET],
            core_model.predict(outer.validation[core_features]),
        )
        outer_rows.append(
            {
                "outer_fold": selection.outer_fold,
                "model": selection.model,
                "selected_configuration": selection.configuration,
                "n_features": len(selected),
                "train_rows": len(outer.train),
                "validation_rows": len(outer.validation),
                "inner_mean_mae": selection.inner_mean_mae,
                "inner_mean_rmse": selection.inner_mean_rmse,
                "inner_mean_r2": selection.inner_mean_r2,
                "mae": selected_metrics["mae"],
                "rmse": selected_metrics["rmse"],
                "r2": selected_metrics["r2"],
                "mae_improvement_vs_core": core_metrics["mae"]
                - selected_metrics["mae"],
                "rmse_improvement_vs_core": core_metrics["rmse"]
                - selected_metrics["rmse"],
                "r2_improvement_vs_core": selected_metrics["r2"]
                - core_metrics["r2"],
            }
        )
        print("outer", selection.outer_fold, selection.model, outer_rows[-1])

    results = pd.DataFrame(outer_rows)
    results.to_csv(output_dir / "candidate_ablation_results.csv", index=False)
    aggregate = (
        results.groupby(["model"], as_index=False)
        .agg(
            outer_folds=("outer_fold", "nunique"),
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
        .sort_values("mean_mae")
    )
    aggregate.to_csv(
        output_dir / "candidate_ablation_aggregate.csv",
        index=False,
    )

    metadata = {
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "selection_metric": "mean inner-fold MAE",
        "outer_data_used_for_selection": False,
        "retired_api": "_research_folds removed; use nested_research_folds",
        "folds": fold_metadata(folds),
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
    print(f"Wrote feature research outputs to {output_dir}")


if __name__ == "__main__":
    main()
