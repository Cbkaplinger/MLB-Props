"""Run ensemble sweep using tuned LGBM params from Optuna artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python import config
from Python.count_layer import fit_count_layer_kappa, p_strikeouts_ge
from Python.features import TARGET
from Python.market import devig_two_way
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from Python.training import build_model, fit_regressor, lightgbm_matrix, predict_clipped, predict_nonnegative
from compare_feature_set_market_skill import _prob_metrics
from edge_floor_sweep_governance import _load_settled_ledger, _risk_metrics

OUT_DIR = ROOT / "artifacts" / "odds_log"


def _feature_constraints(features: list[str]) -> list[int]:
    pos = ("k_rate_", "opp_lineup_k", "opp_lineup_whiff", "opp_lineup_swstr", "opp_lineup_chase", "park_k_factor")
    neg = ("opp_lineup_zcontact", "opp_lineup_bb")
    out = []
    for f in features:
        if any(f == s or f.startswith(s) for s in pos):
            out.append(1)
        elif any(f == s or f.startswith(s) for s in neg):
            out.append(-1)
        else:
            out.append(0)
    return out


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


def _result_to_y(v: object) -> float | None:
    s = str(v or "").strip().lower()
    if s == "win":
        return 1.0
    if s == "loss":
        return 0.0
    return None


def _returns_per_dollar(price: float, y: float) -> float:
    b = (price / 100.0) if price > 0 else (100.0 / abs(price))
    return float(b if y >= 1.0 else -1.0)


def _parse_params(path: Path, monotone_constraints: list[int] | None) -> dict[str, object]:
    df = pd.read_csv(path)
    if "best_value" in df.columns:
        row = df.sort_values("best_value").iloc[0]
    else:
        row = df.iloc[0]
    keys = [c for c in df.columns if c.startswith("param_")]
    params = {k.replace("param_", ""): row[k] for k in keys}
    cast_int = {"num_leaves", "min_child_samples", "bagging_freq"}
    for k in list(params):
        if pd.isna(params[k]):
            params.pop(k)
        elif k in cast_int:
            params[k] = int(params[k])
        else:
            try:
                params[k] = float(params[k])
            except (TypeError, ValueError):
                params[k] = params[k]
    params["objective"] = "regression"
    params["seed"] = 42
    params["feature_fraction_seed"] = 42
    params["bagging_seed"] = 42
    params["data_random_seed"] = 42
    params.setdefault("bagging_freq", 1)
    if monotone_constraints is not None:
        params["monotone_constraints"] = monotone_constraints
        params["monotone_constraints_method"] = "advanced"
    return params


def _score_feature_set(
    frame_all_pl: pl.DataFrame,
    settled: pl.DataFrame,
    feature_set: str,
    calibration_mode: str,
    tuned_params: dict[str, object],
) -> pd.DataFrame:
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
    monotone = feature_set.endswith("_monotone")
    source_set = feature_set.removesuffix("_monotone")
    k_features = list(resolve_feature_names(train, source_set))
    tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))

    cut = int(len(train) * 0.85)
    fit = train.iloc[:cut]
    val = train.iloc[cut:]
    k_model = build_model("lightgbm", lightgbm_verbosity=-1, lightgbm_params=tuned_params)
    fit_regressor(
        k_model,
        "lightgbm",
        lightgbm_matrix(fit, k_features),
        fit[TARGET],
        validation_features=lightgbm_matrix(val, k_features),
        validation_target=val[TARGET],
        early_stopping_rounds=200,
        log_evaluation_period=0,
    )
    tbf_model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(tbf_model, "ridge", train[tbf_features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))
    _ = fit_count_layer_kappa(k=train["K"], pa=train["PA"], k_rate=predict_clipped(k_model, "lightgbm", train, k_features))

    preds = score_pool[["game_pk", "pitcher", "game_date"]].copy()
    preds["game_date"] = pd.to_datetime(preds["game_date"]).dt.date
    preds["k_rate_pred"] = predict_clipped(k_model, "lightgbm", score_pool, k_features)
    preds["projected_tbf"] = predict_nonnegative(tbf_model, "ridge", score_pool, tbf_features, upper=upper)
    preds = preds.drop_duplicates(["game_pk", "pitcher", "game_date"])

    led = settled.with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("game_pk").cast(pl.Int64),
        pl.col("pitcher").cast(pl.Int64),
    )
    joined = led.join(pl.from_pandas(preds), on=["game_pk", "pitcher", "game_date"], how="inner").to_pandas()
    if joined.empty:
        return pd.DataFrame()

    p_raw, y, p_mkt, rpd = [], [], [], []
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
        return pd.DataFrame()
    df = joined.iloc[: len(y)].copy()
    df["y"] = y
    df["p_raw"] = p_raw
    df["p_market"] = p_mkt
    df["rpd"] = rpd
    calibrator = _fit_calibrator(np.asarray(p_raw), np.asarray(y), calibration_mode)
    df["p_model"] = _apply_calibrator(np.asarray(p_raw), calibration_mode, calibrator)
    df["edge"] = df["p_model"] - df["p_market"]
    df["feature_set"] = feature_set
    return df


def _weight_grid(step: float):
    units = int(round(1.0 / step))
    for i in range(units + 1):
        for j in range(units + 1 - i):
            k = units - i - j
            yield i / units, j / units, k / units


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--weight-step", type=float, default=0.05)
    p.add_argument("--floor-min", type=float, default=0.005)
    p.add_argument("--floor-max", type=float, default=0.08)
    p.add_argument("--floor-step", type=float, default=0.005)
    p.add_argument("--min-bets", type=int, default=25)
    p.add_argument("--calibration-mode", default="isotonic", choices=["raw", "platt", "isotonic"])
    p.add_argument("--output-tag", default="tuned_local")
    p.add_argument("--s72-summary", required=True)
    p.add_argument("--s72m-summary", required=True)
    p.add_argument("--f58-summary", required=True)
    args = p.parse_args()

    floors = np.arange(args.floor_min, args.floor_max + 1e-12, args.floor_step)
    frame_all_pl = pl.read_parquet(config.PITCHER_TRAINING_PATH).with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
    settled = _load_settled_ledger()

    fs_list = [
        "production_sparse72",
        "production_sparse72_monotone",
        "production_final58_consensus",
    ]
    param_paths = {
        "production_sparse72": Path(args.s72_summary),
        "production_sparse72_monotone": Path(args.s72m_summary),
        "production_final58_consensus": Path(args.f58_summary),
    }
    scored: dict[str, pd.DataFrame] = {}
    for fs in fs_list:
        train = (
            frame_all_pl.filter(pl.col("season").is_in(list(config.FEATURE_RESEARCH_SEASONS)))
            .filter(pl.col(TARGET).is_not_null() & pl.col("K").is_not_null() & pl.col("PA").is_not_null() & pl.col("game_date").is_not_null())
            .to_pandas()
        )
        features = list(resolve_feature_names(train, fs.removesuffix("_monotone")))
        mono = _feature_constraints(features) if fs.endswith("_monotone") else None
        tuned = _parse_params(param_paths[fs], mono)
        df = _score_feature_set(frame_all_pl, settled, fs, args.calibration_mode, tuned)
        if df.empty:
            raise SystemExit(f"No scored rows for {fs}")
        df["row_id"] = df[["game_date", "game_pk", "pitcher", "line", "side", "bet_price"]].astype(str).agg("|".join, axis=1)
        scored[fs] = df

    base = scored[fs_list[0]][["row_id", "y", "p_market", "stake", "game_date", "clv_pp", "rpd"]].copy()
    for fs in fs_list:
        base = base.merge(scored[fs][["row_id", "p_model"]].rename(columns={"p_model": f"p_{fs}"}), on="row_id", how="inner")

    rows = []
    for w0, w1, w2 in _weight_grid(args.weight_step):
        w = {"production_sparse72": w0, "production_sparse72_monotone": w1, "production_final58_consensus": w2}
        blend = (
            w["production_sparse72"] * base["p_production_sparse72"].to_numpy(float)
            + w["production_sparse72_monotone"] * base["p_production_sparse72_monotone"].to_numpy(float)
            + w["production_final58_consensus"] * base["p_production_final58_consensus"].to_numpy(float)
        )
        work = base.copy()
        work["p_model"] = np.clip(blend, 1e-6, 1 - 1e-6)
        work["edge"] = work["p_model"] - work["p_market"]
        skill = _prob_metrics(work["y"].to_numpy(float), work["p_model"].to_numpy(float), work["p_market"].to_numpy(float))
        for floor in floors:
            scoped = work[work["edge"] >= float(floor)].copy()
            risk = _risk_metrics(scoped)
            row = {
                "weights_json": json.dumps(w),
                "edge_floor": float(floor),
                **skill,
                **risk,
            }
            row["eligible"] = row["n_bets"] >= int(args.min_bets)
            row["profit_score"] = (
                (row["roi"] if pd.notna(row["roi"]) else -999.0) * 4.0
                + (row["sortino"] if pd.notna(row["sortino"]) else -999.0) * 2.5
                + (row["sharpe"] if pd.notna(row["sharpe"]) else -999.0) * 1.5
                + (row["positive_clv_share"] if pd.notna(row["positive_clv_share"]) else 0.0) * 0.75
                - (row["max_drawdown_pct"] if pd.notna(row["max_drawdown_pct"]) else 9.0) * 1.0
            )
            rows.append(row)

    out = pd.DataFrame(rows)
    elig = out[out["eligible"]].copy()
    if elig.empty:
        elig = out.copy()
    ranked = elig.sort_values(
        ["profit_score", "roi", "sortino", "brier_skill_vs_market", "logloss_skill_vs_market", "n_bets"],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)

    out_csv = OUT_DIR / f"ensemble_sweep_tuned_lgbm_{args.output_tag}.csv"
    ranked_csv = OUT_DIR / f"ensemble_sweep_tuned_lgbm_{args.output_tag}_ranked.csv"
    out.to_csv(out_csv, index=False)
    ranked.to_csv(ranked_csv, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "winner": ranked.iloc[0].to_dict(),
        "files": {"full_csv": str(out_csv), "ranked_csv": str(ranked_csv)},
    }
    (OUT_DIR / f"ensemble_sweep_tuned_lgbm_{args.output_tag}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(ranked.head(20).to_string(index=False))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

