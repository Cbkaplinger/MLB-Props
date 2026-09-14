"""Kalshi overlay gate (follows disagreement_signal_probe SURVIVE, r=-0.1375).

Vehicle (pre-registered, no fit): p_adj = p_model - 0.5*gap, gap = p_model -
kalshi_close_side, clamped to [0.02, 0.98]. Halfway to sharp. Gate: Brier
gain >= 0.0005 on the common subset (ledger settled, Kalshi-matched).
Same takes (no selection change) — Brier only, ROI descriptive.

Reads: ledger + kalshi k_closes/k_ladder. No live change.
Writes: artifacts/odds_log/kalshi_overlay_report.json.
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
OUT = REPO / "artifacts" / "odds_log" / "kalshi_overlay_report.json"

BETA = 0.5
MIN_TRADES = 20


def main() -> None:
    closes = pl.read_parquet(KAL / "k_closes.parquet").to_dicts()
    lad = pl.read_parquet(KAL / "k_ladder.parquet").select(
        ["market_ticker", "game_date", "player", "rung"]).to_dicts()
    lad_by_mkt = {r["market_ticker"]: r for r in lad}
    kf: dict[tuple, float] = {}
    for c in closes:
        m = lad_by_mkt.get(c["market_ticker"])
        if not m or int(c.get("n_trades") or 0) < MIN_TRADES:
            continue
        kf[(str(m["game_date"])[:10], _jk.sorted_key(m["player"]), int(m["rung"]))] = float(c["close_fair_over"])

    led = (pl.read_parquet(REPO / "artifacts" / "odds_log" / "ledger.parquet")
           .filter(pl.col("status") == "settled").to_dicts())
    se_b = se_o = 0.0
    n = 0
    cells: dict[str, dict] = {}
    for r in led:
        side = str(r.get("side") or "")
        if side not in ("over", "under"):
            continue
        try:
            line = float(r["line"])
        except (TypeError, ValueError):
            continue
        hit = kf.get((str(r["game_date"])[:10], _jk.sorted_key(r["player_name"]), math.floor(line) + 1))
        if hit is None:
            continue
        pm = float(r.get("p_model") or 0.0)
        if not 0.0 < pm < 1.0:
            continue
        try:
            sv = float(r["settle_value"])
        except (TypeError, ValueError):
            continue
        y_over = 1.0 if sv > line else 0.0
        p_side = pm if side == "over" else 1.0 - pm
        k_side = hit if side == "over" else 1.0 - hit
        y = y_over if side == "over" else 1.0 - y_over
        # Halfway to sharp in over-space, then map to side (same takes).
        p_over_adj = min(0.98, max(0.02, pm - BETA * (pm - hit)))
        p = p_over_adj if side == "over" else 1.0 - p_over_adj
        pb = p_side
        se_b += (pb - y) ** 2
        se_o += (p - y) ** 2
        n += 1
        cell = cells.setdefault(f"{side}@{line}", {"n": 0, "b": 0.0, "o": 0.0})
        cell["n"] += 1
        cell["b"] += (pb - y) ** 2
        cell["o"] += (p - y) ** 2

    gain = (se_b - se_o) / n if n else None
    rep = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "vehicle": f"p_adj = p - {BETA}*gap (halfway to sharp)", "n": n,
           "brier_base": round(se_b / n, 4) if n else None,
           "brier_overlay": round(se_o / n, 4) if n else None,
           "gain": round(gain, 5) if gain is not None else None,
           "cells": {c: {"n": v["n"], "base": round(v["b"] / v["n"], 4), "overlay": round(v["o"] / v["n"], 4)}
                     for c, v in sorted(cells.items()) if v["n"] >= 20},
           "kill": "SURVIVE (shadow proposal next)"
           if gain is not None and gain >= 0.0005 else "KILL (no Brier gain)"}
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
