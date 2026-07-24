"""Screen nonredundant pitcher discipline windows inside 2023-2024."""

from __future__ import annotations

import json

import pandas as pd

from Python import config
from Python.features import TARGET, model_feature_names

from feature_ablation import _families, _metrics, _models, _research_folds


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

    features = list(model_feature_names(frame))
    families = _families(features)
    candidate_columns = {
        feature for family in families.values() for feature in family
    }
    core = [feature for feature in features if feature not in candidate_columns]
    whiff = families["pitcher_whiff"]
    swstr = families["pitcher_swstr"]
    ball = families["pitcher_ball"]

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
    }
    for name, selected in configurations.items():
        if name != "core" and len(selected) == len(core):
            raise ValueError(f"window configuration {name} selected no candidates")

    rows: list[dict[str, object]] = []
    folds = _research_folds(frame)
    for fold, (train, validation) in folds.items():
        for model_name in _models():
            for configuration, selected in configurations.items():
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
                        **result,
                    }
                )

    results = pd.DataFrame(rows)
    core_scores = (
        results[results["configuration"] == "core"]
        .set_index(["fold", "model"])[["mae", "rmse", "r2"]]
        .rename(columns=lambda column: f"core_{column}")
    )
    results = results.join(core_scores, on=["fold", "model"])
    results["mae_improvement_vs_core"] = results["core_mae"] - results["mae"]
    results["rmse_improvement_vs_core"] = (
        results["core_rmse"] - results["rmse"]
    )
    results["r2_improvement_vs_core"] = results["r2"] - results["core_r2"]
    results = results.drop(columns=["core_mae", "core_rmse", "core_r2"])

    aggregate = (
        results.groupby(["model", "configuration"], as_index=False)
        .agg(
            n_features=("n_features", "first"),
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
    output_dir = config.OUTPUT_DIR / "feature_research"
    output_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(output_dir / "window_ablation_results.csv", index=False)
    aggregate.to_csv(output_dir / "window_ablation_aggregate.csv", index=False)
    (output_dir / "window_ablation_metadata.json").write_text(
        json.dumps(
            {
                "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
                "holdout_season_not_read": config.HOLDOUT_SEASON,
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
