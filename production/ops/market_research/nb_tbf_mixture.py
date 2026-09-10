"""NB-TBF mixture challenger (post hoc, research; WS5, #36 direction).

WS3 v1-v3 killed hook-gated POINT mixtures; the family race tied NB/BB to
Poisson on K|xK. Neither tested WORKLOAD uncertainty: TBF ~ NB(mu, r)
marginalized over K|TBF ~ Poisson. Prescribed since #36 (policy-side +
fat tails for TBF uncertainty instead of better point estimates).

  P(K>line) = sum_t NB(t; mu=proj_tbf, r) * Pois_sf(line; k_rate*t)

r = single global moment-match on TRAIN dates (CUT=2026-05-23):
  mean((PA-mu)^2) = mean(mu + mu^2/r). Mean preserved by construction.
Baseline: Poisson + live WS1c (live-equivalent), same TEST subset.
Kill: Brier gain < 0.0005.

Writes artifacts/odds_log/nb_tbf_report.json. No live change.
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
from scipy.stats import nbinom, poisson as _pois

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.count_layer import over_threshold, p_strikeouts_ge  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import ProbCalibrationBundle  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
PANEL = ROOT / "artifacts" / "odds_log" / "universe_panel.parquet"
CALIB = ROOT / "artifacts" / "models" / "prob_calibration_ws1c_platt_20260910_012559.joblib"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
CUT = "2026-05-23"
T_MAX = 60


def fit_r(mu: np.ndarray, pa: np.ndarray) -> float:
    """Global NB size via moment match on squared workload errors."""
    mu = np.asarray(mu, dtype=float)
    pa = np.asarray(pa, dtype=float)
    m = np.isfinite(mu) & np.isfinite(pa) & (mu > 0)
    mu, pa = mu[m], pa[m]
    err2 = np.mean((pa - mu) ** 2)
    denom = err2 - np.mean(mu)
    if denom <= 0 or len(mu) < 100:
        return 500.0  # ~Poisson (matches race cap convention)
    return float(np.mean(mu ** 2) / denom)


def nb_mix_sf(kr: np.ndarray, mu: np.ndarray, r: float, line: float) -> np.ndarray:
    """P(K > line) under Poisson(k_rate*TBF), TBF ~ NB(mu, r). Vectorized."""
    kr = np.asarray(kr, dtype=float)
    mu = np.asarray(mu, dtype=float)
    t = np.arange(0, T_MAX + 1)
    p = r / (r + mu[:, None])
    w = nbinom.pmf(t[None, :], r, p)
    w = w / w.sum(axis=1, keepdims=True)
    th = over_threshold(line)
    sf = _pois.sf(th - 1, kr[:, None] * t[None, :])
    return (w * sf).sum(axis=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--r-grid", default="",
                    help="Extra NB sizes for a sensitivity sweep, e.g. '50,100,200,1000'. "
                         "Appended as r_sensitivity (same TEST subset).")
    args = ap.parse_args()
    sc = pl.scan_parquet(SCORED).select(
        ["gd", "game_pk", "key_sorted", "K", "PA", "k_rate_pred",
         "projected_tbf", "expected_K"]).collect().filter(
        pl.col("K").is_not_null() & pl.col("PA").is_not_null()
        & pl.col("k_rate_pred").is_not_null() & pl.col("projected_tbf").is_not_null()
        & (pl.col("projected_tbf") > 0))
    tr = sc.filter(pl.col("gd") <= CUT)
    te = sc.filter(pl.col("gd") > CUT)
    r = fit_r(tr["projected_tbf"].to_numpy(), tr["PA"].to_numpy())
    print(f"train={tr.height} test={te.height} r={r:.2f} (500~=Poisson)")
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": CUT,
                 "n_train": tr.height, "n_test": te.height, "r": r}

    bundle: ProbCalibrationBundle = joblib.load(CALIB)
    maps = {ln: bundle.line_maps[k] for k, ln in
            [("2_5", 2.5), ("3_5", 3.5), ("4_5", 4.5), ("5_5", 5.5),
             ("6_5", 6.5), ("7_5", 7.5), ("8_5", 8.5), ("9_5", 9.5)]}
    kr = te["k_rate_pred"].to_numpy().astype(float)
    mu = te["projected_tbf"].to_numpy().astype(float)
    karr = te["K"].to_numpy().astype(float)
    xa = (kr * mu)
    x0 = te["expected_K"].to_numpy().astype(float)
    rep["mae"] = {"base": float(np.mean(np.abs(x0 - karr))),
                  "mix_mean_same": bool(np.allclose(xa, x0, atol=1e-9))}
    print(f"mean preserved: {rep['mae']['mix_mean_same']}")

    panel = pl.read_parquet(PANEL).select(["gd", "key", "line", "y", "p_book_close"])
    gd = te["gd"].to_list()
    key = te["key_sorted"].to_list()
    rec, rb, rm = [], [], []
    for ln in LINES:
        mix = nb_mix_sf(kr, mu, r, ln)
        base = np.array([float(p_strikeouts_ge(ln, k_rate=np.array([k]),
                                                projected_tbf=np.array([t]),
                                                family="poisson")[0])
                         for k, t in zip(kr, mu)])
        mix_c = maps[ln].transform(mix)
        base_c = maps[ln].transform(base)
        for i in range(te.height):
            rec.append({"gd": gd[i], "key": key[i], "line": float(ln)})
            rb.append(base_c[i])
            rm.append(mix_c[i])
    cand = pl.DataFrame(rec).with_columns(pl.Series("p_base", np.array(rb)),
                                          pl.Series("p_mix", np.array(rm)))
    cmpf = cand.join(panel, on=["gd", "key", "line"], how="inner").filter(
        pl.col("p_book_close").is_not_null())
    y = cmpf["y"].to_numpy().astype(float)
    pb, pm, pk = (cmpf[c].to_numpy().astype(float) for c in ("p_base", "p_mix", "p_book_close"))
    rep["brier"] = {"n": int(cmpf.height),
                    "base": float(np.mean((pb - y) ** 2)),
                    "mix": float(np.mean((pm - y) ** 2)),
                    "book": float(np.mean((pk - y) ** 2))}
    rep["brier"]["gain"] = rep["brier"]["base"] - rep["brier"]["mix"]
    print(f"Brier n={rep['brier']['n']} base={rep['brier']['base']:.4f} "
          f"mix={rep['brier']['mix']:.4f} book={rep['brier']['book']:.4f} "
          f"gain={rep['brier']['gain']:+.5f}")
    args_r = args.r_grid.strip()
    if args_r:
        kidx = {k: i for i, k in enumerate(zip(gd, key))}
        rep["r_sensitivity"] = {}
        for rr in [float(x) for x in args_r.split(",")]:
            se = 0.0
            n = 0
            for ln in LINES:
                mix = maps[ln].transform(nb_mix_sf(kr, mu, rr, ln))
                sub = cmpf.filter(pl.col("line") == ln)
                if sub.height == 0:
                    continue
                y = sub["y"].to_numpy().astype(float)
                idx = [kidx[k] for k in zip(sub["gd"].to_list(), sub["key"].to_list())]
                se += float(np.sum((mix[idx] - y) ** 2))
                n += len(idx)
            rep["r_sensitivity"][str(rr)] = {"n": n, "gain": rep["brier"]["base"] - se / n}
            print(f"  r={rr}: gain={rep['r_sensitivity'][str(rr)]['gain']:+.5f}")
    rep["kill"] = "SURVIVE" if rep["brier"]["gain"] >= 0.0005 else "KILL"
    out = ODDS_DIR / "nb_tbf_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
