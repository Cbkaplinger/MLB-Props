"""Nightly drift check: settle freshness, model-error drift, side drift,
veto-leak tripwire, WS1c tail-line watch, feature-freshness, ship watch.

Read-only over local artifacts (never mutates the ledger); writes
artifacts/odds_log/nightly_drift_latest.json (+ .jsonl history append).

Exit codes: 0 = GREEN, 1 = YELLOW (warnings/insufficient-n only), 2 = RED,
3 = internal error (traceback printed; the cron runner treats this as a
failure so a crash can never masquerade as a quiet YELLOW night).
Designed for the nightly cron (run_nightly_drift.ps1): RED pages via the
failure-banner alert path; YELLOW is reviewed with the morning board.

Thresholds live next to the checks below; n-floors keep thin windows from
paging (SOP: never promote — or page — on thin n).
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_text  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
LEDGER = ODDS_DIR / "ledger.parquet"
GRADED = ROOT / "artifacts" / "projection_log" / "graded.parquet"
L3 = ROOT / "data" / "processed" / "pitcher_training.parquet"
POINTER = ROOT / "artifacts" / "models" / "prob_calibration_production.json"
OUT_JSON = ODDS_DIR / "nightly_drift_latest.json"
OUT_HIST = ODDS_DIR / "nightly_drift_history.jsonl"

# Live stance anchors (keep in sync with backlog; drift check READS, never sets).
VETO_LIVE_DATE = "2026-09-01"  # 4.5-over hard veto live since
RECENT_DAYS = 14
TAIL_DAYS = 30
BASELINE_DAYS = 60
MIN_N_RECENT = 50      # model-error drift needs this many recent graded starts
MIN_N_WR = 30          # side-drift needs this many recent settled tickets
MIN_N_TAIL = 10        # tail-line watch needs this many recent tickets
NULL_WATCH = ["k_rate_P5", "whiff_rate_P20", "ff_velo_P1", "opp_lineup_k", "csw_rate_P20"]
NULL_RATIO_ALARM = 2.0  # backlog #45 rule: alarm if missing-rate > 2x baseline
NULL_MIN_N = 20

GREEN, YELLOW, RED = "GREEN", "YELLOW", "RED"
_RANK = {GREEN: 0, YELLOW: 1, RED: 2}


def worst(*verdicts: str) -> str:
    out = GREEN
    for v in verdicts:
        if _RANK[v] > _RANK[out]:
            out = v
    return out


def _to_date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _max_date(strs) -> date | None:
    """Latest parseable date, None when nothing parses (never raises)."""
    ds = [d for d in (_to_date(s) for s in strs) if d is not None]
    return max(ds) if ds else None


def freshness_verdict(stale_days: int | None) -> str:
    """Shared stale-data verdict: GREEN <=2d, YELLOW 3-4d, RED >4d/missing."""
    if stale_days is None:
        return RED
    if stale_days <= 2:
        return GREEN
    if stale_days <= 4:
        return YELLOW
    return RED


def wr_drift_verdict(recent_wr: float | None, recent_n: int, base_wr: float | None) -> str:
    """Side-drift gate: thin-n can never page; needs a real 8pp drop to WARN."""
    if recent_n < MIN_N_WR or recent_wr is None or base_wr is None:
        return YELLOW
    if recent_wr < base_wr - 0.08:
        return YELLOW
    return GREEN


def mae_drift_verdict(
    recent_mae: float | None, base_mae: float | None,
    recent_bias: float | None, base_bias: float | None, recent_n: int,
) -> str:
    """Model-error drift: WARN on +0.15 MAE or 0.25 bias shift; RED at 2x."""
    if recent_n < MIN_N_RECENT or None in (recent_mae, base_mae, recent_bias, base_bias):
        return YELLOW
    assert recent_mae is not None and base_mae is not None
    assert recent_bias is not None and base_bias is not None
    d_mae = recent_mae - base_mae
    d_bias = abs(recent_bias - base_bias)
    if d_mae > 0.30 or d_bias > 0.50:
        return RED
    if d_mae > 0.15 or d_bias > 0.25:
        return YELLOW
    return GREEN


def null_ratio_verdict(recent_rate: float, base_rate: float) -> str:
    """Backlog #45 rule: YELLOW when the recent missing-rate exceeds 2x baseline."""
    if base_rate <= 0:
        return YELLOW if recent_rate > 0 else GREEN
    return YELLOW if recent_rate > NULL_RATIO_ALARM * base_rate else GREEN


