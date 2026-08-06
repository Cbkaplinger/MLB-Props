"""Multi-challenger LGBM screen vs production_plus_discipline (184).

Tests parked lift families against the discipline challenger core before any
registry freeze. Configurations are additive and LightGBM-only.

Requires optional columns on the training frame when present:
- quality WD nominees (from stabilization crossings)
- pitcher_age_at_game (research join; see fetch in this module)
- pitcher zswing/swing/zcontact rolling (after DEFAULT_RATE_STATS rebuild)
- opp_lineup_*_vs_hand discipline (after batter hand-split rebuild)
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
from Python.registries import DISCIPLINE_LIFT_FEATURES, resolve_feature_names

from nested_cv import fold_metadata, nested_research_folds


OUTPUT_DIR = config.OUTPUT_DIR / "feature_research" / "multi_lift_pre_freeze"
QUALITY_CROSSINGS = (
    config.OUTPUT_DIR
    / "stabilization"
    / "expanded"
    / "batter_quality"
    / "batter_quality_crossings_summary.csv"
)
BIRTHDATE_CACHE = config.DATA_DIR / "dimensions" / "player_birthdates.parquet"

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

PITCHER_DISCIPLINE_STEMS = ("zswing_rate", "swing_rate", "zcontact_rate")
HAND_SPLIT_DISCIPLINE = (
    "opp_lineup_zswing_vs_hand",
    "opp_lineup_swing_vs_hand",
    "opp_lineup_zcontact_vs_hand",
    "opp_lineup_bb_vs_hand",
    "opp_lineup_whiff_vs_hand",
)


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


def _quality_features(frame: pd.DataFrame) -> list[str] | None:
    if not QUALITY_CROSSINGS.exists():
        return None
    crossings = pd.read_csv(QUALITY_CROSSINGS)
    qualified = crossings.loc[
        crossings["threshold"].eq(0.50)
        & crossings["stat"].isin(QUALITY_METRIC_NAMES)
        & crossings["reliably_estimable"].eq(True)  # noqa: E712
    ].set_index("stat")
    if qualified.empty:
        return None
    features: list[str] = []
    for metric in qualified.index:
        window = _nominee(float(qualified.loc[metric, "typical_starts_at_median_crossing"]))
        suffix = "" if window == "std" else f"_{window}"
        stem = f"opp_lineup_{QUALITY_METRIC_NAMES[metric]}{suffix}"
        for column in (f"{stem}_order_weighted", f"{stem}_order_sd"):
            if column not in frame.columns:
                return None
            features.append(column)
    return features


def _pitcher_discipline_features(frame: pd.DataFrame) -> list[str] | None:
    # Prefer stabilization-style P10/P20 nominees when present; else season-to-date.
    selected: list[str] = []
    for stem in PITCHER_DISCIPLINE_STEMS:
        for candidate in (f"{stem}_P10", f"{stem}_P20", f"{stem}_std", f"{stem}_P5"):
            if candidate in frame.columns:
                selected.append(candidate)
                break
        else:
            return None
    return selected


def _present(frame: pd.DataFrame, columns: tuple[str, ...]) -> list[str] | None:
    if all(column in frame.columns for column in columns):
        return list(columns)
    return None


def _attach_age(frame: pd.DataFrame) -> pd.DataFrame:
    if "pitcher_age_at_game" in frame.columns:
        return frame
    if not BIRTHDATE_CACHE.exists():
        return frame
    births = pd.read_parquet(BIRTHDATE_CACHE)
    if "mlb_id" not in births.columns or "birth_date" not in births.columns:
        return frame
    births = births[["mlb_id", "birth_date"]].copy()
    births["birth_date"] = pd.to_datetime(births["birth_date"])
    out = frame.merge(births, left_on="pitcher", right_on="mlb_id", how="left")
    out["pitcher_age_at_game"] = (
        (out["game_date"] - out["birth_date"]).dt.days / 365.25
    )
    return out.drop(columns=["mlb_id", "birth_date"], errors="ignore")


def _research_frame() -> pd.DataFrame:
    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.dropna(subset=[TARGET, "game_date"])
        .sort_values("game_date")
        .loc[lambda value: value["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .copy()
    )
    return _attach_age(frame)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    raw["game_date"] = pd.to_datetime(raw["game_date"])
    raw = (
        raw.dropna(subset=[TARGET, "game_date"])
        .sort_values("game_date")
        .loc[lambda value: value["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .copy()
    )
    core = list(resolve_feature_names(raw, "production_plus_discipline"))
    frame = _attach_age(raw)
    missing_core = [feature for feature in core if feature not in frame.columns]
    if missing_core:
        raise ValueError(f"core features missing: {missing_core[:10]}")

    blocks: dict[str, list[str]] = {}
    quality = _quality_features(frame)
    if quality:
        blocks["quality_wd"] = quality
    pitcher_disc = _pitcher_discipline_features(frame)
    if pitcher_disc:
        blocks["pitcher_discipline"] = pitcher_disc
    hand = _present(frame, HAND_SPLIT_DISCIPLINE)
    if hand:
        blocks["lineup_discipline_vs_hand"] = hand
    if "pitcher_age_at_game" in frame.columns and frame["pitcher_age_at_game"].notna().any():
        blocks["age"] = ["pitcher_age_at_game"]

    configurations: dict[str, list[str]] = {"core_184": core}
    for name, features in blocks.items():
        configurations[f"core_plus_{name}"] = [*core, *features]
    # Combined of whatever is available (except stacking everything may be huge).
    if len(blocks) >= 2:
        combined: list[str] = list(core)
        for features in blocks.values():
            for feature in features:
                if feature not in combined:
                    combined.append(feature)
        configurations["core_plus_all_available"] = combined

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
                    **selected_metrics,
                    "mae_improvement_vs_core184": (
                        core_metrics["mae"] - selected_metrics["mae"]
                    ),
                }
            )

    results = pd.DataFrame(outer_rows)
    summary = (
        results.assign(
            _improves=results["mae_improvement_vs_core184"] > 0
        )
        .groupby("configuration", as_index=False)
        .agg(
            mean_mae=("mae", "mean"),
            mean_mae_improvement=("mae_improvement_vs_core184", "mean"),
            min_mae_improvement=("mae_improvement_vs_core184", "min"),
            both_folds_improve=("_improves", "all"),
            n_features=("n_features", "first"),
        )
        .sort_values(
            ["both_folds_improve", "mean_mae_improvement"],
            ascending=[False, False],
        )
    )
    summary.loc[summary["configuration"].eq("core_184"), "both_folds_improve"] = False

    # Chrono bake-off late 2024
    train_end = pd.Timestamp("2024-08-05")
    train = frame.loc[frame["game_date"] <= train_end]
    test = frame.loc[frame["game_date"] > train_end]
    bake_rows = []
    for configuration, selected in configurations.items():
        model = _lgbm()
        model.fit(train[selected], train[TARGET])
        bake_rows.append(
            {
                "configuration": configuration,
                "n_features": len(selected),
                **_metrics(test[TARGET], model.predict(test[selected])),
            }
        )
    bakeoff = pd.DataFrame(bake_rows).sort_values("mae")

    # One-shot 2025 confirm (read holdout only for confirmation after nested)
    full = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    full["game_date"] = pd.to_datetime(full["game_date"])
    full = full.dropna(subset=[TARGET, "game_date"]).sort_values("game_date")
    full = _attach_age(full)
    train_all = full.loc[full["season"].isin([2023, 2024])]
    test_2025 = full.loc[full["season"].eq(2025)]
    hold_rows = []
    for configuration, selected in configurations.items():
        missing = [c for c in selected if c not in full.columns]
        if missing:
            continue
        model = _lgbm()
        model.fit(train_all[selected], train_all[TARGET])
        hold_rows.append(
            {
                "configuration": configuration,
                "n_features": len(selected),
                **_metrics(test_2025[TARGET], model.predict(test_2025[selected])),
            }
        )
    holdout = pd.DataFrame(hold_rows).sort_values("mae")

    inner_results.to_csv(OUTPUT_DIR / "inner_results.csv", index=False)
    results.to_csv(OUTPUT_DIR / "outer_results.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "promotion_summary.csv", index=False)
    bakeoff.to_csv(OUTPUT_DIR / "chrono_bakeoff.csv", index=False)
    holdout.to_csv(OUTPUT_DIR / "holdout_2025_confirm.csv", index=False)
    (OUTPUT_DIR / "metadata.json").write_text(
        json.dumps(
            {
                "core": "production_plus_discipline",
                "n_core": len(core),
                "discipline_features": list(DISCIPLINE_LIFT_FEATURES),
                "blocks_available": {k: v for k, v in blocks.items()},
                "blocks_missing": sorted(
                    {
                        "quality_wd",
                        "pitcher_discipline",
                        "lineup_discipline_vs_hand",
                        "age",
                    }
                    - set(blocks)
                ),
                "folds": fold_metadata(folds),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("=== Blocks available ===")
    print(json.dumps({k: len(v) for k, v in blocks.items()}, indent=2))
    print("\n=== Promotion summary ===")
    print(summary.to_string(index=False))
    print("\n=== Chrono bake-off ===")
    print(bakeoff.to_string(index=False))
    print("\n=== 2025 holdout ===")
    print(holdout.to_string(index=False))
    print(f"\nWrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
