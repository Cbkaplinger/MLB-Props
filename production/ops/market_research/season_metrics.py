"""Season quant metrics on the juiced taken set (measurement, 2025 vs 2026).

Per season: ROI/WR/PnL, Sharpe/Sortino (daily PnL, sqrt(162)), max/current
drawdown (units of $50), Calmar, CLV mean + beat rate, mean taken edge
(xROI proxy), concentration (top line-side share). Same-data measurement --
2026 confirmatory, never a promotion input.

Reads: juiced_replay_candidates.parquet.
Writes: artifacts/odds_log/season_report.json.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[3]
CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
OUT = REPO / "artifacts" / "odds_log" / "season_report.json"
UNIT = 50.0
ANN = 162.0 ** 0.5


def season(rows: list[dict]) -> dict:
    n = len(rows)
    st = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pn = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    by_day: dict[str, float] = {}
    for r in rows:
        by_day[str(r["gd"])] = by_day.get(str(r["gd"]), 0.0) + float(r["pnl_flat1u"] or 0.0)
    daily = [by_day[d] for d in sorted(by_day)]
    m = sum(daily) / len(daily) if daily else 0.0
    var = sum((d - m) ** 2 for d in daily) / len(daily) if daily else 0.0
    sd = var ** 0.5
    down = [min(0.0, d) for d in daily]
    md = sum(d * d for d in down) / len(down) if down else 0.0
    dsd = md ** 0.5
    eq, peak, maxdd = 0.0, 0.0, 0.0
    for d in daily:
        eq += d / UNIT
        peak = max(peak, eq)
        maxdd = max(maxdd, peak - eq)
    clvs = [float(r["clv_pp"]) for r in rows if r.get("clv_pp") is not None and not r.get("close_invalid")]
    edges = [float(r["edge"] or 0.0) for r in rows]
    cells: dict[str, int] = {}
    for r in rows:
        cells[f"{r.get('side')}@{r.get('line')}"] = cells.get(f"{r.get('side')}@{r.get('line')}", 0) + 1
    top_cell = max(cells.values()) / n if n else 0.0
    return {
        "n": n, "days": len(daily),
        "roi": round(pn / st, 4) if st else None, "pnl": round(pn, 2),
        "wr": round(sum(1 for r in rows if r["won"]) / n, 3) if n else None,
        "sharpe": round(m / sd * ANN, 2) if sd else None,
        "sortino": round(m / dsd * ANN, 2) if dsd else None,
        "max_dd_u": round(maxdd, 1), "calmar_u": round((pn / UNIT) / maxdd, 2) if maxdd else None,
        "clv_n": len(clvs), "clv_mean_pp": round(sum(clvs) / len(clvs), 2) if clvs else None,
        "clv_beat_rate": round(sum(1 for c in clvs if c > 0) / len(clvs), 3) if clvs else None,
        "mean_edge_xroi": round(sum(edges) / len(edges), 4) if edges else None,
        "top_cell_conc": round(top_cell, 3),
    }


def main() -> None:
    taken = (pl.read_parquet(CAND)
             .filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"]))
             .to_dicts())
    rep = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "note": "2026 confirmatory -- measurement only",
           "2025": season([r for r in taken if str(r.get("yr")) == "2025"]),
           "2026": season([r for r in taken if str(r.get("yr")) == "2026"])}
    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
