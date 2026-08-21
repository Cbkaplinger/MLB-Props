"""Build daily validation/ops artifacts for policy, uncertainty, and data quality.

Outputs:
- artifacts/odds_log/decision_scoreboard_daily.parquet
- artifacts/odds_log/decision_scoreboard_latest.csv
- artifacts/odds_log/validation_ops_daily.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.kpi_policy import DEFAULT_POLICY_PATH, load_kpi_policy  # noqa: E402
from Python.market import american_to_implied_prob, bootstrap_mean_ci, devig_two_way  # noqa: E402
from Python.odds_ledger import load_ledger, settled_bets  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
SCOREBOARD_PATH = ODDS_DIR / "decision_scoreboard_daily.parquet"
SCOREBOARD_CSV = ODDS_DIR / "decision_scoreboard_latest.csv"
SUMMARY_JSON = ODDS_DIR / "validation_ops_daily.json"


def _safe_float(v: object) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _infer_close_ref_roi(row: dict[str, object]) -> float | None:
    side = str(row.get("side") or "")
    bet_price = _safe_float(row.get("bet_price"))
    close_over = _safe_float(row.get("close_over"))
    close_under = _safe_float(row.get("close_under"))
    if side not in {"over", "under"} or bet_price is None or close_over is None or close_under is None:
        return None
    try:
        p_over, p_under = devig_two_way(close_over, close_under)
    except Exception:
        return None
    p_win = p_over if side == "over" else p_under
    if bet_price > 0:
        b = bet_price / 100.0
    else:
        b = 100.0 / abs(bet_price)
    return (p_win * b) - (1.0 - p_win)


def _slippage_decomposition(settled: pl.DataFrame) -> dict[str, object]:
    if settled.is_empty():
        return {"n_with_prices": 0}
    if any(c not in settled.columns for c in ["bet_price", "other_price", "close_over", "close_under", "side"]):
        return {"n_with_prices": 0}

    scoped = settled.filter(
        pl.col("bet_price").is_not_null()
        & pl.col("other_price").is_not_null()
        & pl.col("close_over").is_not_null()
        & pl.col("close_under").is_not_null()
        & pl.col("side").is_in(["over", "under"])
    )
    if scoped.is_empty():
        return {"n_with_prices": 0}

    rows = scoped.select(
        "side",
        "bet_price",
        "other_price",
        "close_over",
        "close_under",
    ).to_dicts()
    recs: list[dict[str, float | str]] = []
    for r in rows:
        side = str(r.get("side"))
        bet_side = _safe_float(r.get("bet_price"))
        bet_other = _safe_float(r.get("other_price"))
        close_over = _safe_float(r.get("close_over"))
        close_under = _safe_float(r.get("close_under"))
        if (
            side not in {"over", "under"}
            or bet_side is None
            or bet_other is None
            or close_over is None
            or close_under is None
        ):
            continue
        try:
            p_open_over, p_open_under = devig_two_way(bet_side, bet_other)
            p_close_over, p_close_under = devig_two_way(close_over, close_under)
        except Exception:
            continue
        p_open = p_open_over if side == "over" else p_open_under
        p_close = p_close_over if side == "over" else p_close_under
        p_bet_single = american_to_implied_prob(bet_side)
        recs.append(
            {
                "side": side,
                "open_to_bet_pp": float(p_open - p_bet_single),
                "bet_to_close_pp": float(p_close - p_open),
                "open_to_close_pp": float(p_close - p_bet_single),
            }
        )
    if not recs:
        return {"n_with_prices": 0}

    rec_df = pl.DataFrame(recs)
    all_stats = {
        "n_with_prices": int(rec_df.height),
        "mean_open_to_bet_pp": float(rec_df["open_to_bet_pp"].mean()),
        "mean_bet_to_close_pp": float(rec_df["bet_to_close_pp"].mean()),
        "mean_open_to_close_pp": float(rec_df["open_to_close_pp"].mean()),
    }
    side_stats = {}
    for side in ("over", "under"):
        s = rec_df.filter(pl.col("side") == side)
        if s.is_empty():
            continue
        side_stats[side] = {
            "n": int(s.height),
            "mean_open_to_bet_pp": float(s["open_to_bet_pp"].mean()),
            "mean_bet_to_close_pp": float(s["bet_to_close_pp"].mean()),
            "mean_open_to_close_pp": float(s["open_to_close_pp"].mean()),
        }
    return {
        "all": all_stats,
        "by_side": side_stats,
    }


def _drawdown_and_rolling(
    pnls: list[float],
    stakes: list[float],
    *,
    window: int = 50,
) -> tuple[float | None, float | None]:
    if not pnls:
        return None, None
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += float(p)
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
    if len(pnls) < window:
        return max_dd, None
    tail_pnl = pnls[-window:]
    tail_stake = stakes[-window:] if stakes else []
    stake_anchor = float(sum(tail_stake)) if tail_stake else 0.0
    rolling_roi = (sum(tail_pnl) / stake_anchor) if stake_anchor > 0 else None
    return max_dd, rolling_roi


def _policy_mask(df: pl.DataFrame, policy_name: str) -> pl.Expr:
    e = pl.col("edge").cast(pl.Float64).fill_null(0.0)
    side = pl.col("side").cast(pl.Utf8).fill_null("")
    if policy_name == "all":
        return pl.lit(True)
    if policy_name == "balanced":
        return e >= 0.16
    if policy_name == "profit_lock":
        return ((side == "over") & (e >= 0.22)) | ((side == "under") & (e >= 0.18))
    return pl.lit(False)


def _ci(vals: list[float], min_n: int) -> tuple[float | None, float | None, float | None]:
    if len(vals) < min_n:
        return None, None, None
    mean, lo, hi = bootstrap_mean_ci([float(v) for v in vals], n_boot=1500, seed=7)
    return float(mean), float(lo), float(hi)


def _score_policy(
    settled: pl.DataFrame,
    policy_name: str,
    *,
    ci_min_n: int,
) -> dict[str, object]:
    sel = settled.filter(_policy_mask(settled, policy_name))
    if sel.is_empty():
        return {"policy": policy_name, "n": 0}
    stake = float(sel["stake"].cast(pl.Float64).fill_null(0.0).sum())
    pnl = float(sel["pnl"].cast(pl.Float64).fill_null(0.0).sum())
    roi = (pnl / stake) if stake > 0 else None
    clv_vals = [
        float(v) for v in sel["clv_pp"].to_list() if v is not None
    ] if "clv_pp" in sel.columns else []
    clv_pos = [v for v in clv_vals if v > 0]
    close_vals = [
        float(v) for v in sel["xroi_close_ref"].to_list() if v is not None
    ] if "xroi_close_ref" in sel.columns else []
    model_vals = [
        float(v) for v in sel["edge"].to_list() if v is not None
    ] if "edge" in sel.columns else []
    per_bet_roi = [
        (float(r["pnl"]) / float(r["stake"]))
        for r in sel.select("pnl", "stake").to_dicts()
        if _safe_float(r.get("stake")) not in (None, 0.0) and _safe_float(r.get("pnl")) is not None
    ]
    if "logged_at_utc" in sel.columns:
        ordered = sel.sort("logged_at_utc")
    else:
        ordered = sel
    pnl_seq = [float(v) for v in ordered["pnl"].cast(pl.Float64).fill_null(0.0).to_list()]
    stake_seq = [float(v) for v in ordered["stake"].cast(pl.Float64).fill_null(0.0).to_list()]
    max_dd, rolling_roi_50 = _drawdown_and_rolling(pnl_seq, stake_seq, window=50)
    roi_mean, roi_lo, roi_hi = _ci(per_bet_roi, ci_min_n)
    clv_mean, clv_lo, clv_hi = _ci(clv_vals, ci_min_n)
    return {
        "policy": policy_name,
        "n": int(sel.height),
        "stake": stake,
        "pnl": pnl,
        "realized_roi": roi,
        "xroi_close_ref": (sum(close_vals) / len(close_vals)) if close_vals else None,
        "xroi_model": (sum(model_vals) / len(model_vals)) if model_vals else None,
        "mean_clv_pp": (sum(clv_vals) / len(clv_vals)) if clv_vals else None,
        "pct_positive_clv": (len(clv_pos) / len(clv_vals)) if clv_vals else None,
        "max_drawdown_dollars": max_dd,
        "rolling_roi_50": rolling_roi_50,
        "roi_ci_mean": roi_mean,
        "roi_ci_lo": roi_lo,
        "roi_ci_hi": roi_hi,
        "clv_ci_mean": clv_mean,
        "clv_ci_lo": clv_lo,
        "clv_ci_hi": clv_hi,
    }


def _data_quality(ledger: pl.DataFrame, policy: dict) -> dict[str, object]:
    dq = policy.get("data_quality", {})
    latest = ledger.sort("logged_at_utc").tail(1) if not ledger.is_empty() and "logged_at_utc" in ledger.columns else ledger
    close_missing = 0
    if not ledger.is_empty():
        close_missing = int(
            ledger.filter(
                (pl.col("status").cast(pl.Utf8) == "settled")
                & (pl.col("close_over").is_null() | pl.col("close_under").is_null())
            ).height
        )
    stale = 0
    if not latest.is_empty() and "minutes_to_tip_at_open" in latest.columns:
        stale = int(
            latest.filter(pl.col("minutes_to_tip_at_open").cast(pl.Float64).fill_null(0.0) < 15).height
        )
    unmatched_rate = None
    meta_path = ODDS_DIR / "recommendations_meta.json"
    if meta_path.exists():
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        n_board = int(payload.get("n_board") or 0)
        n_unmatched = int(payload.get("n_unmatched") or 0)
        unmatched_rate = (n_unmatched / n_board) if n_board > 0 else None
    alerts: list[str] = []
    if close_missing > int(dq.get("max_missing_closes", 0)):
        alerts.append("missing_closes")
    if stale > int(dq.get("max_stale_open_rows", 0)):
        alerts.append("stale_quotes")
    if unmatched_rate is not None and unmatched_rate > float(dq.get("max_unmatched_rate", 0.25)):
        alerts.append("unmatched_rate_high")
    return {
        "missing_close_rows": close_missing,
        "stale_open_rows": stale,
        "unmatched_rate": unmatched_rate,
        "alerts": alerts,
    }


def main() -> None:
    policy = load_kpi_policy(DEFAULT_POLICY_PATH)
    ops = policy.get("ops_validation", {})
    ci_min_n = int(ops.get("ci_min_samples", 25))
    sustain_n = int(ops.get("sustained_underperform_window", 5))
    ledger = load_ledger()
    settled = settled_bets(ledger) if not ledger.is_empty() else ledger
    if settled.is_empty():
        SUMMARY_JSON.write_text(
            json.dumps({"status": "no_settled_rows"}, indent=2),
            encoding="utf-8",
        )
        print(f"wrote {SUMMARY_JSON}")
        return

    settled = settled.with_columns(
        pl.struct(pl.all()).map_elements(_infer_close_ref_roi, return_dtype=pl.Float64).alias("xroi_close_ref")
    )
    snap = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for name in ("all", "balanced", "profit_lock"):
        r = _score_policy(settled, name, ci_min_n=ci_min_n)
        r["snapshot_utc"] = snap
        rows.append(r)
    scoreboard = pl.DataFrame(rows)
    if SCOREBOARD_PATH.exists():
        hist = pl.read_parquet(SCOREBOARD_PATH)
        scoreboard_out = pl.concat([hist, scoreboard], how="diagonal_relaxed")
    else:
        scoreboard_out = scoreboard
    scoreboard_out.write_parquet(SCOREBOARD_PATH)
    scoreboard.write_csv(SCOREBOARD_CSV)

    bal = scoreboard.filter(pl.col("policy") == "balanced").to_dicts()[0]
    plock = scoreboard.filter(pl.col("policy") == "profit_lock").to_dicts()[0]
    underperform_flags = []
    if plock.get("realized_roi") is not None and bal.get("realized_roi") is not None:
        underperform_flags.append(float(plock["realized_roi"]) < float(bal["realized_roi"]))
    if plock.get("mean_clv_pp") is not None and bal.get("mean_clv_pp") is not None:
        underperform_flags.append(float(plock["mean_clv_pp"]) < float(bal["mean_clv_pp"]))
    if plock.get("pct_positive_clv") is not None and bal.get("pct_positive_clv") is not None:
        underperform_flags.append(float(plock["pct_positive_clv"]) < float(bal["pct_positive_clv"]))

    degrade_now = len(underperform_flags) >= 2 and all(underperform_flags)
    recent = (
        pl.read_parquet(SCOREBOARD_PATH)
        .filter(pl.col("policy").is_in(["balanced", "profit_lock"]))
        .sort("snapshot_utc")
        .tail(max(2, sustain_n * 2))
    )
    sustained = False
    if not recent.is_empty():
        p = recent.filter(pl.col("policy") == "profit_lock").tail(sustain_n)
        b = recent.filter(pl.col("policy") == "balanced").tail(sustain_n)
        if p.height == sustain_n and b.height == sustain_n:
            sustained = bool(
                (float(p["realized_roi"].cast(pl.Float64).mean()) < float(b["realized_roi"].cast(pl.Float64).mean()))
                and (float(p["mean_clv_pp"].cast(pl.Float64).mean()) < float(b["mean_clv_pp"].cast(pl.Float64).mean()))
            )

    quality = _data_quality(ledger, policy)
    promote_min_n = int(ops.get("promotion_min_samples", ci_min_n))
    promote_ready = bool(
        (bal.get("n") or 0) >= promote_min_n
        and (bal.get("roi_ci_lo") is not None and float(bal["roi_ci_lo"]) > 0.0)
        and (bal.get("clv_ci_lo") is not None and float(bal["clv_ci_lo"]) > 0.0)
    )
    summary = {
        "snapshot_utc": snap,
        "primary_benchmark": "xroi_close_ref",
        "secondary_benchmark": "xroi_model",
        "promotion_ci_gate_pass": promote_ready,
        "profit_lock_auto_downgrade": bool(degrade_now and sustained),
        "profit_lock_underperform_sustained": sustained,
        "policy_stability_window": sustain_n,
        "data_quality": quality,
        "slippage_decomposition": _slippage_decomposition(settled),
        "scoreboard_latest": rows,
        "outputs": {
            "scoreboard_parquet": str(SCOREBOARD_PATH),
            "scoreboard_latest_csv": str(SCOREBOARD_CSV),
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {SCOREBOARD_PATH}")
    print(f"wrote {SCOREBOARD_CSV}")
    print(f"wrote {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
