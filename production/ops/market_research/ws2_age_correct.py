"""WS2-age correction challenger (post hoc, research).

Fit per-age-bin xK bias offsets on train dates, subtract on test:
  xK_fixed = xK - bias_bin
Judge: MAE_K + Brier skill vs close (poisson probs recomputed from fixed xK).
Research-only precursor to pipeline age features (no retrain yet).

Writes artifacts/odds_log/ws2_age_correct_report.json. No live change.
Kill: no held-out MAE/Brier gain (age noted, not actionable pre-retrain).
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
from join_keys import ODDS_DIR  # noqa: E402
from join_keys import sorted_key as _sk  # noqa: E402
from ws2_age_cells import agebin  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
PANEL = ODDS_DIR / "universe_panel.parquet"
EPS = 1e-9


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-frac", type=float, default=0.7)
    args = ap.parse_args()

    ages = pl.read_parquet(ROOT / "data" / "dimensions" / "player_ages.parquet").filter(
        pl.col("birth_date") != "").with_columns(
        pl.col("birth_date").str.strptime(pl.Date, "%Y-%m-%d").alias("dob"))
    idmap = pl.read_parquet(ROOT / "data" / "dimensions" / "player_id_map.parquet").select(
        ["mlb_id", "player_name"]).with_columns(
        pl.col("player_name").map_elements(_sk, return_dtype=pl.Utf8).alias("key"))
    am = ages.join(idmap, on="mlb_id", how="inner")
    sc = pl.scan_parquet(SCORED).select(["gd", "player_name", "K", "expected_K"]).collect().filter(
        pl.col("K").is_not_null() & pl.col("expected_K").is_not_null()).with_columns(
        pl.col("player_name").map_elements(_sk, return_dtype=pl.Utf8).alias("key"))
    j = sc.join(am.select(["key", "dob"]), on="key", how="left").filter(
        pl.col("dob").is_not_null()).with_columns(
        ((pl.col("gd").str.strptime(pl.Date, "%Y-%m-%d") - pl.col("dob")).dt.total_days() / 365.25).alias("age"))
    j = j.with_columns(pl.col("age").map_elements(agebin, return_dtype=pl.Utf8).alias("abin")).sort("gd")

    dates = sorted(set(j["gd"].to_list()))
    cut = dates[int(len(dates) * args.train_frac)]
    tr, te = j.filter(pl.col("gd") <= cut), j.filter(pl.col("gd") > cut)
    offs = {}
    for keys, sub in tr.group_by("abin"):
        b = keys[0]
        k = sub["K"].cast(pl.Float64).to_numpy()
        x = sub["expected_K"].cast(pl.Float64).to_numpy()
        offs[b] = float(np.mean(x - k)) if len(k) >= 50 else 0.0
    print("offsets:", offs)
    te = te.with_columns(pl.col("abin").map_elements(lambda b: offs.get(b, 0.0),
                                                     return_dtype=pl.Float64).alias("off"))
    kte = te["K"].cast(pl.Float64).to_numpy()
    xte = te["expected_K"].cast(pl.Float64).to_numpy()
    ote = te["off"].to_numpy()
    base_mae = float(np.mean(np.abs(xte - kte)))
    fix_mae = float(np.mean(np.abs(xte - ote - kte)))
    rep: dict = {"generated_utc": datetime.now(timezone.utc).isoformat(), "cut": cut,
                 "n_train": tr.height, "n_test": te.height, "offsets": offs,
                 "mae_base": base_mae, "mae_fixed": fix_mae, "mae_gain": base_mae - fix_mae}

    panel = pl.read_parquet(PANEL).filter(pl.col("p_book_close").is_not_null()).select(
        ["gd", "key", "line", "y", "p_book_close"])
    lp = panel.join(te.select(["gd", "key", "expected_K", "off"]), on=["gd", "key"], how="inner")
    if lp.height > 100:
        y = lp["y"].to_numpy()
        mu0 = np.clip(lp["expected_K"].cast(pl.Float64).to_numpy(), EPS, None)
        mu1 = np.clip((lp["expected_K"].cast(pl.Float64) - lp["off"]).to_numpy(), EPS, None)
        ln = lp["line"].to_numpy()
        p0 = np.array([float(_pois.sf(over_threshold(float(l)) - 1, m)) for l, m in zip(ln, mu0)])
        p1 = np.array([float(_pois.sf(over_threshold(float(l)) - 1, m)) for l, m in zip(ln, mu1)])
        pb = lp["p_book_close"].to_numpy()
        rep["brier"] = {"n": lp.height, "base": float(np.mean((p0 - y) ** 2)),
                        "fixed": float(np.mean((p1 - y) ** 2)),
                        "book": float(np.mean((pb - y) ** 2))}
        rep["brier"]["gain"] = rep["brier"]["base"] - rep["brier"]["fixed"]
        print(json.dumps(rep["brier"], indent=1))
    print(f"MAE {base_mae:.4f}->{fix_mae:.4f}")
    rep["kill"] = "SURVIVE" if (fix_mae < base_mae - 0.01 and rep.get("brier", {}).get("gain", 0) > 0) else "KILL"
    out = ODDS_DIR / "ws2_age_correct_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"kill={rep['kill']}; wrote {out}")


if __name__ == "__main__":
    main()
