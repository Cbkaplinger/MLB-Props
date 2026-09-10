"""WS3 v3 — workhorse features inside the ridge (post hoc, research).

v2 lesson: marathon error is MEAN shrinkage of workhorses, not mixture.
Probe: Ridge(PA ~ WS3-8 + PA_P20 + Outs_P20 + pitches-per-PA_P20 + Outs_P5)
vs production projected_tbf, chrono 70/30. Judge MAE overall + tails.

Writes artifacts/odds_log/ws3c_workhorse_report.json. No live change.
Kill: no held-out tail MAE gain (workhorse info already in ridge).
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
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_text  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
BASE = ["projected_tbf", "days_rest_capped", "bullpen_pitches_L1d", "bullpen_pitches_L2d",
        "bullpen_heavy_outings_L1d", "bullpen_pitchers_used_L1d", "PA_P5", "is_season_debut"]
EXTRA = ["PA_P20", "Outs_P20", "Outs_P5"]


def mae(a, b) -> float:
    return float(np.mean(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()
    cols = list(dict.fromkeys(["gd", "PA", "Pitches_P20", "PA_P20"] + BASE + EXTRA))
    sc = pl.scan_parquet(SCORED).select(cols).collect().filter(
        pl.col("PA").is_not_null()).sort("gd")
    sc = sc.with_columns(
        (pl.col("Pitches_P20").cast(pl.Float64) / pl.col("PA_P20").cast(pl.Float64).clip(1)).alias("ppp20"))
    feats = BASE + EXTRA + ["ppp20"]
    for f in feats:
        sc = sc.with_columns(pl.col(f).cast(pl.Float64).fill_null(0.0).alias(f))
    dates = sorted(set(sc["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    tr, te = sc.filter(pl.col("gd") <= cut), sc.filter(pl.col("gd") > cut)
    ytr, yte = tr["PA"].cast(pl.Float64).to_numpy(), te["PA"].cast(pl.Float64).to_numpy()
    prod_te = te["projected_tbf"].to_numpy()
    scaler = StandardScaler().fit(tr.select(feats).to_numpy())
    reg = Ridge(alpha=1.0).fit(scaler.transform(tr.select(feats).to_numpy()), ytr)
    pred = reg.predict(scaler.transform(te.select(feats).to_numpy()))
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": cut,
                 "n_train": tr.height, "n_test": te.height,
                 "coef": {f: round(float(c), 4) for f, c in zip(feats, reg.coef_)},
                 "mae_prod": mae(prod_te, yte), "mae_work": mae(pred, yte),
                 "tails": {}}
    for name, mask in [("pa_lt15", yte < 15), ("pa_ge28", yte >= 28)]:
        rep["tails"][name] = {"n": int(mask.sum()), "mae_prod": mae(prod_te[mask], yte[mask]),
                              "mae_work": mae(pred[mask], yte[mask])} if mask.sum() >= 20 else {"n": int(mask.sum())}
    print(f"MAE prod {rep['mae_prod']:.4f} -> workhorse {rep['mae_work']:.4f}")
    print(json.dumps(rep["tails"], indent=1))
    gain = rep["mae_prod"] - rep["mae_work"]
    rep["kill"] = "SURVIVE" if gain > 0.05 else "KILL"
    out = ODDS_DIR / "ws3c_workhorse_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
