"""Start-level command aggregates from open-command per-pitch data.

Joins targets (inferred target x/z) + pbp (date, pitcher, pitch_type) on
(game_pk, play_id) → per-pitch miss inches → per (date, pitcher) start rows:
median miss, tail-miss share (>14in), n pitches. Plus trailing-30d rolling
median (leakage-safe: strictly prior dates) for "fast K%" tests.
Season medians (command_scores.csv) join as slow prior in downstream scripts.

Writes data/Open-Command/start_command.parquet (ignored). Research stage,
CC BY-NC-SA 4.0 compliant (no commercial use).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_parquet  # noqa: E402
from join_keys import sorted_key  # noqa: E402

OC = ROOT / "data" / "Open-Command"
OUT = OC / "start_command.parquet"


def main() -> None:
    frames = []
    for year in ("2024", "2025", "2026"):
        pbp = pl.scan_csv(OC / year / "pbp_info.csv.gz").select(
            ["game_pk", "play_id", "date", "pitcher"]).collect()
        tgt = pl.scan_csv(OC / year / "targets.csv.gz").select(
            ["game_pk", "play_id", "plate_x_in", "plate_z_in",
             "inferred_x_in", "inferred_z_in", "plausible"]).collect()
        j = pbp.join(tgt, on=["game_pk", "play_id"], how="inner").filter(
            pl.col("plausible") & pl.col("plate_x_in").is_not_null()
            & pl.col("inferred_x_in").is_not_null())
        j = j.with_columns(
            (((pl.col("plate_x_in").cast(pl.Float64) - pl.col("inferred_x_in").cast(pl.Float64)) ** 2
              + (pl.col("plate_z_in").cast(pl.Float64) - pl.col("inferred_z_in").cast(pl.Float64)) ** 2
              ).sqrt()).alias("miss"))
        print(f"{year}: {j.height} pitches w/ miss")
        frames.append(j.select(["date", "pitcher", "miss"]))
    allp = pl.concat(frames)
    start = allp.group_by(["date", "pitcher"]).agg(
        pl.col("miss").median().alias("cmd_med"),
        (pl.col("miss") > 14.0).mean().alias("cmd_tail"),
        pl.len().alias("cmd_n")).sort(["pitcher", "date"])
    start = start.with_columns(
        pl.col("pitcher").map_elements(sorted_key, return_dtype=pl.Utf8).alias("key"),
        pl.col("date").str.strptime(pl.Date, "%Y-%m-%d").alias("_d"))
    # trailing-30d rolling median, strictly prior dates (leakage-safe)
    recs = []
    for key, sub in start.group_by("key"):
        s = sub.sort("_d")
        dates = s["_d"].to_list()
        meds = s["cmd_med"].to_list()
        roll = []
        for i, d in enumerate(dates):
            prior = [m for dd, m in zip(dates[:i], meds[:i])
                     if 0 < (d - dd).days <= 30]
            roll.append(float(np.median(prior)) if len(prior) >= 2 else None)
        recs.append(s.with_columns(pl.Series("cmd_roll30", roll)).drop("_d"))
    out = pl.concat(recs).sort(["date", "pitcher"])
    atomic_write_parquet(out, OUT)
    print(f"starts: {out.height}, with roll30: {out.filter(pl.col('cmd_roll30').is_not_null()).height} -> {OUT}")


if __name__ == "__main__":
    main()
