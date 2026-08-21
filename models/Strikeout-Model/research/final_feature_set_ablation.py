"""Model-family ablation on a finalized feature set.

Runs chronological outer-fold evaluation on:
- linear
- ridge
- lightgbm (base/default config)

All families are scored on k-rate MAE and expected-K MAE via the same
count-layer handoff (ridge TBF + fitted kappa), so comparisons stay
apples-to-apples.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from Python import config
from Python.count_layer import expected_strikeouts, fit_count_layer_kappa
from Python.features import TARGET
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from Python.training import (
    build_model,
    fit_regressor,
    lightgbm_matrix,
    metrics,
    predict_clipped,
    predict_nonnegative,
)
from nested_cv import nested_research_folds

OUT_ROOT = config.OUTPUT_DIR / "model_quality" / "final_feature_set_ablation"


def _load_frame() -> pd.DataFrame:
    plf = (
        pl.read_parquet(config.PITCHER_TRAINING_PATH)
        .with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
        .filter(pl.col("game_date").is_not_null() & pl.col(TARGET).is_not_null())
        .filter(pl.col("season").is_in(list(config.FEATURE_RESEARCH_SEASONS)))
        .sort(["game_date", "player_name"])
    )
    return plf.to_pandas().reset_index(drop=True)


def _fit_tbf(train: pd.DataFrame, features: list[str]):
    model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(model, "ridge", train[features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return model, upper


def _filled(df: pd.DataFrame, features: list[str], fill: pd.Series) -> pd.DataFrame:
    x = df[features].replace([np.inf, -np.inf], np.nan)
    return x.fillna(fill)


def _fit_linear(train: pd.DataFrame, features: list[str]) -> tuple[LinearRegression, pd.Series]:
    fill = train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)
    m = LinearRegression()
    m.fit(_filled(train, features, fill), train[TARGET])
    return m, fill


def _fit_ridge(
    train: pd.DataFrame, val: pd.DataFrame, features: list[str]
) -> tuple[Ridge, pd.Series, float]:
    fill = train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)
    best = None
    best_mae = float("inf")
    best_alpha = 1.0
    for alpha in (0.1, 1.0, 3.0, 10.0, 30.0, 100.0):
        m = Ridge(alpha=alpha)
        m.fit(_filled(train, features, fill), train[TARGET])
        pred = np.clip(m.predict(_filled(val, features, fill)), 0, 1)
        mae = float(metrics(val[TARGET], pred)["mae"])
        if mae < best_mae:
            best_mae = mae
            best = m
            best_alpha = float(alpha)
    assert best is not None
    return best, fill, best_alpha


def _fit_lgbm(train: pd.DataFrame, val: pd.DataFrame, features: list[str]):
    params = {
        "learning_rate": 0.03,
        "num_leaves": 31,
        "min_child_samples": 50,
        "subsample": 0.8,
        "colsample_bytree": 0.7,
        "reg_alpha": 0.1,
        "reg_lambda": 2.0,
        "objective": "regression",
        "seed": 42,
        "feature_fraction_seed": 42,
        "bagging_seed": 42,
        "data_random_seed": 42,
        "bagging_freq": 1,
    }
    m = build_model("lightgbm", lightgbm_verbosity=-1, lightgbm_params=params)
    fit_regressor(
        m,
        "lightgbm",
        lightgbm_matrix(train, features),
        train[TARGET],
        validation_features=lightgbm_matrix(val, features),
        validation_target=val[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    return m


def _fit_histgbr(train: pd.DataFrame, val: pd.DataFrame, features: list[str]):
    fill = train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)
    x_train = train[features].replace([np.inf, -np.inf], np.nan).fillna(fill)
    x_val = val[features].replace([np.inf, -np.inf], np.nan).fillna(fill)
    m = HistGradientBoostingRegressor(
        learning_rate=0.05,
        max_leaf_nodes=31,
        min_samples_leaf=50,
        max_iter=1000,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=42,
    )
    m.fit(x_train, train[TARGET])
    _ = x_val  # keep val path explicit for family parity
    return m, fill


def _fit_xgboost(train: pd.DataFrame, val: pd.DataFrame, features: list[str]):
    try:
        from xgboost import XGBRegressor
    except ImportError:
        return None
    fill = train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)
    x_train = train[features].replace([np.inf, -np.inf], np.nan).fillna(fill)
    x_val = val[features].replace([np.inf, -np.inf], np.nan).fillna(fill)
    m = XGBRegressor(
        n_estimators=2000,
        learning_rate=0.03,
        max_depth=6,
        min_child_weight=50,
        subsample=0.8,
        colsample_bytree=0.7,
        reg_alpha=0.1,
        reg_lambda=2.0,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1,
    )
    m.fit(x_train, train[TARGET], eval_set=[(x_val, val[TARGET])], verbose=False)
    return m, fill


def _fit_catboost(train: pd.DataFrame, val: pd.DataFrame, features: list[str]):
    try:
        from catboost import CatBoostRegressor
    except ImportError:
        return None
    fill = train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)
    x_train = train[features].replace([np.inf, -np.inf], np.nan).fillna(fill)
    x_val = val[features].replace([np.inf, -np.inf], np.nan).fillna(fill)
    m = CatBoostRegressor(
        loss_function="RMSE",
        learning_rate=0.03,
        depth=6,
        l2_leaf_reg=3.0,
        iterations=2000,
        random_seed=42,
        verbose=False,
    )
    m.fit(x_train, train[TARGET], eval_set=(x_val, val[TARGET]), use_best_model=True)
    return m, fill


def _predict_family(
    family: str,
    model: object,
    test: pd.DataFrame,
    features: list[str],
    *,
    fill: pd.Series | None,
) -> np.ndarray:
    if family in {"linear", "ridge"}:
        assert fill is not None
        return np.clip(model.predict(_filled(test, features, fill)), 0, 1)
    if family in {"histgbr", "xgboost", "catboost"}:
        assert fill is not None
        x = test[features].replace([np.inf, -np.inf], np.nan).fillna(fill)
        return np.clip(model.predict(x), 0, 1)
    return predict_clipped(model, "lightgbm", test, features)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-set", default="production_final58_consensus")
    parser.add_argument("--output-tag", default="")
    args = parser.parse_args()

    out_dir = OUT_ROOT / args.output_tag if args.output_tag else OUT_ROOT
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = _load_frame()
    features = list(resolve_feature_names(frame, args.feature_set))
    features = [f for f in features if f in frame.columns]
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    folds = nested_research_folds(frame)

    outer_rows: list[dict[str, object]] = []
    families = ("linear", "ridge", "lgbm_base", "histgbr", "xgboost", "catboost")
    for outer_name, nested in folds.items():
        outer_train = nested.outer.train
        outer_test = nested.outer.validation
        cut = max(200, int(len(outer_train) * 0.85))
        fit = outer_train.iloc[:cut]
        val = outer_train.iloc[cut:]

        tbf_model, tbf_upper = _fit_tbf(outer_train, tbf_features)
        tbf_hat = predict_nonnegative(tbf_model, "ridge", outer_test, tbf_features, upper=tbf_upper)

        for family in families:
            if family == "linear":
                model, fill = _fit_linear(fit, features)
                family_note = "linear_default"
            elif family == "ridge":
                model, fill, alpha = _fit_ridge(fit, val, features)
                family_note = f"ridge_alpha_{alpha:g}"
            elif family == "histgbr":
                model, fill = _fit_histgbr(fit, val, features)
                family_note = "histgbr_default"
            elif family == "xgboost":
                pair = _fit_xgboost(fit, val, features)
                if pair is None:
                    continue
                model, fill = pair
                family_note = "xgboost_default"
            elif family == "catboost":
                pair = _fit_catboost(fit, val, features)
                if pair is None:
                    continue
                model, fill = pair
                family_note = "catboost_default"
            else:
                model = _fit_lgbm(fit, val, features)
                fill = None
                family_note = "lgbm_base_0.03_31_50"

            k_hat = _predict_family(family, model, outer_test, features, fill=fill)
            ek_hat = expected_strikeouts(k_hat, tbf_hat)
            kappa = float(
                fit_count_layer_kappa(
                    k=outer_train["K"],
                    pa=outer_train["PA"],
                    k_rate=_predict_family(family, model, outer_train, features, fill=fill),
                )
            )
            k_metrics = metrics(outer_test[TARGET], k_hat)
            ek_metrics = metrics(outer_test["K"], ek_hat, clip_to_unit_interval=False)
            outer_rows.append(
                {
                    "outer_fold": outer_name,
                    "feature_set": args.feature_set,
                    "model_family": family,
                    "model_tag": family_note,
                    "n_features": len(features),
                    "train_rows": len(outer_train),
                    "test_rows": len(outer_test),
                    "k_rate_mae": float(k_metrics["mae"]),
                    "k_rate_rmse": float(mean_squared_error(outer_test[TARGET], k_hat) ** 0.5),
                    "k_rate_r2": float(r2_score(outer_test[TARGET], k_hat)),
                    "expected_k_mae": float(ek_metrics["mae"]),
                    "expected_k_rmse": float(mean_squared_error(outer_test["K"], ek_hat) ** 0.5),
                    "expected_k_r2": float(r2_score(outer_test["K"], ek_hat)),
                    "kappa": kappa,
                }
            )

    outer_df = pd.DataFrame(outer_rows)
    summary_df = (
        outer_df.groupby(["feature_set", "model_family", "model_tag"], as_index=False)
        .agg(
            outer_folds=("outer_fold", "nunique"),
            mean_k_rate_mae=("k_rate_mae", "mean"),
            std_k_rate_mae=("k_rate_mae", "std"),
            mean_expected_k_mae=("expected_k_mae", "mean"),
            std_expected_k_mae=("expected_k_mae", "std"),
            mean_k_rate_rmse=("k_rate_rmse", "mean"),
            mean_expected_k_rmse=("expected_k_rmse", "mean"),
            mean_k_rate_r2=("k_rate_r2", "mean"),
            mean_expected_k_r2=("expected_k_r2", "mean"),
            mean_kappa=("kappa", "mean"),
        )
        .sort_values(["mean_expected_k_mae", "mean_k_rate_mae", "mean_expected_k_rmse"])
    )
    best_ek = float(summary_df["mean_expected_k_mae"].iloc[0])
    summary_df["delta_expected_k_mae_vs_best"] = summary_df["mean_expected_k_mae"] - best_ek

    outer_df.to_csv(out_dir / "outer_results.csv", index=False)
    summary_df.to_csv(out_dir / "ablation_summary.csv", index=False)
    pd.DataFrame({"feature": features}).to_csv(out_dir / "features_used.csv", index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_set": args.feature_set,
        "n_features": len(features),
        "families": list(families),
        "best_model_family": str(summary_df.iloc[0]["model_family"]),
        "best_model_tag": str(summary_df.iloc[0]["model_tag"]),
        "best_mean_expected_k_mae": float(summary_df.iloc[0]["mean_expected_k_mae"]),
        "files": {
            "outer_results_csv": str(out_dir / "outer_results.csv"),
            "ablation_summary_csv": str(out_dir / "ablation_summary.csv"),
            "features_used_csv": str(out_dir / "features_used.csv"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(summary_df.to_string(index=False))
    print(json.dumps(payload, indent=2))
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
