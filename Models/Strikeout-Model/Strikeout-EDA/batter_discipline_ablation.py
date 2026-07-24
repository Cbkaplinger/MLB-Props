"""Nested family test for added opposing-lineup batter discipline rates."""

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


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research"
CROSSINGS_PATH = (
    config.OUTPUT_DIR
    / "stabilization"
    / "expanded"
    / "batter_discipline"
    / "batter_discipline_crossings_summary.csv"
)
METRIC_NAMES = {
    "zswing_rate": "zswing",
    "swing_rate": "swing",
    "zcontact_rate": "zcontact",
    "bb_rate": "bb",
}


def _nominee(starts: float) -> str:
    """Choose one predeclared representation from stabilization evidence."""
    if pd.isna(starts) or starts > 25:
        return "std"
    return f"P{min((5, 10, 20), key=lambda window: abs(window - starts))}"


def main() -> None:
    crossings = pd.read_csv(CROSSINGS_PATH)
    crossings = crossings.loc[
        crossings["threshold"].eq(0.50)
        & crossings["stat"].isin(METRIC_NAMES)
    ].set_index("stat")
    if set(crossings.index) != set(METRIC_NAMES):
        raise ValueError("missing r=.50 crossing for an added discipline metric")
    nominees = {
        metric: _nominee(float(crossings.loc[metric, "typical_starts_at_median_crossing"]))
        for metric in METRIC_NAMES
    }

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values("game_date")
        .loc[lambda value: value["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .copy()
    )
    if tuple(sorted(frame["season"].unique())) != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError("batter discipline research must use configured dev seasons")

    features = list(model_feature_names(frame, include_experimental=True))
    existing_candidate_columns = {
        feature
        for family in _families(features).values()
        for feature in family
    }
    added_prefixes = tuple(
        f"opp_lineup_{name}" for name in METRIC_NAMES.values()
    )
    added_columns = [
        feature for feature in features if feature.startswith(added_prefixes)
    ]
    core = [
        feature
        for feature in features
        if feature not in existing_candidate_columns
        and feature not in added_columns
    ]
    nominated = []
    for metric, short_name in METRIC_NAMES.items():
        suffix = "" if nominees[metric] == "std" else f"_{nominees[metric]}"
        feature = f"opp_lineup_{short_name}{suffix}"
        if feature not in features:
            raise ValueError(f"missing nominated lineup feature {feature}")
        nominated.append(feature)
    configurations = {
        "core": core,
        "batter_discipline_nominees": [*core, *nominated],
    }

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
                            "train_rows": len(inner.train),
                            "validation_rows": len(inner.validation),
                            **_metrics(
                                inner.validation[TARGET],
                                model.predict(inner.validation[selected]),
                            ),
                        }
                    )

    inner_results = pd.DataFrame(inner_rows)
    selections = _select_from_inner_results(inner_results)
    outer_rows: list[dict[str, object]] = []
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
                "train_rows": len(outer.train),
                "validation_rows": len(outer.validation),
                "inner_mean_mae": selection.inner_mean_mae,
                "inner_mean_rmse": selection.inner_mean_rmse,
                "inner_mean_r2": selection.inner_mean_r2,
                "mae": selected_metrics["mae"],
                "rmse": selected_metrics["rmse"],
                "r2": selected_metrics["r2"],
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
        OUTPUT_DIR / "batter_discipline_ablation_inner_results.csv",
        index=False,
    )
    selections.to_csv(
        OUTPUT_DIR / "batter_discipline_ablation_inner_selection.csv",
        index=False,
    )
    results.to_csv(
        OUTPUT_DIR / "batter_discipline_ablation_results.csv",
        index=False,
    )
    (OUTPUT_DIR / "batter_discipline_ablation_metadata.json").write_text(
        json.dumps(
            {
                "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
                "holdout_season_not_read": config.HOLDOUT_SEASON,
                "selection_metric": "mean inner-fold MAE",
                "outer_data_used_for_selection": False,
                "fold_api": "nested_research_folds",
                "crossings_source": str(CROSSINGS_PATH),
                "nominees": nominees,
                "features": nominated,
                "configurations_tested": list(configurations),
                "folds": fold_metadata(folds),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(results.to_string(index=False))
    print(f"Wrote batter discipline ablation outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
