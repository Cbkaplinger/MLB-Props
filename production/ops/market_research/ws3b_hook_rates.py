"""WS3 v2 — pitcher empirical-Bayes hook rates (post hoc, research).

v1 died: global short-mean can't model pitcher-specific hooks.
v2: per-pitcher P(PA<18) shrunk toward league prior (pseudo-counts), used as
the stage-1 hook probability; long side keeps ridge-on-long. Leakage-safe:
pitcher history uses STRICTLY prior dates (cumsum-minus-current per pitcher).

Writes artifacts/odds_log/ws3b_hook_report.json. No live change.
Kill: no held-out tail MAE gain vs single ridge (park pitcher-hooks).
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
FEATS = ["projected_tbf", "days_rest_capped", "bullpen_pitches_L1d", "PA_P5"]
SHORT, PRIOR_N = 18, 8.0


def mae(a, b) -> float:
    return float(np.mean(np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()

    cols = list(dict.fromkeys(["gd", "pitcher", "PA", "projected_tbf"] + FEATS))
    sc = pl.scan_parquet(SCORED).select(cols).collect().filter(
        pl.col("PA").is_not_null() & pl.col("projected_tbf").is_not_null()).sort(["pitcher", "gd"])
    for f in FEATS:
        sc = sc.with_columns(pl.col(f).cast(pl.Float64).fill_null(0.0).alias(f))
    sc = sc.with_columns(
        (pl.col("PA").cast(pl.Float64) < SHORT).cast(pl.Float64).alias("is_short"),
        pl.col("PA").cast(pl.Float64).alias("pa"))
    # strictly-prior hook history per pitcher (leakage-safe by construction)
    sc = sc.with_columns(
        (pl.col("is_short").cum_sum().over("pitcher") - pl.col("is_short")).alias("prior_shorts"),
        ((pl.lit(1.0).cum_sum().over("pitcher")) - 1.0).alias("prior_n"))
    league = float(sc["is_short"].mean())
    sc = sc.with_columns(
        ((pl.col("prior_shorts") + PRIOR_N * league) / (pl.col("prior_n") + PRIOR_N)).alias("hook_prior"))
    print(f"rows {sc.height}, league short rate {league:.3f}")
    sc = sc.sort("gd")

    dates = sorted(set(sc["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    # refit league prior on train only (no test leakage through prior mean)
    train_rate = float(sc.filter(pl.col("gd") <= cut)["is_short"].mean())
    sc = sc.with_columns(
        ((pl.col("prior_shorts") + PRIOR_N * train_rate) / (pl.col("prior_n") + PRIOR_N)).alias("hook_prior"))
    tr = sc.filter(pl.col("gd") <= cut)
    te = sc.filter(pl.col("gd") > cut)
    Xtr = tr.select(FEATS).to_numpy()
    Xte = te.select(FEATS).to_numpy()
    ytr, yte = tr["pa"].to_numpy(), te["pa"].to_numpy()
    base_te = te["projected_tbf"].to_numpy()
    base_tr = tr["projected_tbf"].to_numpy()
    hte = te["hook_prior"].to_numpy()
    htr = tr["hook_prior"].to_numpy()

    scaler = StandardScaler().fit(Xtr)
    long_m = tr["is_short"].to_numpy() == 0
    reg = Ridge(alpha=1.0).fit(scaler.transform(Xtr[long_m]), ytr[long_m])
    e_short = float(ytr[tr["is_short"].to_numpy() == 1].mean())
    pred_te = hte * e_short + (1 - hte) * reg.predict(scaler.transform(Xte))
    pred_tr = htr * e_short + (1 - htr) * reg.predict(scaler.transform(Xtr))
    # v2b: gated — mixture only when hook_prior >= 0.20, else baseline ridge-long
    # (tests whether the failure is misapplication to the middle, not the mixture)
    gate = 0.20
    g_te = np.where(hte >= gate, pred_te, reg.predict(scaler.transform(Xte)))
    g_tr = np.where(htr >= gate, pred_tr, reg.predict(scaler.transform(Xtr)))

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": cut,
                 "n_train": tr.height, "n_test": te.height, "prior_n": PRIOR_N,
                 "mae_train_base": mae(base_tr, ytr), "mae_train_eb": mae(pred_tr, ytr),
                 "mae_test_base": mae(base_te, yte), "mae_test_eb": mae(pred_te, yte),
                 "mae_test_gated": mae(g_te, yte), "gate_threshold": gate,
                 "tails": {}}
    for name, mask in [("pa_lt15", yte < 15), ("pa_ge28", yte >= 28)]:
        rep["tails"][name] = {"n": int(mask.sum()), "mae_base": mae(base_te[mask], yte[mask]),
                              "mae_eb": mae(pred_te[mask], yte[mask]),
                              "mae_gated": mae(g_te[mask], yte[mask])} if mask.sum() >= 20 else {"n": int(mask.sum())}
    print(f"MAE test base {rep['mae_test_base']:.4f} -> EB-hooks {rep['mae_test_two'] if 'mae_test_two' in rep else rep['mae_test_eb']:.4f}")
    print(json.dumps(rep["tails"], indent=1))
    gain = rep["mae_test_base"] - rep["mae_test_eb"]
    rep["kill"] = "SURVIVE" if gain > 0.02 else "KILL"
    out = ODDS_DIR / "ws3b_hook_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
