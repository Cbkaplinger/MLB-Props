"""Legacy re-gates at universe scale (shadow research, no live change).

Re-measures each live support-rule gate on the CURRENT full panel and
revisits thin cells. Economics panel: juiced_replay_candidates.parquet
(side/price/won/accepted carry the live filter verdict per row), enriched
with gate fields (days_rest, projected_tbf, opp_lineup_k_vs_hand) joined
from historical_scores on (gd, key). The "same subset" for every
gated-vs-ungated comparison is the live-taken set (accepted == True).

Gates re-measured (all read-only; nothing live is touched):
  matchup_block   live blocks avg+favorable tiers (qcut 3 on
                  opp_lineup_k_vs_hand). Research approx: GLOBAL tercile
                  cut (live cuts per slate) -- direction check only.
  under_long_rest live blocks under & days_rest >= 10
  any_long_rest   live blocks any side & days_rest >= 10
  low_tbf         live blocks projected_tbf < 15
  deploy_matrix   measurement lives in deploy_regate_report.json
                  (bettable-panel Brier re-derive); summarized here.
  cell_gate_2025  display-only take/drop lists from
                  line_cell_gate_2025.json, scored on the taken set.

Cells revisited on the taken set: 2.5-over, 2.5-under, 3.5-under,
9.5-over, 9.5-under, 9.5 combined.

Per-gate verdicts:
  KEEP           blocking helps (gated ROI < ungated ROI), gated n >= 100
  DROP-data-says blocking hurts (gated ROI >= ungated ROI), gated n >= 100
  THIN-n         gated n < 100 (ROI unstable -- hold, do not act)

Writes artifacts/odds_log/legacy_regate_report.json. No live change.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

CANDIDATES = ODDS_DIR / "juiced_replay_candidates.parquet"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
CELL_GATE = Path(__file__).with_name("line_cell_gate_2025.json")
DEPLOY_REP = ODDS_DIR / "deploy_regate_report.json"
UNIT = 50.0
THIN_N = 100


def taken_stats(t: pl.DataFrame) -> dict:
    n = len(t)
    if n == 0:
        return {"n": 0, "roi": None, "pnl": 0.0, "wr": None}
    pnl = float(t["pnl_flat1u"].sum())
    return {"n": n, "roi": round(pnl / (UNIT * n), 4),
            "pnl": round(pnl, 2),
            "wr": round(float(t["won"].mean()), 4)}


def gate_verdict(gated: dict, ungated: dict) -> str:
    if gated["n"] < THIN_N:
        return "THIN-n"
    if gated["roi"] is None or ungated["roi"] is None:
        return "THIN-n"
    return "KEEP" if gated["roi"] < ungated["roi"] else "DROP-data-says"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    cand = pl.read_parquet(CANDIDATES)
    print(f"candidates: {len(cand)} rows, taken={cand.filter(pl.col('accepted')).height}")
    sc = (pl.scan_parquet(SCORED)
          .select(["game_date", "key_sorted", "days_rest",
                   "projected_tbf", "opp_lineup_k_vs_hand"])
          .collect()
          .with_columns(
              pl.col("game_date").cast(pl.Date).cast(pl.Utf8).alias("gd"),
              pl.col("key_sorted").alias("key")))
    j = cand.join(sc.select(["gd", "key", "days_rest", "projected_tbf",
                             "opp_lineup_k_vs_hand"]),
                  on=["gd", "key"], how="left")
    taken = j.filter(pl.col("accepted"))
    print(f"taken rows: {len(taken)}, with gate fields: "
          f"{taken.filter(pl.col('days_rest').is_not_null()).height}")

    g = taken.filter(pl.col("opp_lineup_k_vs_hand").is_not_null())
    lo = float(g["opp_lineup_k_vs_hand"].quantile(1 / 3))
    hi = float(g["opp_lineup_k_vs_hand"].quantile(2 / 3))
    taken = taken.with_columns(
        pl.when(pl.col("opp_lineup_k_vs_hand").is_null())
        .then(pl.lit(None))
        .when(pl.col("opp_lineup_k_vs_hand") <= lo)
        .then(pl.lit("weak_matchup"))
        .when(pl.col("opp_lineup_k_vs_hand") <= hi)
        .then(pl.lit("avg_matchup"))
        .otherwise(pl.lit("favorable_matchup"))
        .alias("matchup_tier"))
    print(f"matchup tercile cuts: lo={lo:.4f} hi={hi:.4f} "
          f"(global approx; live cuts per slate)")

    gates: dict[str, dict] = {}

    def score_gate(name: str, gated_mask: pl.Expr, note: str = "") -> None:
        gated = taken.filter(gated_mask)
        ungated = taken.filter(~gated_mask)
        gs, us = taken_stats(gated), taken_stats(ungated)
        gates[name] = {"gated": gs, "ungated": us,
                       "verdict": gate_verdict(gs, us), "note": note}

    score_gate("matchup_block",
               pl.col("matchup_tier").is_in(["avg_matchup", "favorable_matchup"]),
               "global-tercile approx; live tiers cut per slate")
    score_gate("under_long_rest",
               (pl.col("side") == "under") & (pl.col("days_rest") >= 10))
    score_gate("any_long_rest", pl.col("days_rest") >= 10)
    score_gate("low_tbf", pl.col("projected_tbf") < 15)

    cell_gate = json.loads(CELL_GATE.read_text(encoding="utf-8"))
    take_set = set(cell_gate.get("take", []))
    drop_set = set(cell_gate.get("drop", []))
    taken = taken.with_columns(
        (pl.col("side") + "@" + pl.col("line").cast(pl.Utf8)).alias("cell"))
    take_rows = taken.filter(pl.col("cell").is_in(sorted(take_set)))
    drop_rows = taken.filter(pl.col("cell").is_in(sorted(drop_set)))
    gs, ds = taken_stats(take_rows), taken_stats(drop_rows)
    gates["cell_gate_2025"] = {
        "gated": {"n": ds["n"], "roi": ds["roi"], "pnl": ds["pnl"],
                  "wr": ds["wr"],
                  "note": "drop-list cells = would-block"},
        "ungated": {"n": gs["n"], "roi": gs["roi"], "pnl": gs["pnl"],
                    "wr": gs["wr"],
                    "note": "take-list cells = would-pass"},
        "verdict": gate_verdict(
            {"n": ds["n"], "roi": ds["roi"]},
            {"n": gs["n"], "roi": gs["roi"]}),
        "note": "display-only gate; DROP-data-says = drop list out-earns take list",
    }

    cells: dict[str, dict] = {}
    for cell in ["over@2.5", "under@2.5", "under@3.5",
                 "over@9.5", "under@9.5"]:
        parts = cell.split("@")
        sub = taken.filter((pl.col("side") == parts[0])
                           & (pl.col("line").round(1) == float(parts[1])))
        cells[cell] = taken_stats(sub)
    sub95 = taken.filter(pl.col("line").round(1) == 9.5)
    cells["all@9.5"] = taken_stats(sub95)

    dep: dict = {}
    if DEPLOY_REP.exists():
        d = json.loads(DEPLOY_REP.read_text(encoding="utf-8"))
        dep = {"n": d.get("n"), "rated_segments": d.get("rated_segments"),
               "recommend_on": d.get("recommend_on"),
               "recommend_off": d.get("recommend_off"),
               "unrated_thin": d.get("unrated_thin"),
               "flips_vs_current": d.get("flips_vs_current"),
               "verdict": ("KEEP" if (d.get("recommend_off") or 0) > 0
                           else "THIN-n"),
               "note": ("from deploy_regate_report.json (bettable panel, "
                        "Brier re-derive); acting needs sign-off")}
    else:
        dep = {"verdict": "THIN-n",
               "note": "deploy_regate_report.json absent -- run deploy_regate.py"}
    gates["deploy_matrix"] = {
        "gated": {"n": None, "roi": None, "summary": dep},
        "ungated": {"n": None, "roi": None},
        "verdict": dep["verdict"], "note": dep["note"]}

    rep = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "contract": ("juiced candidates taken set as the common subset; "
                     "gate fields joined from historical_scores on "
                     "(gd, key); flat $50 via pnl_flat1u"),
        "n_candidates": len(cand),
        "n_taken": len(taken),
        "n_taken_with_gates": int(
            taken.filter(pl.col("days_rest").is_not_null()).height),
        "matchup_cuts": {"lo": lo, "hi": hi},
        "gates": gates,
        "cells_revisit": cells,
        "verdict_rule": (f"KEEP iff gated ROI < ungated ROI with gated "
                         f"n>={THIN_N}; DROP-data-says iff gated ROI >= "
                         f"ungated ROI with gated n>={THIN_N}; else THIN-n"),
    }
    out = ODDS_DIR / "legacy_regate_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    for name, gv in gates.items():
        g_, u_ = gv["gated"], gv["ungated"]
        print(f"{name}: gated n={g_.get('n')} roi={g_.get('roi')} vs "
              f"ungated n={u_.get('n')} roi={u_.get('roi')} "
              f"-> {gv['verdict']}")
    for cell, st in cells.items():
        print(f"cell {cell}: n={st['n']} roi={st['roi']} wr={st['wr']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
