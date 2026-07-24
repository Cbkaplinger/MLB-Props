"""Map pitcher rolling windows to denominator-aware stabilization evidence."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from Python import config
from Python.pitcher_rolling import (
    DEFAULT_MEAN_COLS,
    DEFAULT_MEAN_WINDOWS,
    DEFAULT_RATE_STATS,
    DEFAULT_RATE_WINDOWS,
)


THRESHOLD = 0.50
GAP_COLUMNS = (
    "feature",
    "current_default_window",
    "stabilization_crossing_point",
    "gap_direction",
    "denominator_type",
    "metric",
    "metric_family",
    "crossing_denominator",
    "median_crossing",
    "typical_starts_at_crossing",
    "nearest_supported_window",
    "stabilization_status",
)


@dataclass(frozen=True)
class MetricSpec:
    metric: str
    family: str
    windows: tuple[int, ...]
    denominator: str | None


def denominator_type(denominator: str | None) -> str:
    """Collapse source denominators into the requested modeling units."""
    if denominator == "Swings":
        return "swing"
    if denominator == "OutZone":
        return "zone"
    if denominator in {
        "PA",
        "BIP",
        "BABIP_den",
        "xBA_den",
        "wOBA_den",
        "FirstPitches",
    }:
        return "PA"
    return "pitch"


def metric_inventory() -> tuple[MetricSpec, ...]:
    """Return every rate/physics/mechanics/usage metric rolled by the module."""
    rate_specs = tuple(
        MetricSpec(name, "rate", DEFAULT_RATE_WINDOWS, denominator)
        for name, (_numerator, denominator) in DEFAULT_RATE_STATS.items()
    )

    mean_specs: list[MetricSpec] = []
    for name in DEFAULT_MEAN_COLS:
        if "_usage_v" in name:
            family = "usage"
        elif name in {"extension", "rel_x", "rel_z", "rel_x_sd", "rel_z_sd"}:
            family = "mechanics"
        else:
            family = "physics"
        mean_specs.append(MetricSpec(name, family, DEFAULT_MEAN_WINDOWS, "Pitches"))

    generated = (
        MetricSpec("arm_angle", "mechanics", DEFAULT_MEAN_WINDOWS, "arm_angle_den"),
        MetricSpec("siera_mlb", "rate", DEFAULT_MEAN_WINDOWS, "PA"),
        MetricSpec("rv_per_100", "rate", DEFAULT_MEAN_WINDOWS, "RV_den"),
        MetricSpec("FIP", "rate", DEFAULT_MEAN_WINDOWS, "PA"),
        MetricSpec("xFIP", "rate", DEFAULT_MEAN_WINDOWS, "PA"),
    )
    return (*rate_specs, *mean_specs, *generated)


def _crossing_name(metric: str) -> str:
    return {"rv_per_100": "rv_per_pitch"}.get(metric, metric)


def _classify(crossing_games: float, windows: tuple[int, ...]) -> str:
    """Classify only material gaps outside the supported discrete window set."""
    if pd.isna(crossing_games):
        return "not assessed"
    lower, upper = min(windows), max(windows)
    lower_midpoint = lower - (windows[1] - lower) / 2
    upper_midpoint = upper + (upper - windows[-2]) / 2
    if crossing_games < lower_midpoint:
        return "over-windowed"
    if crossing_games > upper_midpoint:
        return "under-windowed"
    return "adequate"


def build_gap_table(crossings: pd.DataFrame) -> pd.DataFrame:
    """Join the r=.50 crossing table to the rolling metric inventory."""
    evidence = crossings.loc[
        (crossings["population"] == "pitcher")
        & crossings["threshold"].eq(THRESHOLD)
    ].set_index("stat")

    rows: list[dict[str, object]] = []
    for spec in metric_inventory():
        crossing_name = _crossing_name(spec.metric)
        match = evidence.loc[crossing_name] if crossing_name in evidence.index else None
        crossing = float(match["median_crossing"]) if match is not None else float("nan")
        starts = (
            float(match["typical_starts_at_median_crossing"])
            if match is not None
            else float("nan")
        )
        crossing_denominator = (
            str(match["denominator"]) if match is not None else spec.denominator
        )
        nearest = (
            min(spec.windows, key=lambda window: abs(window - starts))
            if pd.notna(starts)
            else None
        )
        point = (
            f"{crossing:g} {crossing_denominator} (~{starts:.2f} games)"
            if pd.notna(crossing)
            else "not studied"
        )
        rows.append(
            {
                "feature": spec.metric,
                "current_default_window": "/".join(
                    f"P{window}" for window in spec.windows
                ),
                "stabilization_crossing_point": point,
                "gap_direction": _classify(starts, spec.windows),
                "denominator_type": denominator_type(crossing_denominator),
                "metric": spec.metric,
                "metric_family": spec.family,
                "crossing_denominator": crossing_denominator,
                "median_crossing": crossing,
                "typical_starts_at_crossing": starts,
                "nearest_supported_window": (
                    f"P{nearest}" if nearest is not None else ""
                ),
                "stabilization_status": (
                    "reliably estimable"
                    if match is not None and bool(match["reliably_estimable"])
                    else "crossing observed; CI support insufficient"
                    if match is not None
                    else "not studied"
                ),
            }
        )
    return pd.DataFrame(rows, columns=GAP_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--crossings",
        type=Path,
        default=config.OUTPUT_DIR
        / "stabilization"
        / "expanded"
        / "crossings_summary.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=config.OUTPUT_DIR
        / "feature_research"
        / "window_stabilization_gap.csv",
    )
    args = parser.parse_args()

    table = build_gap_table(pd.read_csv(args.crossings))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.output, index=False)
    print(table["gap_direction"].value_counts(dropna=False).to_string())
    print(f"Wrote {len(table)} metric mappings to {args.output}")


if __name__ == "__main__":
    main()
