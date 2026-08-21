"""Full snapshot-level open-market counterfactual replay.

Builds a large-sample opportunity-universe replay from open snapshots
(2025-2026), scores feature-set models, applies chrono-safe calibration, and
simulates side-selection policy across edge floors.
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
OUT_DIR = ROOT / "artifacts" / "odds_log"


def _parse_floors(raw: str) -> list[float]:
    vals = sorted({float(x.strip()) for x in raw.split(",") if x.strip()})
    if not vals:
        raise ValueError("No floors parsed from --floors")
    return vals


def _safe_div(a: float, b: float) -> float | None:
    return (a / b) if b else None


def _american_to_prob(a: np.ndarray) -> np.ndarray:
    arr = np.asarray(a, dtype=np.float64)
    out = np.empty_like(arr, dtype=np.float64)
    pos = arr > 0
    out[pos] = 100.0 / (arr[pos] + 100.0)
    out[~pos] = (-arr[~pos]) / ((-arr[~pos]) + 100.0)
    return out


def _risk_metrics(rpd: np.ndarray) -> dict[str, float | None]:
    if len(rpd) == 0:
        return {
            "sortino": None,
            "sharpe": None,
            "max_drawdown_pct": None,
            "profit_factor": None,
            "cvar_95": None,
            "expectancy_per_bet": None,
        }
    mean = float(np.mean(rpd))
    std = float(np.std(rpd))
    downside = rpd[rpd < 0.0]
    downside_dev = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else None
    sortino = (mean / downside_dev) if downside_dev and downside_dev > 0 else None
    sharpe = (mean / std) if std > 0 else None
    cum = 1.0 + np.cumsum(rpd)
    peaks = np.maximum.accumulate(cum)
    dd = np.divide(cum - peaks, peaks, out=np.zeros_like(cum), where=peaks > 0)
    max_dd_pct = abs(float(np.min(dd))) if len(dd) else None
    gross_win = float(np.sum(rpd[rpd > 0]))
    gross_loss = abs(float(np.sum(rpd[rpd < 0])))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None
    q = float(np.quantile(rpd, 0.05))
    cvar_95 = float(np.mean(rpd[rpd <= q])) if len(rpd) else None
    return {
        "sortino": sortino,
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd_pct,
        "profit_factor": profit_factor,
        "cvar_95": cvar_95,
        "expectancy_per_bet": mean,
    }


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


def _load_open_outcomes(*, start_date: str, end_date: str, dedupe: bool) -> pl.DataFrame:
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
    )
    if dedupe:
        opens = opens.sort("fetched_at_ts").unique(
            subset=["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line"],
            keep="last",
        )
    if start_date:
        opens = opens.filter(pl.col("game_date_d") >= pl.lit(pd.to_datetime(start_date).date()))
    if end_date:
        opens = opens.filter(pl.col("game_date_d") <= pl.lit(pd.to_datetime(end_date).date()))
    games = (
        pl.read_parquet(PITCHER_GAMES)
        .select(
            pl.col("game_date").cast(pl.Date).alias("game_date_d"),
            pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
            pl.col("K").cast(pl.Float64).alias("actual_k"),
        )
        .drop_nulls(["game_date_d", "pitcher_id_i", "actual_k"])
    )
    return opens.join(games, on=["game_date_d", "pitcher_id_i"], how="inner")


def _train_and_predict_feature_set(frame_all_pl: pl.DataFrame, feature_set: str) -> pl.DataFrame:
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
    k_features = list(resolve_feature_names(train, source))
    tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
    cut = int(len(train) * 0.85)
    fit = train.iloc[:cut]
    val = train.iloc[cut:]
    monotone = feature_set.endswith("_monotone")
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
    out = score_pool[["game_date", "pitcher"]].copy()
    out["game_date_d"] = pd.to_datetime(out["game_date"]).dt.date
    out["pitcher_id_i"] = pd.to_numeric(out["pitcher"], errors="coerce").astype("Int64")
    out["k_rate_pred"] = k_hat
    out["projected_tbf"] = tbf_hat
    out = out.drop_duplicates(["game_date_d", "pitcher_id_i"])
    return pl.from_pandas(out[["game_date_d", "pitcher_id_i", "k_rate_pred", "projected_tbf"]])


def _split_fit_test(pdf: pd.DataFrame, frac_train_dates: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(pd.to_datetime(pdf["game_date_d"]).dt.date.unique().tolist())
    if len(dates) < 10:
        return pdf.copy(), pdf.copy()
    cut_idx = max(1, int(len(dates) * frac_train_dates))
    cut_date = dates[cut_idx - 1]
    fit = pdf[pd.to_datetime(pdf["game_date_d"]).dt.date <= cut_date].copy()
    test = pdf[pd.to_datetime(pdf["game_date_d"]).dt.date > cut_date].copy()
    if test.empty:
        return pdf.copy(), pdf.copy()
    return fit, test


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2025-01-01")
    parser.add_argument("--end-date", default="2026-12-31")
    parser.add_argument("--dedupe-open", action="store_true", help="Use one open snapshot per (game,event,pitcher,book,line).")
    parser.add_argument(
        "--feature-set",
        action="append",
        default=[],
        help="Repeatable feature set list.",
    )
    parser.add_argument("--floors", default="0.05,0.06,0.07,0.08,0.09,0.10,0.12")
    parser.add_argument("--side-floor-over", type=float, default=0.10)
    parser.add_argument("--side-floor-under", type=float, default=0.08)
    parser.add_argument("--output-tag", default="open_snapshot_counterfactual")
    args = parser.parse_args()

    feature_sets = args.feature_set if args.feature_set else [
        "production_sparse72",
        "production_sparse72_monotone",
        "production_final58_consensus",
    ]
    floors = _parse_floors(args.floors)

    open_rows = _load_open_outcomes(
        start_date=args.start_date,
        end_date=args.end_date,
        dedupe=bool(args.dedupe_open),
    )
    if open_rows.is_empty():
        raise SystemExit("No open rows available after filters.")

    frame_all_pl = pl.read_parquet(config.PITCHER_TRAINING_PATH).with_columns(
        pl.col("game_date").cast(pl.Datetime, strict=False)
    )

    model_predictions: dict[str, pl.DataFrame] = {}
    for fs in feature_sets:
        model_predictions[fs] = _train_and_predict_feature_set(frame_all_pl, fs)

    panel_by_model: dict[str, pd.DataFrame] = {}
    for fs in feature_sets:
        joined = open_rows.join(model_predictions[fs], on=["game_date_d", "pitcher_id_i"], how="inner")
        if joined.is_empty():
            continue
        pdf = joined.to_pandas()
        pov = []
        for r in pdf.to_dict(orient="records"):
            pov.append(
                float(
                    p_strikeouts_ge(
                        float(r["line"]),
                        k_rate=np.array([float(r["k_rate_pred"])]),
                        projected_tbf=np.array([float(r["projected_tbf"])]),
                        family="binomial",
                    )[0]
                )
            )
        pdf["p_over_raw"] = np.clip(np.asarray(pov, dtype=np.float64), 1e-6, 1 - 1e-6)
        over_imp = _american_to_prob(pdf["over_odds"].to_numpy(dtype=np.float64))
        under_imp = _american_to_prob(pdf["under_odds"].to_numpy(dtype=np.float64))
        den = np.clip(over_imp + under_imp, 1e-9, None)
        pdf["p_over_market"] = np.clip(over_imp / den, 1e-6, 1 - 1e-6)
        pdf["y_over"] = (pdf["actual_k"].to_numpy(dtype=np.float64) > pdf["line"].to_numpy(dtype=np.float64)).astype(np.float64)
        panel_by_model[fs] = pdf

    if not panel_by_model:
        raise SystemExit("No matched open rows after joining predictions.")

    ensemble_key = "ensemble_sparse72_80_sparse72m_15_final58_05"
    if all(k in panel_by_model for k in ("production_sparse72", "production_sparse72_monotone", "production_final58_consensus")):
        base = panel_by_model["production_sparse72"][
            ["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line", "over_odds", "under_odds", "actual_k", "p_over_market", "y_over", "p_over_raw"]
        ].copy()
        m1 = panel_by_model["production_sparse72"][["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line", "p_over_raw"]].rename(columns={"p_over_raw": "p1"})
        m2 = panel_by_model["production_sparse72_monotone"][["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line", "p_over_raw"]].rename(columns={"p_over_raw": "p2"})
        m3 = panel_by_model["production_final58_consensus"][["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line", "p_over_raw"]].rename(columns={"p_over_raw": "p3"})
        keys = ["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line"]
        blend = (
            m1.merge(m2, on=keys, how="inner")
            .merge(m3, on=keys, how="inner")
        )
        base = base.merge(blend, on=keys, how="inner")
        base["p_over_raw"] = np.clip(0.80 * base["p1"] + 0.15 * base["p2"] + 0.05 * base["p3"], 1e-6, 1 - 1e-6)
        base = base.drop(columns=["p1", "p2", "p3"])
        panel_by_model[ensemble_key] = base

    rows: list[dict[str, object]] = []
    for name, pdf in panel_by_model.items():
        fit_df, test_df = _split_fit_test(pdf, frac_train_dates=0.7)
        for cal_mode in ("raw", "platt", "isotonic"):
            cal = _fit_calibrator(fit_df["p_over_raw"].to_numpy(), fit_df["y_over"].to_numpy(), cal_mode)
            test = test_df.copy()
            test["p_over"] = _apply_calibrator(test["p_over_raw"].to_numpy(), cal_mode, cal)

            skill = _prob_metrics(
                test["y_over"].to_numpy(dtype=np.float64),
                test["p_over"].to_numpy(dtype=np.float64),
                test["p_over_market"].to_numpy(dtype=np.float64),
            )

            edge_over = test["p_over"].to_numpy(dtype=np.float64) - test["p_over_market"].to_numpy(dtype=np.float64)
            choose_over = edge_over >= 0.0
            abs_edge = np.abs(edge_over)
            y_over = test["y_over"].to_numpy(dtype=np.float64)
            y_side = np.where(choose_over, y_over, 1.0 - y_over)
            price = np.where(
                choose_over,
                test["over_odds"].to_numpy(dtype=np.float64),
                test["under_odds"].to_numpy(dtype=np.float64),
            )
            b = np.where(price > 0.0, price / 100.0, 100.0 / np.abs(price))
            rpd = np.where(y_side >= 1.0, b, -1.0)
            side_name = np.where(choose_over, "over", "under")

            for floor in floors:
                mask = abs_edge >= float(floor)
                n = int(mask.sum())
                rr = rpd[mask]
                pos_share = float(np.mean(rr > 0.0)) if n else None
                roi = float(np.mean(rr)) if n else None
                risk = _risk_metrics(rr)
                rows.append(
                    {
                        "model_key": name,
                        "calibration_mode": cal_mode,
                        "policy_mode": "single_floor",
                        "edge_floor": float(floor),
                        "edge_floor_over": None,
                        "edge_floor_under": None,
                        "n_eval_rows": int(len(test)),
                        "n_bets": n,
                        "over_share": float(np.mean(side_name[mask] == "over")) if n else None,
                        "roi": roi,
                        "positive_ticket_share": pos_share,
                        **risk,
                        **skill,
                    }
                )

            over_floor = float(args.side_floor_over)
            under_floor = float(args.side_floor_under)
            dual_mask = np.where(choose_over, abs_edge >= over_floor, abs_edge >= under_floor)
            n2 = int(dual_mask.sum())
            rr2 = rpd[dual_mask]
            risk2 = _risk_metrics(rr2)
            rows.append(
                {
                    "model_key": name,
                    "calibration_mode": cal_mode,
                    "policy_mode": "dual_side_floor",
                    "edge_floor": None,
                    "edge_floor_over": over_floor,
                    "edge_floor_under": under_floor,
                    "n_eval_rows": int(len(test)),
                    "n_bets": n2,
                    "over_share": float(np.mean(side_name[dual_mask] == "over")) if n2 else None,
                    "roi": float(np.mean(rr2)) if n2 else None,
                    "positive_ticket_share": float(np.mean(rr2 > 0.0)) if n2 else None,
                    **risk2,
                    **skill,
                }
            )

    out = pd.DataFrame(rows)
    out["gate_min_bets"] = out["n_bets"].fillna(0).astype(int) >= 100
    out["gate_skill_positive"] = (
        (out["brier_skill_vs_market"].fillna(-9.0) > 0.0)
        & (out["logloss_skill_vs_market"].fillna(-9.0) > 0.0)
    )
    out["gate_roi_positive"] = out["roi"].fillna(-9.0) > 0.0
    out["eligible"] = out["gate_min_bets"] & out["gate_roi_positive"]
    out["profit_score"] = (
        out["roi"].fillna(-9.0) * 4.0
        + out["sortino"].fillna(-9.0) * 2.5
        + out["sharpe"].fillna(-9.0) * 1.5
        + out["brier_skill_vs_market"].fillna(-9.0) * 2.0
        + out["logloss_skill_vs_market"].fillna(-9.0) * 2.0
        - out["max_drawdown_pct"].fillna(9.0) * 1.0
    )
    ranked = out.sort_values(
        ["gate_skill_positive", "eligible", "profit_score", "roi", "sortino", "brier_skill_vs_market", "logloss_skill_vs_market", "n_bets"],
        ascending=[False, False, False, False, False, False, False, False],
    ).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    full_csv = OUT_DIR / f"open_snapshot_counterfactual_{args.output_tag}.csv"
    ranked_csv = OUT_DIR / f"open_snapshot_counterfactual_{args.output_tag}_ranked.csv"
    out.to_csv(full_csv, index=False)
    ranked.to_csv(ranked_csv, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "dedupe_open": bool(args.dedupe_open),
            "feature_sets": feature_sets,
            "floors": floors,
            "dual_side_floor": {"over": args.side_floor_over, "under": args.side_floor_under},
        },
        "winner": ranked.iloc[0].to_dict() if not ranked.empty else {},
        "files": {"full_csv": str(full_csv), "ranked_csv": str(ranked_csv)},
        "sample": {
            "open_rows_with_outcomes": int(open_rows.height),
            "test_rows_by_top": int(ranked.iloc[0]["n_eval_rows"]) if not ranked.empty else 0,
        },
    }
    out_json = OUT_DIR / f"open_snapshot_counterfactual_{args.output_tag}.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(ranked.head(20).to_string(index=False))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
