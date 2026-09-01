"""Calibration + uncertainty-gating sweep for policy-coupled feature-set replay."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python import config
from Python.count_layer import expected_strikeouts, fit_count_layer_kappa, p_strikeouts_ge
from Python.features import TARGET
from Python.market import bootstrap_mean_ci, devig_two_way
from Python.odds_ledger import dedupe_ledger_props  # noqa: E402
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
OUT_CSV = OUT_DIR / "policy_calibration_uncertainty_sweep.csv"
OUT_JSON = OUT_DIR / "policy_calibration_uncertainty_sweep.json"
LEDGER_PATH = OUT_DIR / "ledger.parquet"
LINE_FLOOR_PATH = (
    ROOT / "production" / "ops" / "market_research" / "line_floor_policy.json"
)


def _safe_float(v: object) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _line_key(v: object) -> str:
    fv = _safe_float(v)
    return f"{float(fv):.1f}" if fv is not None else ""


def _load_line_floors() -> tuple[dict[str, float], float]:
    if not LINE_FLOOR_PATH.exists():
        return {}, 0.12
    try:
        payload = json.loads(LINE_FLOOR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}, 0.12
    raw = payload.get("line_edge_floors", {}) if isinstance(payload, dict) else {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        fv = _safe_float(v)
        if fv is not None:
            out[str(k)] = float(fv)
    fallback = _safe_float(payload.get("default_fallback_edge_floor")) if isinstance(payload, dict) else None
    return out, float(fallback if fallback is not None else 0.12)


def _eligible_current_policy(
    ledger: pl.DataFrame,
    *,
    roi_mode: str,
    line_floors: dict[str, float],
    fallback_floor: float,
) -> pl.DataFrame:
    base_by_mode = {
        "aggressive": 0.12,
        "balanced": 0.16,
        "conservative": 0.18,
        "profit_lock": 0.18,
    }
    base_floor = float(base_by_mode.get(roi_mode, 0.16))
    side_floor_over = 0.22 if roi_mode == "profit_lock" else None
    side_floor_under = 0.18 if roi_mode == "profit_lock" else None
    out = ledger.with_columns(
        pl.col("line").map_elements(_line_key, return_dtype=pl.Utf8).alias("line_key"),
        pl.col("line")
        .map_elements(lambda v: float(line_floors.get(_line_key(v), fallback_floor)), return_dtype=pl.Float64)
        .alias("line_floor_current"),
        pl.lit(base_floor).alias("base_floor_current"),
    ).with_columns(
        pl.max_horizontal("line_floor_current", "base_floor_current").alias("floor_current")
    )
    if side_floor_over is not None and side_floor_under is not None and "side" in out.columns:
        out = out.with_columns(
            pl.when(pl.col("side") == "over")
            .then(pl.lit(float(side_floor_over)))
            .otherwise(pl.lit(float(side_floor_under)))
            .alias("side_floor_current")
        ).with_columns(
            pl.max_horizontal("floor_current", "side_floor_current").alias("floor_current")
        )
    return out.with_columns(
        (pl.col("edge").cast(pl.Float64) >= pl.col("floor_current").cast(pl.Float64)).alias(
            "passes_current_policy"
        )
    )


def _result_to_y(v: object) -> float | None:
    s = str(v or "").strip().lower()
    if s == "win":
        return 1.0
    if s == "loss":
        return 0.0
    return None


def _returns_per_dollar(row: dict[str, object]) -> float | None:
    y = _result_to_y(row.get("result"))
    if y is None:
        return None
    price = row.get("bet_price")
    if price is None:
        return None
    price = float(price)
    if price == 0:
        return None
    b = (price / 100.0) if price > 0 else (100.0 / abs(price))
    return float(b if y >= 1.0 else -1.0)


def _load_settled_ledger() -> pl.DataFrame:
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"Missing {LEDGER_PATH}")
    led = pl.read_parquet(LEDGER_PATH)
    settled = led.filter(
        (pl.col("status") == "settled")
        & pl.col("line").is_not_null()
        & pl.col("side").is_not_null()
        & pl.col("bet_price").is_not_null()
        & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
    )
    # One row per prop (no DK+FD double count) so sweep stats are honest.
    return dedupe_ledger_props(settled) if not settled.is_empty() else settled


def _fit_models(train: pd.DataFrame, k_features: list[str], tbf_features: list[str]):
    cut = int(len(train) * 0.85)
    fit = train.iloc[:cut]
    val = train.iloc[cut:]
    k_model = build_model("lightgbm", lightgbm_verbosity=-1)
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


def _brier_ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[float, float]:
    brier = float(np.mean((p - y) ** 2))
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi if i < bins - 1 else p <= hi)
        if not np.any(mask):
            continue
        ece += abs(float(np.mean(y[mask]) - np.mean(p[mask]))) * (np.sum(mask) / len(p))
    return brier, float(ece)


def _score_one(
    frame_all: pd.DataFrame,
    settled: pl.DataFrame,
    feature_set: str,
    uncertainty_quantiles: list[float],
) -> list[dict[str, object]]:
    source = feature_set.removesuffix("_monotone")
    train = (
        frame_all.loc[frame_all["season"].isin(config.FEATURE_RESEARCH_SEASONS)]
        .dropna(subset=[TARGET, "K", "PA", "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    score_pool = (
        frame_all.dropna(subset=["game_pk", "pitcher", "game_date"])
        .sort_values(["game_date", "player_name"])
        .reset_index(drop=True)
    )
    k_features = list(resolve_feature_names(train, source))
    tbf_features = list(tbf_feature_names(train, TBF_DEFAULT_FEATURE_SET))
    k_model, tbf_model, upper, kappa = _fit_models(train, k_features, tbf_features)
    k_hat = predict_clipped(k_model, "lightgbm", score_pool, k_features)
    tbf_hat = predict_nonnegative(tbf_model, "ridge", score_pool, tbf_features, upper=upper)
    preds = score_pool[["game_pk", "pitcher", "game_date"]].copy()
    preds["game_date"] = pd.to_datetime(preds["game_date"]).dt.date
    preds["k_rate_pred"] = k_hat
    preds["projected_tbf"] = tbf_hat
    preds["expected_K"] = expected_strikeouts(k_hat, tbf_hat)
    preds = preds.drop_duplicates(["game_pk", "pitcher", "game_date"])
    led = settled.with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("game_pk").cast(pl.Int64),
        pl.col("pitcher").cast(pl.Int64),
    )
    joined = led.join(pl.from_pandas(preds), on=["game_pk", "pitcher", "game_date"], how="inner")
    if joined.is_empty():
        return []
    pdf = joined.to_pandas()
    records = []
    for row in pdf.to_dict(orient="records"):
        line = float(row["line"])
        p_over = float(
            p_strikeouts_ge(
                line,
                k_rate=np.array([float(row["k_rate_pred"])]),
                projected_tbf=np.array([float(row["projected_tbf"])]),
                family="binomial",
            )[0]
        )
        side = str(row.get("side") or "")
        p_model = p_over if side == "over" else (1.0 - p_over)
        p_market = None
        try:
            po, pu = devig_two_way(float(row["over_price"]), float(row["under_price"]))
            p_market = float(po if side == "over" else pu)
        except Exception:
            pass
        y = _result_to_y(row.get("result"))
        rpd = _returns_per_dollar(row)
        records.append(
            {
                **row,
                "p_model": p_model,
                "p_market": p_market,
                "edge": (p_model - p_market) if p_market is not None else None,
                "margin_from_fair": abs(p_model - 0.5),
                "y": y,
                "rpd": rpd,
            }
        )
    scored = pl.from_pandas(pd.DataFrame(records)).drop_nulls(["edge"])
    floors, fallback = _load_line_floors()
    eligible = _eligible_current_policy(
        scored, roi_mode="balanced", line_floors=floors, fallback_floor=fallback
    ).filter(pl.col("passes_current_policy"))
    if eligible.is_empty():
        return []
    elig = eligible.to_pandas()
    q_values = {q: float(elig["margin_from_fair"].quantile(q)) for q in uncertainty_quantiles}

    out_rows: list[dict[str, object]] = []
    for q in uncertainty_quantiles:
        m = q_values[q]
        gated = elig[elig["margin_from_fair"] >= m].copy()
        if gated.empty:
            continue
        stake = float(gated["stake"].sum())
        pnl = float((gated["stake"] * gated["rpd"]).sum())
        roi = pnl / stake if stake > 0 else np.nan
        clv = (gated["edge"] * 100.0).astype(float).tolist()
        roi_samples = (
            (
                (gated["stake"] * gated["rpd"]).to_numpy(dtype=float)
                / gated["stake"].sum()
            ).tolist()
            if stake > 0
            else []
        )
        roi_lo = roi_hi = None
        if len(roi_samples) >= 25:
            _, roi_lo, roi_hi = bootstrap_mean_ci(roi_samples, n_boot=1200, seed=11)
        clv_lo = clv_hi = None
        if len(clv) >= 25:
            _, clv_lo, clv_hi = bootstrap_mean_ci(clv, n_boot=1200, seed=11)
        y = gated["y"].to_numpy(dtype=float)
        p = gated["p_model"].to_numpy(dtype=float)
        brier, ece = _brier_ece(y, p, bins=10)
        out_rows.append(
            {
                "feature_set": feature_set,
                "source_feature_set": source,
                "uncertainty_gate_quantile": q,
                "margin_threshold": m,
                "n_policy_bets": int(len(gated)),
                "stake": stake,
                "pnl": pnl,
                "roi": float(roi),
                "roi_ci_lo": float(roi_lo) if roi_lo is not None else None,
                "roi_ci_hi": float(roi_hi) if roi_hi is not None else None,
                "clv_mean_pp": float(np.mean(clv)) if clv else None,
                "clv_ci_lo": float(clv_lo) if clv_lo is not None else None,
                "clv_ci_hi": float(clv_hi) if clv_hi is not None else None,
                "brier": brier,
                "ece_10bin": ece,
                "kappa": float(kappa),
            }
        )
    return out_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-set", action="append", default=[])
    parser.add_argument(
        "--uncertainty-quantiles",
        default="0.0,0.1,0.2,0.3",
        help="Comma-separated quantiles on |p_model-0.5| to gate uncertainty tails.",
    )
    args = parser.parse_args()
    sets = (
        args.feature_set
        if args.feature_set
        else ["production", "production_sparse40", "production_stable12", "production_oof72_monotone"]
    )
    quantiles = [float(x.strip()) for x in args.uncertainty_quantiles.split(",") if x.strip()]
    settled = _load_settled_ledger()
    frame_all = pd.read_parquet(config.PITCHER_TRAINING_PATH)
    frame_all["game_date"] = pd.to_datetime(frame_all["game_date"])
    rows: list[dict[str, object]] = []
    for feature_set in sets:
        rows.extend(_score_one(frame_all, settled, feature_set, quantiles))
    out = pd.DataFrame(rows).sort_values(
        ["feature_set", "uncertainty_gate_quantile"], ascending=[True, True]
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_sets": sets,
        "uncertainty_quantiles": quantiles,
        "results_count": int(len(out)),
        "file": str(OUT_CSV),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.to_string(index=False))
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()

