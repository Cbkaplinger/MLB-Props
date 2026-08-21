"""Noise-floor + logit-target checks for manuscript Section 6.1 (Table 3c / 3a).

Does not change the frozen pipeline. Writes artifacts under
``artifacts/feature_research/section61_checks/``.

Period noise floor: production LightGBM fit on 2023 only, scored on 2024 H1
and H2 (Section 7 date bounds). Per-pitcher SD uses the frozen booster on the
chronological test partition.

Example:
    python models/Strikeout-Model/research/section61_checks.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from Python import config
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.live_assembly import DEFAULT_KRATE_STEM, load_krate_booster
from Python.training import (
    chronological_split,
    fit_regressor,
    lightgbm_matrix,
    resolve_sample_weights,
)

# Import Marcel helpers from sibling script.
EDA = Path(__file__).resolve().parent
if str(EDA) not in sys.path:
    sys.path.insert(0, str(EDA))
from marcel_baseline import (  # noqa: E402
    _HISTORY_YEARS,
    _league_rate_by_season,
    _pitcher_season_rates,
    marcel_k_rate,
)

OUT = config.OUTPUT_DIR / "feature_research" / "section61_checks"
EPS = 1e-4
MIN_PITCHER_GAMES = 3


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


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    pred = np.clip(pred, 0.0, 1.0)
    return {
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(mean_squared_error(y, pred) ** 0.5),
        "r2": float(r2_score(y, pred)),
        "n": int(len(y)),
    }


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, EPS, 1.0 - EPS)
    return np.log(p / (1.0 - p))


def _expit(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -50.0, 50.0)
    return 1.0 / (1.0 + np.exp(-z))


def _fit_lgbm_chrono(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
    *,
    target: np.ndarray | pd.Series,
    val_target: np.ndarray | pd.Series,
) -> lgb.LGBMRegressor:
    """Match production train.py early-stopping protocol."""
    model = _lgbm()
    fit_regressor(
        model,
        "lightgbm",
        lightgbm_matrix(train, features),
        target,
        train_weight=resolve_sample_weights(train, "none"),
        validation_features=lightgbm_matrix(validation, features),
        validation_target=val_target,
        validation_weight=resolve_sample_weights(validation, "none"),
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return model


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    frame = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame["game_date"] = pd.to_datetime(frame["game_date"])
    frame = (
        frame.loc[frame["season"].isin(config.TRAIN_SEASONS)]
        .dropna(subset=[TARGET, "game_date", "pitcher"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    features = list(resolve_feature_names(frame, "production"))
    train, validation, test = chronological_split(frame)
    y_test = test[TARGET].to_numpy(dtype=float)

    # --- Frozen booster predictions (matches Table 3 / 3b LightGBM row) ---
    booster, k_features, _ = load_krate_booster(DEFAULT_KRATE_STEM)
    pred_lgbm = np.clip(
        booster.predict(lightgbm_matrix(test, k_features), num_threads=1), 0, 1
    )
    lgbm_test = _metrics(y_test, pred_lgbm)

    # --- Marcel on same test ---
    season_rates = _pitcher_season_rates(_HISTORY_YEARS)
    league_rate = _league_rate_by_season(season_rates)
    by_pitcher: dict[int, dict[int, tuple[float, float]]] = {}
    for pitcher, season, k, pa in season_rates.select(
        "pitcher", "season", "K", "PA"
    ).iter_rows():
        by_pitcher.setdefault(int(pitcher), {})[int(season)] = (float(k), float(pa))
    pred_marcel = np.array(
        [
            marcel_k_rate(int(p), int(s), by_pitcher, league_rate)
            for p, s in zip(test["pitcher"], test["season"])
        ],
        dtype=float,
    )
    marcel_test = _metrics(y_test, pred_marcel)
    mean_pred = np.full_like(y_test, fill_value=float(train[TARGET].mean()))
    mean_test = _metrics(y_test, mean_pred)

    # Published gaps from manuscript Table 3b (do not overwrite frozen metrics).
    published_lgbm_mae = 0.0787
    published_marcel_mae = 0.0826
    published_mean_mae = 0.0854
    gap_marcel = published_marcel_mae - published_lgbm_mae
    gap_mean = published_mean_mae - published_lgbm_mae

    # --- (a) Per-pitcher MAE SD on chronological test (frozen LightGBM) ---
    abs_err = np.abs(y_test - pred_lgbm)
    pitcher_ids = test["pitcher"].to_numpy()
    per_pitcher = (
        pd.DataFrame({"pitcher": pitcher_ids, "abs_err": abs_err})
        .groupby("pitcher", as_index=False)
        .agg(n=("abs_err", "size"), mae=("abs_err", "mean"))
    )
    qualified = per_pitcher.loc[per_pitcher["n"] >= MIN_PITCHER_GAMES]
    per_pitcher_sd = float(qualified["mae"].std(ddof=1))
    per_pitcher_mean = float(qualified["mae"].mean())
    per_pitcher_iqr = float(
        qualified["mae"].quantile(0.75) - qualified["mae"].quantile(0.25)
    )

    # --- (b) 2024 H1 vs H2 MAE under shared pre-2024 training ---
    # Same period bounds as Section 7 nested folds; both windows are forward-
    # looking from one 2023-only fit (production features + early stopping).
    pre_2024 = frame.loc[frame["game_date"] < pd.Timestamp("2024-01-01")].copy()
    pre_2024 = pre_2024.sort_values(["game_date", "player_name"]).reset_index(
        drop=True
    )
    cut = int(len(pre_2024) * 0.85)
    fit_2023, val_2023 = pre_2024.iloc[:cut], pre_2024.iloc[cut:]
    model_2023 = _fit_lgbm_chrono(
        fit_2023,
        val_2023,
        features,
        target=fit_2023[TARGET],
        val_target=val_2023[TARGET],
    )
    h1 = frame.loc[
        (frame["game_date"] >= pd.Timestamp("2024-01-01"))
        & (frame["game_date"] < pd.Timestamp("2024-07-01"))
    ]
    h2 = frame.loc[frame["game_date"] >= pd.Timestamp("2024-07-01")]
    pred_h1 = np.clip(
        model_2023.predict(lightgbm_matrix(h1, features), num_threads=1), 0, 1
    )
    pred_h2 = np.clip(
        model_2023.predict(lightgbm_matrix(h2, features), num_threads=1), 0, 1
    )
    mae_h1 = float(mean_absolute_error(h1[TARGET], pred_h1))
    mae_h2 = float(mean_absolute_error(h2[TARGET], pred_h2))
    period_spread = abs(mae_h1 - mae_h2)
    period_maes = {
        "h1_2024_mae": mae_h1,
        "h2_2024_mae": mae_h2,
        "n_h1": int(len(h1)),
        "n_h2": int(len(h2)),
        "abs_spread": float(period_spread),
        "training": "2023_only_shared",
    }

    # --- Logit target challenger (same chronological split + early stopping) ---
    model_rate = _fit_lgbm_chrono(
        train,
        validation,
        features,
        target=train[TARGET],
        val_target=validation[TARGET],
    )
    pred_rate = np.clip(
        model_rate.predict(lightgbm_matrix(test, features), num_threads=1), 0, 1
    )
    rate_refit = _metrics(y_test, pred_rate)

    model_logit = _fit_lgbm_chrono(
        train,
        validation,
        features,
        target=_logit(train[TARGET].to_numpy(dtype=float)),
        val_target=_logit(validation[TARGET].to_numpy(dtype=float)),
    )
    pred_logit = _expit(
        model_logit.predict(lightgbm_matrix(test, features), num_threads=1)
    )
    logit_test = _metrics(y_test, pred_logit)

    out = {
        "chronological_test_frozen_booster": {
            "lightgbm_rate": lgbm_test,
            "marcel_lite": marcel_test,
            "train_mean": mean_test,
            "published_table3b_gaps": {
                "lgbm_mae": published_lgbm_mae,
                "marcel_mae": published_marcel_mae,
                "mean_mae": published_mean_mae,
                "gap_vs_marcel": gap_marcel,
                "gap_vs_mean": gap_mean,
                "rel_vs_marcel": gap_marcel / published_marcel_mae,
                "rel_vs_mean": gap_mean / published_mean_mae,
            },
        },
        "noise_floor": {
            "per_pitcher_mae": {
                "min_games": MIN_PITCHER_GAMES,
                "n_pitchers": int(len(qualified)),
                "mean_of_pitcher_mae": per_pitcher_mean,
                "sd_of_pitcher_mae": per_pitcher_sd,
                "iqr_of_pitcher_mae": per_pitcher_iqr,
                "predictor": "frozen_lightgbm",
            },
            "h1_h2_period_oos": period_maes,
            "interpretation_ratios": {
                "published_gap_vs_marcel_over_pitcher_sd": gap_marcel / per_pitcher_sd,
                "published_gap_vs_mean_over_pitcher_sd": gap_mean / per_pitcher_sd,
                "published_gap_vs_marcel_over_period_spread": gap_marcel / period_spread,
                "published_gap_vs_mean_over_period_spread": gap_mean / period_spread,
            },
        },
        "logit_target": {
            "untransformed_refit_early_stopping": rate_refit,
            "logit_target_inverse_to_rate": logit_test,
            "delta_mae": float(logit_test["mae"] - rate_refit["mae"]),
            "early_stopping_rounds": 200,
            "protocol": "identical_chrono_split_and_early_stopping",
        },
    }
    (OUT / "summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    qualified.to_csv(OUT / "per_pitcher_mae.csv", index=False)
    print(json.dumps(out, indent=2))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
