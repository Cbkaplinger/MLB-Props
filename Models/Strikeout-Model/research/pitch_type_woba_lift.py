"""LightGBM lift screen for per-pitch-type wOBA/xwOBA vs frozen production.

Tier 2 of the pitch-type "command+stuff" gap (see
docs/research/pitch_type_strike_csw_findings.md for Tier 1). ``{pt}_woba`` and
``{pt}_xwoba`` are already computed at Level 1
(``Python.pitcher_features.build_pitcher_starts``) but were never rolled or
added to any rate map -- this is the "cheapest win" tier because the columns
already exist, they just need a leakage-safe rolling treatment.

Denominator here is PAs *ending* on that pitch type, not pitches thrown, so the
per-start sample is far smaller than the Tier-1 rate stats (median 2-7 PA/start
vs. 12-31 pitches/start). The stabilization pass below confirms this makes raw
per-pitch wOBA/xwOBA essentially unusable without heavy empirical-Bayes
shrinkage, and even shrunk, most pitch types don't reliably stabilize within a
season. Uses the same generalized rolling helper
(:func:`Python.pitcher_rolling.add_pitch_type_rate_features`) and the same
predeclared promotion bar as Tier 1 (both outer folds must improve k_rate MAE
vs. frozen production).
"""

from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
import polars as pl
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from Python import config
from Python.features import TARGET
from Python.pitcher_rolling import (
    DEFAULT_PITCH_TYPE_WOBA_STATS,
    DEFAULT_PITCH_TYPE_WOBA_WINDOWS,
    add_pitch_type_rate_features,
)
from Python.pitcher_features import PITCH_TYPES
from Python.registries import resolve_feature_names

from nested_cv import fold_metadata, nested_research_folds


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "pitch_type_woba_lift"
CROSSINGS_PATH = (
    config.OUTPUT_DIR
    / "stabilization"
    / "expanded"
    / "pitch_type"
    / "pitch_type_crossings_summary.csv"
)

# Empirical-Bayes prior strength (PAs ending on this pitch type). Set near the
# middle of the observed median-crossing PA counts for wOBA/xwOBA (~70-180 PA;
# see the crossings summary) -- not separately tuned, same caveat as Tier 1.
PRIOR_STRENGTH_PA = 100.0

TOP_USAGE_PITCH_TYPES = ("ff", "si", "sl")


def _metrics(actual: pd.Series, prediction: np.ndarray) -> dict[str, float]:
    prediction = np.clip(prediction, 0, 1)
    return {
        "mae": float(mean_absolute_error(actual, prediction)),
        "rmse": float(mean_squared_error(actual, prediction) ** 0.5),
        "r2": float(r2_score(actual, prediction)),
    }


def _lgbm() -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(
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
    )


def _nominee_window(starts: float) -> int:
    if pd.isna(starts):
        return max(DEFAULT_PITCH_TYPE_WOBA_WINDOWS)
    return min(DEFAULT_PITCH_TYPE_WOBA_WINDOWS, key=lambda window: abs(window - starts))


def _pitch_type_window_nominees() -> pd.DataFrame:
    if not CROSSINGS_PATH.exists():
        raise FileNotFoundError(
            f"missing {CROSSINGS_PATH}; run "
            "models/Strikeout-Model/research/run_pitch_type_stabilization.py"
        )
    crossings = pd.read_csv(CROSSINGS_PATH)
    crossings = crossings.loc[crossings["threshold"].eq(0.50)].copy()
    crossings["pitch_type"] = crossings["population"].str.removeprefix("pitcher_")
    crossings = crossings.loc[crossings["stat"].isin(DEFAULT_PITCH_TYPE_WOBA_STATS)].copy()
    crossings["nominee_window"] = crossings["typical_starts_at_median_crossing"].map(
        _nominee_window
    )
    return crossings.set_index(["pitch_type", "stat"])[
        ["nominee_window", "reliably_estimable", "typical_starts_at_median_crossing"]
    ]


