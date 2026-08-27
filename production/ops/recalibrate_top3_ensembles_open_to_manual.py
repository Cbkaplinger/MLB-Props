"""Fit top-3 ensemble calibrations on open data, replay on manual ledger.

Workflow:
1) Read top-3 ensemble configs from ranked ensemble sweep CSV.
2) Build raw model P(over) for each feature-set lane.
3) Fit calibration on 2025-2026 open rows with realized outcomes.
4) Apply calibrated probabilities to manual settled ledger universe.
5) Report policy metrics by edge floor + duplicate bet diagnostics.
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
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python import config
from Python.count_layer import p_strikeouts_ge
from Python.features import TARGET
from Python.market import devig_two_way
from Python.registries import resolve_feature_names
from Python.tbf import TBF_DEFAULT_FEATURE_SET, TBF_TARGET, tbf_feature_names
from Python.training import (
    build_model,
    fit_regressor,
    lightgbm_matrix,
    predict_clipped,
    predict_nonnegative,
)

OPEN_CSV = ROOT / "data" / "Odds-Open-Close-2025-2026" / "pitcher_strikeouts_early_open_2025_2026.csv"
PITCHER_GAMES = ROOT / "data" / "processed" / "pitcher_games.parquet"
LEDGER = ROOT / "artifacts" / "odds_log" / "ledger.parquet"
ENSEMBLE_RANKED = ROOT / "artifacts" / "odds_log" / "ensemble_sweep_ranked_ensemble_full_aug21.csv"
OUT_DIR = ROOT / "artifacts" / "odds_log"


def _fit_calibrator(p_raw: np.ndarray, y: np.ndarray, mode: str):
    p = np.clip(np.asarray(p_raw, dtype=np.float64), 1e-6, 1 - 1e-6)
    yv = np.asarray(y, dtype=np.float64)
    if mode == "raw" or len(p) < 100 or yv.min() == yv.max():
        return None
    if mode == "platt":
        x = np.log(p / (1.0 - p)).reshape(-1, 1)
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
        x = np.log(p / (1.0 - p)).reshape(-1, 1)
        return np.clip(calibrator.predict_proba(x)[:, 1], 1e-6, 1 - 1e-6)
    if mode == "isotonic":
        return np.clip(calibrator.predict(p), 1e-6, 1 - 1e-6)
    return p


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


def _risk_metrics(rpd: np.ndarray) -> dict[str, float | None]:
    if len(rpd) == 0:
        return {
            "sharpe": None,
            "sortino": None,
            "max_drawdown_pct": None,
            "cvar_95": None,
            "profit_factor": None,
            "expectancy_per_bet": None,
            "positive_bet_share": None,
        }
    mean = float(np.mean(rpd))
    std = float(np.std(rpd))
    sharpe = (mean / std) if std > 0 else None
    downside = rpd[rpd < 0.0]
    downside_dev = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else None
    sortino = (mean / downside_dev) if downside_dev and downside_dev > 0 else None
    cum = 1.0 + np.cumsum(rpd)
    peaks = np.maximum.accumulate(cum)
    dd = np.divide(cum - peaks, peaks, out=np.zeros_like(cum), where=peaks > 0)
    max_dd = abs(float(np.min(dd))) if len(dd) else None
    q = float(np.quantile(rpd, 0.05))
    cvar = float(np.mean(rpd[rpd <= q])) if len(rpd) else None
    gross_win = float(np.sum(rpd[rpd > 0]))
    gross_loss = abs(float(np.sum(rpd[rpd < 0])))
    pf = (gross_win / gross_loss) if gross_loss > 0 else None
    return {
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown_pct": max_dd,
        "cvar_95": cvar,
        "profit_factor": pf,
        "expectancy_per_bet": mean,
        "positive_bet_share": float(np.mean(rpd > 0.0)),
    }


def _parse_weight_json(s: str) -> dict[str, float]:
    payload = json.loads(s)
    out = {}
    for k, v in payload.items():
        out[str(k)] = float(v)
    return out


def _fit_models_for_feature_sets(feature_sets: list[str]) -> dict[str, pd.DataFrame]:
    frame_all_pl = pl.read_parquet(config.PITCHER_TRAINING_PATH).with_columns(
        pl.col("game_date").cast(pl.Datetime, strict=False)
    )
    out: dict[str, pd.DataFrame] = {}
    for feature_set in feature_sets:
        train = (
            frame_all_pl
            .filter(pl.col("season").is_in(list(config.FEATURE_RESEARCH_SEASONS)))
            .filter(
                pl.col(TARGET).is_not_null()
                & pl.col("K").is_not_null()
                & pl.col("PA").is_not_null()
                & pl.col("game_date").is_not_null()
            )
            .sort(["game_date", "player_name"])
            .to_pandas()
            .reset_index(drop=True)
        )
        score_pool = (
            frame_all_pl
            .filter(
                pl.col("game_pk").is_not_null()
                & pl.col("pitcher").is_not_null()
                & pl.col("game_date").is_not_null()
            )
            .sort(["game_date", "player_name"])
            .to_pandas()
            .reset_index(drop=True)
        )
        source = feature_set.removesuffix("_monotone")
        monotone = feature_set.endswith("_monotone")
        k_features = list(resolve_feature_names(train, source))
        tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
        params: dict[str, object] | None = None
        if monotone:
            pos = ("k_rate_", "opp_lineup_k", "opp_lineup_whiff", "opp_lineup_swstr", "opp_lineup_chase", "park_k_factor")
            neg = ("opp_lineup_zcontact", "opp_lineup_bb")
            cons = []
            for f in k_features:
                if any(f == s or f.startswith(s) for s in pos):
                    cons.append(1)
                elif any(f == s or f.startswith(s) for s in neg):
                    cons.append(-1)
                else:
                    cons.append(0)
            params = {"monotone_constraints": cons, "monotone_constraints_method": "advanced"}
        cut = int(len(train) * 0.85)
        fit = train.iloc[:cut]
        val = train.iloc[cut:]
        k_model = build_model("lightgbm", lightgbm_verbosity=-1, lightgbm_params=params)
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
        k_hat = predict_clipped(k_model, "lightgbm", score_pool, k_features)
        tbf_hat = predict_nonnegative(tbf_model, "ridge", score_pool, tbf_features, upper=upper)
        preds = score_pool[["game_date", "pitcher"]].copy()
        preds["game_date_d"] = pd.to_datetime(preds["game_date"]).dt.date
        preds["pitcher_id_i"] = pd.to_numeric(preds["pitcher"], errors="coerce").astype("Int64")
        preds["k_rate_pred"] = k_hat
        preds["projected_tbf"] = tbf_hat
        preds = preds.drop_duplicates(["game_date_d", "pitcher_id_i"])
        out[feature_set] = preds[["game_date_d", "pitcher_id_i", "k_rate_pred", "projected_tbf"]].copy()
    return out


def _open_rows() -> pd.DataFrame:
    opens = (
        pl.read_csv(OPEN_CSV, try_parse_dates=True, infer_schema_length=20000)
        .with_columns(
            pl.col("game_date").cast(pl.Utf8).str.to_date(strict=False).alias("game_date_d"),
            pl.col("pitcher_id").cast(pl.Int64).alias("pitcher_id_i"),
            pl.col("line").cast(pl.Float64),
            pl.col("over_odds").cast(pl.Float64),
            pl.col("under_odds").cast(pl.Float64),
            pl.col("fetched_at").cast(pl.Utf8).str.to_datetime(time_zone="UTC", strict=False).alias("fetched_at_ts"),
        )
        .filter(
            pl.col("game_date_d").is_not_null()
            & pl.col("pitcher_id_i").is_not_null()
            & pl.col("line").is_not_null()
            & pl.col("over_odds").is_not_null()
            & pl.col("under_odds").is_not_null()
        )
        .sort("fetched_at_ts")
        .unique(subset=["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line"], keep="last")
    )
    games = (
        pl.read_parquet(PITCHER_GAMES)
        .select(
            pl.col("game_date").cast(pl.Date).alias("game_date_d"),
            pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
            pl.col("K").cast(pl.Float64).alias("actual_k"),
        )
    )
    out = opens.join(games, on=["game_date_d", "pitcher_id_i"], how="inner").to_pandas()
    out["game_date_d"] = pd.to_datetime(out["game_date_d"]).dt.date
    return out


def _manual_rows() -> pd.DataFrame:
    led = (
        pl.read_parquet(LEDGER)
        .filter(
            (pl.col("status") == "settled")
            & pl.col("line").is_not_null()
            & pl.col("side").is_not_null()
            & pl.col("bet_price").is_not_null()
            & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
        )
        .with_columns(
            pl.col("game_date").cast(pl.Date).alias("game_date_d"),
            pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
        )
    )
    games = (
        pl.read_parquet(PITCHER_GAMES)
        .select(
            pl.col("game_date").cast(pl.Date).alias("game_date_d"),
            pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
            pl.col("K").cast(pl.Float64).alias("actual_k"),
            pl.col("PA").cast(pl.Float64).alias("actual_pa"),
        )
    )
    out = led.join(games, on=["game_date_d", "pitcher_id_i"], how="left").to_pandas()
    out["game_date_d"] = pd.to_datetime(out["game_date_d"]).dt.date
    return out


def _result_to_y(v: object) -> float | None:
    s = str(v or "").strip().lower()
    if s == "win":
        return 1.0
    if s == "loss":
        return 0.0
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument(
        "--ranked-ensemble-csv",
        default=str(ENSEMBLE_RANKED),
        help="Ranked ensemble sweep CSV used to choose top-N configs.",
    )
    parser.add_argument("--calibration-mode", choices=["platt", "isotonic"], default="isotonic")
    parser.add_argument("--floors", default="0.08,0.10,0.12")
    parser.add_argument(
        "--dedupe-manual",
        action="store_true",
        help="Keep one ticket per (game_date, player_name, line, side) using highest edge then best price.",
    )
    parser.add_argument("--output-tag", default="open_top3_transfer")
    args = parser.parse_args()

    floors = [float(x.strip()) for x in args.floors.split(",") if x.strip()]
    ranked = pd.read_csv(Path(args.ranked_ensemble_csv)).sort_values("rank")
    top = ranked.head(int(args.top_n)).copy()
    configs = [_parse_weight_json(x) for x in top["weights_json"].tolist()]
    feature_sets = sorted({k for c in configs for k, v in c.items() if float(v) > 0})
    preds_by_feature = _fit_models_for_feature_sets(feature_sets)
    open_df = _open_rows()
    manual_df = _manual_rows()

    all_rows: list[dict[str, object]] = []
    duplicate_rows: list[dict[str, object]] = []
    picks_by_config_floor: dict[tuple[str, float], pd.DataFrame] = {}

    for i, cfg in enumerate(configs, start=1):
        label = f"top{i}"
        active = {k: v for k, v in cfg.items() if v > 0}
        # Build open calibration frame.
        open_work = open_df.copy()
        p_over_blend = np.zeros(len(open_work), dtype=np.float64)
        valid_mask = np.ones(len(open_work), dtype=bool)
        for fs, w in active.items():
            p = preds_by_feature[fs]
            joined = open_work.merge(p, on=["game_date_d", "pitcher_id_i"], how="left")
            open_work = joined
            miss = joined["k_rate_pred"].isna() | joined["projected_tbf"].isna()
            valid_mask &= ~miss.to_numpy()
            pov = np.zeros(len(joined), dtype=np.float64)
            good_idx = np.where(~miss.to_numpy())[0]
            for idx_ in good_idx:
                r = joined.iloc[idx_]
                pov[idx_] = float(
                    p_strikeouts_ge(
                        float(r["line"]),
                        k_rate=np.array([float(r["k_rate_pred"])]),
                        projected_tbf=np.array([float(r["projected_tbf"])]),
                        family="binomial",
                    )[0]
                )
            p_over_blend += float(w) * pov
            open_work = open_work.drop(columns=["k_rate_pred", "projected_tbf"], errors="ignore")
        open_use = open_work.loc[valid_mask].copy()
        p_open = np.clip(p_over_blend[valid_mask], 1e-6, 1 - 1e-6)
        y_open = (open_use["actual_k"].to_numpy(dtype=np.float64) > open_use["line"].to_numpy(dtype=np.float64)).astype(np.float64)
        calibrator = _fit_calibrator(p_open, y_open, args.calibration_mode)

        # Build manual replay frame.
        man_work = manual_df.copy()
        p_over_manual = np.zeros(len(man_work), dtype=np.float64)
        k_rate_blend = np.zeros(len(man_work), dtype=np.float64)
        tbf_blend = np.zeros(len(man_work), dtype=np.float64)
        valid_m = np.ones(len(man_work), dtype=bool)
        for fs, w in active.items():
            p = preds_by_feature[fs]
            joined = man_work.merge(p, on=["game_date_d", "pitcher_id_i"], how="left")
            man_work = joined
            miss = joined["k_rate_pred"].isna() | joined["projected_tbf"].isna()
            valid_m &= ~miss.to_numpy()
            pov = np.zeros(len(joined), dtype=np.float64)
            good_idx = np.where(~miss.to_numpy())[0]
            for idx_ in good_idx:
                r = joined.iloc[idx_]
                pov[idx_] = float(
                    p_strikeouts_ge(
                        float(r["line"]),
                        k_rate=np.array([float(r["k_rate_pred"])]),
                        projected_tbf=np.array([float(r["projected_tbf"])]),
                        family="binomial",
                    )[0]
                )
            p_over_manual += float(w) * pov
            k_vals = np.where(miss.to_numpy(), 0.0, joined["k_rate_pred"].astype(float).to_numpy())
            tbf_vals = np.where(miss.to_numpy(), 0.0, joined["projected_tbf"].astype(float).to_numpy())
            k_rate_blend += float(w) * k_vals
            tbf_blend += float(w) * tbf_vals
            man_work = man_work.drop(columns=["k_rate_pred", "projected_tbf"], errors="ignore")

        man = man_work.loc[valid_m].copy()
        man["k_rate_pred_blend"] = k_rate_blend[valid_m]
        man["projected_tbf_blend"] = tbf_blend[valid_m]
        p_over_cal = _apply_calibrator(np.clip(p_over_manual[valid_m], 1e-6, 1 - 1e-6), args.calibration_mode, calibrator)
        side = man["side"].astype(str).str.lower().to_numpy()
        p_side = np.where(side == "over", p_over_cal, 1.0 - p_over_cal)
        p_mkt = []
        rpd = []
        y = []
        for r in man.to_dict(orient="records"):
            try:
                po, pu = devig_two_way(float(r["over_price"]), float(r["under_price"]))
                p_m = float(po if str(r["side"]).lower() == "over" else pu)
                yy = _result_to_y(r.get("result"))
                if yy is None:
                    p_mkt.append(np.nan)
                    rpd.append(np.nan)
                    y.append(np.nan)
                    continue
                price = float(r["bet_price"])
                b = (price / 100.0) if price > 0 else (100.0 / abs(price))
                p_mkt.append(p_m)
                y.append(float(yy))
                rpd.append(float(b if yy >= 1.0 else -1.0))
            except Exception:
                p_mkt.append(np.nan)
                rpd.append(np.nan)
                y.append(np.nan)
        man["p_side"] = p_side
        man["p_market"] = p_mkt
        man["y"] = y
        man["rpd"] = rpd
        man = man.dropna(subset=["p_market", "y", "rpd"]).copy()
        man["edge"] = man["p_side"] - man["p_market"]
        man["opportunity_key"] = (
            man["game_date_d"].astype(str)
            + "|"
            + man["player_name"].astype(str)
            + "|"
            + man["line"].astype(str)
            + "|"
            + man["side"].astype(str).str.lower()
        )

        # Duplicate diagnostics: same date/player/line/side with >1 entries.
        dup = (
            man.groupby(["game_date_d", "player_name", "line", "side"], as_index=False)
            .size()
            .rename(columns={"size": "n_dupes"})
        )
        dup = dup[dup["n_dupes"] > 1].copy()
        duplicate_rows.append(
            {
                "config": label,
                "weights_json": json.dumps(cfg),
                "duplicate_groups": int(len(dup)),
                "duplicate_tickets": int(dup["n_dupes"].sum()) if len(dup) else 0,
                "dedupe_applied": bool(args.dedupe_manual),
            }
        )

        if args.dedupe_manual and len(man):
            man = (
                man.sort_values(
                    by=["edge", "bet_price", "stake"],
                    ascending=[False, False, False],
                )
                .drop_duplicates(
                    subset=["game_date_d", "player_name", "line", "side"],
                    keep="first",
                )
                .reset_index(drop=True)
            )

        for floor in floors:
            scoped = man[man["edge"] >= float(floor)].copy()
            n = len(scoped)
            if n == 0:
                continue
            mae_expected_k = np.nan
            mae_k_rate = np.nan
            matched_rows = 0
            if "actual_k" in scoped.columns and "actual_pa" in scoped.columns:
                ok = scoped["actual_k"].notna() & scoped["actual_pa"].notna() & (scoped["actual_pa"].astype(float) > 0)
                matched_rows = int(ok.sum())
                if matched_rows > 0:
                    actual_k = scoped.loc[ok, "actual_k"].astype(float).to_numpy()
                    actual_pa = scoped.loc[ok, "actual_pa"].astype(float).to_numpy()
                    k_rate_pred = scoped.loc[ok, "k_rate_pred_blend"].astype(float).to_numpy()
                    projected_tbf = scoped.loc[ok, "projected_tbf_blend"].astype(float).to_numpy()
                    expected_k_pred = k_rate_pred * projected_tbf
                    actual_k_rate = actual_k / actual_pa
                    mae_expected_k = float(np.mean(np.abs(expected_k_pred - actual_k)))
                    mae_k_rate = float(np.mean(np.abs(k_rate_pred - actual_k_rate)))
            picks_by_config_floor[(label, float(floor))] = scoped.copy()
            stake_sum = float(scoped["stake"].astype(float).sum())
            pnl = float((scoped["stake"].astype(float) * scoped["rpd"].astype(float)).sum())
            roi = pnl / stake_sum if stake_sum > 0 else np.nan
            clv = scoped["clv_pp"].dropna().astype(float).to_numpy() if "clv_pp" in scoped.columns else np.array([])
            skill = _prob_metrics(
                scoped["y"].to_numpy(dtype=np.float64),
                scoped["p_side"].to_numpy(dtype=np.float64),
                scoped["p_market"].to_numpy(dtype=np.float64),
            )
            risk = _risk_metrics(scoped["rpd"].to_numpy(dtype=np.float64))
            all_rows.append(
                {
                    "config": label,
                    "weights_json": json.dumps(cfg),
                    "calibration_mode_open_fit": args.calibration_mode,
                    "dedupe_manual": bool(args.dedupe_manual),
                    "edge_floor": float(floor),
                    "n_bets": int(n),
                    "matched_rows_for_mae": matched_rows,
                    "stake": stake_sum,
                    "pnl": pnl,
                    "roi": roi,
                    "expected_k_mae_on_matched": mae_expected_k,
                    "k_rate_mae_on_matched": mae_k_rate,
                    "clv_mean_pp": float(np.mean(clv)) if len(clv) else np.nan,
                    "positive_clv_share": float(np.mean(clv > 0.0)) if len(clv) else np.nan,
                    **risk,
                    **skill,
                }
            )

    out = pd.DataFrame(all_rows).sort_values(
        ["roi", "pnl", "sortino", "sharpe"], ascending=[False, False, False, False]
    )
    best_floor_per_config: dict[str, float] = {}
    if not out.empty:
        per_cfg = (
            out.sort_values(
                ["config", "roi", "pnl", "sortino", "sharpe"],
                ascending=[True, False, False, False, False],
            )
            .groupby("config", as_index=False)
            .head(1)
            .reset_index(drop=True)
        )
        for row in per_cfg.to_dict(orient="records"):
            best_floor_per_config[str(row["config"])] = float(row["edge_floor"])

    picks_rows: list[pd.DataFrame] = []
    for cfg, floor in best_floor_per_config.items():
        scoped = picks_by_config_floor.get((cfg, float(floor)))
        if scoped is None or scoped.empty:
            continue
        scoped = scoped.copy()
        scoped["config"] = cfg
        scoped["best_floor"] = float(floor)
        cols = [
            "config",
            "best_floor",
            "opportunity_key",
            "game_date_d",
            "player_name",
            "line",
            "side",
            "bet_price",
            "stake",
            "edge",
            "p_side",
            "p_market",
            "y",
            "rpd",
            "clv_pp",
        ]
        picks_rows.append(scoped[[c for c in cols if c in scoped.columns]])
    picks_df = (
        pd.concat(picks_rows, ignore_index=True)
        if picks_rows
        else pd.DataFrame(
            columns=[
                "config",
                "best_floor",
                "opportunity_key",
                "game_date_d",
                "player_name",
                "line",
                "side",
                "bet_price",
                "stake",
                "edge",
                "p_side",
                "p_market",
                "y",
                "rpd",
                "clv_pp",
            ]
        )
    )

    overlap_rows: list[dict[str, object]] = []
    cfgs = sorted(best_floor_per_config.keys())
    for a in cfgs:
        for b in cfgs:
            sa = set(picks_df.loc[picks_df["config"] == a, "opportunity_key"].astype(str).tolist())
            sb = set(picks_df.loc[picks_df["config"] == b, "opportunity_key"].astype(str).tolist())
            inter = len(sa & sb)
            union = len(sa | sb)
            overlap_rows.append(
                {
                    "config_a": a,
                    "config_b": b,
                    "n_a": len(sa),
                    "n_b": len(sb),
                    "n_intersection": inter,
                    "jaccard": (float(inter) / float(union)) if union > 0 else 0.0,
                }
            )
    overlap_df = pd.DataFrame(overlap_rows)
    dup_out = pd.DataFrame(duplicate_rows)
    out_csv = OUT_DIR / f"open_top3_transfer_manual_replay_{args.output_tag}.csv"
    dup_csv = OUT_DIR / f"open_top3_transfer_duplicate_diag_{args.output_tag}.csv"
    picks_csv = OUT_DIR / f"open_top3_transfer_bestfloor_picks_{args.output_tag}.csv"
    overlap_csv = OUT_DIR / f"open_top3_transfer_bestfloor_overlap_{args.output_tag}.csv"
    out_json = OUT_DIR / f"open_top3_transfer_manual_replay_{args.output_tag}.json"
    out.to_csv(out_csv, index=False)
    dup_out.to_csv(dup_csv, index=False)
    picks_df.to_csv(picks_csv, index=False)
    overlap_df.to_csv(overlap_csv, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "top_n": int(args.top_n),
        "ranked_ensemble_csv": str(Path(args.ranked_ensemble_csv)),
        "calibration_mode_open_fit": args.calibration_mode,
        "dedupe_manual": bool(args.dedupe_manual),
        "floors": floors,
        "files": {
            "replay_csv": str(out_csv),
            "duplicates_csv": str(dup_csv),
            "bestfloor_picks_csv": str(picks_csv),
            "bestfloor_overlap_csv": str(overlap_csv),
        },
        "best": out.iloc[0].to_dict() if not out.empty else {},
        "best_floor_per_config": best_floor_per_config,
        "duplicate_summary": dup_out.to_dict(orient="records"),
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.head(20).to_string(index=False))
    print(dup_out.to_string(index=False))
    if not overlap_df.empty:
        print(overlap_df.to_string(index=False))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

