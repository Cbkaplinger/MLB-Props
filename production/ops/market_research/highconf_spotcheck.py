"""High-confidence spot-check on taken tickets (descriptive probe, no live surface).

The tutorial 80%-bin question, ported to our market: K-prop taken
probabilities rarely reach 0.80, so scan top bands {0.60, 0.70, 0.80} and
report the highest band holding n>=30: predicted mean vs empirical win rate,
Brier, ECE contribution, CLV/ROI inside the band. Verdict rule: |pred-emp|
<= 0.05 -> calibrated at the top, nothing to fix; else file the direction.

Sources: champion 2026 taken set via the selector (flat $50, frozen).
Writes: artifacts/odds_log/highconf_spotcheck.json (ignored, regenerable).
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
BANDS = (0.80, 0.70, 0.60)
MIN_N = 30


def taken_p() -> pl.Expr:
    """Taken-side calibrated probability expression (pure, testable)."""
    return (pl.when(pl.col("side") == "over").then(pl.col("p_ours_cal"))
            .otherwise(1.0 - pl.col("p_ours_cal")).alias("p_taken"))


def band_stats(t: pl.DataFrame, lo: float) -> dict:
    """Spot-check stats for p_taken >= lo (pure over rows)."""
    sub = t.filter(pl.col("p_taken") >= lo)
    n = len(sub)
    if n == 0:
        return {"lo": lo, "n": 0}
    p = np.asarray(sub["p_taken"], dtype=float)
    w = np.asarray(sub["won"].cast(pl.Float64), dtype=float)
    pnl = np.asarray(sub["pnl"], dtype=float)
    clv = [float(x) for x in sub.filter(pl.col("clv_pp").is_not_null())["clv_pp"].to_list()]
    return {"lo": lo, "n": n,
            "pred_mean": round(float(p.mean()), 4),
            "emp_wr": round(float(w.mean()), 4),
            "gap": round(float(p.mean() - w.mean()), 4),
            "brier": round(float(np.mean((p - w) ** 2)), 4),
            "roi": round(float(pnl.sum() / (50.0 * n)), 4),
            "clv_mean_pp": round(sum(clv) / len(clv), 2) if clv else None,
            "clv_beat": round(sum(1 for x in clv if x > 0) / len(clv), 4) if clv else None}


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
    ap.add_argument("--out", default=str(ODDS_DIR / "highconf_spotcheck.json"))
    args = ap.parse_args()
    sel = load_selector()
    cand = pl.read_parquet(ODDS_DIR / "juiced_replay_candidates.parquet")
    champ = sel.apply_config(
        cand.filter(pl.col("yr").cast(pl.String) == "2026"),
        0.12, 0.24, "lean", "dkfd").with_columns(taken_p())
    rep: dict = {"bands": [band_stats(champ, lo) for lo in BANDS], "n_taken": len(champ)}
    top = next((b for b in rep["bands"] if b["n"] >= MIN_N), None)
    if top is None:
        rep["verdict"] = f"YOUNG: no band holds n>={MIN_N}"
    elif abs(top["gap"]) <= 0.05:
        rep["verdict"] = ("CALIBRATED at top (band>=%.2f, n=%d, gap=%+.3f): nothing to fix"
                          % (top["lo"], top["n"], top["gap"]))
    else:
        rep["verdict"] = ("MISCALIBRATED at top (band>=%.2f, n=%d, gap=%+.3f, "
                          "direction filed, no live action)" % (top["lo"], top["n"], top["gap"]))
    Path(args.out).write_text(json.dumps(rep, indent=2, default=str))
    for b in rep["bands"]:
        print(b)
    print(rep["verdict"])
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
