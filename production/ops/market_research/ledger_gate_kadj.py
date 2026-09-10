"""kAdj overlay ledger gate (post hoc, research; backlog #61 follow-up).

Confirms the WS8 beta-overlay vehicle on the BETTABLE panel (settled paper
tickets with book closes), per SOP gate discipline. Per ticket, taken side:
  base    = Poisson + live WS1c-Platt from production k_rate (live-equivalent)
  overlay = Poisson + live WS1c-Platt from beta-adjusted k_rate
            (k_rate + beta*kadj, beta=0.4938 pre-registered from ws8 train fit)
  book    = devigged consensus (2+ books) — context only, never the kill rule

kadj comes from the pipeline join on ledger keys (game_pk, pitcher,
game_date) — same algorithm as the probe. Common-subset Brier decides.
Includes side×line cells (veto-line interaction: does the overlay touch
the 4.5-over bleed or the under pockets?).

Writes artifacts/odds_log/ledger_gate_kadj_report.json. No live change.
Gate: overlay beats base by >= 0.0005 on the common subset.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.count_layer import p_strikeouts_ge  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.pipeline.training import _join_kadj_features  # noqa: E402
from Python.prob_calibration import ProbCalibrationBundle  # noqa: E402
from analyze_book_skill import build_consensus  # noqa: E402
from join_keys import ODDS_DIR, load_event_date_map, sorted_key  # noqa: E402

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
WS8_REP = ODDS_DIR / "ws8_kadj_report.json"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    beta = float(json.loads(WS8_REP.read_text(encoding="utf-8"))["fit"]["beta"])
    print(f"pre-registered beta={beta:.4f}")
    evdate = load_event_date_map()
    cons = build_consensus(2).with_columns(
        pl.col("event_id").map_elements(lambda e: evdate.get(e, ""), return_dtype=pl.Utf8).alias("gd"),
        pl.col("player_norm").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key"))
    led = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled") & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(
            lambda s: sorted_key(str(s)), return_dtype=pl.Utf8).alias("key"))
    j = led.join(cons, on=["gd", "key", "line"], how="inner")
    print(f"ledger-consensus join: {j.height}")

    kj = _join_kadj_features(
        j.select(["game_pk", "pitcher", "game_date"]).unique(maintain_order=True))
    j = j.join(kj.select(["game_pk", "pitcher", "kadj"]),
               on=["game_pk", "pitcher"], how="left")
    gr = pl.scan_parquet(SCORED).select(
        ["game_pk", "pitcher", "k_rate_pred", "projected_tbf"]).collect()
    # Join on (game_pk, pitcher): game_pk alone fans out (2 starters/game).
    j = j.join(gr, on=["game_pk", "pitcher"], how="left")
    jj = j.filter(pl.col("k_rate_pred").is_not_null()
                  & pl.col("projected_tbf").is_not_null()
                  & pl.col("kadj").is_not_null()
                  & pl.col("line").is_in(LINES))
    print(f"gated panel: {jj.height} (kadj coverage on joined tickets)")

    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def cal(kr: float, tbf: float, ln: float) -> float:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]), family="poisson")[0])
        return float(maps[ln].transform(np.array([raw]))[0])

    se: dict[str, float] = {}
    nn: dict[str, int] = {}
    cells: dict[str, dict[str, float]] = {}
    for r in jj.to_dicts():
        ln = float(r["line"])
        y_over = 1.0 if float(r["settle_value"]) > ln else 0.0
        tbf = float(r["projected_tbf"])
        kr0 = float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5))
        kr1 = float(np.clip(float(r["k_rate_pred"]) + beta * float(r["kadj"]), 0.02, 0.5))
        co = float(r["consensus_over"])
        cands = {"base": cal(kr0, tbf, ln), "overlay": cal(kr1, tbf, ln), "book": co}
        side = str(r["side"])
        cell = cells.setdefault(f"{side}@{ln}", {})
        cell["n"] = cell.get("n", 0) + 1
        for k, p_over in cands.items():
            p = p_over if side == "over" else 1.0 - p_over
            y = y_over if side == "over" else 1.0 - y_over
            se[k] = se.get(k, 0.0) + (p - y) ** 2
            nn[k] = nn.get(k, 0) + 1
            cell[k] = cell.get(k, 0.0) + (p - y) ** 2
    n = nn.get("base", 0)
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": n,
           "beta": beta,
           "brier": {k: se[k] / nn[k] for k in se},
           "gain_overlay_vs_base": (se["base"] - se["overlay"]) / n if n else None,
           "cells": {c: {"n": int(v["n"]),
                         **{k: v[k] / v["n"] for k in v if k != "n"}}
                     for c, v in sorted(cells.items())},
           "kill": "SURVIVE" if n and (se["base"] - se["overlay"]) / n >= 0.0005 else "KILL"}
    out = ODDS_DIR / "ledger_gate_kadj_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"n={n} base={rep['brier'].get('base'):.4f} overlay={rep['brier'].get('overlay'):.4f} "
          f"book={rep['brier'].get('book'):.4f} gain={rep['gain_overlay_vs_base']:+.5f}")
    for c, v in rep["cells"].items():
        if v["n"] >= 20:
            print(f"  {c} n={v['n']}: base={v['base']:.4f} overlay={v['overlay']:.4f} book={v['book']:.4f}")
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
