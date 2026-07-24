"""Nested family test for stabilization-qualified batter quality features."""

from __future__ import annotations

import json

import pandas as pd

from Python import config
from Python.features import TARGET, model_feature_names

from feature_ablation import _metrics, _models, _select_from_inner_results
from nested_cv import fold_metadata, nested_research_folds


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research"
CROSSINGS_PATH = (
    config.OUTPUT_DIR
    / "stabilization"
    / "expanded"
    / "batter_quality"
    / "batter_quality_crossings_summary.csv"
)
METRIC_NAMES = {
    "babip": "babip",
    "hard_hit_rate": "hard_hit",
    "barrel_rate": "barrel",
    "sweet_spot_rate": "sweet_spot",
    "avg_exit_velocity": "avg_ev",
    "avg_launch_angle": "avg_la",
    "xBA": "xba",
    "wOBA": "woba",
    "xwOBA": "xwoba",
    "hr_rate": "hr",
    "fb_rate": "fb",
    "hr_fb_rate": "hr_fb",
    "pull_air_rate": "pull_air",
    "rv_per_pitch": "rv_per_pitch",
}


def _nominee(starts: float) -> str:
    if pd.isna(starts) or starts > 25:
        return "std"
    return f"P{min((5, 10, 20), key=lambda window: abs(window - starts))}"


def _load_configurations(
    frame: pd.DataFrame,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    crossings = pd.read_csv(CROSSINGS_PATH)
    candidates = crossings.loc[
        crossings["threshold"].eq(0.50)
        & crossings["stat"].isin(METRIC_NAMES)
        & crossings["reliably_estimable"].eq(True)  # noqa: E712
    ].set_index("stat")
    if candidates.empty:
        raise ValueError("no batter quality metric cleared the lower-CI r=.50 gate")

    nominees = {
        metric: _nominee(
            float(candidates.loc[metric, "typical_starts_at_median_crossing"])
        )
        for metric in candidates.index
    }
    core = list(model_feature_names(frame))
    flat: list[str] = []
    weighted: list[str] = []
    dispersion: list[str] = []
    research_features = set(
        model_feature_names(frame, include_experimental=True)
    )
    for metric, window in nominees.items():
        suffix = "" if window == "std" else f"_{window}"
        feature = f"opp_lineup_{METRIC_NAMES[metric]}{suffix}"
        family = (
            feature,
            f"{feature}_order_weighted",
            f"{feature}_order_sd",
        )
        missing = [column for column in family if column not in research_features]
        if missing:
            raise ValueError(f"missing batter quality lineup candidates: {missing}")
        flat.append(family[0])
        weighted.append(family[1])
        dispersion.append(family[2])

    return (
        {
            "core": core,
            "quality_flat": [*core, *flat],
            "quality_order_weighted": [*core, *weighted],
            "quality_weighted_dispersion": [*core, *weighted, *dispersion],
        },
        nominees,
    )


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
        raise ValueError("batter quality research must use configured dev seasons")

    configurations, nominees = _load_configurations(frame)
    folds = nested_research_folds(frame)
    inner_rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        for inner_name, inner in nested.inner.items():
            for model_name in _models():
                for configuration, selected in configurations.items():
                    model = _models()[model_name]
                    model.fit(inner.train[selected], inner.train[TARGET])
                    inner_rows.append(
                        {
                            "outer_fold": outer_name,
                            "inner_fold": inner_name,
                            "model": model_name,
                            "configuration": configuration,
                            "n_features": len(selected),
                            **_metrics(
                                inner.validation[TARGET],
                                model.predict(inner.validation[selected]),
                            ),
                        }
                    )

    inner_results = pd.DataFrame(inner_rows)
    selections = _select_from_inner_results(inner_results)
    outer_rows: list[dict[str, object]] = []
    core = configurations["core"]
    for selection in selections.itertuples(index=False):
        outer = folds[selection.outer_fold].outer
        selected = configurations[selection.configuration]
        model = _models()[selection.model]
        model.fit(outer.train[selected], outer.train[TARGET])
        selected_metrics = _metrics(
            outer.validation[TARGET],
            model.predict(outer.validation[selected]),
        )
        core_model = _models()[selection.model]
        core_model.fit(outer.train[core], outer.train[TARGET])
        core_metrics = _metrics(
            outer.validation[TARGET],
            core_model.predict(outer.validation[core]),
        )
        outer_rows.append(
            {
                "outer_fold": selection.outer_fold,
                "model": selection.model,
                "selected_configuration": selection.configuration,
                "n_features": len(selected),
                "inner_mean_mae": selection.inner_mean_mae,
                **selected_metrics,
                "mae_improvement_vs_core": (
                    core_metrics["mae"] - selected_metrics["mae"]
                ),
                "rmse_improvement_vs_core": (
                    core_metrics["rmse"] - selected_metrics["rmse"]
                ),
                "r2_improvement_vs_core": (
                    selected_metrics["r2"] - core_metrics["r2"]
                ),
            }
        )

    results = pd.DataFrame(outer_rows)
    inner_results.to_csv(
        OUTPUT_DIR / "batter_quality_ablation_inner_results.csv", index=False
    )
    selections.to_csv(
        OUTPUT_DIR / "batter_quality_ablation_inner_selection.csv", index=False
    )
    results.to_csv(
        OUTPUT_DIR / "batter_quality_ablation_results.csv", index=False
    )
    (OUTPUT_DIR / "batter_quality_ablation_metadata.json").write_text(
        json.dumps(
            {
                "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
                "holdout_season_not_read": config.HOLDOUT_SEASON,
                "selection_metric": "mean inner-fold MAE",
                "outer_data_used_for_selection": False,
                "fold_api": "nested_research_folds",
                "crossings_source": str(CROSSINGS_PATH),
                "nominees": nominees,
                "configurations_tested": list(configurations),
                "folds": fold_metadata(folds),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(results.to_string(index=False))
    print(f"Wrote batter quality ablation outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
