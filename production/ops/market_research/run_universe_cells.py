"""Pre-registered universe cells (#17) — bins first, calibration second.

On universe_panel + scored starts (actuals K/PA):
  (a) line cells: Brier/skill/bias/ECE per line vs book_close
  (b) xK bins: MAE_K, xK bias, Brier skill vs close
  (c) TBF tails: MAE_TBF, error in PA<15 / >=28
  (d) debut cohorts: career/season debut vs rest (breakout proxy)
  (e) season split: 2025 benchmark vs 2026 clean
  (f) calibration check per line: ECE raw vs cal (decision AFTER bins)

Writes artifacts/odds_log/universe_cells_report.json. No live change.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_text  # noqa: E402
from Python.prob_calibration import expected_calibration_error  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402

PANEL = ODDS_DIR / "universe_panel.parquet"
SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"


def brier(p, y) -> float:
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def ece(y, p) -> float:
    e, _ = expected_calibration_error(np.asarray(y, dtype=float), np.asarray(p, dtype=float))
    return float(e)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    panel = pl.read_parquet(PANEL)
    sc = pl.scan_parquet(SCORED).select(
        ["gd", "key_sorted", "expected_K", "projected_tbf", "K", "PA",
         "is_career_mlb_debut", "is_season_debut"]).collect()
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(),
                 "panel_rows": panel.height, "starts": sc.height}

    # (a) line cells vs book_close
    rep["line_cells"] = []
    for keys, sub in panel.filter(pl.col("p_book_close").is_not_null()).group_by("line"):
        ln = keys[0]
        ys, po, pb = sub["y"].to_numpy(), sub["p_ours_cal"].to_numpy(), sub["p_book_close"].to_numpy()
        rep["line_cells"].append({"line": float(ln), "n": sub.height,
                                  "brier_ours": brier(po, ys), "brier_book": brier(pb, ys),
                                  "skill": brier(pb, ys) - brier(po, ys),
                                  "bias_ours_pp": float(100 * (po.mean() - ys.mean())),
                                  "ece_ours": ece(ys, po), "ece_book": ece(ys, pb)})
    rep["line_cells"].sort(key=lambda d: d["line"])

    # (b) xK bins (start-level MAE/bias + line-point skill)
    scx = sc.with_columns(
        pl.when(pl.col("expected_K") < 4).then(pl.lit("xK<4"))
        .when(pl.col("expected_K") < 6).then(pl.lit("xK4-6"))
        .otherwise(pl.lit("xK6+")).alias("xbin"))
    rep["xkbins"] = []
    for keys, sub in scx.group_by("xbin"):
        b = keys[0]
        k, x = sub["K"].cast(pl.Float64).to_numpy(), sub["expected_K"].cast(pl.Float64).to_numpy()
        m = np.isfinite(k) & np.isfinite(x)
        lp = panel.filter(pl.col("p_book_close").is_not_null()).join(
            sub.select(["gd", "key_sorted"]).rename({"key_sorted": "key"}),
            on=["gd", "key"], how="inner")
        o = {"xbin": str(b), "n_starts": int(m.sum()),
             "mae_k": float(np.mean(np.abs(x[m] - k[m]))),
             "xk_bias": float(np.mean(x[m] - k[m]))}
        if lp.height:
            o["n_points"] = lp.height
            o["skill_vs_close"] = brier(lp["p_book_close"].to_numpy(), lp["y"].to_numpy()) - brier(
                lp["p_ours_cal"].to_numpy(), lp["y"].to_numpy())
        rep["xkbins"].append(o)

    # (c) TBF tails
    t = sc.filter(pl.col("PA").is_not_null() & pl.col("projected_tbf").is_not_null())
    rep["tbf"] = {"n": t.height,
                  "mae": float((t["projected_tbf"].cast(pl.Float64) - t["PA"].cast(pl.Float64)).abs().mean())}
    for name, f in [("pa_lt15", pl.col("PA") < 15), ("pa_ge28", pl.col("PA") >= 28)]:
        s2 = t.filter(f)
        if s2.height:
            err = (s2["projected_tbf"].cast(pl.Float64) - s2["PA"].cast(pl.Float64))
            rep["tbf"][name] = {"n": s2.height, "mean_err": float(err.mean())}

    # (d) debut cohorts
    rep["debut"] = []
    for colnm in ["is_career_mlb_debut", "is_season_debut"]:
        if colnm not in sc.columns:
            continue
        for keys, sub in sc.group_by(colnm):
            val = keys[0]
            k = sub["K"].cast(pl.Float64).to_numpy()
            x = sub["expected_K"].cast(pl.Float64).to_numpy()
            m = np.isfinite(k) & np.isfinite(x)
            if int(m.sum()) < 20:
                continue
            rep["debut"].append({colnm: str(val), "n": int(m.sum()),
                                 "mae_k": float(np.mean(np.abs(x[m] - k[m]))),
                                 "xk_bias": float(np.mean(x[m] - k[m]))})

    # (e) season split
    rep["season"] = []
    for keys, sub in sc.with_columns(pl.col("gd").str.slice(0, 4).alias("season")).group_by("season"):
        ss = keys[0]
        k = sub["K"].cast(pl.Float64).to_numpy()
        x = sub["expected_K"].cast(pl.Float64).to_numpy()
        m = np.isfinite(k) & np.isfinite(x)
        rep["season"].append({"season": str(ss), "n": int(m.sum()),
                              "mae_k": float(np.mean(np.abs(x[m] - k[m]))),
                              "xk_bias": float(np.mean(x[m] - k[m]))})

    # (f) calibration per line, raw vs cal
    rep["calib"] = []
    for ln in sorted(panel["line"].unique().to_list()):
        sub = panel.filter((pl.col("line") == ln) & pl.col("p_ours").is_not_null()
                           & pl.col("p_ours_cal").is_not_null())
        if sub.height < 50:
            continue
        ys = sub["y"].to_numpy()
        rep["calib"].append({"line": float(ln), "n": sub.height,
                             "ece_raw": ece(ys, sub["p_ours"].to_numpy()),
                             "ece_cal": ece(ys, sub["p_ours_cal"].to_numpy())})

    out = ODDS_DIR / "universe_cells_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps({k: (v if not isinstance(v, list) else f"{len(v)} cells") for k, v in rep.items()}, indent=2))
    for c in rep["line_cells"]:
        print("line=%.1f n=%d skill=%+.4f bias=%+.1fpp ece_o=%.3f ece_b=%.3f" % (
            c["line"], c["n"], c["skill"], c["bias_ours_pp"], c["ece_ours"], c["ece_book"]))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
