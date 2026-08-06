"""LightGBM-primary promotion screen for parked lift families vs frozen 180.

Prior expanded research left lineup discipline and batter-quality families
research-only partly because Ridge was mixed/worse. Production k-rate is
LightGBM-only, so this runner re-tests those families against the frozen
``production`` registry with LightGBM nested chronological selection.

Discipline nominees are locked from the documented Phase-3 screen:
``opp_lineup_zswing_P10``, ``opp_lineup_swing_P10``, ``opp_lineup_zcontact_P20``,
``opp_lineup_bb``. Quality nominees are rebuilt from the current
stabilization crossings summary (lower-CI ``r=.50`` only).

Promotion bar (predeclared):
- LightGBM only
- inner selection by mean MAE
- outer MAE must improve vs production core on **both** outer folds
- optional chrono bake-off on the research test partition
"""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from Python import config
from Python.features import TARGET
from Python.registries import resolve_feature_names

from nested_cv import fold_metadata, nested_research_folds


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "lgbm_lift_promotion"
QUALITY_CROSSINGS = (
    config.OUTPUT_DIR
    / "stabilization"
    / "expanded"
    / "batter_quality"
    / "batter_quality_crossings_summary.csv"
)

# Locked Phase-3 discipline nominees (docs/research/PAPER_NOTES.md).
DISCIPLINE_FEATURES = (
    "opp_lineup_zswing_P10",
    "opp_lineup_swing_P10",
    "opp_lineup_zcontact_P20",
    "opp_lineup_bb",
)

QUALITY_METRIC_NAMES = {
    "hard_hit_rate": "hard_hit",
    "barrel_rate": "barrel",
    "avg_exit_velocity": "avg_ev",
    "avg_launch_angle": "avg_la",
    "xBA": "xba",
    "xwOBA": "xwoba",
    "hr_rate": "hr",
    "fb_rate": "fb",
    "hr_fb_rate": "hr_fb",
    "pull_air_rate": "pull_air",
}


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


def _nominee(starts: float) -> str:
    if pd.isna(starts) or starts > 25:
        return "std"
    return f"P{min((5, 10, 20), key=lambda window: abs(window - starts))}"


def _quality_features(frame: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    if not QUALITY_CROSSINGS.exists():
        raise FileNotFoundError(
            f"missing {QUALITY_CROSSINGS}; run "
            "models/Strikeout-Model/research/run_batter_quality_stabilization.py"
        )
    crossings = pd.read_csv(QUALITY_CROSSINGS)
    qualified = crossings.loc[
        crossings["threshold"].eq(0.50)
        & crossings["stat"].isin(QUALITY_METRIC_NAMES)
        & crossings["reliably_estimable"].eq(True)  # noqa: E712
    ].set_index("stat")
    if qualified.empty:
        raise ValueError("no batter quality metric cleared lower-CI r=.50")

    nominees = {
        metric: _nominee(
            float(qualified.loc[metric, "typical_starts_at_median_crossing"])
        )
        for metric in qualified.index
    }
    weighted: list[str] = []
    dispersion: list[str] = []
    columns = set(frame.columns)
    for metric, window in nominees.items():
        suffix = "" if window == "std" else f"_{window}"
        stem = f"opp_lineup_{QUALITY_METRIC_NAMES[metric]}{suffix}"
        family = (f"{stem}_order_weighted", f"{stem}_order_sd")
        missing = [column for column in family if column not in columns]
        if missing:
            raise ValueError(f"missing quality columns: {missing}")
        weighted.append(family[0])
        dispersion.append(family[1])
    return [*weighted, *dispersion], nominees


def _research_frame() -> pd.DataFrame:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values("game_date")
        .loc[lambda value: value["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .copy()
    )
    if tuple(sorted(frame["season"].unique())) != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError("lift promotion must use configured feature-research seasons")
    return frame


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

    missing_discipline = [
        feature for feature in DISCIPLINE_FEATURES if feature not in frame.columns
    ]
    if missing_discipline:
        raise ValueError(f"discipline features missing: {missing_discipline}")

    quality_features, quality_nominees = _quality_features(frame)
    configurations = {
        "production": core,
        "production_plus_discipline": [*core, *DISCIPLINE_FEATURES],
        "production_plus_quality_wd": [*core, *quality_features],
        "production_plus_both": [
            *core,
            *DISCIPLINE_FEATURES,
            *quality_features,
        ],
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
            both_folds_improve=("mae_improvement_vs_production", lambda s: bool((s > 0).all())),
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

    # Chrono bake-off: train through mid-2024 research cut, score late-2024 test.
    # Matches nested outer hygiene: selection seasons only; 2025 still unread.
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
    (OUTPUT_DIR / "metadata.json").write_text(
        json.dumps(
            {
                "core_feature_set": "production",
                "n_core_features": len(core),
                "discipline_features": list(DISCIPLINE_FEATURES),
                "quality_nominees": quality_nominees,
                "quality_features": quality_features,
                "model": "lightgbm",
                "ridge_not_used": True,
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

    print("=== Inner selection (by outer fold) ===")
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
