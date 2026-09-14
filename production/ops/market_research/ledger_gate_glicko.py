"""Glicko overlay ledger gate (post hoc, research; backlog 2026-09-14 follow-up).

Same bettable panel + machinery as ledger_gate_kadj.py (#62, KILL). Per ticket:
  base    = Poisson + live WS1c-Platt from production k_rate (live-equivalent)
  overlay = same, but k_rate shrunk toward the league prior proportional to
            the pitcher's Glicko RD *as of that date* (no lookahead):
              w = min(1, RD / 0.03); kr = (1-w)*kr0 + w*league
            Wide-RD (young/declining/sparse) arms get pulled to league avg;
            narrow-RD workhorses pass through nearly untouched.
  book    = devigged consensus (2+ books) — context only, never the kill rule.

Glicko state is rebuilt from L3 with a strict as-of cutoff per ticket
(game_date < ticket date). Pre-registered vehicle (w form fixed here, no fit).

Writes artifacts/odds_log/ledger_gate_glicko_report.json. No live change.
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
from analyze_book_skill import build_consensus  # noqa: E402
from join_keys import ODDS_DIR, load_event_date_map, sorted_key  # noqa: E402

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
L3 = ROOT / "data" / "processed" / "pitcher_training.parquet"

PRIOR_PA = 300.0
RD_SCALE = 0.03  # pre-registered: w = min(1, RD / RD_SCALE)


def build_histories() -> tuple[dict, float]:
    """pitcher -> sorted [(game_date, K, PA)]; plus league K-rate."""
    rows = (
        pl.read_parquet(L3)
        .filter(pl.col("PA").is_not_null() & (pl.col("PA") > 0))
        .select(["game_date", "pitcher_name", "K", "PA"])
        .sort(["pitcher_name", "game_date"])
        .to_dicts()
    )
    league = sum(float(r["K"]) for r in rows) / max(1.0, sum(float(r["PA"]) for r in rows))
    hist: dict[str, list] = {}
    for r in rows:
        hist.setdefault(str(r["pitcher_name"]), []).append((r["game_date"], float(r["K"]), float(r["PA"])))
    return hist, league


def asof_rd(hist: dict, league: float, pitcher: str, gd) -> tuple[float, float]:
    """EB rating + RD using only starts strictly before gd (no lookahead)."""
    ks, ps = 0.0, 0.0
    for d, k, pa in hist.get(str(pitcher), []):
        if d < gd:
            ks += k
            ps += pa
        else:
            break
    eff = PRIOR_PA + ps
    r = (PRIOR_PA * league + ks) / eff
    rd = max(0.004, (league**0.5) / (eff**0.5))
    return r, rd


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    print(f"pre-registered vehicle: w=min(1,RD/{RD_SCALE}), kr=(1-w)*kr0+w*league")
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

    gr = pl.scan_parquet(SCORED).select(
        ["game_pk", "pitcher", "k_rate_pred", "projected_tbf"]).collect()
    # Join on (game_pk, pitcher): game_pk alone fans out (2 starters/game).
    j = j.join(gr, on=["game_pk", "pitcher"], how="left")
    jj = j.filter(pl.col("k_rate_pred").is_not_null()
                  & pl.col("projected_tbf").is_not_null()
                  & pl.col("line").is_in(LINES))
    print(f"gated panel: {jj.height}")
    hist, league = build_histories()
    print(f"league={league:.4f} pitchers={len(hist)}")

    bundle = joblib.load(CALIB)
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
    wide_n = 0
    for r in jj.to_dicts():
        ln = float(r["line"])
        y_over = 1.0 if float(r["settle_value"]) > ln else 0.0
        tbf = float(r["projected_tbf"])
        kr0 = float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5))
        _rg, rd = asof_rd(hist, league, str(r["pitcher"]), r["game_date"])
        w = min(1.0, rd / RD_SCALE)
        if w >= 0.5:
            wide_n += 1
        kr1 = float(np.clip((1.0 - w) * kr0 + w * league, 0.02, 0.5))
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
    gain = (se["base"] - se["overlay"]) / n if n else None
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": n,
           "vehicle": f"w=min(1,RD/{RD_SCALE})",
           "wide_RD_tickets": wide_n,
           "brier": {k: se[k] / nn[k] for k in se},
           "gain_overlay_vs_base": gain,
           "cells": {c: {"n": int(v["n"]),
                         **{k: v[k] / v["n"] for k in v if k != "n"}}
                     for c, v in sorted(cells.items())},
           "kill": "SURVIVE" if n and gain is not None and gain >= 0.0005 else "KILL"}
    out = ODDS_DIR / "ledger_gate_glicko_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"n={n} base={rep['brier'].get('base'):.4f} overlay={rep['brier'].get('overlay'):.4f} "
          f"book={rep['brier'].get('book'):.4f} gain={gain:+.5f} wide={wide_n}")
    for c, v in rep["cells"].items():
        if v["n"] >= 20:
            print(f"  {c} n={v['n']}: base={v['base']:.4f} overlay={v['overlay']:.4f} book={v['book']:.4f}")
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
