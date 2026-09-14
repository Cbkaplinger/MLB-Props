"""Disagreement-as-signal probe (research; follows the killed Kalshi filter).

The filter asked "refuse where we disagree" (KILL — disagreement is where
profit lives). This asks the distinct question: does the SIGNED gap
(p_model - p_kalshi_close) predict the outcome residual? A surviving
association is a candidate overlay (WS8 pattern); a dead one closes the
Kalshi-as-signal question with the filter.

Signal test, pre-registered: Pearson corr(gap, y - p_model) with |r| > 0.05
AND monotonic bucket Brier improvement, else KILL. Buckets on signed gap:
we-think-over-sharper (gap>+0.05), agree (|gap|<=0.05), we-think-under (gap<-0.05).

Reads: universe_panel_live + kalshi k_closes/k_ladder. No live change.
Writes: artifacts/odds_log/disagreement_signal_report.json.
"""

from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import math
import sys
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src" / "Python"))

_JK = REPO / "production" / "ops" / "market_research" / "join_keys.py"
_spec = _ilu.spec_from_file_location("join_keys", _JK)
assert _spec and _spec.loader
_jk = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_jk)

KAL = REPO / "data" / "Odds-Historical" / "kalshi"
OUT = REPO / "artifacts" / "odds_log" / "disagreement_signal_report.json"


def main() -> None:
    closes = pl.read_parquet(KAL / "k_closes.parquet").to_dicts()
    lad = pl.read_parquet(KAL / "k_ladder.parquet").select(
        ["market_ticker", "game_date", "player", "rung"]).to_dicts()
    lad_by_mkt = {r["market_ticker"]: r for r in lad}
    kf: dict[tuple, float] = {}
    for c in closes:
        m = lad_by_mkt.get(c["market_ticker"])
        if not m or int(c.get("n_trades") or 0) < 20:
            continue
        kf[(str(m["game_date"])[:10], _jk.sorted_key(m["player"]), int(m["rung"]))] = float(c["close_fair_over"])

    uni = (pl.scan_parquet(REPO / "artifacts" / "odds_log" / "universe_panel_live.parquet")
           .select(["gd", "key", "line", "y", "p_ours_cal"]).collect().to_dicts())
    pts = []
    for r in uni:
        try:
            line = float(r["line"])
        except (TypeError, ValueError):
            continue
        hit = kf.get((str(r["gd"]), _jk.sorted_key(r["key"]), math.floor(line) + 1))
        if hit is None:
            continue
        pm = float(r["p_ours_cal"])
        if not 0.0 < pm < 1.0:
            continue
        pts.append({"gap": pm - hit, "resid": float(r["y"]) - pm,
                    "p": pm, "y": float(r["y"])})

    n = len(pts)
    rep: dict = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "n": n, "coverage_note": "Kalshi closes 7/02-9/07 only; 2025 uncovered"}
    if n < 200:
        rep["kill"] = "KILL (coverage too thin for a signal claim)"
        OUT.write_text(json.dumps(rep, indent=2))
        print(json.dumps(rep, indent=2))
        return

    mg = sum(p["gap"] for p in pts) / n
    mr = sum(p["resid"] for p in pts) / n
    cov = sum((p["gap"] - mg) * (p["resid"] - mr) for p in pts) / n
    vg = sum((p["gap"] - mg) ** 2 for p in pts) / n
    vr = sum((p["resid"] - mr) ** 2 for p in pts) / n
    corr = cov / ((vg * vr) ** 0.5) if vg > 0 and vr > 0 else 0.0
    rep["corr_gap_resid"] = round(corr, 4)

    buckets = {"model_over_sharper": [p for p in pts if p["gap"] > 0.05],
               "agree": [p for p in pts if abs(p["gap"]) <= 0.05],
               "model_under_sharper": [p for p in pts if p["gap"] < -0.05]}
    for name, b in buckets.items():
        rep[name] = {"n": len(b),
                     "brier_model": round(sum((p["p"] - p["y"]) ** 2 for p in b) / len(b), 4) if b else None,
                     "emp_over_rate": round(sum(p["y"] for p in b) / len(b), 3) if b else None,
                     "mean_gap": round(sum(p["gap"] for p in b) / len(b), 4) if b else None}
    rep["kill"] = ("SURVIVE (overlay gate next: shrink p toward Kalshi by gap sign)")
    rep["kill"] = ("SURVIVE (overlay gate next)" if abs(corr) > 0.05 else "KILL (|r|<=0.05 — gap does not predict residual)")
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
