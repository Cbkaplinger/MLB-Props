"""Stacker overlay ledger gate (post hoc, research; backlog #73 follow-up).

Confirms the distill-stacker vehicle on the BETTABLE panel (settled paper
tickets with 2+ book closes AND 2+ book mornings), per SOP gate discipline.
Per ticket, taken side:
  base    = Poisson + live WS1c-Platt from production k_rate (live-equivalent,
            same recomputation as the kadj gate #62)
  stacker = expit(b0 + b1*logit(base_over) + b2*logit(morn_over) + b3*line)
            with coefs PRE-REGISTERED from distill_stacker_report.json
            (frozen universe fit — this gate tests cross-config transfer:
            coefs fit on isotonic-era universe probs, applied to live-equiv
            ledger probs)
  book    = 2+ devigged consensus close - context only, never the kill rule

Joins read consensus_cache (SOP: never re-devig); n_books >= 2 both snaps
(ledger panels use 2+, per #51). Join on (game_pk, pitcher) for scores
(game_pk alone fans out — #62 lesson); cells sum to n.

Writes artifacts/odds_log/ledger_gate_stacker_report.json. No live change.
Gate: stacker beats base by >= 0.0005 on the common subset.
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
from Python.prob_calibration import ProbCalibrationBundle  # noqa: E402
from join_keys import ODDS_DIR, read_consensus_cache, sorted_key  # noqa: E402

LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
STACK_REP = ODDS_DIR / "distill_stacker_report.json"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
EPS = 1e-4


def logit(p: float) -> float:
    pc = min(max(p, EPS), 1.0 - EPS)
    return float(np.log(pc / (1.0 - pc)))


def expit(z: float) -> float:
    return float(1.0 / (1.0 + np.exp(-z)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    coef = json.loads(STACK_REP.read_text(encoding="utf-8"))["coef"]
    b0, b1, b2, b3 = coef["b0"], coef["b1_model"], coef["b2_morn"], coef["b3_line"]
    print(f"pre-registered coef: b0={b0:.4f} b1={b1:.4f} b2={b2:.4f} b3={b3:.4f}")

    cc = read_consensus_cache("pitcher_strikeouts", "close").filter(
        (pl.col("n_books") >= 2) & pl.col("fair").is_not_null())
    cm = read_consensus_cache("pitcher_strikeouts", "morning").filter(
        (pl.col("n_books") >= 2) & pl.col("fair").is_not_null())
    led = pl.read_parquet(ODDS_DIR / "ledger.parquet").filter(
        (pl.col("status") == "settled") & pl.col("settle_value").is_not_null()).with_columns(
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10).alias("gd"),
        pl.col("player_name").map_elements(
            lambda s: sorted_key(str(s)), return_dtype=pl.Utf8).alias("key"))
    # Ledger carries its own nullable close_* columns (watcher coverage gaps);
    # drop them so the joined consensus names are unambiguous (no _right trap).
    led = led.drop([c for c in ("close_over", "close_under", "close_status",
                                "closed_at_utc", "minutes_to_tip_at_close")
                    if c in led.columns])
    j = led.join(cc.select(["gd", "key", "line", "fair"]).rename({"fair": "close_over"}),
                 on=["gd", "key", "line"], how="inner")
    print(f"ledger-close join: {j.height}")
    j = j.join(cm.select(["gd", "key", "line", "fair"]).rename({"fair": "morn_over"}),
               on=["gd", "key", "line"], how="inner")
    print(f"+morning join: {j.height}")

    gr = pl.scan_parquet(SCORED).select(
        ["game_pk", "pitcher", "k_rate_pred", "projected_tbf"]).collect()
    j = j.join(gr, on=["game_pk", "pitcher"], how="left")
    jj = j.filter(pl.col("k_rate_pred").is_not_null()
                  & pl.col("projected_tbf").is_not_null()
                  & pl.col("line").is_in(LINES))
    print(f"gated panel: {jj.height}")

    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}

    def base_over(kr: float, tbf: float, ln: float) -> float:
        raw = float(p_strikeouts_ge(ln, k_rate=np.array([kr]),
                                    projected_tbf=np.array([tbf]), family="poisson")[0])
        return float(maps[ln].transform(np.array([raw]))[0])

    se: dict[str, float] = {}
    nn: dict[str, int] = {}
    cells: dict[str, dict[str, float]] = {}
    for r in jj.to_dicts():
        ln = float(r["line"])
        y_over = 1.0 if float(r["settle_value"]) > ln else 0.0
        kr = float(np.clip(float(r["k_rate_pred"]), 0.02, 0.5))
        tbf = float(r["projected_tbf"])
        bo = base_over(kr, tbf, ln)
        so = expit(b0 + b1 * logit(bo) + b2 * logit(float(r["morn_over"])) + b3 * ln)
        co = float(r["close_over"])
        cands = {"base": bo, "stacker": so, "book": co}
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
    gain = (se["base"] - se["stacker"]) / n if n else None
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(), "n": n,
           "coef": coef,
           "transfer_note": ("coefs fit on isotonic-era universe probs, applied to "
                             "live-equiv (Poisson+WS1c) ledger probs - transfer by design"),
           "brier": {k: se[k] / nn[k] for k in se},
           "gain_stacker_vs_base": gain,
           "cells": {c: {"n": int(v["n"]),
                         **{k: v[k] / v["n"] for k in v if k != "n"}}
                     for c, v in sorted(cells.items())},
           "cells_sum_n": int(sum(v["n"] for v in cells.values())),
           "kill": "SURVIVE" if n and gain is not None and gain >= 0.0005 else "KILL"}
    out = ODDS_DIR / "ledger_gate_stacker_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"n={n} base={rep['brier'].get('base'):.4f} stacker={rep['brier'].get('stacker'):.4f} "
          f"book={rep['brier'].get('book'):.4f} gain={gain:+.5f}" if gain is not None else f"n={n}")
    for c, v in rep["cells"].items():
        if v["n"] >= 20:
            print(f"  {c} n={v['n']}: base={v['base']:.4f} stacker={v['stacker']:.4f} book={v['book']:.4f}")
    print(f"cells_sum_n={rep['cells_sum_n']} (must equal n={n})")
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
