"""WS3 TBF two-stage probe (post hoc, research).

Baseline: single ridge projected_tbf (MAE 2.53, tails +9.5/-5.4).
Challenger: P(short outing) logistic + conditional means
  pred = p_short * E[PA|short] + (1-p_short) * E[PA|long-ridge]
Short = PA < 18 (~10% mass; tails <15/>=28 judged separately).
Features: projected_tbf, days_rest_capped, bullpen load L1/L2,
heavy outings, PA_P5, season debut. Chrono 70/30. Judge: MAE overall
+ MAE in tails (<15, >=28).

Writes artifacts/odds_log/ws3_tbf_report.json. No live change.
Kill: no held-out MAE gain in tails (keep single ridge).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import atomic_write_text  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
FEATS = ["projected_tbf", "days_rest_capped", "bullpen_pitches_L1d", "bullpen_pitches_L2d",
         "bullpen_heavy_outings_L1d", "bullpen_pitchers_used_L1d", "PA_P5", "is_season_debut"]
SHORT = 18


def mae(a, b) -> float:
    return float(np.mean(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()

    cols = list(dict.fromkeys(["gd", "PA", "projected_tbf"] + FEATS))
    sc = pl.scan_parquet(SCORED).select(cols).collect().filter(
        pl.col("PA").is_not_null() & pl.col("projected_tbf").is_not_null()).sort("gd")
    for f in FEATS:
        sc = sc.with_columns(pl.col(f).cast(pl.Float64).fill_null(0.0).alias(f))
    sc = sc.with_columns((pl.col("PA").cast(pl.Float64) < SHORT).cast(pl.Float64).alias("is_short"))
    print(f"rows {sc.height}, short rate {sc['is_short'].mean():.3f}")

    dates = sorted(set(sc["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    tr = sc.filter(pl.col("gd") <= cut)
    te = sc.filter(pl.col("gd") > cut)
    Xtr = tr.select(FEATS).to_numpy()
    Xte = te.select(FEATS).to_numpy()
    ytr_short = tr["is_short"].to_numpy()
    ytr_pa = tr["PA"].cast(pl.Float64).to_numpy()
    yte_pa = te["PA"].cast(pl.Float64).to_numpy()
    base_te = te["projected_tbf"].cast(pl.Float64).to_numpy()
    base_tr = tr["projected_tbf"].cast(pl.Float64).to_numpy()

    scaler = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=2000).fit(scaler.transform(Xtr), ytr_short)
    e_short = float(ytr_pa[ytr_short == 1].mean())
    long_m = ytr_short == 0
    reg = Ridge(alpha=1.0).fit(scaler.transform(Xtr[long_m]), ytr_pa[long_m])
    p_te = clf.predict_proba(scaler.transform(Xte))[:, 1]
    pred_te = p_te * e_short + (1 - p_te) * reg.predict(scaler.transform(Xte))
    p_tr = clf.predict_proba(scaler.transform(Xtr))[:, 1]
    pred_tr = p_tr * e_short + (1 - p_tr) * reg.predict(scaler.transform(Xtr))

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": cut,
                 "n_train": tr.height, "n_test": te.height,
                 "short_threshold": SHORT, "short_rate_train": float(ytr_short.mean()),
                 "E_short": e_short,
                 "mae_train_base": mae(base_tr, ytr_pa), "mae_train_two": mae(pred_tr, ytr_pa),
                 "mae_test_base": mae(base_te, yte_pa), "mae_test_two": mae(pred_te, yte_pa),
                 "tails": {}}
    for name, mask in [("pa_lt15", yte_pa < 15), ("pa_ge28", yte_pa >= 28)]:
        if mask.sum() < 20:
            rep["tails"][name] = {"n": int(mask.sum()), "note": "thin"}
            continue
        rep["tails"][name] = {"n": int(mask.sum()),
                              "mae_base": mae(base_te[mask], yte_pa[mask]),
                              "mae_two": mae(pred_te[mask], yte_pa[mask])}
    print(f"MAE test base {rep['mae_test_base']:.4f} -> two-stage {rep['mae_test_two']:.4f}")
    print(json.dumps(rep["tails"], indent=1))
    gain = rep["mae_test_base"] - rep["mae_test_two"]
    tail_gain = min(rep["tails"].get("pa_lt15", {}).get("mae_base", 0) - rep["tails"].get("pa_lt15", {}).get("mae_two", 0),
                    rep["tails"].get("pa_ge28", {}).get("mae_base", 0) - rep["tails"].get("pa_ge28", {}).get("mae_two", 0))
    rep["kill"] = "SURVIVE" if gain > 0.02 and tail_gain > 0 else "KILL"
    out = ODDS_DIR / "ws3_tbf_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
