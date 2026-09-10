"""Combo matrix — bundle x Poisson x WS1c(+combo) on ONE panel/split.

Same universe test split (cut 2026-05-23) and same book_close-matched subset
for every cell (apples-to-apples). Per-line Platt refit on train for BOTH
binomial-raw and Poisson (no cross-family map reuse). WS2 joins this matrix
when its features exist (debut-minors parked; recency/velocity pending).

Cells: bundle-raw, bundle-iso(live), poisson, ws1c-on-binom, ws1c-on-poisson,
combo-note. Writes artifacts/odds_log/combo_matrix_report.json. No live change.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import poisson as _pois

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.count_layer import over_threshold  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import clip_prob, fit_platt, logit, sigmoid  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel.parquet"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CUT = "2026-05-23"


def apply_platt(p: np.ndarray, a: float, b: float) -> np.ndarray:
    return np.asarray(clip_prob(sigmoid(a * logit(np.asarray(p, dtype=float)) + b)), dtype=float)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    panel = pl.read_parquet(PANEL).filter(
        pl.col("p_ours").is_not_null() & pl.col("p_ours_cal").is_not_null()
        & pl.col("p_book_close").is_not_null())
    kt = pl.scan_parquet(SCORED).select(["gd", "key_sorted", "k_rate_pred", "projected_tbf"]).collect()
    panel = panel.join(kt, left_on=["gd", "key"], right_on=["gd", "key_sorted"], how="left").filter(
        pl.col("k_rate_pred").is_not_null() & (pl.col("projected_tbf") > 0))
    print(f"matrix rows: {panel.height}")

    tr = panel.filter(pl.col("gd") <= CUT).to_dicts()
    te = panel.filter(pl.col("gd") > CUT).to_dicts()
    print(f"train {len(tr)} / test {len(te)}")

    # poisson p per row (train + test)
    for rows in (tr, te):
        for r in rows:
            mu = max(float(r["k_rate_pred"]) * float(r["projected_tbf"]), 1e-9)
            r["p_pois"] = float(_pois.sf(over_threshold(float(r["line"])) - 1, mu))
    # per-line Platt maps on train, separately for binom-raw and poisson
    maps: dict = {}
    for ln in LINES:
        s = [(r["p_ours"], r["p_pois"], r["y"]) for r in tr if float(r["line"]) == ln]
        if len(s) < 200:
            continue
        pb = np.array([x[0] for x in s])
        pp = np.array([x[1] for x in s])
        yy = np.array([x[2] for x in s])
        cb = fit_platt(pb, yy)
        cp = fit_platt(pp, yy)
        maps[ln] = {"b": (cb.platt_a, cb.platt_b), "p": (cp.platt_a, cp.platt_b)}

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": CUT,
                 "per_line": [], "maps": {str(k): v for k, v in maps.items()}}
    cells = ["bundle_raw", "bundle_iso", "poisson", "ws1c_binom", "ws1c_pois", "book"]
    agg: dict[str, list[float]] = {c: [] for c in cells}
    for ln in LINES:
        if ln not in maps:
            continue
        s = [r for r in te if float(r["line"]) == ln]
        if len(s) < 50:
            continue
        y = np.array([r["y"] for r in s])
        raw = np.array([r["p_ours"] for r in s])
        iso = np.array([r["p_ours_cal"] for r in s])
        poi = np.array([r["p_pois"] for r in s])
        bk = np.array([r["p_book_close"] for r in s])
        (ab, bb), (ap_, bp) = maps[ln]["b"], maps[ln]["p"]
        preds = {"bundle_raw": raw, "bundle_iso": iso, "poisson": poi,
                 "ws1c_binom": apply_platt(raw, ab or 0, bb or 0),
                 "ws1c_pois": apply_platt(poi, ap_ or 0, bp or 0), "book": bk}
        entry: dict = {"line": ln, "n": len(s)}
        for c in cells:
            b = float(np.mean((preds[c] - y) ** 2))
            entry[c] = round(b, 4)
            agg[c].append(b)
        rep["per_line"].append(entry)
        print("line=%.1f n=%d " % (ln, len(s)) + " ".join(f"{c}={entry[c]:.4f}" for c in cells))
    rep["means"] = {c: round(float(np.mean(agg[c])), 4) for c in cells}
    print(rep["means"])
    out = ODDS_DIR / "combo_matrix_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
