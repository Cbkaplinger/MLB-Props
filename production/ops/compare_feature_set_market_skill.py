"""Compare feature-set probability skill vs market on open opportunity universe.

Key differences vs governance replay:
- Uses open quote opportunities (not only historically staked bets).
- Evaluates on chrono holdout rows for calibration modes (raw/platt/isotonic).
- Reports Brier/LogLoss/ECE/MCE and skill-vs-market on the same eval slice.
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
from Python.count_layer import expected_strikeouts, fit_count_layer_kappa, p_strikeouts_ge
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
OUT_CSV = ROOT / "artifacts" / "odds_log" / "feature_set_market_skill_compare.csv"
OUT_JSON = ROOT / "artifacts" / "odds_log" / "feature_set_market_skill_compare.json"


def _fit_models(train: pd.DataFrame, k_features: list[str], tbf_features: list[str], *, monotone: bool = False):
    cut = int(len(train) * 0.85)
    fit = train.iloc[:cut]
    val = train.iloc[cut:]
    lightgbm_params: dict[str, object] = {}
    if monotone:
        # Reuse same directional prior used in governance script.
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
        lightgbm_params["monotone_constraints"] = cons
        lightgbm_params["monotone_constraints_method"] = "advanced"

    k_model = build_model("lightgbm", lightgbm_verbosity=-1, lightgbm_params=lightgbm_params if lightgbm_params else None)
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

    k_hat_train = predict_clipped(k_model, "lightgbm", train, k_features)
    kappa = fit_count_layer_kappa(k=train["K"], pa=train["PA"], k_rate=k_hat_train)
    return k_model, tbf_model, upper, kappa


def _load_open_with_outcomes() -> pd.DataFrame:
    if not OPEN_CSV.exists():
        raise FileNotFoundError(f"Missing {OPEN_CSV}")
    if not PITCHER_GAMES.exists():
        raise FileNotFoundError(f"Missing {PITCHER_GAMES}")

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
        .unique(
            subset=["game_date_d", "event_id", "pitcher_id_i", "bookmaker", "line"],
            keep="last",
        )
    )

    games = (
        pl.read_parquet(PITCHER_GAMES)
        .select(
            pl.col("game_date").cast(pl.Date).alias("game_date_d"),
            pl.col("pitcher").cast(pl.Int64).alias("pitcher_id_i"),
            pl.col("K").cast(pl.Float64).alias("actual_k"),
        )
        .drop_nulls(["game_date_d", "pitcher_id_i", "actual_k"])
    )

    joined = opens.join(games, on=["game_date_d", "pitcher_id_i"], how="inner")
    out = joined.to_pandas()
    out["game_date_d"] = pd.to_datetime(out["game_date_d"]).dt.date
    return out


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


def _split_dates(df: pd.DataFrame, frac_train_dates: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = sorted(pd.to_datetime(df["game_date_d"]).dt.date.unique().tolist())
    if len(dates) < 10:
        return df, df.iloc[0:0].copy()
    cut_idx = max(1, int(len(dates) * frac_train_dates))
    cut_date = dates[cut_idx - 1]
    train = df[pd.to_datetime(df["game_date_d"]).dt.date <= cut_date].copy()
    test = df[pd.to_datetime(df["game_date_d"]).dt.date > cut_date].copy()
    return train, test


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feature-set",
        action="append",
        default=[],
        help="Repeatable feature-set list",
    )
    parser.add_argument(
        "--eval-start-date",
        default="",
        help="Optional eval lower bound YYYY-MM-DD on open opportunities.",
    )
    parser.add_argument(
        "--eval-end-date",
        default="",
        help="Optional eval upper bound YYYY-MM-DD on open opportunities.",
    )
    parser.add_argument(
        "--output-tag",
        default="",
        help="Optional suffix for output files.",
    )
    args = parser.parse_args()
    sets = args.feature_set if args.feature_set else [
        "production",
        "production_final58_consensus",
        "production_sparse72",
        "production_sparse72_monotone",
    ]

    frame_all_pl = pl.read_parquet(config.PITCHER_TRAINING_PATH).with_columns(
        pl.col("game_date").cast(pl.Datetime, strict=False)
    )
    frame_all = frame_all_pl.to_pandas()
    frame_all["game_date"] = pd.to_datetime(frame_all["game_date"])

    open_df = _load_open_with_outcomes()
    if args.eval_start_date:
        lo = pd.to_datetime(args.eval_start_date).date()
        open_df = open_df[open_df["game_date_d"] >= lo].copy()
    if args.eval_end_date:
        hi = pd.to_datetime(args.eval_end_date).date()
        open_df = open_df[open_df["game_date_d"] <= hi].copy()
    if open_df.empty:
        raise SystemExit("No open opportunities after eval date filtering.")
    rows: list[dict[str, object]] = []

    for feature_set in sets:
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
        monotone = feature_set.endswith("_monotone")
        source_feature_set = feature_set.removesuffix("_monotone")
        k_features = list(resolve_feature_names(train, source_feature_set))
        tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
        k_model, tbf_model, upper, kappa = _fit_models(train, k_features, tbf_features, monotone=monotone)

        k_hat = predict_clipped(k_model, "lightgbm", score_pool, k_features)
        tbf_hat = predict_nonnegative(tbf_model, "ridge", score_pool, tbf_features, upper=upper)
        preds = score_pool[["game_date", "pitcher"]].copy()
        preds["game_date_d"] = pd.to_datetime(preds["game_date"]).dt.date
        preds["pitcher_id_i"] = pd.to_numeric(preds["pitcher"], errors="coerce").astype("Int64")
        preds["k_rate_pred"] = k_hat
        preds["projected_tbf"] = tbf_hat
        preds = preds.drop_duplicates(["game_date_d", "pitcher_id_i"])

        joined = open_df.merge(preds, on=["game_date_d", "pitcher_id_i"], how="inner")
        if joined.empty:
            continue

        p_model = []
        p_mkt = []
        y = []
        for r in joined.to_dict(orient="records"):
            line = float(r["line"])
            pov = float(
                p_strikeouts_ge(
                    line,
                    k_rate=np.array([float(r["k_rate_pred"])]),
                    projected_tbf=np.array([float(r["projected_tbf"])]),
                    family="binomial",
                )[0]
            )
            try:
                p_over, _p_under = devig_two_way(float(r["over_odds"]), float(r["under_odds"]))
            except Exception:
                continue
            p_model.append(pov)
            p_mkt.append(float(p_over))
            y.append(1.0 if float(r["actual_k"]) > float(r["line"]) else 0.0)

        eval_df = joined.copy()
        eval_df["p_model_raw"] = p_model
        eval_df["p_market"] = p_mkt
        eval_df["y"] = y
        eval_df = eval_df[["game_date_d", "p_model_raw", "p_market", "y"]].copy()
        if eval_df.empty:
            continue
        fit_df, test_df = _split_dates(eval_df, frac_train_dates=0.7)
        if test_df.empty:
            test_df = eval_df.copy()
            fit_df = eval_df.copy()

        for mode in ("raw", "platt", "isotonic"):
            calibrator = _fit_calibrator(fit_df["p_model_raw"].to_numpy(), fit_df["y"].to_numpy(), mode)
            p_eval = _apply_calibrator(test_df["p_model_raw"].to_numpy(), mode, calibrator)
            met = _prob_metrics(test_df["y"].to_numpy(), p_eval, test_df["p_market"].to_numpy())
            rows.append(
                {
                    "feature_set": feature_set,
                    "source_feature_set": source_feature_set,
                    "monotone_constraints": bool(monotone),
                    "calibration_mode": mode,
                    "n_eval_rows": int(len(test_df)),
                    "n_fit_rows": int(len(fit_df)),
                    "kappa": float(kappa),
                    **met,
                }
            )

    out = pd.DataFrame(rows).sort_values(
        ["brier_skill_vs_market", "logloss_skill_vs_market", "brier"],
        ascending=[False, False, True],
    )
    out_csv = OUT_CSV
    out_json = OUT_JSON
    if args.output_tag:
        out_csv = OUT_CSV.with_name(f"{OUT_CSV.stem}_{args.output_tag}{OUT_CSV.suffix}")
        out_json = OUT_JSON.with_name(f"{OUT_JSON.stem}_{args.output_tag}{OUT_JSON.suffix}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_sets": sets,
        "eval_start_date": args.eval_start_date or None,
        "eval_end_date": args.eval_end_date or None,
        "open_source_csv": str(OPEN_CSV),
        "outcomes_source": str(PITCHER_GAMES),
        "rows": rows,
        "file": str(out_csv),
    }
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.to_string(index=False))
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()

