"""Compare model families on MAE + market skill + policy risk metrics.

Purpose:
- Extend family ablation beyond MAE-only ranking.
- Evaluate each family on settled replay rows with the same edge-floor sweep logic.
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
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import ElasticNetCV, LassoCV, LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.neighbors import KNeighborsRegressor

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python import config
from Python.count_layer import expected_strikeouts, fit_count_layer_kappa, p_strikeouts_ge
from Python.features import TARGET
from Python.market import devig_two_way
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from Python.training import build_model, fit_regressor, lightgbm_matrix, metrics, predict_clipped, predict_nonnegative

OUT_DIR = ROOT / "artifacts" / "odds_log"
LEDGER_PATH = OUT_DIR / "ledger.parquet"
OUT_CSV = OUT_DIR / "model_family_governance_compare.csv"
OUT_JSON = OUT_DIR / "model_family_governance_compare.json"

FAMILIES = (
    "linear",
    "ridge",
    "lasso",
    "elasticnet",
    "knn",
    "lightgbm",
    "xgboost",
    "random_forest",
    "histgbr",
)


def _fill(train: pd.DataFrame, features: list[str]) -> pd.Series:
    return train[features].replace([np.inf, -np.inf], np.nan).median(numeric_only=True)


def _x(df: pd.DataFrame, features: list[str], fill: pd.Series) -> pd.DataFrame:
    return df[features].replace([np.inf, -np.inf], np.nan).fillna(fill)


def _fit_tbf(train: pd.DataFrame, features: list[str]):
    m = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(m, "ridge", train[features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    return m, upper


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
        m = ElasticNetCV(l1_ratio=[0.1, 0.3, 0.5, 0.7, 0.9], cv=5, random_state=42, max_iter=20000, n_jobs=-1)
        m.fit(_x(train, features, fill), train[TARGET])
        return m, fill, f"elasticnet_alpha_{float(m.alpha_):.6f}_l1_{float(m.l1_ratio_):.2f}"
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
    if family == "random_forest":
        m = RandomForestRegressor(n_estimators=500, min_samples_leaf=20, max_features="sqrt", n_jobs=-1, random_state=42)
        m.fit(_x(train, features, fill), train[TARGET])
        return m, fill, "rf_500_sqrt_leaf20"
    if family == "histgbr":
        m = HistGradientBoostingRegressor(
            learning_rate=0.05,
            max_leaf_nodes=31,
            min_samples_leaf=50,
            max_iter=1000,
            early_stopping=True,
            validation_fraction=0.15,
            random_state=42,
        )
        m.fit(_x(train, features, fill), train[TARGET])
        return m, fill, "histgbr_base"
    if family == "lightgbm":
        params: dict[str, object] = {
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
        return m, None, "lgbm_base"
    if family == "xgboost":
        try:
            from xgboost import XGBRegressor
        except ImportError:
            return None, None, "xgboost_unavailable"
        candidates = (
            [
                {"learning_rate": 0.03, "max_depth": 6, "min_child_weight": 50, "subsample": 0.8, "colsample_bytree": 0.7, "reg_alpha": 0.1, "reg_lambda": 2.0},
                {"learning_rate": 0.05, "max_depth": 4, "min_child_weight": 30, "subsample": 0.9, "colsample_bytree": 0.8, "reg_alpha": 0.01, "reg_lambda": 1.0},
                {"learning_rate": 0.02, "max_depth": 8, "min_child_weight": 60, "subsample": 0.8, "colsample_bytree": 0.7, "reg_alpha": 0.1, "reg_lambda": 3.0},
            ]
            if tune_small
            else [{"learning_rate": 0.03, "max_depth": 6, "min_child_weight": 50, "subsample": 0.8, "colsample_bytree": 0.7, "reg_alpha": 0.1, "reg_lambda": 2.0}]
        )
        mono_cons: tuple[int, ...] | None = None
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
            mono_cons = tuple(cons)
        best, best_tag, best_mae = None, "", float("inf")
        xtr = _x(train, features, fill)
        xva = _x(val, features, fill)
        for i, g in enumerate(candidates):
            params: dict[str, object] = {
                "n_estimators": 2000,
                "objective": "reg:squarederror",
                "random_state": 42,
                "n_jobs": -1,
                **g,
            }
            if mono_cons is not None:
                params["monotone_constraints"] = mono_cons
            m = XGBRegressor(**params)
            m.fit(xtr, train[TARGET], eval_set=[(xva, val[TARGET])], verbose=False)
            pred = np.clip(m.predict(xva), 0, 1)
            mae = float(metrics(val[TARGET], pred)["mae"])
            if mae < best_mae:
                best, best_mae = m, mae
                base_tag = "xgboost_tuned_small" if tune_small else "xgboost_base"
                mono_tag = "_monotone" if mono_cons is not None else "_unconstrained"
                best_tag = f"{base_tag}_{i}{mono_tag}"
        return best, fill, best_tag
    raise ValueError(f"Unsupported family {family}")


def _predict_non_ts(family: str, model, test: pd.DataFrame, features: list[str], fill: pd.Series | None) -> np.ndarray:
    if family == "lightgbm":
        return predict_clipped(model, "lightgbm", test, features)
    assert fill is not None
    return np.clip(model.predict(_x(test, features, fill)), 0, 1)


def _fit_calibrator(p_raw: np.ndarray, y: np.ndarray, mode: str):
    p = np.clip(np.asarray(p_raw, dtype=np.float64), 1e-6, 1 - 1e-6)
    yv = np.asarray(y, dtype=np.float64)
    if mode == "raw" or len(p) < 100 or yv.min() == yv.max():
        return None
    if mode == "platt":
        x = np.log(p / (1 - p)).reshape(-1, 1)
        clf = LogisticRegression(solver="lbfgs", max_iter=1000)
        clf.fit(x, yv)
        return clf
    if mode == "isotonic":
        iso = IsotonicRegression(y_min=1e-6, y_max=1 - 1e-6, out_of_bounds="clip")
        iso.fit(p, yv)
        return iso
    return None


def _apply_calibrator(p_raw: np.ndarray, mode: str, calibrator) -> np.ndarray:
    p = np.clip(np.asarray(p_raw, dtype=np.float64), 1e-6, 1 - 1e-6)
    if mode == "raw" or calibrator is None:
        return p
    if mode == "platt":
        x = np.log(p / (1 - p)).reshape(-1, 1)
        return np.clip(calibrator.predict_proba(x)[:, 1], 1e-6, 1 - 1e-6)
    return np.clip(calibrator.predict(p), 1e-6, 1 - 1e-6)


def _prob_metrics(y: np.ndarray, p: np.ndarray, p_mkt: np.ndarray) -> dict[str, float]:
    yv = np.asarray(y, dtype=np.float64)
    pm = np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1 - 1e-6)
    pb = np.clip(np.asarray(p_mkt, dtype=np.float64), 1e-6, 1 - 1e-6)
    n = len(yv)
    brier = float(np.mean((pm - yv) ** 2))
    brier_base = float(np.mean((pb - yv) ** 2))
    logloss = float(-np.mean(yv * np.log(pm) + (1.0 - yv) * np.log(1.0 - pm)))
    logloss_base = float(-np.mean(yv * np.log(pb) + (1.0 - yv) * np.log(1.0 - pb)))
    bins = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    mce = 0.0
    for i in range(10):
        lo, hi = bins[i], bins[i + 1]
        mask = (pm >= lo) & (pm <= hi) if i == 9 else (pm >= lo) & (pm < hi)
        count = int(mask.sum())
        if count == 0:
            continue
        err = abs(float(yv[mask].mean() - pm[mask].mean()))
        ece += err * (count / n)
        mce = max(mce, err)
    return {
        "brier": brier,
        "logloss": logloss,
        "ece": float(ece),
        "mce": float(mce),
        "brier_skill_vs_market": float(1.0 - (brier / brier_base)) if brier_base > 0 else float("nan"),
        "logloss_skill_vs_market": float(1.0 - (logloss / logloss_base)) if logloss_base > 0 else float("nan"),
    }


def _risk_metrics(scoped: pd.DataFrame) -> dict[str, float | int]:
    if scoped.empty:
        return {
            "n_bets": 0,
            "roi": np.nan,
            "sharpe": np.nan,
            "sortino": np.nan,
            "cvar_95": np.nan,
            "max_drawdown_pct": np.nan,
            "turnover_stability": np.nan,
            "positive_clv_share": np.nan,
        }
    stake = scoped["stake"].astype(float).to_numpy()
    rpd = scoped["rpd"].astype(float).to_numpy()
    pnl = stake * rpd
    roi = float(pnl.sum() / stake.sum()) if stake.sum() > 0 else np.nan
    sharpe = float(rpd.mean() / rpd.std(ddof=1)) if len(rpd) > 1 and rpd.std(ddof=1) > 0 else np.nan
    dn = rpd[rpd < 0]
    sortino = float(rpd.mean() / np.sqrt(np.mean(np.square(dn)))) if len(dn) > 0 else np.nan
    q = float(np.quantile(rpd, 0.05))
    cvar = float(rpd[rpd <= q].mean()) if len(rpd) else np.nan
    equity = 1.0 + np.cumsum(pnl)
    peak = np.maximum.accumulate(equity)
    dd = np.where(peak > 0, (equity - peak) / peak, 0.0)
    max_dd_pct = float(abs(np.min(dd))) if len(dd) else np.nan
    by_day = scoped.groupby("game_date", observed=True).size().to_numpy()
    turnover = float(1.0 - (by_day.std() / by_day.mean())) if len(by_day) >= 3 and by_day.mean() > 0 else np.nan
    clv = pd.to_numeric(scoped.get("clv_pp"), errors="coerce")
    pos_clv = float((clv > 0).mean()) if clv.notna().any() else np.nan
    return {
        "n_bets": int(len(scoped)),
        "roi": roi,
        "sharpe": sharpe,
        "sortino": sortino,
        "cvar_95": cvar,
        "max_drawdown_pct": max_dd_pct,
        "turnover_stability": turnover,
        "positive_clv_share": pos_clv,
    }


def _returns_per_dollar(price: float, y: float) -> float:
    b = (price / 100.0) if price > 0 else (100.0 / abs(price))
    return float(b if y >= 1.0 else -1.0)


def _result_to_y(v: object) -> float | None:
    s = str(v or "").strip().lower()
    if s == "win":
        return 1.0
    if s == "loss":
        return 0.0
    return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--feature-set", action="append", default=[])
    p.add_argument("--families", default="ridge,lightgbm,histgbr,random_forest,xgboost")
    p.add_argument("--calibration-mode", default="isotonic", choices=["raw", "platt", "isotonic"])
    p.add_argument("--floor-min", type=float, default=0.005)
    p.add_argument("--floor-max", type=float, default=0.08)
    p.add_argument("--floor-step", type=float, default=0.005)
    p.add_argument("--min-bets", type=int, default=25)
    p.add_argument("--output-tag", default="")
    p.add_argument("--tune-small", action="store_true", help="Small local tuning grid for xgboost.")
    args = p.parse_args()

    families = [f.strip() for f in args.families.split(",") if f.strip()]
    bad = [f for f in families if f not in FAMILIES]
    if bad:
        raise SystemExit(f"Unsupported families: {bad}. Allowed: {FAMILIES}")

    frame_all_pl = pl.read_parquet(config.PITCHER_TRAINING_PATH).with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
    settled = (
        pl.read_parquet(LEDGER_PATH)
        .filter(
            (pl.col("status") == "settled")
            & pl.col("line").is_not_null()
            & pl.col("side").is_not_null()
            & pl.col("bet_price").is_not_null()
            & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
        )
    )
    train = (
        frame_all_pl
        .filter(pl.col("season").is_in(list(config.FEATURE_RESEARCH_SEASONS)))
        .filter(pl.col(TARGET).is_not_null() & pl.col("K").is_not_null() & pl.col("PA").is_not_null() & pl.col("game_date").is_not_null())
        .sort(["game_date", "player_name"])
        .to_pandas()
        .reset_index(drop=True)
    )
    score_pool = (
        frame_all_pl
        .filter(pl.col("game_pk").is_not_null() & pl.col("pitcher").is_not_null() & pl.col("game_date").is_not_null())
        .sort(["game_date", "player_name"])
        .to_pandas()
        .reset_index(drop=True)
    )

    floors = np.arange(args.floor_min, args.floor_max + 1e-12, args.floor_step)
    rows: list[dict[str, object]] = []
    tag_rows: list[dict[str, object]] = []

    feature_sets = args.feature_set if args.feature_set else ["production_sparse72", "production_sparse72_monotone"]
    for fs in feature_sets:
        monotone = fs.endswith("_monotone")
        source_set = fs.removesuffix("_monotone")
        k_features = [c for c in resolve_feature_names(train, source_set) if c in train.columns]
        tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
        cut = int(len(train) * 0.85)
        fit = train.iloc[:cut].copy()
        val = train.iloc[cut:].copy()
        tbf_model, tbf_upper = _fit_tbf(train, tbf_features)
        tbf_hat = predict_nonnegative(tbf_model, "ridge", score_pool, tbf_features, upper=tbf_upper)

        for fam in families:
            model, fill, model_tag = _fit_family(fam, fit, val, k_features, monotone, args.tune_small)
            if model is None:
                continue
            k_hat = _predict_non_ts(fam, model, score_pool, k_features, fill)
            kappa = float(fit_count_layer_kappa(k=train["K"], pa=train["PA"], k_rate=np.clip(_predict_non_ts(fam, model, train, k_features, fill), 1e-6, 1 - 1e-6)))
            ek_hat = expected_strikeouts(k_hat, tbf_hat)
            val_tbf_hat = predict_nonnegative(tbf_model, "ridge", val, tbf_features, upper=tbf_upper)
            val_k_hat = _predict_non_ts(fam, model, val, k_features, fill)
            val_ek_hat = expected_strikeouts(val_k_hat, val_tbf_hat)

            preds = score_pool[["game_pk", "pitcher", "game_date"]].copy()
            preds["game_date"] = pd.to_datetime(preds["game_date"]).dt.date
            preds["k_rate_pred"] = np.clip(k_hat, 1e-6, 1 - 1e-6)
            preds["projected_tbf"] = tbf_hat
            preds["expected_k_pred"] = ek_hat
            preds = preds.drop_duplicates(["game_pk", "pitcher", "game_date"])

            led = settled.with_columns(
                pl.col("game_date").cast(pl.Date),
                pl.col("game_pk").cast(pl.Int64),
                pl.col("pitcher").cast(pl.Int64),
            )
            joined = led.join(pl.from_pandas(preds), on=["game_pk", "pitcher", "game_date"], how="inner").to_pandas()
            if joined.empty:
                continue

            p_raw, p_mkt, y, rpd = [], [], [], []
            for row in joined.to_dict(orient="records"):
                try:
                    line = float(row["line"])
                    pov = float(
                        p_strikeouts_ge(
                            line,
                            k_rate=np.array([float(row["k_rate_pred"])]),
                            projected_tbf=np.array([float(row["projected_tbf"])]),
                            family="binomial",
                        )[0]
                    )
                    side = str(row.get("side") or "")
                    p_side = pov if side == "over" else (1.0 - pov)
                    po, pu = devig_two_way(float(row["over_price"]), float(row["under_price"]))
                    p_base = float(po if side == "over" else pu)
                    yy = _result_to_y(row.get("result"))
                    if yy is None:
                        continue
                    p_raw.append(p_side)
                    p_mkt.append(p_base)
                    y.append(yy)
                    rpd.append(_returns_per_dollar(float(row["bet_price"]), yy))
                except Exception:
                    continue
            if not y:
                continue

            df = joined.iloc[: len(y)].copy()
            df["y"] = y
            df["p_raw"] = p_raw
            df["p_market"] = p_mkt
            df["rpd"] = rpd
            cal = _fit_calibrator(np.asarray(p_raw), np.asarray(y), args.calibration_mode)
            df["p_model"] = _apply_calibrator(np.asarray(p_raw), args.calibration_mode, cal)
            df["edge"] = df["p_model"] - df["p_market"]

            mae_k_rate = float(metrics(val[TARGET], val_k_hat)["mae"])
            mae_expected = float(metrics(val["K"], val_ek_hat, clip_to_unit_interval=False)["mae"])
            rmse_expected = float(mean_squared_error(val["K"], val_ek_hat) ** 0.5)
            r2_expected = float(r2_score(val["K"], val_ek_hat))
            skill = _prob_metrics(np.asarray(y, dtype=float), df["p_model"].to_numpy(float), df["p_market"].to_numpy(float))

            best_row = None
            for floor in floors:
                scoped = df[df["edge"] >= float(floor)].copy()
                risk = _risk_metrics(scoped)
                rec = {
                    "feature_set": fs,
                    "model_family": fam,
                    "model_tag": model_tag,
                    "calibration_mode": args.calibration_mode,
                    "edge_floor": float(floor),
                    "kappa": kappa,
                    "expected_k_mae": mae_expected,
                    "expected_k_rmse": rmse_expected,
                    "expected_k_r2": r2_expected,
                    "k_rate_mae": mae_k_rate,
                    **skill,
                    **risk,
                }
                rec["eligible"] = rec["n_bets"] >= int(args.min_bets)
                rec["composite"] = (
                    (rec["sortino"] if pd.notna(rec["sortino"]) else -999.0) * 2.0
                    + (rec["roi"] if pd.notna(rec["roi"]) else -999.0) * 1.0
                    + (rec["positive_clv_share"] if pd.notna(rec["positive_clv_share"]) else 0.0) * 0.5
                    + (rec["turnover_stability"] if pd.notna(rec["turnover_stability"]) else 0.0) * 0.25
                    - (rec["max_drawdown_pct"] if pd.notna(rec["max_drawdown_pct"]) else 9.0) * 0.5
                )
                rows.append(rec)
                if best_row is None or (rec["eligible"], rec["composite"]) > (best_row["eligible"], best_row["composite"]):
                    best_row = rec
            if best_row is not None:
                tag_rows.append(best_row)

    all_df = pd.DataFrame(rows)
    best_df = pd.DataFrame(tag_rows)
    if best_df.empty:
        raise SystemExit("No model-family governance rows produced.")
    best_df = best_df.sort_values(
        ["brier_skill_vs_market", "logloss_skill_vs_market", "composite", "roi", "n_bets"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    best_df["decision"] = np.where(
        (best_df["brier_skill_vs_market"] > 0) & (best_df["logloss_skill_vs_market"] > 0) & (best_df["eligible"]),
        "PROMOTE",
        "HOLD",
    )
    best_df["rank"] = np.arange(1, len(best_df) + 1)

    tag = args.output_tag.strip()
    out_csv = OUT_CSV if not tag else OUT_CSV.with_name(f"{OUT_CSV.stem}_{tag}{OUT_CSV.suffix}")
    out_best = out_csv.with_name(out_csv.stem + "_best_rows.csv")
    out_json = OUT_JSON if not tag else OUT_JSON.with_name(f"{OUT_JSON.stem}_{tag}{OUT_JSON.suffix}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    all_df.to_csv(out_csv, index=False)
    best_df.to_csv(out_best, index=False)

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_sets": feature_sets,
        "families": families,
        "calibration_mode": args.calibration_mode,
        "rows_total": int(len(all_df)),
        "rows_best": int(len(best_df)),
        "winner": best_df.iloc[0].to_dict(),
        "files": {"full_csv": str(out_csv), "best_rows_csv": str(out_best)},
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(best_df.to_string(index=False))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

