"""Reusable saved-artifact evaluation package (B: owner work packet).

Operates on SAVED run artifacts (predictions.csv with per-row scores +
pmfs.parquet with per-arm count PMFs). No fitting, no challenger
selection, no new gates - descriptive metric tables + a Markdown
report. MACHINE-READABLE output (JSON) with artifact hashes and
durable claim IDs supplied by the caller.

Functionality status (owner requirement):
  IMPLEMENTED: row matching, summed-RPS + support, log-score floor
    accounting, mean bias + point errors (signed conventions),
    milestone Brier + reliability, predicted/observed event counts,
    marginal-variance accounting (E[var] + Var[means]), discrete PIT
    (seeded), origin summaries with sparse-cell warnings.
  PROPOSED: transfer-validation metrics (see
    transfer-validation-readiness docs), calibration intercept/slope.
  BLOCKED: anything requiring 2024+ outcomes or announced-lineup
    inputs (no acquisition authorized).

Conventions (frozen, matching the count lane): residual =
actual - predicted; bias = predicted - actual (positive =
overprediction); RPS summed over categories; K support 24 categories
(absorbing >=23); PIT seed explicit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

import kcount_combiner as kc

K_MAX = 24
PIT_BINS = 10
SPARSE_N = 30
SPARSE_EVENTS = 5


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sparse_warning(n: int, events: int) -> str | None:
    if n < SPARSE_N:
        return "sparse: n=%d < %d" % (n, SPARSE_N)
    if events < SPARSE_EVENTS:
        return "sparse: %d events < %d" % (events, SPARSE_EVENTS)
    return None


def _pit(pmf: np.ndarray, k: np.ndarray, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    v = rng.uniform(0.0, 1.0, size=len(k))
    u = np.empty(len(k))
    cdf = np.cumsum(pmf, axis=1)
    for i in range(len(k)):
        kk = int(k[i])
        f_km1 = float(cdf[i, kk - 1]) if kk > 0 else 0.0
        u[i] = f_km1 + v[i] * float(pmf[i, min(kk, K_MAX - 1)])
    hist, _ = np.histogram(u, bins=PIT_BINS, range=(0.0, 1.0))
    return {"seed": seed, "bins": PIT_BINS,
            "hist": [int(x) for x in hist], "mean_u": float(u.mean())}


def evaluate(preds_csv: Path, pmfs_parquet: Path,
             arms: list[str], k_col: str = "K",
             date_col: str = "game_date",
             origin_col: str = "origin",
             mean_cols: dict[str, str] | None = None,
             pit_seed: int = 20261001,
             claim_ids: dict[str, str] | None = None,
             extra_hashes: dict[str, str] | None = None) -> dict:
    """Evaluate saved run artifacts. mean_cols maps arm -> the saved
    per-row predicted-mean column (signed-bias convention: bias =
    predicted - actual). Returns a JSON-serializable metric dict."""
    mean_cols = mean_cols or {}
    preds = pl.read_csv(preds_csv)
    pmf_df = pl.read_parquet(pmfs_parquet)
    n = preds.height
    if pmf_df.height != n:
        raise ValueError("row-count mismatch predictions vs pmfs")
    # canonical row matching: (game_pk, pitcher) unique
    key = preds.select(["game_pk", "pitcher"]).unique()
    if key.height != n:
        raise ValueError("canonical identity violated: duplicate "
                         "(game_pk, pitcher) rows")
    k = preds[k_col].to_numpy()
    dates = preds[date_col].to_numpy().astype(str)
    origins = preds[origin_col].to_numpy().astype(str)
    out = {"n": n, "conventions": {
        "rps": "summed over categories",
        "support": "K=0..22 exact + absorbing >=23 (24 categories)",
        "bias": "predicted - actual (positive = overprediction)",
        "residual": "actual - predicted",
        "pit_seed": pit_seed}}
    pk = {}
    for a in arms:
        cols = ["pk%s_%02d" % (a, i) for i in range(K_MAX)]
        missing = [c for c in cols if c not in pmf_df.columns]
        if missing:
            raise ValueError("pmfs missing columns for arm %s: %s"
                             % (a, missing[:2]))
        pk[a] = pmf_df.select(cols).to_numpy()
        if not np.isclose(pk[a].sum(axis=1), 1.0, atol=1e-9).all():
            raise ValueError("arm %s PMFs do not sum to 1" % a)
    rps_cols = ["rps_" + a for a in arms]
    for a, c in zip(arms, rps_cols):
        if c in preds.columns:
            rep = np.array([kc.count_rps(pk[a][i], int(k[i]))
                            for i in range(n)])
            d = float(np.abs(rep - preds[c].to_numpy()).max())
            out.setdefault("verification", {})[a] = {
                "rps_reproduction_max_diff": d,
                "status": "OK" if d < 1e-8 else "MISMATCH"}
    out["arms"] = {}
    for a in arms:
        m = {"mean_rps": float(preds["rps_" + a].mean())
             if "rps_" + a in preds.columns else None}
        ls = np.array([kc.count_logscore(pk[a][i], int(k[i]))
                       for i in range(n)])
        m["mean_logscore"] = float(ls.mean())
        m["logscore_floor_rows"] = int(sum(
            1 for i in range(n)
            if pk[a][i, min(int(k[i]), K_MAX - 1)] < 1e-12))
        if a in mean_cols and mean_cols[a] in preds.columns:
            mk = preds[mean_cols[a]].to_numpy()
            m["mean_bias"] = float(mk.mean() - k.mean())
            m["mean_mae"] = float(np.abs(mk - k).mean())
        m["milestone_brier"] = {}
        m["ladder"] = {}
        for mm in (6, 8, 10, 12):
            ge = np.array([kc.exceedance(pk[a][i], mm)
                           for i in range(n)])
            y = (k >= mm).astype(float)
            ev = int(y.sum())
            entry = {"pred_mean": float(ge.mean()),
                     "observed": float(y.mean()), "events": ev,
                     "brier": float(((ge - y) ** 2).mean()),
                     "reliability": float(ge.mean() - y.mean()),
                     "sparse_warning": _sparse_warning(n, ev)}
            m["ladder"]["ge%d" % mm] = entry
            m["milestone_brier"]["ge%d" % mm] = entry["brier"]
        m["pit"] = _pit(pk[a], k, pit_seed)
        # marginal-variance accounting (per-row PMF variance, bucket
        # valued at 23: slight tail underestimate, documented)
        ks = np.arange(K_MAX)
        ek = (pk[a] * ks).sum(axis=1)
        ek2 = (pk[a] * ks ** 2).sum(axis=1)
        pv = ek2 - ek ** 2
        m["variance_accounting"] = {
            "obs_var": float(np.var(k.astype(float))),
            "mean_pred_var": float(pv.mean()),
            "var_pred_means": float(ek.var()),
            "total_pred": float(pv.mean() + ek.var()),
            "ratio_obs_over_total": float(
                np.var(k.astype(float)) / (pv.mean() + ek.var())),
            "note": "bucket 23 valued at 23 (slight tail underestimate)"}
        out["arms"][a] = m
    # origin summaries with sparse-cell warnings
    out["by_origin"] = {}
    for o in sorted(set(origins)):
        msk = origins == o
        entry = {"n": int(msk.sum()),
                 "events": int(k[msk].sum())}
        for a in arms:
            entry["mean_rps_" + a] = float(
                preds["rps_" + a].to_numpy()[msk].mean()) \
                if "rps_" + a in preds.columns else None
        entry["sparse_warning"] = _sparse_warning(
            entry["n"], entry["events"])
        out["by_origin"][o] = entry
    out["claim_ids"] = claim_ids or {}
    out["artifact_hashes"] = {
        "predictions_csv": sha256_file(Path(preds_csv)),
        "pmfs_parquet": sha256_file(Path(pmfs_parquet)),
        **(extra_hashes or {})}
    return out


def write_report(metrics: dict, path: Path, title: str) -> None:
    lines = ["# %s" % title, "",
             "n = %d | conventions: %s" % (
                 metrics["n"], json.dumps(metrics["conventions"])),
             ""]
    for a, m in metrics["arms"].items():
        lines.append("## Arm %s" % a)
        lines.append("- mean RPS: %s" % m["mean_rps"])
        lines.append("- mean log score: %.5f (floor rows: %d)"
                     % (m["mean_logscore"], m["logscore_floor_rows"]))
        if "mean_bias" in m:
            lines.append("- mean bias (pred-act): %+.5f | MAE: %.5f"
                         % (m["mean_bias"], m["mean_mae"]))
        for lg, e in m["ladder"].items():
            lines.append("- %s: pred %.5f vs obs %.5f (%d events)%s"
                         % (lg, e["pred_mean"], e["observed"],
                            e["events"],
                            " [%s]" % e["sparse_warning"]
                            if e["sparse_warning"] else ""))
        v = m["variance_accounting"]
        lines.append("- variance: obs %.4f vs pred-total %.4f "
                     "(ratio %.3f)" % (v["obs_var"], v["total_pred"],
                                       v["ratio_obs_over_total"]))
        lines.append("- PIT: mean U %.4f, hist %s"
                     % (m["pit"]["mean_u"], m["pit"]["hist"]))
        lines.append("")
    lines.append("## By origin")
    for o, e in metrics["by_origin"].items():
        rps = {k: round(v, 5) for k, v in e.items()
               if k.startswith("mean_rps") and v is not None}
        lines.append("- %s: n=%d, events=%d%s %s"
                     % (o, e["n"], e["events"],
                        " [SPARSE]" if e["sparse_warning"] else "",
                        rps))
    lines.append("")
    lines.append("Claim IDs: %s" % json.dumps(metrics["claim_ids"]))
    lines.append("Artifact hashes: %s"
                 % json.dumps(metrics["artifact_hashes"], indent=1))
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def write_metrics(metrics: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(metrics, indent=2, default=str),
                          encoding="utf-8")
