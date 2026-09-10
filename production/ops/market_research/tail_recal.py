"""Tail-line calibration check (post hoc, research; backlog #67).

Live WS1c per-line Platt maps cover 8 lines, but 8.5/9.5 were NEVER held-out
tested (thin on the main-close join). The panel itself carries ~8.7k points
per line (y + p_ours need no book match), so test them directly.

Per line in 6.5/7.5/8.5/9.5, chrono split (CUT=2026-05-23, same as WS1c):
  raw   = model Poisson probs (p_ours)
  live  = production WS1c bundle maps (what tomorrow's board uses)
  refit = fresh per-line Platt fit on TRAIN only
Judge TEST Brier + ECE. Kill (tails stand): refit gains < 0.0005 over live
AND live ECE sane. A live-map failure becomes a SCOPED refit proposal —
no live edit without sign-off + revert (standing rules).

Writes artifacts/odds_log/tail_recal_report.json. No live change.
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

from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import (  # noqa: E402
    ProbCalibrationBundle,
    expected_calibration_error,
    fit_platt,
)
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel.parquet"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
LINES = [6.5, 7.5, 8.5, 9.5]
CUT = "2026-05-23"


def _ece(y: np.ndarray, p: np.ndarray) -> float:
    e, _ = expected_calibration_error(y, p)
    return float(e)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    key = {2.5: "2_5", 3.5: "3_5", 4.5: "4_5", 5.5: "5_5",
           6.5: "6_5", 7.5: "7_5", 8.5: "8_5", 9.5: "9_5"}
    p = pl.read_parquet(PANEL).filter(
        pl.col("p_ours").is_not_null() & pl.col("line").is_in(LINES)).sort("gd")
    tr, te = p.filter(pl.col("gd") <= CUT), p.filter(pl.col("gd") > CUT)
    print(f"train {tr.height} / test {te.height} points, cut {CUT}")
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "cut": CUT, "per_line": []}
    for ln in LINES:
        strn = tr.filter(pl.col("line") == ln)
        ste = te.filter(pl.col("line") == ln)
        if strn.height < 200 or ste.height < 50:
            rep["per_line"].append({"line": ln, "n_train": strn.height,
                                    "n_test": ste.height, "note": "thin-skip"})
            continue
        refit = fit_platt(strn["p_ours"].to_numpy(), strn["y"].to_numpy())
        y = ste["y"].to_numpy()
        raw = ste["p_ours"].to_numpy()
        live = bundle.line_maps[key[ln]].transform(raw)
        adj = refit.transform(raw)
        entry = {"line": ln, "n_train": strn.height, "n_test": ste.height,
                 "platt_a": refit.platt_a, "platt_b": refit.platt_b,
                 "raw": {"brier": float(np.mean((raw - y) ** 2)), "ece": _ece(y, raw)},
                 "live": {"brier": float(np.mean((live - y) ** 2)), "ece": _ece(y, live)},
                 "refit": {"brier": float(np.mean((adj - y) ** 2)), "ece": _ece(y, adj)}}
        entry["live_sane"] = bool(entry["live"]["ece"] < 0.03)
        entry["refit_gain"] = entry["live"]["brier"] - entry["refit"]["brier"]
        rep["per_line"].append(entry)
        print("line=%.1f ntr=%d nte=%d raw=%.4f/%.3f live=%.4f/%.3f refit=%.4f/%.3f (a=%.2f b=%+.2f)" % (
            ln, strn.height, ste.height,
            entry["raw"]["brier"], entry["raw"]["ece"],
            entry["live"]["brier"], entry["live"]["ece"],
            entry["refit"]["brier"], entry["refit"]["ece"],
            refit.platt_a or 0, refit.platt_b or 0))
    getest = [e for e in rep["per_line"] if "refit_gain" in e]
    rep["kill"] = ("TAILS-STAND" if getest and all(e["refit_gain"] < 0.0005 for e in getest)
                   and all(e["live_sane"] for e in getest) else "REFIT-SCOPED")
    out = ODDS_DIR / "tail_recal_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
