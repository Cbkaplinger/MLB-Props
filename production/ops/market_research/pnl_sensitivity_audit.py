"""Max-PnL sensitivity audit (measurement only, labeled same-data).

Answers, on the juiced taken set (n=2,077, 2025+2026):
  1. Floor grid: PnL/ROI/n at uniform floors 0.05..0.24 (upward from the
     live base; lowering below live floors is unmeasurable — rejects lack
     fillable pnl, reported as unmeasurable, not zero).
  2. Single-slip rule: top-1-edge-per-day PnL/ROI/n (owner fires ~1 slip/day).
  3. Edge-band dollars (not just ROI): where the PnL mass lives.
  4. TBF-tail ROI via historical_scores projected_tbf join (marathon/hook
     bands); drop-tail vehicle delta for the policy-side fix.

Same-data measurement: describes this set, never a promotion license.
Writes artifacts/odds_log/pnl_sensitivity_report.json.
"""

from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
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

CAND = REPO / "artifacts" / "odds_log" / "juiced_replay_candidates.parquet"
SCORES = REPO / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
OUT = REPO / "artifacts" / "odds_log" / "pnl_sensitivity_report.json"


def stats(rows: list[dict]) -> dict:
    n = len(rows)
    st = sum(float(r["stake_flat1u"] or 0.0) for r in rows)
    pn = sum(float(r["pnl_flat1u"] or 0.0) for r in rows)
    return {"n": n, "roi": round(pn / st, 4) if st else None, "pnl": round(pn, 2),
            "wr": round(sum(1 for r in rows if r["won"]) / n, 3) if n else None}


def main() -> None:
    taken = (
        pl.read_parquet(CAND)
        .filter(pl.col("accepted") & pl.col("side").is_in(["over", "under"]))
        .to_dicts()
    )
    rep: dict = {"built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 "taken_n": len(taken), "overall": stats(taken)}

    # 1. Floor grid (upward only — see docstring).
    grid = {}
    for f in (0.05, 0.08, 0.10, 0.12, 0.14, 0.16, 0.18, 0.20, 0.24):
        grid[f"{f:.2f}"] = stats([r for r in taken if float(r["edge"] or 0.0) >= f])
    grid["note"] = ("Upward-only: taken set already passed live floors; lowering "
                    "floors needs rejected-row outcomes at fillable prices (unmeasured).")
    rep["floor_grid"] = grid

    # 2. Single-slip: top-1 edge per calendar day.
    by_day: dict[str, list] = {}
    for r in taken:
        by_day.setdefault(str(r["gd"]), []).append(r)
    top1 = [max(v, key=lambda r: float(r["edge"] or 0.0)) for v in by_day.values()]
    rep["single_slip_top1_per_day"] = {**stats(top1), "days": len(by_day)}

    # 3. Edge-band dollars.
    bands: dict[str, list] = {}
    for r in taken:
        e = float(r["edge"] or 0.0)
        b = "0.08-0.12" if e < 0.12 else ("0.12-0.18" if e < 0.18 else ("0.18-0.24" if e < 0.24 else "0.24+"))
        bands.setdefault(b, []).append(r)
    rep["edge_band_dollars"] = {b: stats(v) for b, v in sorted(bands.items())}

    # 4. TBF tails via historical_scores join on (gd, sorted name).
    sc = pl.read_parquet(SCORES).select(["game_date", "player_name", "projected_tbf"]).to_dicts()
    tbf_index: dict[tuple, float] = {}
    for r in sc:
        try:
            tbf_index[(str(r["game_date"])[:10], _jk.sorted_key(r["player_name"]))] = float(r["projected_tbf"])
        except (TypeError, ValueError):
            continue
    bands4: dict[str, list] = {"hook(<18)": [], "mid(18-24)": [], "workhorse(24-28)": [], "marathon(28+)": []}
    unmapped = 0
    for r in taken:
        t = tbf_index.get((str(r["gd"]), _jk.sorted_key(r["player_name"])))
        if t is None:
            unmapped += 1
            continue
        if t < 18:
            bands4["hook(<18)"].append(r)
        elif t < 24:
            bands4["mid(18-24)"].append(r)
        elif t < 28:
            bands4["workhorse(24-28)"].append(r)
        else:
            bands4["marathon(28+)"].append(r)
    rep["tbf_bands"] = {b: stats(v) for b, v in bands4.items()}
    rep["tbf_unmapped"] = unmapped
    keep = bands4["mid(18-24)"] + bands4["workhorse(24-28)"]
    drop = bands4["hook(<18)"] + bands4["marathon(28+)"]
    rep["tbf_drop_tails_vehicle"] = {"keep": stats(keep), "dropped": stats(drop),
        "roi_delta_keep_minus_full": round(stats(keep)["roi"] - stats(taken)["roi"], 4)}

    OUT.write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
