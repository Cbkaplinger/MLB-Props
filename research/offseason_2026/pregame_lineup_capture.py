"""Research-only pregame lineup capture adapter (no writes, no live calls).

Reads the production-captured RotoGrinders lineup snapshots
(`data/processed/daily_lineups_*.parquet`, written by the live pipeline)
as IMMUTABLE inputs and enforces the forecast-cutoff contract for the
future deployment-relevant B-vs-A comparison:

TIMESTAMP CONTRACT (writer side, documented here):
- the production writer stores `fetched_at` at ingestion, UTC;
  stored-naive values are interpreted as UTC per that contract;
- `forecast_cutoff` MUST be timezone-aware (naive -> ValueError) and is
  normalized to UTC before comparison. Never inferred from data.

ACCEPTANCE POLICY (explicit; never chosen from observed outcomes):
- mode `confirmed_only` (PILOT DEFAULT): only a cutoff-valid COMPLETE
  (9 unique ordered slots) snapshot with lineup_status "confirmed" is
  accepted; a full projected lineup returns REASON_PROJECTED_ONLY
  (canonical-A fallback).
- mode `projected_allowed` (explicit future research; NOT scored in the
  pilot): a complete cutoff-valid snapshot is accepted regardless of
  confirmed/projected status; status is preserved in the receipt.
- selection (PINNED): the LATEST cutoff-valid snapshot wins; if that
  snapshot is partial or conflicting, return the declared fallback --
  no older-revision substitution (older-snapshot fallback would be a
  separate policy with explicit staleness controls; not implemented).
  `forecast_cutoff` tz-awareness is validated BEFORE any UTC coercion.
- unknown/invalid team codes return REASON_UNKNOWN_TEAM (distinct from
  a genuinely missing snapshot); canonical codes normalized via an
  explicit alias map at the caller boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

sys_path = Path(__file__).resolve().parents[2] / "src"
import sys  # noqa: E402
sys.path.insert(0, str(sys_path))
from Python.daily_lineups import canonical_team_code  # noqa: E402

SLOT_COUNT = 9
STATUS_CONFIRMED = "confirmed"

MODE_CONFIRMED_ONLY = "confirmed_only"
MODE_PROJECTED_ALLOWED = "projected_allowed"
MODES = (MODE_CONFIRMED_ONLY, MODE_PROJECTED_ALLOWED)

REASON_OK = "ok"
REASON_MISSING = "missing_no_snapshot"
REASON_LATE_ONLY = "all_snapshots_after_cutoff"
REASON_NOT_9_SLOTS = "not_9_unique_slots"
REASON_PROJECTED_ONLY = "full_projected_confirmed_only_mode"
REASON_UNKNOWN_TEAM = "unknown_team_code"
REASON_MIXED_STATUS = "mixed_lineup_status_latest_snapshot"
REASON_MALFORMED_TIMESTAMP = "malformed_fetched_at"


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(
            "forecast_cutoff must be timezone-aware; got naive %r" % (dt,))
    return dt.astimezone(timezone.utc)


def load_snapshots(paths: list[Path]) -> pl.DataFrame:
    """Read captured snapshot files read-only; never writes."""
    frames = [pl.read_parquet(p) for p in paths]
    if not frames:
        return pl.DataFrame()
    return pl.concat(frames, how="diagonal_relaxed")


def select_pregame_lineup(snaps: pl.DataFrame, game_pk: int, team: str,
                          forecast_cutoff: datetime,
                          mode: str = MODE_CONFIRMED_ONLY) -> dict:
    """Cutoff-valid COMPLETE-snapshot selection with explicit policy.

    Returns {ok, reason, batters, status, fetched_at}. Ordered batters =
    batting_order 1..9; failures return explicit fallback reasons
    (canonical-A fallback), never a deleted row.
    """
    if mode not in MODES:
        raise ValueError("unknown mode: %r" % (mode,))
    cutoff = _aware_utc(forecast_cutoff)
    try:
        team_c = canonical_team_code(str(team).strip().upper())
    except ValueError:
        return {"ok": False, "reason": REASON_UNKNOWN_TEAM,
                "batters": None, "status": None, "fetched_at": None}
    g = snaps.filter(
        (pl.col("game_pk") == game_pk) & (pl.col("team") == team_c))
    if g.height == 0:
        return {"ok": False, "reason": REASON_MISSING, "batters": None,
                "status": None, "fetched_at": None}
    dt = g.schema["fetched_at"]
    # D4: stored-naive timestamps are interpreted as UTC per the
    # documented writer contract; unparseable values raise an explicit
    # fallback (never silently dropped).
    if dt == pl.String:
        try:
            g = g.with_columns(
                pl.col("fetched_at")
                .str.to_datetime(time_zone="UTC", strict=False)
                .alias("fetched_at"))
        except Exception:
            # D4: unparseable timestamps must NOT silently disappear
            # under strict=False; explicit fallback instead.
            return {"ok": False, "reason": REASON_MALFORMED_TIMESTAMP,
                    "batters": None, "status": None, "fetched_at": None}
        if g["fetched_at"].null_count() > 0:
            return {"ok": False, "reason": REASON_MALFORMED_TIMESTAMP,
                    "batters": None, "status": None, "fetched_at": None}
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
    # PINNED SELECTION RULE (owner 2026-10-09): latest cutoff-valid
    # snapshot wins. If that latest snapshot is partial or conflicting,
    # return the declared fallback -- NO older-revision substitution
    # (older-snapshot fallback would be a separate policy with explicit
    # staleness controls; not implemented).
    latest = g.sort("fetched_at")["fetched_at"][-1]
    snap = g.filter(pl.col("fetched_at") == latest)
    # D3: mixed statuses inside one latest snapshot -> explicit fallback
    # (status is a snapshot-level property; per-row conflict is a defect)
    statuses = {s.strip().lower() for s in snap["lineup_status"].to_list()
                if s is not None}
    if len(statuses) > 1:
        return {"ok": False, "reason": REASON_MIXED_STATUS,
                "batters": None, "status": "|".join(sorted(statuses)),
                "fetched_at": latest}
    slots = snap.unique(["batting_order", "batter"], keep="last")
    n_slots = slots["batting_order"].n_unique()
    n_players = slots["batter"].n_unique()
    if n_slots != SLOT_COUNT or n_players != SLOT_COUNT:
        last = snap.row(0, named=True)
        return {"ok": False, "reason": REASON_NOT_9_SLOTS,
                "batters": None, "status": last.get("lineup_status"),
                "fetched_at": latest}
    status = (snap.row(0, named=True).get("lineup_status")
              or "").strip().lower()
    if mode == MODE_CONFIRMED_ONLY and status != STATUS_CONFIRMED:
        return {"ok": False, "reason": REASON_PROJECTED_ONLY,
                "batters": None, "status": status, "fetched_at": latest}
    ordered = (slots.sort("batting_order")["batter"].cast(pl.Int64)
               .to_list())
    return {"ok": True, "reason": REASON_OK, "batters": ordered,
            "status": status, "fetched_at": latest}


def opportunity_sequence(lineup: dict, n: int) -> list[int] | None:
    """Cycled ordered lineup -> exactly n opportunities (repeats kept)."""
    if not lineup["ok"]:
        return None
    batters = lineup["batters"]
    reps = n // SLOT_COUNT + 1
    return (batters * reps)[:n]
