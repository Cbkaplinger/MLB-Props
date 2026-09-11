"""Paper money-track quant pack (observability, #114).

Deduped settled paper at juiced live prices, full track + veto lane
(skip side==over & line==4.5): Sharpe/Sortino (daily, sqrt(162)),
max/current drawdown (units), Calmar, WR/ROI, CLV. The juiced reality
against which harness-fair Sharpe 7.64 decomposes.

Writes artifacts/odds_log/paper_quant_report.json. No live change.
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

from Python.odds_ledger import dedupe_ledger_props  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"


def track(df: pl.DataFrame) -> dict:
    rep: dict = {"n": int(df.height)}
    if df.is_empty():
        return rep
    pnl = df["pnl"].to_numpy().astype(float)
    rep["pnl"] = round(float(np.sum(pnl)), 2)
    rep["wr"] = float(np.mean((pnl > 0).astype(float)))
    stake = df["stake"].to_numpy().astype(float)
    stake = np.where(stake > 0, stake, 50.0)
    rep["roi"] = float(np.sum(pnl) / np.sum(stake))
    days = df.group_by(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10)).agg(
        pl.col("pnl").sum().alias("dpnl")).sort("game_date")
    dp = days["dpnl"].to_numpy().astype(float)
    rep["n_days"] = int(len(dp))
    if len(dp) > 5 and float(np.std(dp)) > 0:
        rep["sharpe"] = float(np.mean(dp) / np.std(dp) * np.sqrt(162.0))
        dn = dp[dp < 0]
        rep["sortino"] = (float(np.mean(dp) / np.std(dn) * np.sqrt(162.0))
                          if len(dn) > 1 and float(np.std(dn)) > 0 else None)
    else:
        rep["sharpe"], rep["sortino"] = None, None
    u = df["unit_dollars"].to_numpy().astype(float) if "unit_dollars" in df.columns else np.full(len(dp), 50.0)
    u = np.where(u > 0, u, 50.0)
    eq = np.cumsum(pnl / u)
    peak = np.maximum.accumulate(eq)
    trail = peak - eq
    rep["profit_u"] = round(float(eq[-1]), 2)
    rep["max_dd_u"] = round(float(trail.max()), 2)
    rep["current_dd_u"] = round(float(trail[-1]), 2)
    rep["calmar_u"] = (round(float(eq[-1]) / float(trail.max()), 3)
                       if float(trail.max()) > 0 else None)
    clv = df.filter(pl.col("clv_pp").is_not_null())["clv_pp"].to_numpy().astype(float)
    rep["clv_n"] = int(len(clv))
    rep["clv_mean_pp"] = float(np.mean(clv) * 100) if len(clv) else None
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    lg = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled") & pl.col("pnl").is_not_null())
    dd = dedupe_ledger_props(lg)
    bets = dd.filter(pl.col("units").fill_null(0) > 0).sort(["game_date", "logged_at_utc"])
    veto = bets.filter(~((pl.col("side") == "over") & (pl.col("line") == 4.5)))
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "full": track(bets), "veto_lane": track(veto)}
    out = ODDS_DIR / "paper_quant_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
