"""Grade logged projections against postgame actuals (K / PA).

Joins ``artifacts/projection_log/projections.parquet`` to Level 1
``pitcher_games`` on ``(game_date, pitcher)``. Run after Statcast + Level 1
refresh so yesterday's games have labels.

Examples:
    python production/grade_projections.py
    python production/grade_projections.py --date 2026-07-27
    python production/grade_projections.py --preferred-only
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402

LOG_DIR = config.OUTPUT_DIR / "projection_log"
LOG_PATH = LOG_DIR / "projections.parquet"
GRADED_PATH = LOG_DIR / "graded.parquet"
SUMMARY_PATH = LOG_DIR / "grade_summary.json"


def _yesterday_et() -> date:
    return datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=1)


def grade_log(
    *,
    slate_date: date | None = None,
    preferred_only: bool = False,
) -> dict[str, object]:
    if not LOG_PATH.exists():
        raise FileNotFoundError(
            f"No projection log at {LOG_PATH}. Run production/log_projections.py first."
        )
    if not config.PITCHER_GAMES_PATH.exists():
        raise FileNotFoundError(
            f"Missing {config.PITCHER_GAMES_PATH}. Refresh Level 1 first."
        )

    log = pl.read_parquet(LOG_PATH).with_columns(pl.col("game_date").cast(pl.Date))
    target = slate_date or _yesterday_et()
    day = log.filter(pl.col("game_date") == target)
    if preferred_only and "is_preferred" in day.columns:
        day = day.filter(pl.col("is_preferred"))
    if day.is_empty():
        raise ValueError(
            f"No logged rows for {target}. "
            f"Available dates: {log['game_date'].unique().sort().to_list()}"
        )

    actuals = (
        pl.scan_parquet(config.PITCHER_GAMES_PATH)
        .select(
            pl.col("game_date").cast(pl.Date),
            pl.col("pitcher").cast(pl.Int64),
            pl.col("K").cast(pl.Float64).alias("actual_K"),
            pl.col("PA").cast(pl.Float64).alias("actual_PA"),
            (pl.col("K") / pl.col("PA").clip(lower_bound=1)).alias("actual_k_rate"),
        )
        .collect()
    )

    graded = day.join(actuals, on=["game_date", "pitcher"], how="left").with_columns(
        (pl.col("expected_K") - pl.col("actual_K")).alias("residual_K"),
        (pl.col("projected_tbf") - pl.col("actual_PA")).alias("residual_TBF"),
        (pl.col("k_rate_pred") - pl.col("actual_k_rate")).alias("residual_k_rate"),
        pl.col("actual_K").is_not_null().alias("has_actual"),
    )

    matched = graded.filter(pl.col("has_actual"))
    summary: dict[str, object] = {
        "slate_date": target.isoformat(),
        "preferred_only": preferred_only,
        "n_logged": day.height,
        "n_matched": matched.height,
        "n_missing_actual": int(graded.filter(~pl.col("has_actual")).height),
        "graded_path": str(GRADED_PATH),
    }
    if matched.height:
        summary.update(
            {
                "mae_K": float(matched["residual_K"].abs().mean()),
                "mean_residual_K": float(matched["residual_K"].mean()),
                "mae_TBF": float(matched["residual_TBF"].abs().mean()),
                "mean_residual_TBF": float(matched["residual_TBF"].mean()),
                "mae_k_rate": float(matched["residual_k_rate"].abs().mean()),
                "mean_expected_K": float(matched["expected_K"].mean()),
                "mean_actual_K": float(matched["actual_K"].mean()),
            }
        )
        if "starter_source" in matched.columns:
            by_src = (
                matched.group_by("starter_source")
                .agg(
                    pl.len().alias("n"),
                    pl.col("residual_K").abs().mean().alias("mae_K"),
                    pl.col("residual_K").mean().alias("mean_residual_K"),
                )
                .sort("starter_source")
            )
            summary["by_starter_source"] = by_src.to_dicts()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Keep one graded table; replace rows for this slate_date (+ preferred filter tag).
    graded = graded.with_columns(pl.lit(preferred_only).alias("grade_preferred_only"))
    if GRADED_PATH.exists():
        prior = pl.read_parquet(GRADED_PATH).with_columns(
            pl.col("game_date").cast(pl.Date)
        )
        if "grade_preferred_only" not in prior.columns:
            prior = prior.with_columns(pl.lit(False).alias("grade_preferred_only"))
        prior = prior.filter(
            ~(
                (pl.col("game_date") == target)
                & (pl.col("grade_preferred_only") == preferred_only)
            )
        )
        out = pl.concat([prior, graded], how="diagonal_relaxed")
    else:
        out = graded
    out.write_parquet(GRADED_PATH)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Slate date to grade (default: yesterday ET).",
    )
    parser.add_argument(
        "--preferred-only",
        action="store_true",
        help="Grade only is_preferred rows (MLB on disagreement).",
    )
    args = parser.parse_args()
    summary = grade_log(slate_date=args.date, preferred_only=args.preferred_only)
    print(json.dumps(summary, indent=2))
    print(f"Wrote {GRADED_PATH}")


if __name__ == "__main__":
    main()
