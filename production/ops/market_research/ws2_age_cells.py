"""WS2-age cells — residual/MAE/skill by age-as-of-game (post hoc, research).

Joins player_ages (MLBAM DOB) via id-map names (sorted-key both sides;
family-first L3 vs given-first map) to scored universe starts.
Bins: <=26 / 27-29 / 30-32 / 33+. Reports n, MAE_K, xK bias, Brier skill
vs book_close (panel join). The Sale/Eovaldi overrate question, answered.

Writes artifacts/odds_log/ws2_age_report.json. No live change.
Kill: flat across bins (age is not signal; keep parked).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from datetime import datetime as dt
from datetime import timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import ODDS_DIR  # noqa: E402
from join_keys import sorted_key as _sk  # noqa: E402

SCORED = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"
PANEL = ODDS_DIR / "universe_panel.parquet"


def agebin(a: float) -> str:
    if a <= 26:
        return "<=26"
    if a <= 29:
        return "27-29"
    if a <= 32:
        return "30-32"
    return "33+"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    args = ap.parse_args()
    ages = pl.read_parquet(ROOT / "data" / "dimensions" / "player_ages.parquet").filter(
        pl.col("birth_date") != "").with_columns(
        pl.col("birth_date").str.strptime(pl.Date, "%Y-%m-%d").alias("dob"))
    idmap = pl.read_parquet(ROOT / "data" / "dimensions" / "player_id_map.parquet").select(
        ["mlb_id", "player_name"]).with_columns(
        pl.col("player_name").map_elements(_sk, return_dtype=pl.Utf8).alias("key"))
    am = ages.join(idmap, on="mlb_id", how="inner")
    print(f"ages w/ names: {am.height}")

    sc = pl.scan_parquet(SCORED).select(["gd", "player_name", "K", "expected_K"]).collect().filter(
        pl.col("K").is_not_null() & pl.col("expected_K").is_not_null()).with_columns(
        pl.col("player_name").map_elements(_sk, return_dtype=pl.Utf8).alias("key"))
    j = sc.join(am.select(["key", "dob"]), on="key", how="left")
    print(f"scored {sc.height}, age-matched {j.filter(pl.col('dob').is_not_null()).height}")
    j = j.filter(pl.col("dob").is_not_null()).with_columns(
        ((pl.col("gd").str.strptime(pl.Date, "%Y-%m-%d") - pl.col("dob")).dt.total_days() / 365.25).alias("age"))
    j = j.with_columns(pl.col("age").map_elements(agebin, return_dtype=pl.Utf8).alias("abin"))

    panel = pl.read_parquet(PANEL).filter(pl.col("p_book_close").is_not_null()).select(
        ["gd", "key", "line", "y", "p_ours_cal", "p_book_close"])
    rep: dict = {"generated_utc": dt.now(timezone.utc).isoformat(), "bins": []}
    for keys, sub in j.group_by("abin"):
        b = keys[0]
        k = sub["K"].cast(pl.Float64).to_numpy()
        x = sub["expected_K"].cast(pl.Float64).to_numpy()
        lp = panel.join(sub.select(["gd", "key"]).with_columns(pl.lit(1).alias("_m")),
                        on=["gd", "key"], how="inner")
        o: dict = {"abin": b, "n": sub.height,
                   "mae_k": float(np.mean(np.abs(x - k))), "xk_bias": float(np.mean(x - k))}
        if lp.height > 100:
            yo, po, pb = lp["y"].to_numpy(), lp["p_ours_cal"].to_numpy(), lp["p_book_close"].to_numpy()
            o["n_points"] = lp.height
            o["skill_vs_close"] = float(np.mean((pb - yo) ** 2) - np.mean((po - yo) ** 2))
        rep["bins"].append(o)
        print(json.dumps(o))
    out = ODDS_DIR / "ws2_age_report.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
