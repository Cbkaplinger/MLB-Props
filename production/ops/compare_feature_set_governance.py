"""Side-by-side historical governance replay across feature sets.

Compares model-derived edges on the same settled ledger universe, then applies
the current policy floor logic to estimate ROI/CLV and simple go/no-go gates.
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
from Python.market import bootstrap_mean_ci, devig_two_way
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

OUT_DIR = ROOT / "artifacts" / "odds_log"
LEDGER_PATH = OUT_DIR / "ledger.parquet"
OUT_CSV = OUT_DIR / "feature_set_governance_compare.csv"
OUT_JSON = OUT_DIR / "feature_set_governance_compare.json"
OUT_DAILY_CSV = OUT_DIR / "feature_set_governance_daily.csv"
OUT_SEGMENT_CSV = OUT_DIR / "feature_set_governance_segments.csv"
OUT_RANK_CSV = OUT_DIR / "feature_set_governance_ranked.csv"
OUT_EDGE_DECILE_CSV = OUT_DIR / "feature_set_governance_edge_deciles.csv"
LINE_FLOOR_PATH = (
    ROOT / "production" / "ops" / "market_research" / "line_floor_policy.json"
)
_MONO_POSITIVE_STEMS = (
    "k_rate_",
    "opp_lineup_k",
    "opp_lineup_whiff",
    "opp_lineup_swstr",
    "opp_lineup_chase",
    "park_k_factor",
)
_MONO_NEGATIVE_STEMS = (
    "opp_lineup_zcontact",
    "opp_lineup_bb",
)


def _bootstrap_ci_mean(vals: np.ndarray, *, n_boot: int = 1200, seed: int = 19) -> tuple[float, float]:
    if len(vals) < 25:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(n_boot):
        sample = rng.choice(vals, size=len(vals), replace=True)
        means.append(float(np.mean(sample)))
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def _bootstrap_ci_mae(
    y_true: np.ndarray, y_pred: np.ndarray, *, n_boot: int = 1200, seed: int = 19
) -> tuple[float, float]:
    y = np.asarray(y_true, dtype=np.float64)
    p = np.asarray(y_pred, dtype=np.float64)
    if len(y) < 25 or len(y) != len(p):
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    maes = []
    idx = np.arange(len(y))
    for _ in range(n_boot):
        sel = rng.choice(idx, size=len(idx), replace=True)
        maes.append(float(np.mean(np.abs(y[sel] - p[sel]))))
    return float(np.quantile(maes, 0.025)), float(np.quantile(maes, 0.975))


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


def _close_side_prob(row: dict[str, object]) -> float | None:
    over = row.get("over_price")
    under = row.get("under_price")
    side = str(row.get("side") or "")
    if over is None or under is None or side not in {"over", "under"}:
        return None
    try:
        p_over, p_under = devig_two_way(float(over), float(under))
    except Exception:
        return None
    return float(p_over if side == "over" else p_under)


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
    return led.filter(
        (pl.col("status") == "settled")
        & pl.col("line").is_not_null()
        & pl.col("side").is_not_null()
        & pl.col("bet_price").is_not_null()
        & (pl.col("stake").cast(pl.Float64).fill_null(0.0) > 0)
    )


def _feature_constraints(k_features: list[str]) -> list[int]:
    out: list[int] = []
    for feature in k_features:
        if any(feature == stem or feature.startswith(stem) for stem in _MONO_POSITIVE_STEMS):
            out.append(1)
        elif any(feature == stem or feature.startswith(stem) for stem in _MONO_NEGATIVE_STEMS):
            out.append(-1)
        else:
            out.append(0)
    return out


def _fit_models(
    train: pd.DataFrame,
    k_features: list[str],
    tbf_features: list[str],
    *,
    monotone: bool = False,
):
    # k-rate model
    cut = int(len(train) * 0.85)
    fit = train.iloc[:cut]
    val = train.iloc[cut:]
    lightgbm_params: dict[str, object] = {}
    if monotone:
        lightgbm_params["monotone_constraints"] = _feature_constraints(k_features)
        lightgbm_params["monotone_constraints_method"] = "advanced"
    k_model = build_model(
        "lightgbm",
        lightgbm_verbosity=-1,
        lightgbm_params=lightgbm_params if lightgbm_params else None,
    )
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

    # tbf model
    tbf_model = build_model("ridge", ridge_alpha=123.28467394420659)
    fit_regressor(tbf_model, "ridge", train[tbf_features], train[TBF_TARGET])
    upper = float(train[TBF_TARGET].quantile(0.999))

    # concentration on train
    k_hat_train = predict_clipped(k_model, "lightgbm", train, k_features)
    kappa = fit_count_layer_kappa(
        k=train["K"], pa=train["PA"], k_rate=k_hat_train
    )
    return k_model, tbf_model, upper, kappa


def _fit_calibrator(
    probs: np.ndarray,
    outcomes: np.ndarray,
    method: str,
) -> tuple[np.ndarray, dict[str, float] | None]:
    p = np.clip(np.asarray(probs, dtype=np.float64), 1e-6, 1.0 - 1e-6)
    y = np.asarray(outcomes, dtype=np.float64)
    if method == "raw":
        return p, None
    if len(p) < 100 or y.min() == y.max():
        return p, None
    if method == "platt":
        x = np.log(p / (1.0 - p)).reshape(-1, 1)
        clf = LogisticRegression(solver="lbfgs", max_iter=1000)
        clf.fit(x, y)
        z = clf.coef_.ravel()[0] * x.ravel() + clf.intercept_.ravel()[0]
        p_cal = 1.0 / (1.0 + np.exp(-np.clip(z, -50.0, 50.0)))
        return np.clip(p_cal, 1e-6, 1.0 - 1e-6), {
            "platt_a": float(clf.coef_.ravel()[0]),
            "platt_b": float(clf.intercept_.ravel()[0]),
        }
    if method == "isotonic":
        iso = IsotonicRegression(y_min=1e-6, y_max=1.0 - 1e-6, out_of_bounds="clip")
        iso.fit(p, y)
        return np.clip(iso.predict(p), 1e-6, 1.0 - 1e-6), None
    raise ValueError(f"Unsupported calibration method: {method}")


def _calibration_metrics(
    y: np.ndarray,
    p: np.ndarray,
    p_baseline: np.ndarray | None = None,
) -> dict[str, float]:
    yv = np.asarray(y, dtype=np.float64)
    pv = np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1.0 - 1e-6)
    n = len(yv)
    brier = float(np.mean((pv - yv) ** 2)) if n else float("nan")
    logloss = (
        float(-np.mean(yv * np.log(pv) + (1.0 - yv) * np.log(1.0 - pv)))
        if n
        else float("nan")
    )
    # Equal-width 10-bin ECE.
    ece = 0.0
    mce = 0.0
    if n:
        bins = np.linspace(0.0, 1.0, 11)
        for i in range(10):
            lo, hi = bins[i], bins[i + 1]
            if i == 9:
                mask = (pv >= lo) & (pv <= hi)
            else:
                mask = (pv >= lo) & (pv < hi)
            count = int(mask.sum())
            if count == 0:
                continue
            err = abs(float(yv[mask].mean() - pv[mask].mean()))
            ece += err * (count / n)
            mce = max(mce, err)
    brier_skill = float("nan")
    logloss_skill = float("nan")
    if p_baseline is not None and len(p_baseline) == n and n > 0:
        pb = np.clip(np.asarray(p_baseline, dtype=np.float64), 1e-6, 1.0 - 1e-6)
        brier_base = float(np.mean((pb - yv) ** 2))
        logloss_base = float(-np.mean(yv * np.log(pb) + (1.0 - yv) * np.log(1.0 - pb)))
        if brier_base > 0:
            brier_skill = 1.0 - (brier / brier_base)
        if logloss_base > 0:
            logloss_skill = 1.0 - (logloss / logloss_base)
    return {
        "brier": brier,
        "logloss": logloss,
        "ece": float(ece),
        "mce": float(mce),
        "brier_skill_vs_market": float(brier_skill),
        "logloss_skill_vs_market": float(logloss_skill),
    }


def _risk_metrics(eligible: pl.DataFrame) -> dict[str, float | None]:
    if eligible.is_empty():
        return {
            "sortino": None,
            "max_drawdown_abs": None,
            "calmar": None,
            "profit_factor": None,
            "cvar_95": None,
            "expectancy_per_bet": None,
            "turnover_stability": None,
            "max_drawdown_pct": None,
            "max_recovery_bets": None,
        }
    pnl = (eligible["stake"].cast(pl.Float64) * eligible["rpd"].cast(pl.Float64)).to_list()
    pnl_seq = [float(v) for v in pnl if v is not None]
    if not pnl_seq:
        return {
            "sortino": None,
            "max_drawdown_abs": None,
            "calmar": None,
            "profit_factor": None,
            "cvar_95": None,
            "expectancy_per_bet": None,
            "turnover_stability": None,
            "max_drawdown_pct": None,
            "max_recovery_bets": None,
        }
    pnl_arr = np.asarray(pnl_seq, dtype=np.float64)
    mean_pnl = float(pnl_arr.mean())
    downside = pnl_arr[pnl_arr < 0.0]
    downside_dev = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else None
    sortino = (mean_pnl / downside_dev) if downside_dev and downside_dev > 0 else None

    cum = np.cumsum(pnl_arr)
    peaks = np.maximum.accumulate(cum)
    drawdowns = cum - peaks
    max_dd_abs = abs(float(drawdowns.min())) if len(drawdowns) else None
    max_recovery_bets = None
    if len(cum):
        dd_spans: list[int] = []
        peak_idx = 0
        for i in range(1, len(cum)):
            if cum[i] >= cum[peak_idx]:
                if i - peak_idx > 0:
                    dd_spans.append(i - peak_idx)
                peak_idx = i
        if peak_idx < len(cum) - 1:
            dd_spans.append((len(cum) - 1) - peak_idx)
        if dd_spans:
            max_recovery_bets = int(max(dd_spans))
    total_pnl = float(pnl_arr.sum())
    calmar = (total_pnl / max_dd_abs) if max_dd_abs and max_dd_abs > 0 else None
    cum_equity = 1.0 + np.cumsum(pnl_arr)
    peak_equity = np.maximum.accumulate(cum_equity)
    dd_pct = np.where(peak_equity > 0, (cum_equity - peak_equity) / peak_equity, 0.0)
    max_dd_pct = abs(float(np.min(dd_pct))) if len(dd_pct) else None

    gross_win = float(pnl_arr[pnl_arr > 0].sum())
    gross_loss = abs(float(pnl_arr[pnl_arr < 0].sum()))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None

    q = float(np.quantile(pnl_arr, 0.05))
    tail = pnl_arr[pnl_arr <= q]
    cvar_95 = float(tail.mean()) if len(tail) else None

    turnover_stability = None
    if "game_date" in eligible.columns:
        by_day = eligible.group_by("game_date").agg(pl.len().alias("n_bets")).sort("game_date")
        daily_counts = np.asarray(by_day["n_bets"].to_list(), dtype=np.float64)
        if len(daily_counts) >= 3 and float(daily_counts.mean()) > 0:
            turnover_stability = float(1.0 - (daily_counts.std() / daily_counts.mean()))

    return {
        "sortino": sortino,
        "max_drawdown_abs": max_dd_abs,
        "calmar": calmar,
        "profit_factor": profit_factor,
        "cvar_95": cvar_95,
        "expectancy_per_bet": mean_pnl,
        "turnover_stability": turnover_stability,
        "max_drawdown_pct": max_dd_pct,
        "max_recovery_bets": max_recovery_bets,
    }


def _edge_decile_rows(
    eligible: pl.DataFrame, *, feature_set: str, calibration_mode: str
) -> list[dict[str, object]]:
    if eligible.is_empty() or "edge" not in eligible.columns:
        return []
    scoped = eligible.with_columns(
        pl.col("edge").cast(pl.Float64).alias("edge_f"),
        (pl.col("stake").cast(pl.Float64) * pl.col("rpd").cast(pl.Float64)).alias("pnl_row"),
    )
    if scoped.height < 20:
        return []
    deciles = (
        scoped.with_columns(
            pl.col("edge_f")
            .rank(method="ordinal")
            .mul(10)
            .truediv(pl.lit(float(scoped.height)))
            .ceil()
            .clip(1, 10)
            .cast(pl.Int64)
            .alias("edge_decile")
        )
        .group_by("edge_decile")
        .agg(
            pl.len().alias("n_bets"),
            pl.col("stake").sum().alias("stake"),
            pl.col("pnl_row").sum().alias("pnl"),
            pl.col("edge_f").mean().alias("mean_edge"),
            pl.col("clv_pp").cast(pl.Float64).mean().alias("mean_clv_pp"),
        )
        .with_columns(
            pl.when(pl.col("stake") > 0)
            .then(pl.col("pnl") / pl.col("stake"))
            .otherwise(None)
            .alias("roi")
        )
        .sort("edge_decile")
    )
    out: list[dict[str, object]] = []
    for row in deciles.to_dicts():
        out.append(
            {
                "feature_set": feature_set,
                "calibration_mode": calibration_mode,
                "edge_decile": int(row.get("edge_decile") or 0),
                "n_bets": int(row.get("n_bets") or 0),
                "stake": _safe_float(row.get("stake")),
                "pnl": _safe_float(row.get("pnl")),
                "roi": _safe_float(row.get("roi")),
                "mean_edge": _safe_float(row.get("mean_edge")),
                "mean_clv_pp": _safe_float(row.get("mean_clv_pp")),
            }
        )
    return out


def _daily_stability_rows(
    eligible: pl.DataFrame, *, feature_set: str, calibration_mode: str
) -> list[dict[str, object]]:
    if eligible.is_empty():
        return []
    by_day = (
        eligible.with_columns(
            (pl.col("stake").cast(pl.Float64) * pl.col("rpd").cast(pl.Float64)).alias("pnl_row")
        )
        .group_by("game_date")
        .agg(
            pl.len().alias("n_bets"),
            pl.col("stake").cast(pl.Float64).sum().alias("stake"),
            pl.col("pnl_row").sum().alias("pnl"),
            pl.col("edge").cast(pl.Float64).mean().alias("avg_edge"),
        )
        .sort("game_date")
        .with_columns(
            pl.when(pl.col("stake") > 0).then(pl.col("pnl") / pl.col("stake")).otherwise(None).alias("roi_day")
        )
    )
    out = []
    for row in by_day.to_dicts():
        row["feature_set"] = feature_set
        row["calibration_mode"] = calibration_mode
        out.append(row)
    return out


def _segment_rows(
    eligible: pl.DataFrame, *, feature_set: str, calibration_mode: str
) -> list[dict[str, object]]:
    if eligible.is_empty():
        return []
    scoped = eligible.with_columns(
        (pl.col("stake").cast(pl.Float64) * pl.col("rpd").cast(pl.Float64)).alias("pnl_row"),
        pl.when(pl.col("bet_price").cast(pl.Float64) <= -150)
        .then(pl.lit("fav_le_-150"))
        .when(pl.col("bet_price").cast(pl.Float64) <= -110)
        .then(pl.lit("fav_-149_to_-110"))
        .when(pl.col("bet_price").cast(pl.Float64) < 110)
        .then(pl.lit("near_even_-109_to_109"))
        .otherwise(pl.lit("dog_ge_110"))
        .alias("odds_band"),
        pl.when(pl.col("line").cast(pl.Float64) <= 4.5)
        .then(pl.lit("line_le_4_5"))
        .when(pl.col("line").cast(pl.Float64) <= 6.0)
        .then(pl.lit("line_5_0_to_6_0"))
        .otherwise(pl.lit("line_ge_6_5"))
        .alias("line_band"),
    )
    segment_defs = [
        ("side", "side"),
        ("market", "market"),
        ("odds_band", "odds_band"),
        ("line_band", "line_band"),
    ]
    out: list[dict[str, object]] = []
    for seg_name, seg_col in segment_defs:
        grouped = (
            scoped.group_by(seg_col)
            .agg(
                pl.len().alias("n_bets"),
                pl.col("stake").cast(pl.Float64).sum().alias("stake"),
                pl.col("pnl_row").sum().alias("pnl"),
                pl.col("edge").cast(pl.Float64).mean().alias("avg_edge"),
            )
            .with_columns(
                pl.when(pl.col("stake") > 0).then(pl.col("pnl") / pl.col("stake")).otherwise(None).alias("roi")
            )
        )
        for row in grouped.to_dicts():
            out.append(
                {
                    "feature_set": feature_set,
                    "calibration_mode": calibration_mode,
                    "segment_type": seg_name,
                    "segment_value": str(row.get(seg_col)),
                    "n_bets": int(row.get("n_bets") or 0),
                    "stake": _safe_float(row.get("stake")),
                    "pnl": _safe_float(row.get("pnl")),
                    "roi": _safe_float(row.get("roi")),
                    "avg_edge": _safe_float(row.get("avg_edge")),
                }
            )
    return out


def _gate_and_rank(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    defaults = {
        "n_policy_bets": 0,
        "expected_k_mae_on_matched": np.nan,
        "k_rate_mae_on_matched": np.nan,
        "brier": np.nan,
        "ece": np.nan,
        "sortino": np.nan,
        "profit_factor": np.nan,
        "tbf_sensitivity_mae_delta": np.nan,
        "roi": np.nan,
        "go_no_go_replay_ci_gate": False,
    }
    for col, val in defaults.items():
        if col not in out.columns:
            out[col] = val
    out["gate_min_bets"] = out["n_policy_bets"].fillna(0) >= 25
    out["gate_expected_k_mae"] = out["expected_k_mae_on_matched"].fillna(np.inf) <= 1.70
    out["gate_k_rate_mae"] = out["k_rate_mae_on_matched"].fillna(np.inf) <= 0.0745
    out["gate_calibration"] = (
        out["brier"].fillna(np.inf) <= 0.245
    ) & (out["ece"].fillna(np.inf) <= 0.07)
    out["gate_risk"] = (
        out["sortino"].fillna(-np.inf) >= 0.25
    ) & (out["profit_factor"].fillna(-np.inf) >= 1.2)
    out["gate_tbf_stability"] = out["tbf_sensitivity_mae_delta"].fillna(np.inf) <= 0.012
    gate_cols = [
        "gate_min_bets",
        "gate_expected_k_mae",
        "gate_k_rate_mae",
        "gate_calibration",
        "gate_risk",
        "gate_tbf_stability",
    ]
    out["gate_pass_count"] = out[gate_cols].sum(axis=1)
    out["composite_score"] = (
        -100.0 * out["expected_k_mae_on_matched"].fillna(np.inf)
        - 20.0 * out["k_rate_mae_on_matched"].fillna(np.inf)
        - 10.0 * out["brier"].fillna(np.inf)
        + 20.0 * out["roi"].fillna(-1.0)
        + 4.0 * out["sortino"].fillna(0.0)
        + 2.0 * out["profit_factor"].fillna(0.0)
    )
    return out.sort_values(
        ["gate_pass_count", "go_no_go_replay_ci_gate", "composite_score"],
        ascending=[False, False, False],
    )


def _score_feature_set(
    frame_all: pd.DataFrame,
    settled: pl.DataFrame,
    feature_set: str,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    frame_pl = pl.from_pandas(frame_all)
    train = (
        frame_pl
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
        frame_pl
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
    k_model, tbf_model, upper, kappa = _fit_models(
        train, k_features, tbf_features, monotone=monotone
    )

    k_hat = predict_clipped(k_model, "lightgbm", score_pool, k_features)
    tbf_hat = predict_nonnegative(tbf_model, "ridge", score_pool, tbf_features, upper=upper)

    pred_cols = ["game_pk", "pitcher", "game_date"]
    if "K" in score_pool.columns:
        pred_cols.append("K")
    preds = score_pool[pred_cols].copy()
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
    joined = led.join(
        pl.from_pandas(preds),
        on=["game_pk", "pitcher", "game_date"],
        how="inner",
    )
    if joined.is_empty():
        return ([{"feature_set": feature_set, "n": 0}], [], [], [])

    pdf = joined.to_pandas()
    probs: list[float] = []
    p_market: list[float | None] = []
    rpd: list[float | None] = []
    y_vec: list[float | None] = []
    for row in pdf.to_dict(orient="records"):
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
        p_model = pov if side == "over" else (1.0 - pov)
        probs.append(p_model)
        p_mkt = _close_side_prob(row)
        p_market.append(p_mkt)
        rpd.append(_returns_per_dollar(row))
        y_vec.append(_result_to_y(row.get("result")))
    pdf["p_model_new"] = probs
    pdf["p_market_new"] = p_market
    pdf["rpd"] = rpd
    pdf["y"] = y_vec
    pdf = pdf[pd.notnull(pdf["p_market_new"]) & pd.notnull(pdf["rpd"])].copy()
    if pdf.empty:
        return ([{"feature_set": feature_set, "n": 0}], [], [], [])
    eval_pdf = score_pool.dropna(subset=["K", "PA"]).copy() if {"K", "PA"}.issubset(score_pool.columns) else pd.DataFrame()
    if not eval_pdf.empty:
        eval_pdf["k_rate_pred"] = predict_clipped(k_model, "lightgbm", eval_pdf, k_features)
        eval_pdf["projected_tbf"] = predict_nonnegative(
            tbf_model, "ridge", eval_pdf, tbf_features, upper=upper
        )
        eval_pdf["expected_K"] = expected_strikeouts(eval_pdf["k_rate_pred"], eval_pdf["projected_tbf"])
    expected_k_mae = None
    k_rate_mae = None
    expected_k_mae_tbf_minus_3pct = None
    expected_k_mae_tbf_plus_3pct = None
    tbf_sensitivity_mae_delta = None
    if not eval_pdf.empty:
        expected_k_mae = float(
            metrics(eval_pdf["K"], eval_pdf["expected_K"], clip_to_unit_interval=False)["mae"]
        )
        eval_pa = eval_pdf["PA"].replace(0, np.nan)
        k_rate_obs = (eval_pdf["K"] / eval_pa).fillna(0.0)
        k_rate_mae = float(np.mean(np.abs(k_rate_obs - eval_pdf["k_rate_pred"])))
        expected_k_mae_tbf_minus_3pct = float(
            metrics(
                eval_pdf["K"],
                expected_strikeouts(eval_pdf["k_rate_pred"], eval_pdf["projected_tbf"] * 0.97),
                clip_to_unit_interval=False,
            )["mae"]
        )
        expected_k_mae_tbf_plus_3pct = float(
            metrics(
                eval_pdf["K"],
                expected_strikeouts(eval_pdf["k_rate_pred"], eval_pdf["projected_tbf"] * 1.03),
                clip_to_unit_interval=False,
            )["mae"]
        )
        tbf_sensitivity_mae_delta = float(
            max(
                abs(expected_k_mae_tbf_minus_3pct - expected_k_mae),
                abs(expected_k_mae_tbf_plus_3pct - expected_k_mae),
            )
        )

    rows: list[dict[str, object]] = []
    daily_rows: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []
    edge_decile_rows: list[dict[str, object]] = []
    line_floors, fallback = _load_line_floors()
    y_fit = pdf["y"].astype(float).to_numpy()
    raw_probs = pdf["p_model_new"].astype(float).to_numpy()
    for calibration_mode in ("raw", "platt", "isotonic"):
        p_cal, cal_meta = _fit_calibrator(raw_probs, y_fit, calibration_mode)
        mode_pdf = pdf.copy()
        mode_pdf["p_model_mode"] = p_cal
        mode_pdf["edge_new"] = mode_pdf["p_model_mode"] - mode_pdf["p_market_new"]
        scored = (
            pl.from_pandas(mode_pdf)
            .drop("edge")
            .rename({"edge_new": "edge"})
            .with_columns(pl.col("rpd").cast(pl.Float64), pl.col("clv_pp").cast(pl.Float64))
        )
        eligible = _eligible_current_policy(
            scored,
            roi_mode="balanced",
            line_floors=line_floors,
            fallback_floor=fallback,
        ).filter(pl.col("passes_current_policy"))
        if eligible.is_empty():
            rows.append(
                {
                    "feature_set": feature_set,
                    "source_feature_set": source_feature_set,
                    "monotone_constraints": bool(monotone),
                    "calibration_mode": calibration_mode,
                    "matched_rows": int(scored.height),
                    "n_policy_bets": 0,
                    "expected_k_mae_on_matched": expected_k_mae,
                    "k_rate_mae_on_matched": k_rate_mae,
                    "expected_k_mae_tbf_minus_3pct": expected_k_mae_tbf_minus_3pct,
                    "expected_k_mae_tbf_plus_3pct": expected_k_mae_tbf_plus_3pct,
                    "tbf_sensitivity_mae_delta": tbf_sensitivity_mae_delta,
                    "kappa": float(kappa),
                }
            )
            continue

        stake = float(eligible["stake"].cast(pl.Float64).sum())
        pnl = float((eligible["stake"].cast(pl.Float64) * eligible["rpd"].cast(pl.Float64)).sum())
        roi = pnl / stake if stake > 0 else None
        roi_vals = [float(v) for v in eligible["rpd"].to_list() if v is not None]
        clv_vals = [float(v) for v in eligible["clv_pp"].to_list() if v is not None]
        roi_mean, roi_lo, roi_hi = (None, None, None)
        if len(roi_vals) >= 25:
            roi_mean, roi_lo, roi_hi = bootstrap_mean_ci(roi_vals, n_boot=1200, seed=11)
        clv_mean, clv_lo, clv_hi = (None, None, None)
        if len(clv_vals) >= 25:
            clv_mean, clv_lo, clv_hi = bootstrap_mean_ci(clv_vals, n_boot=1200, seed=11)
        replay_ci_ok = (
            roi_lo is not None and clv_lo is not None and float(roi_lo) > 0 and float(clv_lo) > 0
        )
        cal_metrics = _calibration_metrics(
            y_fit,
            p_cal,
            mode_pdf["p_market_new"].astype(float).to_numpy(),
        )
        risk = _risk_metrics(eligible)
        daily_rows.extend(
            _daily_stability_rows(eligible, feature_set=feature_set, calibration_mode=calibration_mode)
        )
        segment_rows.extend(
            _segment_rows(eligible, feature_set=feature_set, calibration_mode=calibration_mode)
        )
        edge_decile_rows.extend(
            _edge_decile_rows(eligible, feature_set=feature_set, calibration_mode=calibration_mode)
        )
        rows.append(
            {
                "feature_set": feature_set,
                "source_feature_set": source_feature_set,
                "monotone_constraints": bool(monotone),
                "calibration_mode": calibration_mode,
                "matched_rows": int(scored.height),
                "n_policy_bets": int(eligible.height),
                "stake": stake,
                "pnl": pnl,
                "roi": roi,
                "roi_ci_lo": float(roi_lo) if roi_lo is not None else None,
                "roi_ci_hi": float(roi_hi) if roi_hi is not None else None,
                "clv_mean_pp": (sum(clv_vals) / len(clv_vals)) if clv_vals else None,
                "clv_ci_lo": float(clv_lo) if clv_lo is not None else None,
                "clv_ci_hi": float(clv_hi) if clv_hi is not None else None,
                "go_no_go_replay_ci_gate": bool(replay_ci_ok),
                "expected_k_mae_on_matched": expected_k_mae,
                "k_rate_mae_on_matched": k_rate_mae,
                "expected_k_mae_tbf_minus_3pct": expected_k_mae_tbf_minus_3pct,
                "expected_k_mae_tbf_plus_3pct": expected_k_mae_tbf_plus_3pct,
                "tbf_sensitivity_mae_delta": tbf_sensitivity_mae_delta,
                "expected_k_mae_ci_lo": (
                    None
                    if eval_pdf.empty
                    else _bootstrap_ci_mae(
                        eval_pdf["K"].to_numpy(),
                        eval_pdf["expected_K"].to_numpy(),
                    )[0]
                ),
                "expected_k_mae_ci_hi": (
                    None
                    if eval_pdf.empty
                    else _bootstrap_ci_mae(
                        eval_pdf["K"].to_numpy(),
                        eval_pdf["expected_K"].to_numpy(),
                    )[1]
                ),
                "brier": cal_metrics["brier"],
                "logloss": cal_metrics["logloss"],
                "ece": cal_metrics["ece"],
                "mce": cal_metrics["mce"],
                "brier_skill_vs_market": cal_metrics["brier_skill_vs_market"],
                "logloss_skill_vs_market": cal_metrics["logloss_skill_vs_market"],
                "kappa": float(kappa),
                "sortino": risk["sortino"],
                "max_drawdown_abs": risk["max_drawdown_abs"],
                "max_drawdown_pct": risk["max_drawdown_pct"],
                "max_recovery_bets": risk["max_recovery_bets"],
                "calmar": risk["calmar"],
                "profit_factor": risk["profit_factor"],
                "cvar_95": risk["cvar_95"],
                "expectancy_per_bet": risk["expectancy_per_bet"],
                "turnover_stability": risk["turnover_stability"],
                "calibration_meta": cal_meta,
            }
        )
    return rows, daily_rows, segment_rows, edge_decile_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feature-set",
        action="append",
        default=[],
        help="Repeatable feature set override. Suffix with _monotone to enable monotonic constraints.",
    )
    args = parser.parse_args()
    sets = (
        args.feature_set
        if args.feature_set
        else [
            "production",
            "production_final58_consensus",
            "production_plus_xwoba_luck",
            "production_sparse40",
            "production_stable12",
            "production_sparse72_monotone",
        ]
    )

    settled = _load_settled_ledger()
    frame_all_pl = (
        pl.read_parquet(config.PITCHER_TRAINING_PATH)
        .with_columns(pl.col("game_date").cast(pl.Datetime, strict=False))
    )
    frame_all = frame_all_pl.to_pandas()
    frame_all["game_date"] = pd.to_datetime(frame_all["game_date"])
    rows_nested = [_score_feature_set(frame_all, settled, feature_set) for feature_set in sets]
    rows = [item for sub, _, _, _ in rows_nested for item in sub]
    daily_rows = [item for _, sub, _, _ in rows_nested for item in sub]
    segment_rows = [item for _, _, sub, _ in rows_nested for item in sub]
    edge_decile_rows = [item for _, _, _, sub in rows_nested for item in sub]
    out = pd.DataFrame(rows).sort_values(
        ["go_no_go_replay_ci_gate", "expected_k_mae_on_matched", "roi"],
        ascending=[False, True, False],
    )
    ranked = _gate_and_rank(out) if not out.empty else out
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    ranked.to_csv(OUT_RANK_CSV, index=False)
    if daily_rows:
        pd.DataFrame(daily_rows).to_csv(OUT_DAILY_CSV, index=False)
    if segment_rows:
        pd.DataFrame(segment_rows).to_csv(OUT_SEGMENT_CSV, index=False)
    if edge_decile_rows:
        pd.DataFrame(edge_decile_rows).to_csv(OUT_EDGE_DECILE_CSV, index=False)
    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feature_sets": sets,
        "results": rows,
        "file": str(OUT_CSV),
        "ranked_file": str(OUT_RANK_CSV),
        "daily_file": str(OUT_DAILY_CSV),
        "segment_file": str(OUT_SEGMENT_CSV),
        "edge_decile_file": str(OUT_EDGE_DECILE_CSV),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(out.to_string(index=False))
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()

