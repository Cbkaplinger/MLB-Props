"""Calibration-drift simulation on the taken set (research probe, no live surface).

We monitor drift (NightlyDrift, scorecard) but never quantified tolerance:
how much probability drift must occur before it MATTERS for money? Inject
synthetic bias shifts d into taken-side p (clip to [0.01, 0.99]) on the
frozen champion 2026 set — decisions stay frozen (same tickets) — and report
Brier, taken-ECE, and mean-edge shift per shift. Read off the shift where
taken-ECE doubles vs baseline: that is the drift budget the monitors must
catch. Descriptive only; gates and policy untouched.

Writes: artifacts/odds_log/calib_drift_sim.json (ignored, regenerable).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "production" / "ops" / "market_research"))

ODDS_DIR = ROOT / "artifacts" / "odds_log"
SHIFTS = (-0.05, -0.02, -0.01, 0.0, 0.01, 0.02, 0.05)


def ece_10(p: np.ndarray, w: np.ndarray) -> float:
    """Equal-width 10-bin ECE (pure, testable)."""
    ece, n = 0.0, len(p)
    if n == 0:
        return 0.0
    for b in range(10):
        lo, hi = b / 10.0, (b + 1) / 10.0
        m = (p >= lo) & (p < hi if b < 9 else p <= hi)
        if m.sum():
            ece += (m.sum() / n) * abs(p[m].mean() - w[m].mean())
    return float(ece)


def drift_row(p: np.ndarray, w: np.ndarray, edge: np.ndarray, d: float) -> dict:
    """Metrics under bias shift d (pure, testable)."""
    q = np.clip(p + d, 0.01, 0.99)
    return {"shift": d,
            "brier": round(float(np.mean((q - w) ** 2)), 4),
            "ece_taken": round(ece_10(q, w), 4),
            "mean_edge_shift": round(float((q - p).mean()), 4),
            "edge_mean": round(float(edge.mean() + (q - p).mean()), 4)}


def load_selector():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "select_2025_champion",
        ROOT / "production" / "ops" / "market_research" / "select_2025_champion.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["select_2025_champion"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ODDS_DIR / "calib_drift_sim.json"))
    args = ap.parse_args()
    sel = load_selector()
    cand = pl.read_parquet(ODDS_DIR / "juiced_replay_candidates.parquet")
    champ = sel.apply_config(
        cand.filter(pl.col("yr").cast(pl.String) == "2026"),
        0.12, 0.24, "lean", "dkfd").with_columns(
        (pl.when(pl.col("side") == "over").then(pl.col("p_ours_cal"))
         .otherwise(1.0 - pl.col("p_ours_cal"))).alias("p_taken"))
    p = np.asarray(champ["p_taken"], dtype=float)
    w = np.asarray(champ["won"].cast(pl.Float64), dtype=float)
    e = np.asarray(champ["edge"], dtype=float)
    rows = [drift_row(p, w, e, d) for d in SHIFTS]
    base = next(r for r in rows if r["shift"] == 0.0)["ece_taken"]
    budget = next((r["shift"] for r in rows
                   if r["shift"] != 0.0 and r["ece_taken"] >= 2 * base), None)
    rep = {"rows": rows, "baseline_ece": base,
           "drift_budget": ("taken-ECE doubles at shift %+.2f" % budget
                            if budget is not None else
                            "no doubling within +-0.05: monitors own this range"),
           "note": "decisions frozen; tolerance only, no live input"}
    Path(args.out).write_text(json.dumps(rep, indent=2, default=str))
    for r in rows:
        print(r)
    print(rep["drift_budget"])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
