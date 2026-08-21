"""Edge-floor sweep + deterministic champion/challenger decision artifact.

This script evaluates candidate feature sets on the settled-ledger replay universe
using a fixed calibration mode (default isotonic), then sweeps edge floors to
derive bet/hold policy frontiers and emits:
- per-model/per-floor quant metrics
- deterministic winner recommendation
- immutable release card (PROMOTE/HOLD)
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
from Python.count_layer import fit_count_layer_kappa, p_strikeouts_ge
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

OUT_DIR = ROOT / "artifacts" / "odds_log"
LEDGER_PATH = OUT_DIR / "ledger.parquet"
OPEN_SKILL_PATH = OUT_DIR / "feature_set_market_skill_compare.csv"
SWEEP_CSV = OUT_DIR / "edge_floor_sweep_governance.csv"
DECISION_JSON = OUT_DIR / "champion_challenger_decision.json"
FREEZE_MD = OUT_DIR / "model_freeze_card.md"

_MONO_POSITIVE_STEMS = (
    "k_rate_",
    "opp_lineup_k",
    "opp_lineup_whiff",
    "opp_lineup_swstr",
    "opp_lineup_chase",
    "park_k_factor",
)
_MONO_NEGATIVE_STEMS = ("opp_lineup_zcontact", "opp_lineup_bb")


def _feature_constraints(features: list[str]) -> list[int]:
    out: list[int] = []
    for f in features:
        if any(f == s or f.startswith(s) for s in _MONO_POSITIVE_STEMS):
            out.append(1)
        elif any(f == s or f.startswith(s) for s in _MONO_NEGATIVE_STEMS):
            out.append(-1)
        else:
            out.append(0)
    return out


def _load_settled_ledger() -> pl.DataFrame:
    led = pl.read_parquet(LEDGER_PATH)
    return led.filter(
        (pl.col("status") == "settled")
        & pl.col("line").is_not_null()
        & pl.col("side").is_not_null()
        & pl.col("bet_price").is_not_null()
        & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
    )


def _apply_recent_window(settled: pl.DataFrame, recent_n: int | None) -> pl.DataFrame:
    if recent_n is None or recent_n <= 0:
        return settled
    dates = (
        settled.select(pl.col("game_date").cast(pl.Date).alias("game_date"))
        .drop_nulls()
        .unique()
        .sort("game_date")
    )
    if dates.height <= recent_n:
        return settled
    keep_dates = set(dates.tail(recent_n)["game_date"].to_list())
    return settled.filter(pl.col("game_date").cast(pl.Date).is_in(list(keep_dates)))


def _fit_models(train: pd.DataFrame, k_features: list[str], tbf_features: list[str], monotone: bool):
    cut = int(len(train) * 0.85)
    fit = train.iloc[:cut]
    val = train.iloc[cut:]
    params: dict[str, object] = {}
    if monotone:
        params["monotone_constraints"] = _feature_constraints(k_features)
        params["monotone_constraints_method"] = "advanced"
    k_model = build_model("lightgbm", lightgbm_verbosity=-1, lightgbm_params=params if params else None)
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
    kappa = fit_count_layer_kappa(
        k=train["K"],
        pa=train["PA"],
        k_rate=predict_clipped(k_model, "lightgbm", train, k_features),
    )
    return k_model, tbf_model, upper, float(kappa)


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


def _score_model_rows(
    frame_all_pl: pl.DataFrame,
    settled: pl.DataFrame,
    feature_set: str,
    calibration_mode: str,
) -> pd.DataFrame:
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
    src_set = feature_set.removesuffix("_monotone")
    k_features = list(resolve_feature_names(train, src_set))
    tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
    k_model, tbf_model, upper, kappa = _fit_models(train, k_features, tbf_features, monotone)

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
    df["calibration_mode"] = calibration_mode
    df["kappa"] = kappa
    return df


def _risk_metrics(scoped: pd.DataFrame) -> dict[str, float | int | None]:
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-set", action="append", default=[])
    parser.add_argument("--calibration-mode", default="isotonic", choices=["raw", "platt", "isotonic"])
    parser.add_argument("--floor-min", type=float, default=0.005)
    parser.add_argument("--floor-max", type=float, default=0.08)
    parser.add_argument("--floor-step", type=float, default=0.005)
    parser.add_argument("--min-bets", type=int, default=25)
    parser.add_argument(
        "--recent-settled",
        type=int,
        default=0,
        help="Use only last N settled game dates (0 means full history).",
    )
    args = parser.parse_args()

    sets = args.feature_set if args.feature_set else [
        "production_sparse72",
        "production_sparse72_monotone",
        "production_final58_consensus",
        "production_frontier42_aug20",
    ]
    settled_all = _load_settled_ledger()
    recent_n = int(args.recent_settled) if int(args.recent_settled) > 0 else None
    settled = _apply_recent_window(settled_all, recent_n)
    frame_all_pl = pl.read_parquet(config.PITCHER_TRAINING_PATH).with_columns(
        pl.col("game_date").cast(pl.Datetime, strict=False)
    )
    floors = np.arange(args.floor_min, args.floor_max + 1e-12, args.floor_step)

    all_rows: list[dict[str, object]] = []
    for fs in sets:
        scored = _score_model_rows(frame_all_pl, settled, fs, args.calibration_mode)
        if scored.empty:
            continue
        for floor in floors:
            scoped = scored[scored["edge"] >= float(floor)].copy()
            met = _risk_metrics(scoped)
            all_rows.append(
                {
                    "feature_set": fs,
                    "calibration_mode": args.calibration_mode,
                    "window_label": f"last_{recent_n}" if recent_n else "full",
                    "edge_floor": float(floor),
                    **met,
                }
            )

    out = pd.DataFrame(all_rows)
    if out.empty:
        raise SystemExit("No sweep rows produced.")
    out["eligible"] = (out["n_bets"] >= int(args.min_bets))
    out["composite"] = (
        out["sortino"].fillna(-999.0) * 2.0
        + out["roi"].fillna(-999.0) * 1.0
        + out["positive_clv_share"].fillna(0.0) * 0.5
        + out["turnover_stability"].fillna(0.0) * 0.25
        - out["max_drawdown_pct"].fillna(9.0) * 0.5
    )
    out.to_csv(SWEEP_CSV, index=False)

    # model-level best point under sample gate
    elig = out[out["eligible"]].copy()
    if elig.empty:
        elig = out.copy()
    best_rows = (
        elig.sort_values(["feature_set", "composite"], ascending=[True, False])
        .groupby("feature_set", as_index=False)
        .head(1)
    )

    # include open skill as primary quality gate
    open_skill = pd.read_csv(OPEN_SKILL_PATH)
    open_iso = open_skill[open_skill["calibration_mode"] == "isotonic"][
        ["feature_set", "brier_skill_vs_market", "logloss_skill_vs_market"]
    ].copy()
    merged = best_rows.merge(open_iso, on="feature_set", how="left")
    merged["open_skill_pass"] = (
        (merged["brier_skill_vs_market"].fillna(-999.0) > 0.0)
        & (merged["logloss_skill_vs_market"].fillna(-999.0) > 0.0)
    )
    ranked_pool = merged[merged["open_skill_pass"]].copy()
    if ranked_pool.empty:
        ranked_pool = merged.copy()
    ranked_pool = ranked_pool.sort_values(
        ["brier_skill_vs_market", "logloss_skill_vs_market", "composite", "roi", "n_bets"],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    ranked_pool["decision_rank"] = np.arange(1, len(ranked_pool) + 1)
    merged = ranked_pool
    winner = merged.iloc[0].to_dict()
    promote = bool(
        pd.notna(winner.get("brier_skill_vs_market"))
        and float(winner.get("brier_skill_vs_market", -1)) > 0
        and pd.notna(winner.get("logloss_skill_vs_market"))
        and float(winner.get("logloss_skill_vs_market", -1)) > 0
        and int(winner.get("n_bets", 0)) >= int(args.min_bets)
    )
    action = "PROMOTE" if promote else "HOLD"

    decision = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "calibration_mode": args.calibration_mode,
        "window_label": f"last_{recent_n}" if recent_n else "full",
        "edge_floor_grid": {
            "min": args.floor_min,
            "max": args.floor_max,
            "step": args.floor_step,
        },
        "min_bets_gate": args.min_bets,
        "winner": winner,
        "action": action,
        "ranking": merged.to_dict(orient="records"),
        "artifacts": {
            "sweep_csv": str(SWEEP_CSV),
            "open_skill_csv": str(OPEN_SKILL_PATH),
        },
    }
    DECISION_JSON.write_text(json.dumps(decision, indent=2), encoding="utf-8")

    card = [
        "# Model Freeze Card",
        "",
        f"- Generated UTC: {decision['generated_utc']}",
        f"- Decision: **{action}**",
        f"- Winner candidate: `{winner.get('feature_set')}`",
        f"- Calibration mode: `{args.calibration_mode}`",
        f"- Recommended edge floor: `{float(winner.get('edge_floor', np.nan)):.3f}`",
        f"- Open skill (Brier/LogLoss vs market): `{winner.get('brier_skill_vs_market')}` / `{winner.get('logloss_skill_vs_market')}`",
        f"- Policy metrics at recommended floor: ROI `{winner.get('roi')}`, Sortino `{winner.get('sortino')}`, Sharpe `{winner.get('sharpe')}`, CVaR95 `{winner.get('cvar_95')}`, MaxDD `{winner.get('max_drawdown_pct')}`, Positive CLV share `{winner.get('positive_clv_share')}`, Bets `{winner.get('n_bets')}`",
        "",
        "## Promotion Rationale",
        "",
        "- Primary gate uses open-market probability skill (brier/logloss skill vs market).",
        "- Secondary gate uses edge-floor policy risk/return profile with sample-size gate.",
        "- Action is deterministic from `champion_challenger_decision.json` rank order.",
    ]
    FREEZE_MD.write_text("\n".join(card), encoding="utf-8")
    print(merged.to_string(index=False))
    print(f"Wrote {SWEEP_CSV}")
    print(f"Wrote {DECISION_JSON}")
    print(f"Wrote {FREEZE_MD}")


if __name__ == "__main__":
    main()

