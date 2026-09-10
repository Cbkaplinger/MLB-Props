"""WS2 staleness probe — does recency predict the residual? (post hoc, research).

The bundle already sees P5/P10/P20 windows. Question: does it UNDERWEIGHT
them? Correlate residual_K (= K - expected_K) with recency deltas
(P5-P20 whiff/swstr/csw, P1-vs-P10 velo, xFIP_P1-vs-P10), fit tiny ridge
(deltas -> residual correction) on train dates, judge MAE_K on held-out.

Writes artifacts/odds_log/ws2_staleness_report.json. No live change.
Kill: no held-out MAE_K gain (model already absorbs recency; move to WS3).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_text  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
ODDS_DIR = ROOT / "artifacts" / "odds_log"

DELTA_PAIRS = [("whiff_rate_P5", "whiff_rate_P20"), ("swstr_rate_P5", "swstr_rate_P20"),
               ("csw_rate_P5", "csw_rate_P20"), ("xFIP_P1", "xFIP_P10"),
               ("ff_velo_P1", "ff_velo_P10"), ("k_rate_P5", "k_rate_P20"),
               ("FIP_P1", "FIP_P10")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()

    cols = ["gd", "K", "expected_K"] + [c for p in DELTA_PAIRS for c in p]
    sc = pl.scan_parquet(SCORED).select([c for c in cols]).collect().filter(
        pl.col("K").is_not_null() & pl.col("expected_K").is_not_null()).sort("gd")
    sc = sc.with_columns((pl.col("K").cast(pl.Float64) - pl.col("expected_K").cast(pl.Float64)).alias("resid"))
    feat_names = []
    for a, b in DELTA_PAIRS:
        if a in sc.columns and b in sc.columns:
            fn = f"d_{a}_minus_{b}"
            sc = sc.with_columns((pl.col(a).cast(pl.Float64) - pl.col(b).cast(pl.Float64)).alias(fn))
            feat_names.append(fn)
    sc = sc.filter(pl.all_horizontal([pl.col(f).is_not_null() for f in feat_names]))
    print(f"rows {sc.height}, features {feat_names}")

    dates = sorted(set(sc["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    tr = sc.filter(pl.col("gd") <= cut).to_dicts()
    te = sc.filter(pl.col("gd") > cut).to_dicts()

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": cut,
                 "n_train": len(tr), "n_test": len(te), "correlations": []}
    for f in feat_names:
        x = np.array([r[f] for r in tr], dtype=float)
        y = np.array([r["resid"] for r in tr], dtype=float)
        m = np.isfinite(x) & np.isfinite(y)
        corr = float(np.corrcoef(x[m], y[m])[0, 1]) if m.sum() > 30 else None
        rep["correlations"].append({"feature": f, "train_corr_vs_resid": corr,
                                    "n": int(m.sum())})
        print(f"{f}: corr={corr:+.3f}" if corr is not None else f"{f}: n/a")

    Xtr = np.array([[r[f] for f in feat_names] for r in tr], dtype=float)
    ytr = np.array([r["resid"] for r in tr], dtype=float)
    Xte = np.array([[r[f] for f in feat_names] for r in te], dtype=float)
    yte = np.array([r["resid"] for r in te], dtype=float)
    ktr = np.array([r["K"] for r in tr], dtype=float)
    kte = np.array([r["K"] for r in te], dtype=float)
    xtr = np.array([r["expected_K"] for r in tr], dtype=float)
    xte = np.array([r["expected_K"] for r in te], dtype=float)
    ridge = Ridge(alpha=1.0).fit(Xtr, ytr)
    base_te = float(np.mean(np.abs(xte - kte)))
    fix_te = float(np.mean(np.abs(xte + ridge.predict(Xte) - kte)))
    base_tr = float(np.mean(np.abs(xtr - ktr)))
    fix_tr = float(np.mean(np.abs(xtr + ridge.predict(Xtr) - ktr)))
    rep["ridge"] = {"coef": {f: round(float(c), 4) for f, c in zip(feat_names, ridge.coef_)},
                    "mae_train_base": base_tr, "mae_train_fixed": fix_tr,
                    "mae_test_base": base_te, "mae_test_fixed": fix_te,
                    "mae_gain": base_te - fix_te}
    print(f"MAE train {base_tr:.4f}->{fix_tr:.4f} test {base_te:.4f}->{fix_te:.4f}")
    rep["kill"] = ("SURVIVE" if fix_te < base_te - 0.01 else "KILL")
    out = ODDS_DIR / "ws2_staleness_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
