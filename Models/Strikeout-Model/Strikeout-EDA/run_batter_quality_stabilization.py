"""Stabilize the added batter quality and batted-ball research rates."""

from __future__ import annotations

import pandas as pd
import polars as pl

from Python import config

from run_stabilization import BATTER_SPECS, analyze


METRICS = {
    "babip",
    "hard_hit_rate",
    "barrel_rate",
    "sweet_spot_rate",
    "avg_exit_velocity",
    "avg_launch_angle",
    "xBA",
    "wOBA",
    "xwOBA",
    "hr_rate",
    "fb_rate",
    "hr_fb_rate",
    "pull_air_rate",
    "rv_per_pitch",
}


def main() -> None:
    frame = (
        pl.read_parquet(config.BATTER_GAMES_PATH)
        .with_columns(pl.col("game_date").dt.year().alias("season"))
        .filter(pl.col("season").is_in(config.FEATURE_RESEARCH_SEASONS))
        .sort(["batter", "game_date"])
        .to_pandas()
    )
    observed = tuple(sorted(frame["season"].unique()))
    if observed != config.FEATURE_RESEARCH_SEASONS:
        raise ValueError(
            f"expected dev seasons {config.FEATURE_RESEARCH_SEASONS}, got {observed}"
        )

    output_dir = (
        config.OUTPUT_DIR / "stabilization" / "expanded" / "batter_quality"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    for spec in BATTER_SPECS:
        if spec.name not in METRICS:
            continue
        print(f"Analyzing batter {spec.name}...")
        summaries.extend(
            analyze(
                frame,
                spec,
                id_col="batter",
                output_dir=output_dir,
                n_boot=300,
            )
        )

    summary = pd.DataFrame(summaries)
    summary.to_csv(
        output_dir / "batter_quality_crossings_summary.csv",
        index=False,
    )
    print(summary.to_string(index=False))
    print(f"Wrote batter quality stabilization outputs to {output_dir}")


if __name__ == "__main__":
    main()
