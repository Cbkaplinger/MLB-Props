"""WS7 floor re-gating on MORNING numbers (chrono gate, post hoc research).

Edge vs morning consensus (the bettable number): over if
p_ours_cal - p_morn >= floor_over; under if mirrored edge >= floor_under.
Sweep asymmetric floors on TRAIN dates, confirm winner on TEST dates.
Metrics: n, WR, Brier, CLV (morning->close move in bet direction, pp).
Variants: plain + veto-overlay (exclude over 4.5, current live policy).

Writes artifacts/odds_log/ws7_floor_report.json. No live change.
Kill: no test confirm (WR/CLV) vs current policy proxy (veto-overlay @live floors).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel.parquet"
CUT = "2026-05-23"
OVER_FLOORS = [0.10, 0.12, 0.14, 0.16, 0.18, 0.20]
UNDER_FLOORS = [0.08, 0.10, 0.12, 0.14, 0.16]


def evaluate(df: pl.DataFrame, fo: float, fu: float, veto: bool) -> dict | None:
    rows = df.to_dicts()
    sel = []
    for r in rows:
        if r.get("p_ours_cal") is None or r.get("p_book_morning") is None:
            continue
        p, pm = float(r["p_ours_cal"]), float(r["p_book_morning"])
        y = float(r["y"])
        ln = float(r["line"])
        side = None
        if p - pm >= fo and not (veto and ln == 4.5):
            side = "over"  # veto kills 4.5 overs (live policy)
        elif (1 - p) - (1 - pm) >= fu:
            side = "under"
        if side is None:
            continue
        ps = p if side == "over" else 1 - p
        won = y if side == "over" else 1 - y
        clv = None
        if r.get("p_book_close") is not None:
            pc = float(r["p_book_close"])
            clv = (pc - pm) if side == "over" else ((1 - pc) - (1 - pm))
        sel.append((ps, won, clv))
    if len(sel) < 50:
        return None
    ps = np.array([s[0] for s in sel])
    w = np.array([s[1] for s in sel])
    cl = np.array([s[2] for s in sel if s[2] is not None])
    return {"n": len(sel), "wr": float(w.mean()),
            "brier": float(np.mean((ps - w) ** 2)),
            "clv_pp": float(cl.mean() * 100) if len(cl) else None,
            "clv_beat": float(np.mean(cl > 0)) if len(cl) else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    p = pl.read_parquet(PANEL).filter(
        pl.col("p_ours_cal").is_not_null() & pl.col("p_book_morning").is_not_null()).sort("gd")
    tr = p.filter(pl.col("gd") <= CUT)
    te = p.filter(pl.col("gd") > CUT)
    print(f"train {tr.height} / test {te.height} points")
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": CUT,
                 "train": [], "test": {}}
    for veto in (False, True):
        for fo, fu in itertools.product(OVER_FLOORS, UNDER_FLOORS):
            m = evaluate(tr, fo, fu, veto)
            if m:
                m.update({"fo": fo, "fu": fu, "veto": veto})
                rep["train"].append(m)
    # pick: max WR subject to n>=300 and clv_beat>=0.5, tie-break Brier
    cand = [m for m in rep["train"] if m["n"] >= 300 and (m["clv_beat"] or 0) >= 0.5]
    cand.sort(key=lambda m: (-m["wr"], m["brier"]))
    rep["pick"] = cand[0] if cand else None
    print("train top3:", json.dumps(sorted(rep["train"], key=lambda m: -m["wr"])[:3], indent=1))
    if rep["pick"]:
        pk = rep["pick"]
        t = evaluate(te, pk["fo"], pk["fu"], pk["veto"])
        rep["test"] = {"floors": pk, "metrics": t}
        base = evaluate(te, 0.12, 0.12, True)  # live-policy proxy
        rep["test"]["live_proxy"] = base
        print("PICK:", json.dumps(pk, indent=1))
        print("TEST:", json.dumps(t, indent=1))
        print("LIVE-PROXY:", json.dumps(base, indent=1))
        rep["kill"] = ("SURVIVE" if t and base and t["wr"] > base["wr"] and t["n"] >= 100
                       else "KILL")
    else:
        rep["kill"] = "KILL-no-candidate"
    out = ODDS_DIR / "ws7_floor_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
