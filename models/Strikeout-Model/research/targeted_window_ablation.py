"""Nested window re-ablation for stabilization-flagged pitcher metrics only."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import polars as pl

from Python import config
from Python.features import TARGET, model_feature_names
from Python.pitcher_rolling import (
    DEFAULT_RATE_STATS,
    add_rolling_pitcher_features,
)

from feature_ablation import _families, _metrics, _models
from nested_cv import fold_metadata, nested_research_folds


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research"
GAP_PATH = OUTPUT_DIR / "window_stabilization_gap.csv"
PROPOSAL_PATH = OUTPUT_DIR / "window_change_proposals.csv"


def _metric_columns(
    features: list[str],
    metric: str,
    windows: tuple[int, ...],
) -> dict[str, str]:
    available = {
        f"P{window}": f"{metric}_P{window}"
        for window in windows
        if f"{metric}_P{window}" in features
    }
    if not available:
        raise ValueError(f"no rolling alternatives found for flagged metric {metric}")
    return available


def _materialize_candidate_windows(
    frame: pd.DataFrame,
    candidates: dict[str, tuple[int, ...]],
) -> pd.DataFrame:
    """Build proposed windows transiently without changing rolling defaults."""
    games = pl.read_parquet(config.PITCHER_GAMES_PATH)
    out = frame
    for metric, windows in candidates.items():
        if metric == "babip":
            generated = add_rolling_pitcher_features(
                games,
                rate_stats={"babip": DEFAULT_RATE_STATS["babip"]},
                mean_cols=(),
                rate_windows=windows,
                mean_windows=(),
                season_to_date=False,
            )
        else:
            generated = add_rolling_pitcher_features(
                games,
                rate_stats={},
                mean_cols=(),
                rate_windows=(),
                mean_windows=windows,
                season_to_date=False,
            )
        columns = [f"{metric}_P{window}" for window in windows]
        missing = [column for column in columns if column not in generated.columns]
        if missing:
            raise ValueError(f"failed to materialize {metric} windows: {missing}")

        values = generated.select("game_pk", "pitcher", *columns).to_pandas()
        existing = [column for column in columns if column in out.columns]
        if existing:
            comparison = out[["game_pk", "pitcher", *existing]].merge(
                values[["game_pk", "pitcher", *existing]],
                on=["game_pk", "pitcher"],
                how="left",
                validate="1:1",
                suffixes=("_stored", "_generated"),
            )
            for column in existing:
                stored = comparison[f"{column}_stored"].to_numpy(dtype=float)
                rebuilt = comparison[f"{column}_generated"].to_numpy(dtype=float)
                if not np.allclose(stored, rebuilt, equal_nan=True):
                    raise ValueError(
                        f"transient rebuild disagrees with stored {column}"
                    )
        additions = [column for column in columns if column not in out.columns]
        if additions:
            out = out.merge(
                values[["game_pk", "pitcher", *additions]],
                on=["game_pk", "pitcher"],
                how="left",
                validate="1:1",
            )
    return out


def _select_from_inner_results(results: pd.DataFrame) -> pd.DataFrame:
    aggregate = (
        results.groupby(
            ["metric", "outer_fold", "model", "configuration"],
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
                "metric",
                "outer_fold",
                "model",
                "inner_mean_mae",
                "n_features",
                "configuration",
            ]
        )
    )
    return aggregate.drop_duplicates(
        ["metric", "outer_fold", "model"],
        keep="first",
    )


def main() -> None:
    gap = pd.read_csv(GAP_PATH)
    proposals = pd.read_csv(PROPOSAL_PATH)
    candidates = {
        str(row["feature"]): tuple(
            int(value.removeprefix("P"))
            for value in str(row["proposed candidate windows"]).split("/")
        )
        for row in proposals.to_dict("records")
    }
    if not candidates:
        raise ValueError("the window proposal table contains no candidates")
    directions = dict(zip(gap["metric"], gap["gap_direction"], strict=True))

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values("game_date")
        .loc[lambda value: value["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .copy()
    )
    if tuple(sorted(frame["season"].unique())) != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError("targeted window research must use configured dev seasons")
    frame = _materialize_candidate_windows(frame, candidates)

    features = list(model_feature_names(frame, include_experimental=True))
    families = _families(features)
    candidate_columns = {
        feature for family in families.values() for feature in family
    }
    common_core = [
        feature for feature in features if feature not in candidate_columns
    ]
    configurations: dict[str, dict[str, list[str]]] = {}
    alternatives: dict[str, dict[str, str]] = {}
    for metric, windows in candidates.items():
        available = _metric_columns(features, metric, windows)
        configurations[metric] = {
            "core": common_core,
            **{
                window: [*common_core, column]
                for window, column in available.items()
            },
        }
        alternatives[metric] = available

    folds = nested_research_folds(frame)
    inner_rows: list[dict[str, object]] = []
    for metric, metric_configurations in configurations.items():
        for outer_name, nested in folds.items():
            for inner_name, inner in nested.inner.items():
                for model_name in _models():
                    for configuration, selected in metric_configurations.items():
                        model = _models()[model_name]
                        model.fit(inner.train[selected], inner.train[TARGET])
                        result = _metrics(
                            inner.validation[TARGET],
                            model.predict(inner.validation[selected]),
                        )
                        inner_rows.append(
                            {
                                "metric": metric,
                                "gap_direction": directions[metric],
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
            print(f"Completed inner selection: {metric} / {outer_name}")

    inner_results = pd.DataFrame(inner_rows)
    selections = _select_from_inner_results(inner_results)

    outer_rows: list[dict[str, object]] = []
    for selection in selections.itertuples(index=False):
        outer = folds[selection.outer_fold].outer
        metric_configurations = configurations[selection.metric]
        selected = metric_configurations[selection.configuration]
        selected_model = _models()[selection.model]
        selected_model.fit(outer.train[selected], outer.train[TARGET])
        selected_metrics = _metrics(
            outer.validation[TARGET],
            selected_model.predict(outer.validation[selected]),
        )

        core_features = metric_configurations["core"]
        core_model = _models()[selection.model]
        core_model.fit(outer.train[core_features], outer.train[TARGET])
        core_metrics = _metrics(
            outer.validation[TARGET],
            core_model.predict(outer.validation[core_features]),
        )
        outer_rows.append(
            {
                "metric": selection.metric,
                "gap_direction": directions[selection.metric],
                "outer_fold": selection.outer_fold,
                "model": selection.model,
                "selected_configuration": selection.configuration,
                "selected_feature": alternatives[selection.metric].get(
                    selection.configuration,
                    "",
                ),
                "n_features": len(selected),
                "train_rows": len(outer.train),
                "validation_rows": len(outer.validation),
                "inner_mean_mae": selection.inner_mean_mae,
                "inner_mean_rmse": selection.inner_mean_rmse,
                "inner_mean_r2": selection.inner_mean_r2,
                "mae": selected_metrics["mae"],
                "rmse": selected_metrics["rmse"],
                "r2": selected_metrics["r2"],
                "mae_improvement_vs_metric_core": (
                    core_metrics["mae"] - selected_metrics["mae"]
                ),
                "rmse_improvement_vs_metric_core": (
                    core_metrics["rmse"] - selected_metrics["rmse"]
                ),
                "r2_improvement_vs_metric_core": (
                    selected_metrics["r2"] - core_metrics["r2"]
                ),
            }
        )

    results = pd.DataFrame(outer_rows)
    aggregate = (
        results.groupby(["metric", "gap_direction", "model"], as_index=False)
        .agg(
            outer_folds=("outer_fold", "nunique"),
            selected_configurations=(
                "selected_configuration",
                lambda values: "|".join(values),
            ),
            mean_mae=("mae", "mean"),
            mean_rmse=("rmse", "mean"),
            mean_r2=("r2", "mean"),
            mean_mae_improvement=("mae_improvement_vs_metric_core", "mean"),
            mean_rmse_improvement=("rmse_improvement_vs_metric_core", "mean"),
            mean_r2_improvement=("r2_improvement_vs_metric_core", "mean"),
            positive_mae_folds=(
                "mae_improvement_vs_metric_core",
                lambda values: int((values > 0).sum()),
            ),
        )
        .sort_values(["metric", "model"])
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inner_results.to_csv(
        OUTPUT_DIR / "targeted_window_ablation_inner_results.csv",
        index=False,
    )
    selections.to_csv(
        OUTPUT_DIR / "targeted_window_ablation_inner_selection.csv",
        index=False,
    )
    results.to_csv(
        OUTPUT_DIR / "targeted_window_ablation_results.csv",
        index=False,
    )
    aggregate.to_csv(
        OUTPUT_DIR / "targeted_window_ablation_aggregate.csv",
        index=False,
    )
    (OUTPUT_DIR / "targeted_window_ablation_metadata.json").write_text(
        json.dumps(
            {
                "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
                "holdout_season_not_read": config.HOLDOUT_SEASON,
                "selection_metric": "mean inner-fold MAE, independently per metric",
                "outer_data_used_for_selection": False,
                "fold_api": "nested_research_folds",
                "gap_source": str(GAP_PATH),
                "proposal_source": str(PROPOSAL_PATH),
                "candidate_policy": (
                    "exactly the 2-3 predeclared candidates per flagged metric"
                ),
                "alternatives": alternatives,
                "folds": fold_metadata(folds),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(aggregate.to_string(index=False))
    print(f"Wrote targeted window ablation outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
