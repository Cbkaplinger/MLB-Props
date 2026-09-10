"""Drawdown brake monitor (paper track; SHADOW — no live stake change).

Risk-only, no modeling. Reads the settled ledger on the canonical deduped
track, builds unit equity in settle order, and reports a brake state:
  GREEN   trailing DD < 8u                        -> stake x1.0
  CAUTION trailing DD >= 8u                       -> stake x0.5
  HALT    trailing DD >= 15u                      -> no new BETs (x0.0)
Release uses hysteresis (HALT clears at <=10u, CAUTION at <=5u) so the
state cannot flicker day to day. Levels were set from history (max DD
24.4u would have halted the over-bleed era; current hole 10.5u = CAUTION).

Slate cap (today's board, recommendations.parquet BET units sum):
  soft 12u / hard 20u (p50/p90 of history are 11.4/20.8u).

Promoting any multiplier to live staking needs explicit sign-off per
standing rules (never silently touch staking). Until then this is the
number the weekly pack reviews alongside veto ROI.

Exit 0 always (monitor, not a gate). Writes
artifacts/odds_log/drawdown_brake_latest.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_text, dedupe_ledger_props  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
LEDGER = ODDS_DIR / "ledger.parquet"
REC = ODDS_DIR / "recommendations.parquet"
OUT_JSON = ODDS_DIR / "drawdown_brake_latest.json"

CAUTION_DD_U = 8.0
HALT_DD_U = 15.0
RELEASE_HALT_U = 10.0
RELEASE_CAUTION_U = 5.0
SLATE_SOFT_U = 12.0
SLATE_HARD_U = 20.0


def brake_state(trailing_dd_u: float, prev: str) -> tuple[str, float]:
    """Hysteresis state machine. Returns (state, stake_multiplier)."""
    if trailing_dd_u >= HALT_DD_U:
        return "HALT", 0.0
    if prev == "HALT":
        if trailing_dd_u <= RELEASE_HALT_U:
            return ("CAUTION", 0.5) if trailing_dd_u > RELEASE_CAUTION_U else ("GREEN", 1.0)
        return "HALT", 0.0
    if prev == "CAUTION":
        if trailing_dd_u <= RELEASE_CAUTION_U:
            return "GREEN", 1.0
        return "CAUTION", 0.5
    if trailing_dd_u >= CAUTION_DD_U:
        return "CAUTION", 0.5
    return "GREEN", 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prev-state", default="GREEN",
                    help="Yesterday's state (for hysteresis; default GREEN).")
    args = ap.parse_args()
    lg = pl.read_parquet(LEDGER).filter(pl.col("status") == "settled")
    dd = dedupe_ledger_props(lg)
    bets = dd.filter(pl.col("units") > 0).sort(["game_date", "logged_at_utc"])
    u = bets["unit_dollars"].to_numpy().astype(float)
    p = bets["pnl"].to_numpy().astype(float)
    u = np.where(u > 0, u, 50.0)
    eq = np.cumsum(p / u)
    peak = np.maximum.accumulate(eq)
    trail = peak - eq
    cur_dd = float(trail[-1]) if len(trail) else 0.0
    max_dd = float(trail.max()) if len(trail) else 0.0
    state, mult = brake_state(cur_dd, args.prev_state.upper())
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "n_bet_props": int(bets.height),
                 "profit_u": float(eq[-1]) if len(eq) else 0.0,
                 "trailing_dd_u": round(cur_dd, 2), "max_dd_u": round(max_dd, 2),
                 "state": state, "stake_multiplier": mult,
                 "levels": {"caution": CAUTION_DD_U, "halt": HALT_DD_U,
                            "release_halt": RELEASE_HALT_U,
                            "release_caution": RELEASE_CAUTION_U}}
    if REC.exists():
        try:
            rec = pl.read_parquet(REC)
        except Exception:
            rec = None
        if rec is not None and "recommendation" in rec.columns and "units" in rec.columns:
            bets_today = rec.filter(
                pl.col("recommendation").cast(pl.Utf8).str.to_uppercase() == "BET")
            slate_u = float(bets_today["units"].sum())
            rep["slate"] = {"n_bets": int(bets_today.height), "units": round(slate_u, 2),
                            "soft_cap": SLATE_SOFT_U, "hard_cap": SLATE_HARD_U,
                            "verdict": ("OVER-HARD" if slate_u > SLATE_HARD_U
                                        else "OVER-SOFT" if slate_u > SLATE_SOFT_U
                                        else "OK")}
    atomic_write_text(OUT_JSON, json.dumps(rep, indent=2, default=str))
    print(f"profit={rep['profit_u']:+.1f}u trailDD={rep['trailing_dd_u']}u "
          f"maxDD={rep['max_dd_u']}u state={state} x{mult} slate={rep.get('slate')}")
    print(f"wrote {OUT_JSON} (SHADOW — live stakes unchanged without sign-off)")
    return 0


if __name__ == "__main__":
    main()