def _research_frame() -> pd.DataFrame:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values("game_date")
        .loc[lambda value: value["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .reset_index(drop=True)
    )
    if tuple(sorted(frame["season"].unique())) != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError("lift promotion must use configured feature-research seasons")
    return frame


def _build_pitch_type_candidates(
    frame: pd.DataFrame,
    nominees: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    starts = (
        pl.read_parquet(config.PITCHER_GAMES_PATH)
        .filter(pl.col("season").is_in(config.FEATURE_RESEARCH_SEASONS))
        .select("game_pk", "pitcher", "game_date")
    )
    pitch_type_games = pl.read_parquet(config.PITCH_TYPE_GAMES_PATH).filter(
        pl.col("season").is_in(config.FEATURE_RESEARCH_SEASONS)
    )
    enriched = add_pitch_type_rate_features(
        starts,
        pitch_type_games,
        stats=DEFAULT_PITCH_TYPE_WOBA_STATS,
        prior_strength=PRIOR_STRENGTH_PA,
        windows=DEFAULT_PITCH_TYPE_WOBA_WINDOWS,
        pitch_types=PITCH_TYPES,
    )

    shrunk_features: list[str] = []
    unshrunk_features: list[str] = []
    keep_columns = ["game_pk", "pitcher"]
    for pitch_type in PITCH_TYPES:
        for stat_name in DEFAULT_PITCH_TYPE_WOBA_STATS:
            window = int(nominees.loc[(pitch_type, stat_name), "nominee_window"])
            shrunk_col = f"{pitch_type}_{stat_name}_shrunk_P{window}"
            unshrunk_col = f"{pitch_type}_{stat_name}_P{window}"
            keep_columns.extend([shrunk_col, unshrunk_col])
            shrunk_features.append(shrunk_col)
            unshrunk_features.append(unshrunk_col)

    merged = frame.merge(
        enriched.select(keep_columns).to_pandas(),
        on=["game_pk", "pitcher"],
        how="left",
        validate="one_to_one",
    )
    return merged, shrunk_features, unshrunk_features


def _select_inner(results: pd.DataFrame) -> pd.DataFrame:
    aggregate = (
        results.groupby(["outer_fold", "configuration"], as_index=False)
        .agg(
            inner_mean_mae=("mae", "mean"),
            inner_mean_rmse=("rmse", "mean"),
            inner_mean_r2=("r2", "mean"),
        )
        .sort_values(["outer_fold", "inner_mean_mae", "configuration"])
    )
    return aggregate.groupby("outer_fold", as_index=False).first()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = _research_frame()
    core = list(resolve_feature_names(frame, "production"))
    missing_core = [feature for feature in core if feature not in frame.columns]
    if missing_core:
        raise ValueError(f"production features missing from frame: {missing_core}")

    nominees = _pitch_type_window_nominees()
    frame, shrunk_features, unshrunk_features = _build_pitch_type_candidates(
        frame, nominees
    )
    top_usage_shrunk = [
        feature
        for feature in shrunk_features
        if feature.split("_", 1)[0] in TOP_USAGE_PITCH_TYPES
    ]

    configurations = {
        "production": core,
        "production_plus_pitch_type_woba_shrunk": [*core, *shrunk_features],
        "production_plus_pitch_type_woba_unshrunk": [*core, *unshrunk_features],
        "production_plus_pitch_type_woba_shrunk_top3": [*core, *top_usage_shrunk],
    }

    folds = nested_research_folds(frame)
    inner_rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        for inner_name, inner in nested.inner.items():
            for configuration, selected in configurations.items():
                model = _lgbm()
                model.fit(inner.train[selected], inner.train[TARGET])
                inner_rows.append(
                    {
                        "outer_fold": outer_name,
                        "inner_fold": inner_name,
                        "configuration": configuration,
                        "n_features": len(selected),
                        **_metrics(
                            inner.validation[TARGET],
                            model.predict(inner.validation[selected]),
                        ),
                    }
                )

    inner_results = pd.DataFrame(inner_rows)
    selections = _select_inner(inner_results)

    outer_rows: list[dict[str, object]] = []
    for outer_name, nested in folds.items():
        outer = nested.outer
        core_model = _lgbm()
        core_model.fit(outer.train[core], outer.train[TARGET])
        core_metrics = _metrics(
            outer.validation[TARGET],
            core_model.predict(outer.validation[core]),
        )
        for configuration, selected in configurations.items():
            model = _lgbm()
            model.fit(outer.train[selected], outer.train[TARGET])
            selected_metrics = _metrics(
                outer.validation[TARGET],
                model.predict(outer.validation[selected]),
            )
            outer_rows.append(
                {
                    "outer_fold": outer_name,
                    "configuration": configuration,
                    "n_features": len(selected),
                    "inner_selected": (
                        selections.loc[
                            selections["outer_fold"].eq(outer_name),
                            "configuration",
                        ].iloc[0]
                        == configuration
                    ),
                    **selected_metrics,
                    "mae_improvement_vs_production": (
                        core_metrics["mae"] - selected_metrics["mae"]
                    ),
                    "rmse_improvement_vs_production": (
                        core_metrics["rmse"] - selected_metrics["rmse"]
                    ),
                    "r2_improvement_vs_production": (
                        selected_metrics["r2"] - core_metrics["r2"]
                    ),
                }
            )

    results = pd.DataFrame(outer_rows)
    both_fold = (
        results.loc[results["configuration"].ne("production")]
        .groupby("configuration", as_index=False)
        .agg(
            mean_mae_improvement=("mae_improvement_vs_production", "mean"),
            min_mae_improvement=("mae_improvement_vs_production", "min"),
            both_folds_improve=(
                "mae_improvement_vs_production", lambda s: bool((s > 0).all())
            ),
            mean_mae=("mae", "mean"),
            mean_rmse=("rmse", "mean"),
            mean_r2=("r2", "mean"),
            n_features=("n_features", "first"),
        )
        .sort_values(
            ["both_folds_improve", "mean_mae_improvement"],
            ascending=[False, False],
        )
    )

    train_end = pd.Timestamp("2024-08-05")
    test = frame.loc[frame["game_date"] > train_end].copy()
    train = frame.loc[frame["game_date"] <= train_end].copy()
    bake_rows: list[dict[str, object]] = []
    for configuration, selected in configurations.items():
        model = _lgbm()
        model.fit(train[selected], train[TARGET])
        bake_rows.append(
            {
                "configuration": configuration,
                "n_features": len(selected),
                "train_rows": len(train),
                "test_rows": len(test),
                **_metrics(test[TARGET], model.predict(test[selected])),
            }
        )
    bakeoff = pd.DataFrame(bake_rows).sort_values("mae")

    inner_results.to_csv(OUTPUT_DIR / "inner_results.csv", index=False)
    selections.to_csv(OUTPUT_DIR / "inner_selection.csv", index=False)
    results.to_csv(OUTPUT_DIR / "outer_results.csv", index=False)
    both_fold.to_csv(OUTPUT_DIR / "promotion_summary.csv", index=False)
    bakeoff.to_csv(OUTPUT_DIR / "chrono_bakeoff.csv", index=False)
    nominees.to_csv(OUTPUT_DIR / "pitch_type_window_nominees.csv")
    (OUTPUT_DIR / "metadata.json").write_text(
        json.dumps(
            {
                "core_feature_set": "production",
                "n_core_features": len(core),
                "prior_strength_pa": PRIOR_STRENGTH_PA,
                "pitch_type_woba_windows_candidate_grid": list(
                    DEFAULT_PITCH_TYPE_WOBA_WINDOWS
                ),
                "top_usage_pitch_types": list(TOP_USAGE_PITCH_TYPES),
                "n_shrunk_features": len(shrunk_features),
                "n_unshrunk_features": len(unshrunk_features),
                "model": "lightgbm",
                "promotion_rule": (
                    "both outer folds MAE improvement vs production > 0"
                ),
                "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
                "holdout_season_not_read": config.HOLDOUT_SEASON,
                "folds": fold_metadata(folds),
                "chrono_bakeoff_train_end": str(train_end.date()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=== Pitch-type wOBA/xwOBA window nominees ===")
    print(nominees.to_string())
    print("\n=== Inner selection (by outer fold) ===")
    print(selections.to_string(index=False))
    print("\n=== Outer results ===")
    print(results.to_string(index=False))
    print("\n=== Promotion summary ===")
    print(both_fold.to_string(index=False))
    print("\n=== Chrono bake-off (train <= 2024-08-05) ===")
    print(bakeoff.to_string(index=False))
    print(f"\nWrote outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
