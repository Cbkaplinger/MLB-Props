"""Append daily dual-source projections to a durable log (no notebook clutter).

Logs every scored row (RG + MLB probable when they disagree) plus flags.
Opponent lineup features always come from the RotoGrinders batting-order scrape;
only the starting pitcher ID differs by ``starter_source``.

Examples:
    python production/log_projections.py --allow-stale
    python production/log_projections.py --date 2026-07-28 --allow-stale
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES  # noqa: E402
from Python.daily_lineups import build_daily_slate  # noqa: E402
from Python.live_assembly import (  # noqa: E402
    build_live_feature_frame,
    daily_projection_board,
    score_frame,
)

LOG_DIR = config.OUTPUT_DIR / "projection_log"
LOG_PATH = LOG_DIR / "projections.parquet"
META_PATH = LOG_DIR / "last_log.json"

_KEEP = [
    "game_pk",
    "game_date",
    "away_team",
    "home_team",
    "is_home",
    "player_name",
    "pitcher",
    "starter_source",
    "starter_disagreement",
    "is_preferred",
    "rg_pitcher_id",
    "mlb_probable_pitcher_id",
    "expected_K",
    "projected_tbf",
    "k_rate_pred",
    "days_rest",
    "opp_lineup_size",
    "opp_lineup_k",
    "opp_lineup_k_vs_hand",
    "opp_lineup_whiff",
    "opp_lineup_swstr",
    "opp_lineup_chase",
]


def _line_cols(frame: pl.DataFrame) -> list[str]:
    cols: list[str] = []
    for line in PROJECTION_K_LINES:
        stem = str(line).replace(".", "_")
        for name in (
            f"p_over_{stem}",
            f"p_over_{stem}_cal",
            f"fair_amer_{stem}",
        ):
            if name in frame.columns:
                cols.append(name)
    for meta in ("calibration_version", "calibration_method", "calibration_scope"):
        if meta in frame.columns:
            cols.append(meta)
    return cols


def _p_over_cols(frame: pl.DataFrame) -> list[str]:
    """Display line probs: prefer calibrated when present."""
    cols: list[str] = []
    for line in PROJECTION_K_LINES:
        stem = str(line).replace(".", "_")
        cal = f"p_over_{stem}_cal"
        raw = f"p_over_{stem}"
        if cal in frame.columns:
            cols.append(cal)
        elif raw in frame.columns:
            cols.append(raw)
    return cols


def _print_preferred_board(board: pl.DataFrame) -> None:
    """Print preferred SP board: team, name, matchup, xK, p(over) by line."""
    view = board
    if "is_preferred" in view.columns:
        view = view.filter(pl.col("is_preferred"))
    if "is_home" in view.columns and "away_team" in view.columns:
        view = view.with_columns(
            pl.when(pl.col("is_home"))
            .then(pl.col("home_team"))
            .otherwise(pl.col("away_team"))
            .alias("pitcher_team")
        )
    if "expected_K" in view.columns:
        view = view.with_columns(pl.col("expected_K").alias("xK")).sort(
            "expected_K", descending=True
        )

    front = [
        c
        for c in ("pitcher_team", "player_name", "away_team", "home_team", "xK")
        if c in view.columns
    ]
    cols = front + _p_over_cols(view)
    view = view.select(cols)

    round_exprs = []
    for c in view.columns:
        if view.schema[c] in (pl.Float32, pl.Float64):
            digits = 3 if c == "xK" or c.startswith("p_over_") else 2
            round_exprs.append(pl.col(c).round(digits))
    if round_exprs:
        view = view.with_columns(round_exprs)

    print()
    print(f"Preferred SP board ({view.height} pitchers)")
    print("-" * 72)
    with pl.Config(
        tbl_rows=-1,
        tbl_cols=-1,
        tbl_width_chars=200,
        fmt_str_lengths=40,
    ):
        print(view)
    print("-" * 72)


def log_slate(
    *,
    game_date: date | None = None,
    allow_stale: bool = False,
    print_board: bool = True,
) -> dict[str, object]:
    slate = build_daily_slate(
        game_date=game_date,
        require_probable_match=False,
    )
    features, build_meta = build_live_feature_frame(
        slate,
        allow_stale=allow_stale,
        dual_starters=True,
    )
    scored_pd, report = score_frame(features, lines=PROJECTION_K_LINES)
    board = daily_projection_board(scored_pd, lines=PROJECTION_K_LINES)

    logged_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    keep = [c for c in _KEEP if c in board.columns] + _line_cols(board)
    batch = board.select(keep).with_columns(
        pl.lit(logged_at).alias("logged_at_utc"),
        pl.lit(str(report.get("k_rate_sha256"))).alias("k_rate_sha256"),
        pl.lit(str(report.get("tbf_sha256"))).alias("tbf_sha256"),
        pl.lit("rg_lineups").alias("lineup_source"),
        pl.lit(
            "Opponent batting order is always RotoGrinders; "
            "starter_source only swaps the SP identity."
        ).alias("lineup_note"),
    )
    # Ensure game_date is Date for joins.
    if "game_date" in batch.columns:
        batch = batch.with_columns(pl.col("game_date").cast(pl.Date))

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    slate_dates = batch["game_date"].unique().to_list()
    if LOG_PATH.exists():
        prior = pl.read_parquet(LOG_PATH)
        if "game_date" in prior.columns:
            prior = prior.with_columns(pl.col("game_date").cast(pl.Date))
            prior = prior.filter(~pl.col("game_date").is_in(slate_dates))
        combined = pl.concat([prior, batch], how="diagonal_relaxed")
    else:
        combined = batch
    combined.write_parquet(LOG_PATH)

    if print_board:
        _print_preferred_board(board)

    meta = {
        "logged_at_utc": logged_at,
        "path": str(LOG_PATH),
        "slate_dates": [str(d) for d in slate_dates],
        "n_rows_logged": batch.height,
        "n_preferred": int(batch.filter(pl.col("is_preferred")).height)
        if "is_preferred" in batch.columns
        else None,
        "build_meta": build_meta,
        "mean_expected_K": report.get("mean_expected_K"),
        "k_rate_sha256": report.get("k_rate_sha256"),
        "tbf_sha256": report.get("tbf_sha256"),
    }
    META_PATH.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None)
    parser.add_argument("--allow-stale", action="store_true")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Skip printing the preferred SP board.",
    )
    args = parser.parse_args()
    meta = log_slate(
        game_date=args.date,
        allow_stale=args.allow_stale,
        print_board=not args.quiet,
    )
    print(json.dumps(meta, indent=2, default=str))
    print(f"Appended/replaced log -> {LOG_PATH}")


if __name__ == "__main__":
    main()
