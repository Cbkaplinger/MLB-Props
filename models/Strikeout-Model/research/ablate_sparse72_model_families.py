"""Cross-compare model families on sparse72 feature sets.

Evaluates requested model families on:
- production_sparse72
- production_sparse72_monotone

Primary ranking metric:
- expected_K MAE (outer-fold mean)
Guardrail:
- k_rate MAE
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import ElasticNetCV, LassoCV, LinearRegression, Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.neighbors import KNeighborsRegressor

ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
EDA_DIR = Path(__file__).resolve().parent
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from Python import config
from Python.count_layer import expected_strikeouts
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

OUT_ROOT = config.OUTPUT_DIR / "model_quality" / "sparse72_model_family_ablation"

ALL_FAMILIES = (
    "linear",
    "ridge",
    "lasso",
    "elasticnet",
    "knn",
    "lightgbm",
    "xgboost",
    "random_forest",
    "histgbr",
    "arima",
    "sarimax",
)


def _load_frame() -> pd.DataFrame:
    return (
        pl.read_parquet(config.PITCHER_TRAINING_PATH)
        .with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
        .filter(
            pl.col("season").is_in(list(config.FEATURE_RESEARCH_SEASONS))
            & pl.col("game_date").is_not_null()
            & pl.col(TARGET).is_not_null()
            & pl.col("K").is_not_null()
            & pl.col("PA").is_not_null()
        )
        .sort(["game_date", "player_name"])
        .to_pandas()
        .reset_index(drop=True)
    )


def _fit_tbf(train: pd.DataFrame, features: list[str]):
    model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(model, "ridge", train[features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return model, upper


def _fill(train: pd.DataFrame, features: list[str]) -> pd.Series:
    return train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)


def _x(df: pd.DataFrame, features: list[str], fill: pd.Series) -> pd.DataFrame:
    return df[features].replace([np.inf, -np.inf], np.nan).fillna(fill)


def _fit_family(
    family: str,
    train: pd.DataFrame,
    val: pd.DataFrame,
    features: list[str],
    monotone: bool,
    tune_small: bool,
):
    fill = _fill(train, features)
    if family == "linear":
        m = LinearRegression()
        m.fit(_x(train, features, fill), train[TARGET])
        return m, fill, "linear_default"
    if family == "ridge":
        best, best_alpha, best_mae = None, None, float("inf")
        for alpha in (0.1, 1.0, 3.0, 10.0, 30.0, 100.0):
            m = Ridge(alpha=alpha)
            m.fit(_x(train, features, fill), train[TARGET])
            pred = np.clip(m.predict(_x(val, features, fill)), 0, 1)
            mae = float(metrics(val[TARGET], pred)["mae"])
            if mae < best_mae:
                best, best_alpha, best_mae = m, alpha, mae
        return best, fill, f"ridge_alpha_{best_alpha:g}"
    if family == "lasso":
        m = LassoCV(cv=5, random_state=42, max_iter=20000, n_jobs=-1)
        m.fit(_x(train, features, fill), train[TARGET])
        return m, fill, f"lasso_alpha_{float(m.alpha_):.6f}"
    if family == "elasticnet":
        m = ElasticNetCV(
            l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9],
            cv=5,
            random_state=42,
            max_iter=20000,
            n_jobs=-1,
        )
        m.fit(_x(train, features, fill), train[TARGET])
        return m, fill, f"elasticnet_alpha_{float(m.alpha_):.6f}_l1_{float(m.l1_ratio_):.2f}"
    if family == "random_forest":
        candidates = (
            [
                (300, 10, "sqrt"),
                (500, 20, "sqrt"),
                (800, 20, "sqrt"),
                (500, 40, "sqrt"),
                (500, 20, 0.7),
            ]
            if tune_small
            else [(500, 20, "sqrt")]
        )
        best, best_tag, best_mae = None, "", float("inf")
        xtr = _x(train, features, fill)
        xva = _x(val, features, fill)
        for n_est, min_leaf, max_feat in candidates:
            m = RandomForestRegressor(
                n_estimators=n_est,
                min_samples_leaf=min_leaf,
                max_features=max_feat,
                n_jobs=-1,
                random_state=42,
            )
            m.fit(xtr, train[TARGET])
            pred = np.clip(m.predict(xva), 0, 1)
            mae = float(metrics(val[TARGET], pred)["mae"])
            if mae < best_mae:
                best, best_mae = m, mae
                mf = max_feat if isinstance(max_feat, str) else f"{float(max_feat):.2f}"
                best_tag = f"rf_{n_est}_{mf}_leaf{min_leaf}"
        return best, fill, best_tag
    if family == "histgbr":
        candidates = (
            [
                (0.03, 31, 30),
                (0.05, 31, 50),
                (0.08, 31, 50),
                (0.05, 63, 30),
                (0.05, 15, 80),
            ]
            if tune_small
            else [(0.05, 31, 50)]
        )
        best, best_tag, best_mae = None, "", float("inf")
        xtr = _x(train, features, fill)
        xva = _x(val, features, fill)
        for lr, leaves, min_leaf in candidates:
            m = HistGradientBoostingRegressor(
                learning_rate=lr,
                max_leaf_nodes=leaves,
                min_samples_leaf=min_leaf,
                max_iter=1000,
                early_stopping=True,
                validation_fraction=0.15,
                random_state=42,
            )
            m.fit(xtr, train[TARGET])
            pred = np.clip(m.predict(xva), 0, 1)
            mae = float(metrics(val[TARGET], pred)["mae"])
            if mae < best_mae:
                best, best_mae = m, mae
                best_tag = f"histgbr_lr{lr:.2f}_leaf{leaves}_min{min_leaf}"
        return best, fill, best_tag
    if family == "knn":
        best, best_k, best_mae = None, None, float("inf")
        xtr = _x(train, features, fill)
        xva = _x(val, features, fill)
        for k in (5, 11, 21, 31, 51):
            m = KNeighborsRegressor(n_neighbors=k, weights="distance")
            m.fit(xtr, train[TARGET])
            pred = np.clip(m.predict(xva), 0, 1)
            mae = float(metrics(val[TARGET], pred)["mae"])
            if mae < best_mae:
                best, best_k, best_mae = m, k, mae
        return best, fill, f"knn_k_{best_k}_dist"
    if family == "lightgbm":
        base = {
            "objective": "regression",
            "seed": 42,
            "feature_fraction_seed": 42,
            "bagging_seed": 42,
            "data_random_seed": 42,
            "bagging_freq": 1,
        }
        grid = (
            [
                {"learning_rate": 0.03, "num_leaves": 31, "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.7, "reg_alpha": 0.1, "reg_lambda": 2.0},
                {"learning_rate": 0.02, "num_leaves": 31, "min_child_samples": 30, "subsample": 0.9, "colsample_bytree": 0.8, "reg_alpha": 0.01, "reg_lambda": 1.0},
                {"learning_rate": 0.05, "num_leaves": 63, "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.1, "reg_lambda": 3.0},
                {"learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 80, "subsample": 1.0, "colsample_bytree": 0.7, "reg_alpha": 0.01, "reg_lambda": 2.0},
            ]
            if tune_small
            else [{"learning_rate": 0.03, "num_leaves": 31, "min_child_samples": 50, "subsample": 0.8, "colsample_bytree": 0.7, "reg_alpha": 0.1, "reg_lambda": 2.0}]
        )
        cons: list[int] | None = None
        if monotone:
            pos = ("k_rate_", "opp_lineup_k", "opp_lineup_whiff", "opp_lineup_swstr", "opp_lineup_chase", "park_k_factor")
            neg = ("opp_lineup_zcontact", "opp_lineup_bb")
            cons = []
            for f in features:
                if any(f == s or f.startswith(s) for s in pos):
                    cons.append(1)
                elif any(f == s or f.startswith(s) for s in neg):
                    cons.append(-1)
                else:
                    cons.append(0)
        best, best_tag, best_mae = None, "", float("inf")
        for i, g in enumerate(grid):
            params = {**base, **g}
            if cons is not None:
                params["monotone_constraints"] = cons
                params["monotone_constraints_method"] = "advanced"
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
            pred = predict_clipped(m, "lightgbm", val, features)
            mae = float(metrics(val[TARGET], pred)["mae"])
            if mae < best_mae:
                best, best_mae = m, mae
                best_tag = f"lgbm_tuned_small_{i}"
        return best, None, best_tag
    if family == "xgboost":
        try:
            from xgboost import XGBRegressor
        except ImportError:
            return None, None, "xgboost_unavailable"
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
        m.fit(_x(train, features, fill), train[TARGET], eval_set=[(_x(val, features, fill), val[TARGET])], verbose=False)
        return m, fill, "xgboost_base"
    raise ValueError(f"Unsupported family {family}")


def _predict_non_ts(family: str, model, test: pd.DataFrame, features: list[str], fill: pd.Series | None) -> np.ndarray:
    if family == "lightgbm":
        return predict_clipped(model, "lightgbm", test, features)
    assert fill is not None
    return np.clip(model.predict(_x(test, features, fill)), 0, 1)


def _predict_ts_daily(family: str, train: pd.DataFrame, test: pd.DataFrame) -> tuple[np.ndarray | None, str]:
    try:
        import statsmodels.api as sm
    except ImportError:
        return None, f"{family}_unavailable"
    train_daily = train.groupby(pd.to_datetime(train["game_date"]).dt.date, observed=True)[TARGET].mean().sort_index()
    test_dates = sorted(pd.to_datetime(test["game_date"]).dt.date.unique().tolist())
    if len(train_daily) < 30 or len(test_dates) == 0:
        return None, f"{family}_insufficient_history"
    horizon = len(test_dates)
    try:
        if family == "arima":
            fit = sm.tsa.ARIMA(train_daily.astype(float), order=(1, 0, 0)).fit()
            fc = fit.forecast(steps=horizon)
            tag = "arima_1_0_0_daily_mean"
        else:
            fit = sm.tsa.SARIMAX(
                train_daily.astype(float),
                order=(1, 0, 0),
                seasonal_order=(1, 0, 0, 7),
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False)
            fc = fit.forecast(steps=horizon)
            tag = "sarimax_1_0_0x1_0_0_7_daily_mean"
    except Exception:
        return None, f"{family}_fit_failed"
    map_fc = {d: float(np.clip(v, 0, 1)) for d, v in zip(test_dates, np.asarray(fc, dtype=float))}
    pred = np.asarray([map_fc.get(d, float(train_daily.iloc[-1])) for d in pd.to_datetime(test["game_date"]).dt.date], dtype=float)
    return pred, tag


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feature-set", action="append", default=[])
    p.add_argument("--families", default=",".join(ALL_FAMILIES))
    p.add_argument("--output-tag", default="")
    p.add_argument("--tune-small", action="store_true", help="Small local tuning grid for lightgbm/random_forest/histgbr.")
    args = p.parse_args()

    feature_sets = args.feature_set if args.feature_set else ["production_sparse72", "production_sparse72_monotone"]
    families = [f.strip() for f in args.families.split(",") if f.strip()]
    bad = [f for f in families if f not in ALL_FAMILIES]
    if bad:
        raise SystemExit(f"Unsupported families: {bad}. Allowed: {ALL_FAMILIES}")

    out_dir = OUT_ROOT / (args.output_tag or "default")
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = _load_frame()
    tbf_features = list(tbf_feature_names(frame, TBF_DEFAULT_FEATURE_SET))
    folds = nested_research_folds(frame)

    rows: list[dict[str, object]] = []
    skips: list[dict[str, object]] = []
    for fs in feature_sets:
        monotone = fs.endswith("_monotone")
        source_fs = fs.removesuffix("_monotone")
        features = [f for f in resolve_feature_names(frame, source_fs) if f in frame.columns]
        for outer_name, nested in folds.items():
            train = nested.outer.train.copy()
            test = nested.outer.validation.copy()
            cut = max(200, int(len(train) * 0.85))
            fit = train.iloc[:cut].copy()
            val = train.iloc[cut:].copy()
            tbf_model, tbf_upper = _fit_tbf(train, tbf_features)
            tbf_hat = predict_nonnegative(tbf_model, "ridge", test, tbf_features, upper=tbf_upper)
            for fam in families:
                if fam in {"arima", "sarimax"}:
                    k_hat, tag = _predict_ts_daily(fam, train, test)
                    if k_hat is None:
                        skips.append(
                            {
                                "feature_set": fs,
                                "outer_fold": outer_name,
                                "model_family": fam,
                                "reason": tag,
                            }
                        )
                        continue
                else:
                    model, fill, tag = _fit_family(fam, fit, val, features, monotone, args.tune_small)
                    if model is None:
                        skips.append(
                            {
                                "feature_set": fs,
                                "outer_fold": outer_name,
                                "model_family": fam,
                                "reason": tag,
                            }
                        )
                        continue
                    k_hat = _predict_non_ts(fam, model, test, features, fill)
                ek_hat = expected_strikeouts(k_hat, tbf_hat)
                k_metrics = metrics(test[TARGET], k_hat)
                ek_metrics = metrics(test["K"], ek_hat, clip_to_unit_interval=False)
                rows.append(
                    {
                        "feature_set": fs,
                        "source_feature_set": source_fs,
                        "monotone_constraints": bool(monotone),
                        "outer_fold": outer_name,
                        "model_family": fam,
                        "model_tag": tag,
                        "n_features": len(features),
                        "train_rows": len(train),
                        "test_rows": len(test),
                        "k_rate_mae": float(k_metrics["mae"]),
                        "k_rate_rmse": float(mean_squared_error(test[TARGET], k_hat) ** 0.5),
                        "k_rate_r2": float(r2_score(test[TARGET], k_hat)),
                        "expected_k_mae": float(ek_metrics["mae"]),
                        "expected_k_rmse": float(mean_squared_error(test["K"], ek_hat) ** 0.5),
                        "expected_k_r2": float(r2_score(test["K"], ek_hat)),
                        "kappa_train": None,
                    }
                )

    if not rows:
        raise SystemExit("No model rows generated.")
    outer_df = pd.DataFrame(rows)
    summary_df = (
        outer_df.groupby(["feature_set", "model_family", "model_tag"], as_index=False)
        .agg(
            outer_folds=("outer_fold", "nunique"),
            mean_expected_k_mae=("expected_k_mae", "mean"),
            std_expected_k_mae=("expected_k_mae", "std"),
            mean_k_rate_mae=("k_rate_mae", "mean"),
            std_k_rate_mae=("k_rate_mae", "std"),
            mean_expected_k_rmse=("expected_k_rmse", "mean"),
            mean_k_rate_rmse=("k_rate_rmse", "mean"),
            mean_expected_k_r2=("expected_k_r2", "mean"),
            mean_k_rate_r2=("k_rate_r2", "mean"),
            mean_test_rows=("test_rows", "mean"),
        )
    )
    summary_df = summary_df.sort_values(["mean_expected_k_mae", "mean_k_rate_mae", "mean_expected_k_rmse"], ascending=[True, True, True])
    best = float(summary_df["mean_expected_k_mae"].min())
    summary_df["delta_expected_k_mae_vs_best"] = summary_df["mean_expected_k_mae"] - best

    outer_csv = out_dir / "outer_results.csv"
    summary_csv = out_dir / "ablation_summary_ranked.csv"
    skips_csv = out_dir / "skipped_families.csv"
    outer_df.to_csv(outer_csv, index=False)
    summary_df.to_csv(summary_csv, index=False)
    pd.DataFrame(skips).to_csv(skips_csv, index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_sets": feature_sets,
        "families_requested": families,
        "rows_scored": len(outer_df),
        "rows_skipped": len(skips),
        "best": summary_df.iloc[0].to_dict(),
        "files": {
            "outer_results_csv": str(outer_csv),
            "summary_csv": str(summary_csv),
            "skips_csv": str(skips_csv),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(summary_df.to_string(index=False))
    print(json.dumps(payload, indent=2))
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()