def _wr(frame: pl.DataFrame) -> tuple[float | None, int]:
    n = frame.height
    if n == 0:
        return None, 0
    w = frame.filter(pl.col("result") == "win").height
    return w / n, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    today = datetime.now(timezone.utc).date()
    recent_cut = (today - timedelta(days=RECENT_DAYS)).isoformat()
    tail_cut = (today - timedelta(days=TAIL_DAYS)).isoformat()
    base_cut = (today - timedelta(days=RECENT_DAYS + BASELINE_DAYS)).isoformat()
    checks: list[dict] = []

    # 1. Settle freshness (ledger data, not task health — self-check owns tasks).
    lg = pl.scan_parquet(LEDGER).filter(pl.col("status") == "settled").select(
        ["game_date", "side", "line", "result"]).collect()
    lg_dates = [d for d in (lg["game_date"].to_list() or []) if d]
    latest = _max_date(lg_dates)
    stale = (today - latest).days if latest else None
    checks.append({"name": "settle_freshness", "verdict": freshness_verdict(stale),
                   "stale_days": stale, "n_settled": lg.height})

    # 2. Model-error drift (graded projections carry residual_K).
    gd = pl.scan_parquet(GRADED).filter(pl.col("has_actual")).select(
        ["game_date", "residual_K"]).collect().filter(
        pl.col("residual_K").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8))
    rec = gd.filter(pl.col("game_date") > recent_cut)
    base = gd.filter((pl.col("game_date") > base_cut) & (pl.col("game_date") <= recent_cut))
    rK = rec["residual_K"].to_numpy()
    bK = base["residual_K"].to_numpy()
    r_mae = float(np_abs_mean(rK)) if len(rK) else None
    b_mae = float(np_abs_mean(bK)) if len(bK) else None
    r_bias = float(rK.mean()) if len(rK) else None
    b_bias = float(bK.mean()) if len(bK) else None
    checks.append({"name": "model_error_drift",
                   "verdict": mae_drift_verdict(r_mae, b_mae, r_bias, b_bias, len(rK)),
                   "n_recent": len(rK), "mae_recent": r_mae, "mae_base": b_mae,
                   "bias_recent": r_bias, "bias_base": b_bias})

    # 3. Side drift (settled tickets, full-cohort WR — never trailing-10).
    recent_lg = lg.filter(pl.col("game_date") > recent_cut)
    base_lg = lg.filter(pl.col("game_date") <= recent_cut)
    r_wr, r_n = _wr(recent_lg)
    b_wr, _ = _wr(base_lg)
    per_side = {}
    for side in ("over", "under"):
        w, n = _wr(recent_lg.filter(pl.col("side") == side))
        per_side[side] = {"wr": w, "n": n}
    checks.append({"name": "side_drift", "verdict": wr_drift_verdict(r_wr, r_n, b_wr or 0.5),
                   "wr_recent": r_wr, "n_recent": r_n, "wr_base": b_wr,
                   "per_side": per_side})

    # 4. Veto-leak tripwire on the LIVE board (recommendations.parquet), not the
    # paper ledger — the ledger logs every opportunity by design (shadow/A-B),
    # so ledger 4.5-overs are expected paper, never a leak.
    REC = ODDS_DIR / "recommendations.parquet"
    if REC.exists():
        rb = pl.scan_parquet(REC).select(
            ["game_date", "line", "best_side", "recommendation"]).collect()
        rb_dates = [d for d in (rb["game_date"].cast(pl.Utf8).to_list() or []) if d]
        rb_latest = _max_date(rb_dates)
        rb_stale = (today - rb_latest).days if rb_latest else None
        leak = rb.filter((pl.col("game_date").cast(pl.Utf8) >= VETO_LIVE_DATE)
                         & (pl.col("line") == 4.5) & (pl.col("best_side") == "over")
                         & (pl.col("recommendation").cast(pl.Utf8) == "BET"))
        if rb_stale is not None and rb_stale > 2:
            checks.append({"name": "veto_leak", "verdict": YELLOW,
                           "n_leaked": leak.height, "since": VETO_LIVE_DATE,
                           "note": f"board stale {rb_stale}d — cannot verify"})
        else:
            checks.append({"name": "veto_leak", "verdict": RED if leak.height > 0 else GREEN,
                           "n_leaked": leak.height, "since": VETO_LIVE_DATE})
    else:
        checks.append({"name": "veto_leak", "verdict": YELLOW, "note": "no board file"})

    # 5. WS1c tail-line watch (8.5/9.5 behave under per-line Platt).
    tail = lg.filter((pl.col("game_date") > tail_cut) & (pl.col("line").is_in([8.5, 9.5])))
    t_wr, t_n = _wr(tail)
    checks.append({"name": "tail_watch",
                   "verdict": (YELLOW if (t_n >= MIN_N_TAIL and (t_wr or 1.0) < 0.40)
                               else GREEN),
                   "wr": t_wr, "n": t_n, "window_days": TAIL_DAYS})

    # 6. Feature freshness: L3 staleness + missing-rate vs baseline (#45 rule).
    if L3.exists():
        l3 = pl.scan_parquet(L3).select(["game_date"] + NULL_WATCH).collect()
        l3_dates = [d for d in (l3["game_date"].cast(pl.Utf8).to_list() or []) if d]
        l3_latest = _max_date(l3_dates)
        l3_stale = (today - l3_latest).days if l3_latest else None
        null_flags = []
        for col in NULL_WATCH:
            if col not in l3.columns:
                null_flags.append({"col": col, "verdict": YELLOW, "note": "missing_col"})
                continue
            r7 = l3.filter(pl.col("game_date").cast(pl.Utf8) > recent_cut)
            b60 = l3.filter((pl.col("game_date").cast(pl.Utf8) > base_cut)
                            & (pl.col("game_date").cast(pl.Utf8) <= recent_cut))
            rr = r7[col].null_count() / r7.height if r7.height >= NULL_MIN_N else None
            bb = b60[col].null_count() / b60.height if b60.height else 0.0
            v = YELLOW if rr is None else null_ratio_verdict(rr, bb or 0.0)
            null_flags.append({"col": col, "verdict": v, "recent_rate": rr,
                               "base_rate": bb, "n_recent": r7.height})
        checks.append({"name": "feature_freshness",
                       "verdict": worst(freshness_verdict(l3_stale),
                                        *[f["verdict"] for f in null_flags]),
                       "stale_days": l3_stale, "nulls": null_flags})
    else:
        checks.append({"name": "feature_freshness", "verdict": YELLOW, "note": "no L3 file"})

    # 7. Ship watch: calibrator bundle (line maps live in the joblib bundle the
    # pointer names — the pointer itself carries no maps) + count-layer default
    # (audit catch (a): board fallback once shipped Poisson while hardcoded).
    try:
        ptr = json.loads(POINTER.read_text(encoding="utf-8"))
        import joblib  # noqa: E402
        bundle = joblib.load(ROOT / "artifacts" / "models" / ptr["joblib"])
        maps = getattr(bundle, "line_maps", {}) or {}
        n_lines = len(maps)
        method = ptr.get("method", getattr(bundle, "method", "unknown"))
        ship_v = GREEN if (method == "platt" and n_lines >= 8) else RED
        ship_note: dict = {"version": ptr.get("version"), "method": method, "n_lines": n_lines}
    except (OSError, ValueError, KeyError, ImportError) as exc:
        ship_v, ship_note = RED, {"error": str(exc)[:200]}
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from Python.count_layer import COUNT_LAYER_FAMILY_DEFAULT  # noqa: E402
        fam_ok = COUNT_LAYER_FAMILY_DEFAULT == "poisson"
        ship_note["count_family"] = COUNT_LAYER_FAMILY_DEFAULT
    except ImportError as exc:
        fam_ok, ship_note["count_family"] = False, f"import_failed: {exc}"
    checks.append({"name": "ship_watch",
                   "verdict": worst(ship_v, GREEN if fam_ok else RED), **ship_note})

    verdict = worst(*[c["verdict"] for c in checks])
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "verdict": verdict, "today": today.isoformat(), "checks": checks}
    atomic_write_text(OUT_JSON, json.dumps(rep, indent=2, default=str))
    try:
        with open(OUT_HIST, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rep, default=str) + "\n")
    except OSError:
        pass
    for c in checks:
        print(f"[{c['verdict']}] {c['name']}: "
              + ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("name", "verdict")))
    print(f"verdict={verdict}; wrote {OUT_JSON}")
    return 0 if verdict == GREEN else (1 if verdict == YELLOW else 2)


def np_abs_mean(a):  # tiny local helper (keeps imports light for tests)
    import numpy as np
    return float(np.mean(np.abs(np.asarray(a, dtype=float))))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(3)
