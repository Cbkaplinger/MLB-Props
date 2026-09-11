"""Calibration cells: ECE/MCE/bias per line x arm + xK bins (post hoc).

Answers: did the ships fix calibration (ECE/MCE), where do we still trail
books, and is there ANY pocket where we beat them. Same common-subset
close-matched panel as rescore_shiplift (frozen vs live vs book).
MEASUREMENT ONLY (#81): no kill, evidence for the gap-closing plan.

Writes artifacts/odds_log/rescore_cal_report.json. No live change.
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
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

FROZEN = ODDS_DIR / "universe_panel.parquet"
LIVE = ODDS_DIR / "universe_panel_live.parquet"
ARMS = ["p_frozen", "p_live", "p_book"]


def ece_mce(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    ece, bins = expected_calibration_error(y, p)
    gaps = [float(b["gap"]) for b in bins
            if b.get("n", 0) and b.get("gap") == b.get("gap")]
    return float(ece), float(max(gaps)) if gaps else float("nan")


def cell(y: np.ndarray, pf: np.ndarray, plv: np.ndarray, pb: np.ndarray) -> dict:
    outs = {}
    for name, p in (("frozen", pf), ("live", plv), ("book", pb)):
        e, m = ece_mce(y, p)
        outs[name] = {"n": int(len(y)), "brier": float(np.mean((p - y) ** 2)),
                      "ece": e, "mce": m, "bias_pp": float(np.mean(p - y) * 100)}
    outs["shiplift"] = outs["frozen"]["brier"] - outs["live"]["brier"]
    outs["skill_live_vs_book"] = outs["book"]["brier"] - outs["live"]["brier"]
    return outs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    fz = pl.read_parquet(FROZEN).select(
        ["gd", "key", "line", "y", "expected_K", "p_ours_cal", "p_book_close"])
    lv = pl.read_parquet(LIVE).select(["gd", "key", "line", "p_ours_cal"])
    jm = fz.join(lv, on=["gd", "key", "line"], how="inner",
                 suffix="_live").filter(
        pl.col("p_ours_cal").is_not_null()
        & pl.col("p_ours_cal_live").is_not_null()
        & pl.col("p_book_close").is_not_null()
        & pl.col("y").is_not_null())
    print(f"close-matched common n={jm.height}")
    y = jm["y"].to_numpy().astype(float)
    pf = jm["p_ours_cal"].to_numpy().astype(float)
    plv = jm["p_ours_cal_live"].to_numpy().astype(float)
    pb = jm["p_book_close"].to_numpy().astype(float)
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "n": int(jm.height), "pooled": cell(y, pf, plv, pb)}
    lines = []
    for ln in sorted(set(jm["line"].to_list())):
        sub = jm.filter(pl.col("line") == ln)
        yy = sub["y"].to_numpy().astype(float)
        lines.append({"line": float(ln),
                      **cell(yy, sub["p_ours_cal"].to_numpy().astype(float),
                             sub["p_ours_cal_live"].to_numpy().astype(float),
                             sub["p_book_close"].to_numpy().astype(float))})
    rep["per_line"] = lines
    xk = jm["expected_K"].to_numpy().astype(float)
    bins = []
    for name, lo, hi in (("low_xK_lt4", -99, 4.0), ("mid_xK_4_6", 4.0, 6.0),
                         ("high_xK_gt6", 6.0, 999)):
        idx = np.where((xk >= lo) & (xk < hi))[0] if lo != -99 else np.where(xk < hi)[0]
        if len(idx) < 100:
            continue
        bins.append({"bin": name, **cell(y[idx], pf[idx], plv[idx], pb[idx])})
    rep["per_xk"] = bins
    pockets = [c["line"] for c in lines if c["skill_live_vs_book"] > 0]
    rep["pockets_live_beats_book"] = pockets
    out = ODDS_DIR / "rescore_cal_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps({"n": rep["n"], "pooled": rep["pooled"],
                      "per_xk": rep["per_xk"],
                      "pockets": pockets}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
