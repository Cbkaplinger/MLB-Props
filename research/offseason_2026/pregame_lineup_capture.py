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

# Explicit alias map (caller-boundary normalization; no inference).
TEAM_ALIASES = {
    "ana": "LAA", "laa": "LAA",
    "ari": "ARI", "az": "ARI",
    "atl": "ATL", "bal": "BAL", "bos": "BOS",
    "cha": "CWS", "cws": "CWS", "chw": "CWS", "chc": "CHC",
    "cin": "CIN", "cle": "CLE", "col": "COL",
    "det": "DET", "hou": "HOU", "kc": "KC", "kan": "KC",
    "la": "LAA", "lad": "LAD", "mia": "MIA", "fla": "MIA",
    "mil": "MIL", "min": "MIN", "nym": "NYM", "nyy": "NYY",
    "oak": "ATH", "ath": "ATH", "phi": "PHI",
    "pit": "PIT", "sd": "SD", "sdp": "SD",
    "sea": "SEA", "sf": "SF", "sfg": "SF",
    "stl": "STL", "tb": "TB", "tamp": "TB",
    "tex": "TEX", "tor": "TOR", "wsh": "WSH", "was": "WSH",
}


def normalize_team(code: str) -> str:
    """Explicit canonical team code; raises ValueError on unknown input
    (callers map that to REASON_UNKNOWN_TEAM)."""
    key = str(code).strip().lower()
    if key not in TEAM_ALIASES:
        raise ValueError("unknown team code: %r" % (code,))
    return TEAM_ALIASES[key]


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


def _receipt(ok: bool, reason: str, snaps: pl.DataFrame | None,
             status_col: str = "lineup_status") -> dict:
    return {"ok": ok, "reason": reason,
            "batters": None, "status": None, "fetched_at": None} \
        if not ok and snaps is None else {}


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
        team_c = normalize_team(team)
    except ValueError:
        return {"ok": False, "reason": REASON_UNKNOWN_TEAM,
                "batters": None, "status": None, "fetched_at": None}
    g = snaps.filter(
        (pl.col("game_pk") == game_pk) & (pl.col("team") == team_c))
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
    # PINNED SELECTION RULE (owner 2026-10-09): latest cutoff-valid
    # snapshot wins. If that latest snapshot is partial or conflicting,
    # return the declared fallback -- NO older-revision substitution
    # (older-snapshot fallback would be a separate policy with explicit
    # staleness controls; not implemented).
    latest = g.sort("fetched_at")["fetched_at"][-1]
    slots = (g.filter(pl.col("fetched_at") == latest)
             .unique(["batting_order", "batter"], keep="last"))
    n_slots = slots["batting_order"].n_unique()
    n_players = slots["batter"].n_unique()
    if n_slots != SLOT_COUNT or n_players != SLOT_COUNT:
        last = g.filter(pl.col("fetched_at") == latest).row(0, named=True)
        return {"ok": False, "reason": REASON_NOT_9_SLOTS,
                "batters": None, "status": last.get("lineup_status"),
                "fetched_at": latest}
    status = (slots.row(0, named=True).get("lineup_status") or "").strip().lower()
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
