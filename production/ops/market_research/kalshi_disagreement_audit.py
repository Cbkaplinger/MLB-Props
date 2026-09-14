"""Kalshi-disagreement filter audit (measurement, pre-registered vehicle).

Cheapest unbuilt edge: refuse taken tickets where the sharp anchor (Kalshi
close-anchored fair, NOT settled ladder prices — those are post-game
converged, Brier ~0.06 lookahead trap) disagrees hard with our model.

Vehicle (fixed here, no fit): refuse if |p_model_side - kalshi_side| > 0.10,
rung volume via n_trades >= 20. Kill: kept ROI <= full ROI OR kept n < 100.
Descriptive; a SURVIVE needs a live-machinery proposal (Kalshi at board time).

Reads: kalshi k_closes + k_ladder parquet, settled ledger.
Writes: artifacts/odds_log/kalshi_disagreement_report.json.
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
OUT = REPO / "artifacts" / "odds_log" / "kalshi_disagreement_report.json"

DISAGREE_CUT = 0.10
MIN_TRADES = 20


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    st = sum(float(r["stake"] or 0.0) for r in rows)
    pn = sum(float(r["pnl"] or 0.0) for r in rows)
    # WR only over decided staked rows (stake>0, pnl!=0): HOLD/skip rows
    # (stake 0) and voids (pnl 0) are not wins or losses.
    dec = [r for r in rows if float(r["stake"] or 0.0) > 0 and float(r["pnl"] or 0.0) != 0]
    return {"n": n, "roi": round(pn / st, 4) if st else None, "pnl": round(pn, 2),
            "wr": round(sum(1 for r in dec if float(r["pnl"]) > 0) / len(dec), 3) if dec else None,
            "n_decided": len(dec)}


def main() -> None:
    closes = pl.read_parquet(KAL / "k_closes.parquet").to_dicts()
    lad = pl.read_parquet(KAL / "k_ladder.parquet").select(
        ["market_ticker", "game_date", "player", "rung"]).to_dicts()
    lad_by_mkt = {r["market_ticker"]: r for r in lad}
    # (gd, skey, rung) -> close-anchored fair P(over rung)
    kf: dict[tuple, tuple[float, int]] = {}
    for c in closes:
        m = lad_by_mkt.get(c["market_ticker"])
        if not m or int(c.get("n_trades") or 0) < MIN_TRADES:
            continue
        kf[(str(m["game_date"])[:10], _jk.sorted_key(m["player"]), int(m["rung"]))] = (
            float(c["close_fair_over"]), int(c["n_trades"]))

    led = (pl.read_parquet(REPO / "artifacts" / "odds_log" / "ledger.parquet")
           .filter(pl.col("status") == "settled").to_dicts())
    matched, rows = 0, []
    for r in led:
        side = str(r.get("side") or "")
        if side not in ("over", "under"):
            continue
        try:
            line = float(r["line"])
        except (TypeError, ValueError):
            continue
        key = (str(r["game_date"])[:10], _jk.sorted_key(r["player_name"]), math.floor(line) + 1)
        hit = kf.get(key)
        if hit is None:
            continue
        k_over, nt = hit
        pm = float(r.get("p_model") or 0.0)
        if not 0.0 < pm < 1.0:
            continue
        k_side = k_over if side == "over" else 1.0 - k_over
        p_side = pm if side == "over" else 1.0 - pm
        matched += 1
        rows.append({**r, "kalshi_side": k_side, "disagree": abs(p_side - k_side)})

    kept = [r for r in rows if r["disagree"] <= DISAGREE_CUT]
    refused = [r for r in rows if r["disagree"] > DISAGREE_CUT]
    full, k, f = stats(rows), stats(kept), stats(refused)
    rep = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "vehicle": f"refuse |p_model-kalshi| > {DISAGREE_CUT}, n_trades >= {MIN_TRADES}",
        "matched_tickets": matched,
        "full": full, "kept": k, "refused": f,
        "roi_delta_kept_minus_full": round(k["roi"] - full["roi"], 4)
        if k["roi"] is not None and full["roi"] is not None else None,
        "kill": "SURVIVE (needs live-machinery proposal)"
        if k["roi"] is not None and full["roi"] is not None and k["roi"] > full["roi"] and k["n"] >= 100
        else "KILL (no gain or too thin for a live input)",
    }
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
