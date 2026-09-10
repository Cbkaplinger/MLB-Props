"""Count-layer family horse-race (post hoc, research).

Chrono 70/30 split on scored universe starts. Train: BB kappa (MLE,
existing two-stage helper on actual K/PA + k_rate) + NB r (moment match on
K vs xK). Test: Brier + logloss per line 2.5-9.5 per family —
binomial (live), poisson, beta-binomial, negative-binomial.

Writes artifacts/odds_log/count_family_report.json. No live change.
Kill: no family beats binomial on held-out Brier+logloss (keep binomial).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import nbinom

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.count_layer import over_threshold, p_strikeouts_ge  # noqa: E402
from Python.likelihoods import fit_beta_binomial_kappa  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
ODDS_DIR = ROOT / "artifacts" / "odds_log"
LINES = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5]
EPS = 1e-9


def nb_p_ge(line: float, mu: np.ndarray, r: float) -> np.ndarray:
    mu = np.clip(np.asarray(mu, dtype=float), EPS, None)
    t = over_threshold(line)
    p = r / (r + mu)
    return nbinom.sf(t - 1, r, p)


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()

    sc = pl.scan_parquet(SCORED).select(
        ["gd", "K", "PA", "k_rate_pred", "projected_tbf"]).collect().filter(
        pl.col("K").is_not_null() & pl.col("PA").is_not_null()
        & pl.col("k_rate_pred").is_not_null() & pl.col("projected_tbf").is_not_null()
        & (pl.col("projected_tbf") > 0) & (pl.col("K") >= 0)).sort("gd")
    dates = sorted(set(sc["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    tr = sc.filter(pl.col("gd") <= cut).to_dicts()
    te = sc.filter(pl.col("gd") > cut).to_dicts()
    print(f"train {len(tr)} / test {len(te)} starts, cut {cut}")

    ktr = np.array([r["K"] for r in tr], dtype=float)
    ptr = np.array([r["PA"] for r in tr], dtype=float)
    rtr = np.array([r["k_rate_pred"] for r in tr], dtype=float)
    ttr = np.array([r["projected_tbf"] for r in tr], dtype=float)
    xtr = np.clip(rtr * ttr, EPS, None)
    valid = (ktr <= ptr) & (ptr > 0)
    kappa = fit_beta_binomial_kappa(ktr[valid], ptr[valid], np.clip(rtr[valid], 1e-12, 1 - 1e-12))
    resid = ktr - xtr
    r_nb = float(np.sum(xtr ** 2) / max(EPS, np.sum(resid ** 2) - np.sum(xtr)))
    r_nb = min(max(r_nb, 0.5), 500.0)
    print(f"fit kappa={kappa:.2f} r_nb={r_nb:.2f}")

    kte = np.array([r["K"] for r in te], dtype=float)
    rte = np.array([r["k_rate_pred"] for r in te], dtype=float)
    tte = np.array([r["projected_tbf"] for r in te], dtype=float)
    xte = np.clip(rte * tte, EPS, None)

    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "n_train": len(tr), "n_test": len(te), "cut": cut,
                 "kappa": kappa, "r_nb": r_nb, "per_line": []}
    for ln in LINES:
        y = (kte > ln).astype(float)
        fams = {"binomial": p_strikeouts_ge(ln, k_rate=rte, projected_tbf=tte, family="binomial"),
                "poisson": p_strikeouts_ge(ln, k_rate=rte, projected_tbf=tte, family="poisson"),
                "beta_binomial": p_strikeouts_ge(ln, k_rate=rte, projected_tbf=tte,
                                                 family="beta_binomial", kappa=kappa),
                "neg_binomial": nb_p_ge(ln, xte, r_nb)}
        entry: dict = {"line": ln, "n": len(y), "base_rate": float(y.mean())}
        for name, p in fams.items():
            entry[name] = {"brier": float(np.mean((p - y) ** 2)), "logloss": logloss(y, p)}
        rep["per_line"].append(entry)
    for fam in ["binomial", "poisson", "beta_binomial", "neg_binomial"]:
        bb = np.mean([e[fam]["brier"] for e in rep["per_line"]])
        ll = np.mean([e[fam]["logloss"] for e in rep["per_line"]])
        rep[f"mean_{fam}"] = {"brier": bb, "logloss": ll}
        print(f"{fam}: mean brier={bb:.4f} logloss={ll:.4f}")
    base = rep["mean_binomial"]["brier"]
    best = min(rep[f"mean_{f}"]["brier"] for f in ["poisson", "beta_binomial", "neg_binomial"])
    rep["kill"] = "SURVIVE-challenger" if best < base - 0.0005 else "KILL-keep-binomial"
    out = ODDS_DIR / "count_family_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
