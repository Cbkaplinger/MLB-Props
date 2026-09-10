"""Promote WS1c per-line Platt to production pointer (LIVE CHANGE, gated).

Gate (all must pass; else abort with no changes):
  1. ws1c beats bundle on ledger common subset (ledger_gate_report.json).
  2. Final bundle reloads via load_bundle + transforms sane (0,1-monotone spot).
  3. Pointer backup written BEFORE swap.

Final fit: per-line Platt on FULL universe panel (all dates; gate already
proved held-out). Lines 2.5-9.5 (n~8.7k each, no book join needed).
Revert: restore pointer JSON from backup (command printed + backlog #28).

Usage: python production/ops/market_research/promote_ws1c.py [--no-swap]
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

from Python import config  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import (  # noqa: E402
    LineCalibrator,
    ProbCalibrationBundle,
    fit_bundle_from_arrays,
    load_bundle,
    save_bundle,
)

PANEL = ROOT / "artifacts" / "odds_log" / "universe_panel.parquet"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-swap", action="store_true", help="build + validate only")
    args = ap.parse_args()

    gate = json.loads((ROOT / "artifacts" / "odds_log" / "ledger_gate_report.json").read_text())
    b = gate["brier_common_subset"]
    assert b["ws1c"] < b["bundle"] - 0.0005, f"GATE FAIL: ws1c {b['ws1c']} vs bundle {b['bundle']}"
    print(f"gate 1 PASS: ws1c {b['ws1c']:.4f} vs bundle {b['bundle']:.4f} (n={gate['n_common']})")

    panel = pl.read_parquet(PANEL).filter(
        pl.col("p_ours").is_not_null()).sort("gd")
    line_data = {}
    for ln in LINES:
        sub = panel.filter(pl.col("line") == ln)
        p = sub["p_ours"].to_numpy()
        y = sub["y"].to_numpy()
        m = np.isfinite(p)
        line_data[ln] = (p[m], y[m])
        print(f"line {ln}: fit n={m.sum()}")
    bundle = fit_bundle_from_arrays(
        method="platt", line_data=line_data,
        fit_cutoff=str(panel["gd"].max()), fit_source="universe_panel.parquet (frozen bundle raw p)",
        version=f"prob_calibration_ws1c_platt_{STAMP}",
        notes=["WS1c per-line Platt; backlog #22/#28; supersedes isotonic-20260821 on 6/6 gated lines."])
    joblib_path, json_path = save_bundle(
        bundle, config.MODEL_DIR / f"prob_calibration_ws1c_platt_{STAMP}.joblib")
    print(f"saved {joblib_path} + {json_path}")

    re = load_bundle(joblib_path)
    test = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    for ln in [4.5, 6.5]:
        out, scope = re.transform_line(bundle, ln, test) if hasattr(re, "transform_line") else (None, None)
    from Python.prob_calibration import transform_line as _tl
    for ln in [4.5, 6.5]:
        out, scope = _tl(re, ln, test)
        assert bool(np.all(np.diff(out) > 0)), f"monotone fail line {ln}"
        assert bool(((out > 0) & (out < 1)).all()), f"range fail line {ln}"
    print("gate 2 PASS: reload + monotone + range sane")

    pointer = config.MODEL_DIR / "prob_calibration_production.json"
    backup = config.MODEL_DIR / f"prob_calibration_production.backup_pre_ws1c_{STAMP}.json"
    backup.write_text(pointer.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"gate 3 PASS: backup -> {backup.name}")
    if args.no_swap:
        print("no-swap: stopping before pointer flip")
        return
    payload = {"joblib": joblib_path.name, "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "version": bundle.version, "method": "platt", "fit_cutoff": bundle.fit_cutoff,
               "supersedes": "prob_calibration_isotonic_20260821_160723",
               "revert": f"copy {backup.name} over prob_calibration_production.json"}
    pointer.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"LIVE: pointer -> {bundle.version}")
    print(f"REVERT: Copy-Item '{backup}' prob_calibration_production.json")


if __name__ == "__main__":
    main()
