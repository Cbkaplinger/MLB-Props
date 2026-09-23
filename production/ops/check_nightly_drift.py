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
LAST_LOG = ROOT / "artifacts" / "projection_log" / "last_log.json"
HB_PATH = ODDS_DIR / "cloud_heartbeat.jsonl"
# Trailing-24h minimum beats per job (owner 2026-09-21: dead-man switch).
# Floors sit well below nominal (1/14/66/1) so normal variance never pages;
# a fully-missing critical job (morning/settle) is RED, other gaps YELLOW.
HB_EXPECTED = {"morning_workflow": 1, "hourly_refresh": 12,
               "close_sweep": 40, "end_of_day_settle": 1}
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


def heartbeat_beats(path: Path | None = None,
                     *, now: datetime | None = None,
                     window_h: float = 24.0) -> tuple[dict | None, str]:
    """Per-job beat counts in the trailing window (never raises).

    Returns (counts|None, note). None = unreadable file (YELLOW downstream:
    unknown, not proof of outage — matches the fail-open doctrine).
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    try:
        lines = Path(path or HB_PATH).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, "no heartbeat file"
    counts: dict[str, int] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        try:
            ts = datetime.fromisoformat(str(row.get("utc")))
        except (ValueError, TypeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if (now - ts).total_seconds() < 0 or (now - ts).total_seconds() > window_h * 3600:
            continue
        job = str(row.get("job") or "unknown")
        counts[job] = counts.get(job, 0) + 1
    return counts, f"{sum(counts.values())} beats in {window_h:g}h"


def serving_freshness(today: date) -> tuple[int | None, str]:
    """Serving-truth staleness from the projection sidecar (never raises).

    Returns (stale_days|None, note). Live scoring stops at L2 rolling
    (``refresh_features --skip-training``), so the rarely-rebuilt L3
    *training* parquet must NOT measure serving freshness — doing so
    false-REDs on a healthy board (owner 2026-09-18: 11d RED vs 1d truth).
    Missing/unparseable sidecar = unknown (YELLOW downstream, never RED:
    unknown freshness is fail-open, matching the board tag rule).
    """
    try:
        meta = json.loads(LAST_LOG.read_text(encoding="utf-8")).get("build_meta", {})
        max_s = str(meta.get("rolling_max_date") or "")[:10]
    except (OSError, ValueError):
        return None, "no last_log sidecar"
    latest = _max_date([max_s])
    if latest is None:
        return None, "unparseable rolling_max_date"
    return (today - latest).days, f"rolling_max {max_s}"


def freshness_verdict(stale_days: int | None) -> str:
    """Shared stale-data verdict: GREEN <=2d, YELLOW 3-4d, RED >4d/missing."""
    if stale_days is None:
        return RED
    if stale_days <= 2:
        return GREEN
    if stale_days <= 4:
        return YELLOW
    return RED


def l3_null_flag_verdict(n_recent: int, rr: float | None, bb: float) -> tuple[str, str]:
    """Verdict + note for one L3 null-rate column (pure, testable).

    Live scoring stops at L2 (``--skip-training``), so an L3 with zero recent
    rows is the healthy steady state — not drift (owner 2026-09-23: this
    exact shape YELLOWed every morning). Zero recent rows = GREEN with an
    explicit not-rebuilt note; thin-but-nonzero stays YELLOW (can't judge);
    real null ratios keep the existing rule.
    """
    if n_recent == 0:
        return GREEN, "l3_not_rebuilt_live_skips_training"
    if rr is None:
        return YELLOW, "thin_recent_window"
    return null_ratio_verdict(rr, bb or 0.0), ""


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


def _page_red(checks: list[dict]) -> tuple[bool, str]:
    """Opt-in RED banner (Modal drift chain; laptop cron pages via its own
    banner path, so this defaults OFF to avoid double-sends)."""
    import os
    from urllib import request

    reds = [c for c in checks if c.get("verdict") == RED]
    if not reds:
        return True, "no red checks"
    topic = os.getenv("NTFY_TOPIC", "").strip()
    url = os.getenv("NTFY_URL", "").strip() or (f"https://ntfy.sh/{topic}" if topic else "")
    if not url:
        return False, "ntfy_env_missing"
    body = "MLBProps nightly drift RED\n" + "\n".join(
        f"- {c.get('name')}: "
        + ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("name", "verdict"))
        for c in reds)
    req = request.Request(url, data=body.encode("utf-8"),
                          headers={"Title": "MLBProps drift RED", "Priority": "high"},
                          method="POST")
    try:
        with request.urlopen(req, timeout=15) as resp:
            return True, f"ntfy_status={resp.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"ntfy_error={exc}"


def veto_leak_check(rec_path, today) -> dict:
    """Veto-leak tripwire on the live board file. Never raises: a missing,
    unreadable, or empty board (e.g. pre-morning blank slate) reports YELLOW
    instead of crashing the drift chain (owner 2026-09-17: 0-row parquet
    raised ColumnNotFoundError, exit 3, no report written)."""
    if not rec_path.exists():
        return {"name": "veto_leak", "verdict": YELLOW, "note": "no board file"}
    try:
        rb = pl.scan_parquet(rec_path).select(
            ["game_date", "line", "best_side", "recommendation"]).collect()
    except Exception as exc:  # noqa: BLE001
        return {"name": "veto_leak", "verdict": YELLOW,
                "note": f"board unreadable: {type(exc).__name__}"}
    if rb.is_empty():
        return {"name": "veto_leak", "verdict": YELLOW, "note": "board empty"}
    rb_dates = [d for d in (rb["game_date"].cast(pl.Utf8).to_list() or []) if d]
    rb_latest = _max_date(rb_dates)
    rb_stale = (today - rb_latest).days if rb_latest else None
    leak = rb.filter((pl.col("game_date").cast(pl.Utf8) >= VETO_LIVE_DATE)
                     & (pl.col("line") == 4.5) & (pl.col("best_side") == "over")
                     & (pl.col("recommendation").cast(pl.Utf8) == "BET"))
    if rb_stale is not None and rb_stale > 2:
        return {"name": "veto_leak", "verdict": YELLOW,
                "n_leaked": leak.height, "since": VETO_LIVE_DATE,
                "note": f"board stale {rb_stale}d — cannot verify"}
    return {"name": "veto_leak", "verdict": RED if leak.height > 0 else GREEN,
            "n_leaked": leak.height, "since": VETO_LIVE_DATE}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--page-on-red", action="store_true",
                    help="send an ntfy banner when verdict is RED (Modal chain)")
    args = ap.parse_args()
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
    checks.append(veto_leak_check(REC, today))

    # 5. WS1c tail-line watch (8.5/9.5 behave under per-line Platt).
    tail = lg.filter((pl.col("game_date") > tail_cut) & (pl.col("line").is_in([8.5, 9.5])))
    t_wr, t_n = _wr(tail)
    checks.append({"name": "tail_watch",
                   "verdict": (YELLOW if (t_n >= MIN_N_TAIL and (t_wr or 1.0) < 0.40)
                               else GREEN),
                   "wr": t_wr, "n": t_n, "window_days": TAIL_DAYS})

    # 6. Feature freshness: SERVING staleness (last_log rolling max — what the
    # board actually scored on) + L3 missing-rate vs baseline (#45 rule).
    serve_stale, serve_note = serving_freshness(today)
    if serve_stale is None:
        serve_verdict = YELLOW
    else:
        serve_verdict = freshness_verdict(serve_stale)
    if L3.exists():
        l3 = pl.scan_parquet(L3).select(["game_date"] + NULL_WATCH).collect()
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
            v, vnote = l3_null_flag_verdict(r7.height, rr, bb or 0.0)
            entry = {"col": col, "verdict": v, "recent_rate": rr,
                     "base_rate": bb, "n_recent": r7.height}
            if vnote:
                entry["note"] = vnote
            null_flags.append(entry)
        checks.append({"name": "feature_freshness",
                       "verdict": worst(serve_verdict,
                                        *[f["verdict"] for f in null_flags]),
                       "stale_days": serve_stale, "stale_note": serve_note,
                       "nulls": null_flags})
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

    # 8. Heartbeat completeness (dead-man switch, owner 2026-09-21): every
    # scheduled job must have beaten within the trailing 24h. Catches the
    # job that never starts — no exit code, no log, no other check fires.
    hb_counts, hb_note = heartbeat_beats(HB_PATH)
    if hb_counts is None:
        checks.append({"name": "heartbeat_completeness", "verdict": YELLOW,
                       "note": hb_note})
    else:
        short = {job: (HB_EXPECTED[job] - hb_counts.get(job, 0))
                 for job in HB_EXPECTED if hb_counts.get(job, 0) < HB_EXPECTED[job]}
        if not short:
            verdict_hb, note_hb = GREEN, f"all jobs beat in 24h: {hb_counts}"
        elif short.get("morning_workflow", 0) >= HB_EXPECTED["morning_workflow"] \
                or short.get("end_of_day_settle", 0) >= HB_EXPECTED["end_of_day_settle"]:
            verdict_hb, note_hb = RED, f"critical job missing beats: {short}"
        else:
            verdict_hb, note_hb = YELLOW, f"below floor: {short}"
        checks.append({"name": "heartbeat_completeness", "verdict": verdict_hb,
                       "note": note_hb, "counts": hb_counts})

    verdict = worst(*[c["verdict"] for c in checks])
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "verdict": verdict, "today": today.isoformat(), "checks": checks}
    atomic_write_text(OUT_JSON, json.dumps(rep, indent=2, default=str))
    # OBS-1 run manifest (provenance only — never gates, never raises).
    try:
        from Python.run_manifest import (  # noqa: E402
            artifact_version,
            emit_manifest_safely,
            manifest_from_drift,
            manifest_path,
        )
        _failing = [c["name"] for c in checks if c.get("verdict") != "GREEN"]
        _man = manifest_from_drift(
            verdict=verdict, today=today.isoformat(), failing_checks=_failing,
            n_settled=int(lg.height),
            policy_version=artifact_version(
                ROOT / "production" / "ops" / "kpi_policy.json", "kpi"),
            model_version=artifact_version(
                ROOT / "production" / "ops" / "live_krate_ensemble.json", "krate"),
            calibration_version=artifact_version(POINTER, "ws1c"),
            as_of_utc=rep.get("generated_utc"),
        )
        emit_manifest_safely(_man, manifest_path(ODDS_DIR, "P6-SETTLE"))
    except Exception:
        pass
    try:
        with open(OUT_HIST, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rep, default=str) + "\n")
    except OSError:
        pass
    for c in checks:
        print(f"[{c['verdict']}] {c['name']}: "
              + ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("name", "verdict")))
    print(f"verdict={verdict}; wrote {OUT_JSON}")
    if verdict == RED and args.page_on_red:
        ok, info = _page_red(checks)
        print(f"red page: {info}")
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
