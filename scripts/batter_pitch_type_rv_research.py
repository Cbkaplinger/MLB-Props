"""Research-only batter pitch-type run-value reliability audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import polars as pl

from Python import config
from Python.pitcher_features import CANON_PITCH, PITCH_TYPES
from Python.statcast import (
    add_event_flags,
    add_plate_discipline_flags,
    discipline_count_exprs,
    load_statcast_years,
    xwoba_num,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EDA_DIR = PROJECT_ROOT / "models" / "Strikeout-Model" / "research"
if str(EDA_DIR) not in sys.path:
    sys.path.insert(0, str(EDA_DIR))

from run_stabilization import StatSpec, analyze  # noqa: E402


OUTPUT_DIR = config.OUTPUT_DIR / "stabilization" / "expanded" / "batter_pitch_type"
BUCKETS = {
    "ff": "fastball",
    "si": "fastball",
    "fc": "fastball",
    "sl": "breaking",
    "st": "breaking",
    "cu": "breaking",
    "ch": "offspeed",
    "fs": "offspeed",
}


def build_games() -> pl.DataFrame:
    raw = load_statcast_years(
        config.FEATURE_RESEARCH_SEASONS,
        columns=(
            "game_pk",
            "game_date",
            "batter",
            "pitch_type",
            "type",
            "description",
            "zone",
            "events",
            "bb_type",
            "launch_speed",
            "launch_angle",
            "launch_speed_angle",
            "estimated_ba_using_speedangle",
            "estimated_woba_using_speedangle",
            "woba_value",
            "woba_denom",
            "delta_run_exp",
        ),
    )
    raw = raw.with_columns(
        pl.col(column).cast(pl.Float64).fill_nan(None)
        for column in (
            "launch_speed",
            "launch_angle",
            "estimated_ba_using_speedangle",
            "estimated_woba_using_speedangle",
            "woba_value",
            "delta_run_exp",
        )
    )
    flagged = add_plate_discipline_flags(add_event_flags(raw)).with_columns(
        pl.col("pitch_type")
        .replace_strict(CANON_PITCH, default=None)
        .alias("pitch_type"),
        xwoba_num().alias("xwOBA_num"),
    )
    return (
        flagged
        .filter(pl.col("pitch_type").is_not_null())
        .group_by("game_pk", "game_date", "batter", "pitch_type")
        .agg(
            pl.col("delta_run_exp").sum().alias("RV_num"),
            pl.col("delta_run_exp").is_not_null().sum().alias("RV_den"),
            pl.len().alias("Pitches"),
            pl.col("is_pa").sum().alias("PA"),
            pl.col("is_k").sum().alias("K"),
            pl.col("is_bb").sum().alias("BB"),
            pl.col("is_hr").sum().alias("HR"),
            pl.col("is_whiff").sum().alias("Whiffs"),
            (pl.col("type") == "X").sum().alias("BIP"),
            *discipline_count_exprs(),
            (
                (pl.col("type") == "X") & (pl.col("launch_speed") >= 95.0)
            ).sum().alias("HardHit"),
            (
                (pl.col("type") == "X") & (pl.col("launch_speed_angle") == 6)
            ).sum().alias("Barrels"),
            pl.when(pl.col("type") == "X")
            .then(pl.col("launch_speed"))
            .sum()
            .alias("EV_num"),
            (
                (pl.col("type") == "X") & pl.col("launch_speed").is_not_null()
            ).sum().alias("EV_den"),
            pl.when(pl.col("type") == "X")
            .then(pl.col("estimated_ba_using_speedangle"))
            .sum()
            .alias("xBA_num"),
            (
                (pl.col("type") == "X")
                & pl.col("estimated_ba_using_speedangle").is_not_null()
            ).sum().alias("xBA_den"),
            pl.col("woba_value").sum().alias("wOBA_num"),
            pl.col("woba_denom").sum().alias("wOBA_den"),
            pl.col("xwOBA_num").sum(),
        )
        .with_columns(
            pl.when(pl.col("Swings") > 0)
            .then(pl.col("Whiffs") / pl.col("Swings"))
            .otherwise(None)
            .alias("whiff_rate"),
            pl.when(pl.col("EV_den") > 0)
            .then(pl.col("HardHit") / pl.col("EV_den"))
            .otherwise(None)
            .alias("hard_hit_rate"),
            pl.when(pl.col("xBA_den") > 0)
            .then(pl.col("Barrels") / pl.col("xBA_den"))
            .otherwise(None)
            .alias("barrel_rate"),
            pl.when(pl.col("EV_den") > 0)
            .then(pl.col("EV_num") / pl.col("EV_den"))
            .otherwise(None)
            .alias("avg_exit_velocity"),
            pl.when(pl.col("xBA_den") > 0)
            .then(pl.col("xBA_num") / pl.col("xBA_den"))
            .otherwise(None)
            .alias("xBA"),
            pl.when(pl.col("wOBA_den") > 0)
            .then(pl.col("wOBA_num") / pl.col("wOBA_den"))
            .otherwise(None)
            .alias("wOBA"),
            pl.when(pl.col("wOBA_den") > 0)
            .then(pl.col("xwOBA_num") / pl.col("wOBA_den"))
            .otherwise(None)
            .alias("xwOBA"),
        )
        .sort(["batter", "game_date", "pitch_type"])
    )


def coverage_table(games: pl.DataFrame) -> pd.DataFrame:
    by_player = games.group_by("pitch_type", "batter").agg(
        pl.col("RV_den").sum().alias("pitches")
    )
    rows: list[dict[str, object]] = []
    for pitch_type in PITCH_TYPES:
        values = by_player.filter(pl.col("pitch_type") == pitch_type)["pitches"]
        rows.append(
            {
                "pitch_group": pitch_type,
                "batters": len(values),
                "median_pitches": float(values.median()) if len(values) else 0.0,
                **{
                    f"batters_ge_{threshold}": int((values >= threshold).sum())
                    for threshold in (100, 200, 500, 1000)
                },
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    games = build_games()
    games.write_parquet(OUTPUT_DIR / "batter_pitch_type_games.parquet")
    coverage = coverage_table(games)
    coverage.to_csv(OUTPUT_DIR / "coverage.csv", index=False)

    detailed = games.to_pandas()
    summaries: list[dict[str, object]] = []
    targets = tuple(range(50, 2001, 50))
    for pitch_type in PITCH_TYPES:
        subset = detailed[detailed["pitch_type"] == pitch_type].copy()
        summaries.extend(
            analyze(
                subset,
                StatSpec(
                    f"batter_{pitch_type}",
                    "rv_per_pitch",
                    "RV_num",
                    "RV_den",
                    targets,
                ),
                id_col="batter",
                output_dir=OUTPUT_DIR,
                n_boot=300,
            )
        )

    bucket_games = (
        games.with_columns(
            pl.col("pitch_type").replace_strict(BUCKETS).alias("pitch_group")
        )
        .group_by("game_pk", "game_date", "batter", "pitch_group")
        .agg(
            pl.col("RV_num").sum(),
            pl.col("RV_den").sum(),
            pl.col("Pitches").sum(),
        )
        .sort(["batter", "game_date", "pitch_group"])
    )
    bucket_frame = bucket_games.to_pandas()
    for bucket in ("fastball", "breaking", "offspeed"):
        subset = bucket_frame[bucket_frame["pitch_group"] == bucket].copy()
        summaries.extend(
            analyze(
                subset,
                StatSpec(
                    f"batter_{bucket}",
                    "rv_per_pitch",
                    "RV_num",
                    "RV_den",
                    targets,
                ),
                id_col="batter",
                output_dir=OUTPUT_DIR,
                n_boot=300,
            )
        )
    summary = pd.DataFrame(summaries)
    summary.to_csv(OUTPUT_DIR / "crossings_summary.csv", index=False)
    reliable = summary[
        (summary["threshold"] == 0.5) & summary["reliably_estimable"]
    ]["population"].tolist()
    feasibility = {
        "research_seasons": list(config.FEATURE_RESEARCH_SEASONS),
        "holdout_season_not_read": config.HOLDOUT_SEASON,
        "reliable_at_ci_low_r_0_5": reliable,
        "production_integration": False,
        "decision": (
            "defer matchup integration; require shrinkage and nested ablation"
            if not reliable
            else "reliability cleared for listed groups only; shrinkage design remains"
        ),
    }
    (OUTPUT_DIR / "feasibility.json").write_text(
        json.dumps(feasibility, indent=2), encoding="utf-8"
    )
    print(json.dumps(feasibility, indent=2))


if __name__ == "__main__":
    main()
