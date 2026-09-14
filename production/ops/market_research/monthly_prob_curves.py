"""Monthly series + probability-curve cuts on the juiced taken set (descriptive).

A. Monthly: ROI/PnL/WR/CLV/xROI-edge per calendar month (thin months flagged,
   never cited alone). Answers "when does it win" for the paper's monthly view.
B. Probability curve: p_model deciles x side -> n/ROI/WR/emp-rate. Answers
   "do we do better on longshots or chalk, overs or unders" on the probability
   scale (complements the price-band cut, which is on the payout scale).

Same-data measurement; 2026 confirmatory. No live change.
Reads: juiced_replay_candidates.parquet.
Writes: monthly_report.json + probcurve_report.json (artifacts/odds_log).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT_M = REPO / "artifacts" / "odds_log" / "monthly_report.json"
OUT_P = REPO / "artifacts" / "odds_log" / "probcurve_report.json"


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    st = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pn = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    clvs = [float(r["clv_pp"]) for r in rows if r.get("clv_pp") is not None and not r.get("close_invalid")]
    edges = [float(r["edge"] or 0.0) for r in rows]
    return {"n": n, "roi": round(pn / st, 4) if st else None, "pnl": round(pn, 2),
            "wr": round(sum(1 for r in rows if r["won"]) / n, 3) if n else None,
            "clv_mean_pp": round(sum(clvs) / len(clvs), 2) if clvs else None,
            "xroi_edge": round(sum(edges) / len(edges), 4) if edges else None,
            "thin": n < 100}


def main() -> None:
    taken = (pl.read_parquet(CAND)
             .filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"]))
             .with_columns(pl.col("gd").str.slice(0, 7).alias("month"),
                           (pl.col("p_ours_cal") * 10).floor().alias("pdec"))
             .to_dicts())
    months: dict[str, list] = {}
    for r in taken:
        months.setdefault(r["month"], []).append(r)
    rep_m = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "note": "thin months (n<100) flagged, never cited alone",
             "months": {m: stats(v) for m, v in sorted(months.items())}}
    OUT_M.write_text(json.dumps(rep_m, indent=2))

    cells: dict[str, list] = {}
    for r in taken:
        try:
            p = float(r["p_ours_cal"])
        except (TypeError, ValueError):
            continue
        lo = int(p * 10) * 10
        cells.setdefault(f"{r['side']}|p{lo}-{lo + 10}", []).append({**r, "_p": p})
    rep_p = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "cells": {}}
    for name in sorted(cells, key=lambda k: (k.split("|")[0], k)):
        v = cells[name]
        s = stats(v)
        s["n"] = len(v)
        rep_p["cells"][name] = s
    OUT_P.write_text(json.dumps(rep_p, indent=2))
    print("months:")
    for m, s in rep_m["months"].items():
        print(f"  {m} n={s['n']} ROI={s['roi']} PnL={s['pnl']} CLV={s['clv_mean_pp']}{' THIN' if s['thin'] else ''}")
    print("prob curve:")
    for name, s in rep_p["cells"].items():
        print(f"  {name} n={s['n']} ROI={s['roi']} WR={s['wr']}")


if __name__ == "__main__":
    main()
