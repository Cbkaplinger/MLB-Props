"""Research-only pregame lineup capture adapter (no writes, no live calls).

Reads the production-captured RotoGrinders lineup snapshots
(`data/processed/daily_lineups_*.parquet`, written by the live pipeline)
as IMMUTABLE inputs and enforces the forecast-cutoff contract for the
future deployment-relevant B-vs-A comparison:

- a snapshot is usable only if `fetched_at` <= forecast cutoff;
- the latest valid snapshot per (game_pk, team) wins (revisions kept
  upstream, never mutated here);
- a usable lineup has exactly 9 unique ordered slots;
- any failure returns an explicit fallback reason (canonical-A fallback),
  never a deleted row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

SLOT_COUNT = 9

REASON_OK = "ok"
REASON_MISSING = "missing_no_snapshot"
REASON_LATE_ONLY = "all_snapshots_after_cutoff"
REASON_NOT_9_SLOTS = "not_9_unique_slots"


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_snapshots(paths: list[Path]) -> pl.DataFrame:
    """Read captured snapshot files read-only; never writes."""
    frames = [pl.read_parquet(p) for p in paths]
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def select_pregame_lineup(snaps: pl.DataFrame, game_pk: int, team: str,
                          forecast_cutoff: datetime) -> dict:
    """Latest cutoff-valid snapshot with 9 unique ordered slots.

    Returns {ok, reason, batters, status, fetched_at}. Ordered batters =
    batting_order 1..9; missing slots -> not-9 reason (no imputation).
    """
    cutoff = _utc(forecast_cutoff)
    g = snaps.filter(
        (pl.col("game_pk") == game_pk) & (pl.col("team") == team))
    if g.height == 0:
        return {"ok": False, "reason": REASON_MISSING, "batters": None,
                "status": None, "fetched_at": None}
    dt = g.schema["fetched_at"]
    if dt == pl.String:
        g = g.with_columns(pl.col("fetched_at")
                           .str.to_datetime(time_zone="UTC",
                                            strict=False).alias("fetched_at"))
    elif isinstance(dt, pl.Datetime) and dt.time_zone is None:
        g = g.with_columns(pl.col("fetched_at")
                           .dt.replace_time_zone("UTC").alias("fetched_at"))
    elif isinstance(dt, pl.Datetime):
        g = g.with_columns(pl.col("fetched_at")
                           .dt.convert_time_zone("UTC").alias("fetched_at"))
    g = g.filter(pl.col("fetched_at") <= cutoff)
    if g.height == 0:
        return {"ok": False, "reason": REASON_LATE_ONLY, "batters": None,
                "status": None, "fetched_at": None}
    latest = g.sort("fetched_at").row(-1, named=True)
    slots = (g.filter(pl.col("fetched_at") == latest["fetched_at"])
             .unique(["batting_order", "batter"], keep="last"))
    n_slots = slots["batting_order"].n_unique()
    n_players = slots["batter"].n_unique()
    if n_slots != SLOT_COUNT or n_players != SLOT_COUNT:
        return {"ok": False, "reason": REASON_NOT_9_SLOTS,
                "batters": None, "status": latest.get("lineup_status"),
                "fetched_at": latest["fetched_at"]}
    ordered = (slots.sort("batting_order")["batter"].cast(pl.Int64)
               .to_list())
    return {"ok": True, "reason": REASON_OK, "batters": ordered,
            "status": latest.get("lineup_status"),
            "fetched_at": latest["fetched_at"]}


def opportunity_sequence(lineup: dict, n: int) -> list[int] | None:
    """Cycled ordered lineup -> exactly n opportunities (repeats kept)."""
    if not lineup["ok"]:
        return None
    batters = lineup["batters"]
    reps = n // SLOT_COUNT + 1
    return (batters * reps)[:n]
