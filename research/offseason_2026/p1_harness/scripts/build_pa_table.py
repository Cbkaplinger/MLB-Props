"""P1 harness v2 step 1: build PA-level K-probability table from raw Statcast.

v2 corrections vs v1 (owner rulings 2026-10-13):
  1. COMPLETED-PA ALLOWLIST: y=1 iff events in {strikeout, strikeout_double_play}.
     Rows whose terminal event is "truncated_pa" are EXCLUDED from the completed-PA
     table entirely (v1 kept them as y=0 completions). Exclusion counts per season
     are written to reports/truncation_exclusions.txt.
  3. ALL-PITCHERS POLICY kept (every pitcher, no starter filter), plus pitcher_role
     slices: for each (game_pk, side), first pitcher of record = opener-inclusive
     starter; each PA row is tagged starter_pa / reliever_pa by whether its pitcher
     is that side's first pitcher of record. Side = inning_topbot of the PA.

Read-only source: <raw_dir>/<season>/statcast_<season>_regular.parquet, seasons 2022-2025.
Output: data/pa_table.parquet (one row per completed PA, truncated_pa excluded).
"""
from __future__ import annotations

import os
from pathlib import Path

import polars as pl

HARNESS = Path(__file__).resolve().parent.parent
RAW_DIR = Path(
    os.environ.get(
        "P1_RAW_SAVANT_DIR",
        r"C:\Users\ckaplinger\Downloads\Personal-Projects\MLB-Props\data\Savant-Data\regular",
    )
)
OUT_DIR = HARNESS / "data"
REPORTS = HARNESS / "reports"
SEASONS = [2022, 2023, 2024, 2025]  # 2026 reserved
K_EVENTS = ["strikeout", "strikeout_double_play"]
EXCLUDED_EVENTS = ["truncated_pa"]

COLUMNS = [
    "game_pk",
    "game_date",
    "at_bat_number",
    "pitch_number",
    "batter",
    "pitcher",
    "p_throws",
    "stand",
    "events",
    "inning_topbot",
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    frames = []
    for season in SEASONS:
        path = RAW_DIR / str(season) / f"statcast_{season}_regular.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing raw file: {path}")
        lf = pl.scan_parquet(path).select(COLUMNS).with_columns(
            pl.col("game_date").cast(pl.Date)
        )
        frames.append(lf.with_columns(pl.lit(season).alias("season")))

    raw = pl.concat(frames, how="vertical")

    raw_trunc_by_season = (
        raw.filter(pl.col("events").is_in(EXCLUDED_EVENTS))
        .group_by("season")
        .agg(n_raw_truncated_rows=pl.len())
        .sort("season")
        .collect()
    )

    completed = (
        raw.filter(pl.col("events").is_not_null())
        .sort(["game_pk", "at_bat_number", "pitch_number"])
        .unique(subset=["game_pk", "at_bat_number", "batter"], keep="last")
        .with_columns(
            pl.col("events").is_in(K_EVENTS).cast(pl.Int8).alias("y"),
        )
    )

    excluded = (
        completed.filter(pl.col("events").is_in(EXCLUDED_EVENTS))
        .group_by("season")
        .agg(n_pa_excluded=pl.len())
        .sort("season")
        .collect()
    )

    pa = (
        completed.filter(~pl.col("events").is_in(EXCLUDED_EVENTS))
        .select(
            "game_pk",
            "game_date",
            "season",
            "at_bat_number",
            "batter",
            "pitcher",
            "p_throws",
            "stand",
            "events",
            "inning_topbot",
            "y",
        )
        .collect()
    )

    # pitcher_role: first pitcher of record per (game_pk, side); opener-inclusive.
    # Side of a PA = its inning_topbot ("Top" = away team batting, "Bot" = home).
    first_pitcher = (
        pa.sort(["game_pk", "inning_topbot", "at_bat_number"])
        .unique(subset=["game_pk", "inning_topbot"], keep="first")
        .select(
            "game_pk",
            pl.col("inning_topbot").alias("side"),
            pl.col("pitcher").alias("first_pitcher_of_record"),
        )
    )
    pa = (
        pa.join(
            first_pitcher,
            left_on=["game_pk", "inning_topbot"],
            right_on=["game_pk", "side"],
            how="left",
        )
        .with_columns(
            pl.when(pl.col("pitcher") == pl.col("first_pitcher_of_record"))
            .then(pl.lit("starter_pa"))
            .otherwise(pl.lit("reliever_pa"))
            .cast(pl.String)
            .alias("pitcher_role")
        )
        .drop("first_pitcher_of_record")
    )

    counts = pa.group_by("season").agg(
        n_pas=pl.len(), n_k=pl.col("y").sum(), k_rate=pl.col("y").mean()
    ).sort("season")

    dup_check = pa.group_by("game_pk", "at_bat_number", "batter").agg(n=pl.len()).filter(pl.col("n") > 1).height
    stand_nulls = pa.filter(pl.col("stand").is_null()).height
    truncated_left = pa.filter(pl.col("events").is_in(EXCLUDED_EVENTS)).height

    pa.write_parquet(OUT_DIR / "pa_table.parquet")

    lines = []
    lines.append("PA table per-season counts (2022-2025; 2026 reserved; truncated_pa EXCLUDED):")
    for row in counts.iter_rows(named=True):
        lines.append(
            f"  {row['season']}: {row['n_pas']:,} PAs, {row['n_k']:,} Ks, rate {row['k_rate']:.4f}"
        )
    lines.append(f"  TOTAL: {pa.height:,} PAs, {pa['y'].sum():,} Ks, rate {pa['y'].mean():.4f}")
    lines.append(f"duplicate PA identities after dedupe: {dup_check}")
    lines.append(f"rows with null stand (derived fallback needed): {stand_nulls}")
    lines.append(f"truncated_pa rows remaining in table (must be 0): {truncated_left}")
    lines.append("")
    lines.append("truncation exclusions (terminal event truncated_pa, excluded from the completed-PA table):")
    raw_trunc = {r["season"]: r["n_raw_truncated_rows"] for r in raw_trunc_by_season.iter_rows(named=True)}
    exc = {r["season"]: r["n_pa_excluded"] for r in excluded.iter_rows(named=True)}
    for season in SEASONS:
        lines.append(
            f"  {season}: {exc.get(season, 0):,} completed-PA rows excluded "
            f"({raw_trunc.get(season, 0):,} raw event rows)"
        )
    lines.append(
        f"  TOTAL excluded: {sum(exc.values()):,} completed-PA rows "
        f"({sum(raw_trunc.values()):,} raw event rows)"
    )
    lines.append("")
    lines.append(f"pitcher_role counts: {pa.group_by('pitcher_role').agg(n=pl.len()).sort('pitcher_role').to_dicts()}")
    report = "\n".join(lines)
    (REPORTS / "pa_counts.txt").write_text(report)
    trunc_lines = ["truncation exclusions (terminal event truncated_pa, excluded from the completed-PA table):"]
    for season in SEASONS:
        trunc_lines.append(
            f"  {season}: {exc.get(season, 0):,} completed-PA rows excluded "
            f"({raw_trunc.get(season, 0):,} raw event rows)"
        )
    trunc_lines.append(
        f"  TOTAL excluded: {sum(exc.values()):,} completed-PA rows "
        f"({sum(raw_trunc.values()):,} raw event rows)"
    )
    trunc_lines.append("These rows are excluded from the completed-PA table entirely (v1 kept them as y=0).")
    (REPORTS / "truncation_exclusions.txt").write_text("\n".join(trunc_lines))
    print(report)


if __name__ == "__main__":
    main()
