"""Run denominator-aware stabilization separately for each pitch type."""

from __future__ import annotations

import pandas as pd
import polars as pl

from Python import config
from Python.pitcher_features import PITCH_TYPES

from run_stabilization import StatSpec, analyze


PITCH_DISCIPLINE_SPECS = (
    ("whiff_rate", "Whiffs", "Swings", tuple(range(25, 1001, 25))),
    ("swstr_rate", "Whiffs", "Pitches", tuple(range(50, 2001, 50))),
    ("ball_rate", "Balls", "Pitches", tuple(range(50, 2001, 50))),
    ("csw_rate", "CSW", "Pitches", tuple(range(50, 2001, 50))),
    ("chase_rate", "Chases", "OutZone", tuple(range(25, 1001, 25))),
)
PITCH_CONTACT_SPECS = (
    ("weak_contact_rate", "WeakContact", "xBA_den", tuple(range(10, 401, 10))),
    ("hard_hit_rate", "HardHit", "EV_den", tuple(range(10, 401, 10))),
    ("barrel_rate", "Barrels", "xBA_den", tuple(range(10, 401, 10))),
    ("gb_rate", "GB", "BIP", tuple(range(10, 401, 10))),
    ("xBA", "xBA_num", "xBA_den", tuple(range(10, 401, 10))),
    ("wOBA", "wOBA_num", "wOBA_den", tuple(range(10, 401, 10))),
    ("xwOBA", "xwOBA_num", "wOBA_den", tuple(range(10, 401, 10))),
)


def descriptive_summary(frame: pl.DataFrame) -> pl.DataFrame:
    """Pool count pairs by pitch type without averaging per-game rates."""
    totals = (
        "Pitches", "Swings", "Whiffs", "Balls", "CSW", "OutZone", "Chases",
        "BIP", "GB", "WeakContact", "HardHit", "Barrels", "EV_den", "xBA_den",
        "wOBA_num", "wOBA_den", "xwOBA_num",
    )
    return (
        frame.group_by("pitch_type")
        .agg(*(pl.col(column).sum() for column in totals))
        .with_columns(
            (pl.col("Whiffs") / pl.col("Swings")).alias("whiff_rate"),
            (pl.col("Whiffs") / pl.col("Pitches")).alias("swstr_rate"),
            (pl.col("Balls") / pl.col("Pitches")).alias("ball_rate"),
            (pl.col("CSW") / pl.col("Pitches")).alias("csw_rate"),
            (pl.col("Chases") / pl.col("OutZone")).alias("chase_rate"),
            (pl.col("GB") / pl.col("BIP")).alias("gb_rate"),
            (pl.col("WeakContact") / pl.col("xBA_den")).alias("weak_rate"),
            (pl.col("HardHit") / pl.col("EV_den")).alias("hard_hit_rate"),
            (pl.col("Barrels") / pl.col("xBA_den")).alias("barrel_rate"),
            (pl.col("wOBA_num") / pl.col("wOBA_den")).alias("wOBA"),
            (pl.col("xwOBA_num") / pl.col("wOBA_den")).alias("xwOBA"),
        )
        .sort("Pitches", descending=True)
    )


def main() -> None:
    dev = (
        pl.read_parquet(config.PITCH_TYPE_GAMES_PATH)
        .filter(pl.col("season").is_in(config.FEATURE_RESEARCH_SEASONS))
        .sort(["pitcher", "game_date", "pitch_type"])
    )
    frame = dev.to_pandas()
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected dev seasons {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )

    output_dir = config.OUTPUT_DIR / "stabilization" / "pitch_type"
    output_dir.mkdir(parents=True, exist_ok=True)
    descriptive_summary(dev).write_csv(
        output_dir / "pitch_type_descriptive_summary.csv"
    )
    summaries: list[dict[str, object]] = []
    for pitch_type in PITCH_TYPES:
        pitch_frame = frame[frame["pitch_type"] == pitch_type].copy()
        if pitch_frame.empty:
            continue
        for name, numerator, denominator, targets in (
            *PITCH_DISCIPLINE_SPECS,
            *PITCH_CONTACT_SPECS,
        ):
            print(f"Analyzing {pitch_type} {name}...")
            summaries.extend(
                analyze(
                    pitch_frame,
                    StatSpec(
                        f"pitcher_{pitch_type}",
                        name,
                        numerator,
                        denominator,
                        targets,
                    ),
                    id_col="pitcher",
                    output_dir=output_dir,
                    n_boot=300,
                )
            )

    summary = pd.DataFrame(summaries)
    summary.to_csv(output_dir / "pitch_type_crossings_summary.csv", index=False)
    print(summary.to_string(index=False))
    print(f"Wrote pitch-type stabilization outputs to {output_dir}")


if __name__ == "__main__":
    main()
