"""Select discipline windows on inner folds and confirm them on outer folds."""

from __future__ import annotations

import json

import pandas as pd

from Python import config
from Python.features import TARGET, model_feature_names

from feature_ablation import (
    _families,
    _metrics,
    _models,
    _select_from_inner_results,
)
from nested_cv import fold_metadata, nested_research_folds


def _select(columns: list[str], *suffixes: str) -> list[str]:
    return [
        column
        for column in columns
        if any(column.endswith(suffix) for suffix in suffixes)
    ]


def main() -> None:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values("game_date")
        .loc[lambda value: value["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .copy()
    )
    if tuple(sorted(frame["season"].unique())) != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError("window research is not restricted to configured dev seasons")

    features = list(model_feature_names(frame, include_experimental=True))
    families = _families(features)
    candidate_columns = {
        feature for family in families.values() for feature in family
    }
    core = [feature for feature in features if feature not in candidate_columns]
    whiff = families["pitcher_whiff"]
    swstr = families["pitcher_swstr"]
    ball = families["pitcher_ball"]
    batted_ball = families["batted_ball"]
    count_state = families["count_state"]
    siera = families["siera"]
    arm_angle = families["arm_angle"]
    run_value = families["run_value"]

    configurations = {
        "core": core,
        "whiff_P5": [*core, *_select(whiff, "_P5")],
        "whiff_P10": [*core, *_select(whiff, "_P10")],
        "whiff_P20": [*core, *_select(whiff, "_P20")],
        "whiff_std": [*core, *_select(whiff, "_std")],
        "whiff_P5_P10": [*core, *_select(whiff, "_P5", "_P10")],
        "swstr_P5": [*core, *_select(swstr, "_P5")],
        "swstr_P10": [*core, *_select(swstr, "_P10")],
        "swstr_P20": [*core, *_select(swstr, "_P20")],
        "swstr_std": [*core, *_select(swstr, "_std")],
        "swstr_P5_P10": [*core, *_select(swstr, "_P5", "_P10")],
        "ball_P5": [*core, *_select(ball, "_P5")],
        "ball_P20": [*core, *_select(ball, "_P20")],
        "ball_std": [*core, *_select(ball, "_std")],
        "whiff_swstr_P20": [
            *core,
            *_select(whiff, "_P20"),
            *_select(swstr, "_P20"),
        ],
        "discipline_short": [
            *core,
            *_select(whiff, "_P5"),
            *_select(swstr, "_P5"),
            *_select(ball, "_P5"),
        ],
        "discipline_short_long": [
            *core,
            *_select(whiff, "_P5", "_P10"),
            *_select(swstr, "_P5", "_P10"),
            *_select(ball, "_P5", "_std"),
        ],
        "batted_ball_P5": [*core, *_select(batted_ball, "_P5")],
        "batted_ball_P10": [*core, *_select(batted_ball, "_P10")],
        "batted_ball_P20": [*core, *_select(batted_ball, "_P20")],
        "batted_ball_std": [*core, *_select(batted_ball, "_std")],
        "count_state_P5": [*core, *_select(count_state, "_P5")],
        "count_state_P10": [*core, *_select(count_state, "_P10")],
        "count_state_P20": [*core, *_select(count_state, "_P20")],
        "count_state_std": [*core, *_select(count_state, "_std")],
        "siera_P3": [*core, *_select(siera, "_P3")],
        "siera_P5": [*core, *_select(siera, "_P5")],
        "siera_P10": [*core, *_select(siera, "_P10")],
        "arm_angle_P3": [*core, *_select(arm_angle, "_P3")],
        "arm_angle_P5": [*core, *_select(arm_angle, "_P5")],
        "arm_angle_P10": [*core, *_select(arm_angle, "_P10")],
        "run_value_P3": [*core, *_select(run_value, "_P3")],
        "run_value_P5": [*core, *_select(run_value, "_P5")],
        "run_value_P10": [*core, *_select(run_value, "_P10")],
    }
    for name, selected in configurations.items():
        if name != "core" and len(selected) == len(core):
            raise ValueError(f"window configuration {name} selected no candidates")

    folds = nested_research_folds(frame)
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

    inner_results = pd.DataFrame(inner_rows)
    selections = _select_from_inner_results(inner_results)

    outer_rows: list[dict[str, object]] = []
    for selection in selections.itertuples(index=False):
        outer = folds[selection.outer_fold].outer
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

    results = pd.DataFrame(outer_rows)
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
    output_dir = config.OUTPUT_DIR / "feature_research" / "expanded"
    output_dir.mkdir(parents=True, exist_ok=True)
    inner_results.to_csv(
        output_dir / "window_ablation_inner_results.csv",
        index=False,
    )
    selections.to_csv(
        output_dir / "window_ablation_inner_selection.csv",
        index=False,
    )
    results.to_csv(output_dir / "window_ablation_results.csv", index=False)
    aggregate.to_csv(output_dir / "window_ablation_aggregate.csv", index=False)
    (output_dir / "window_ablation_metadata.json").write_text(
        json.dumps(
            {
                "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
                "holdout_season_not_read": config.HOLDOUT_SEASON,
                "selection_metric": "mean inner-fold MAE",
                "outer_data_used_for_selection": False,
                "retired_api": "_research_folds removed; use nested_research_folds",
                "folds": fold_metadata(folds),
                "configurations": {
                    name: selected[len(core) :]
                    for name, selected in configurations.items()
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(aggregate.to_string(index=False))
    print(f"Wrote window research outputs to {output_dir}")


if __name__ == "__main__":
    main()
