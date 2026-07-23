"""Raw Statcast (Baseball Savant) loading and plate-appearance extraction.

The per-start pitcher table only has pitching aggregates. To engineer opponent
(batter) context, intangibles, and park features we go back to the pitch-level
Statcast exports in ``SAVANT_DATA_DIR/<year>/statcast_<year>_regular.parquet``.

This module is the shared primitive: it loads seasons and reduces pitch-level
rows to one row per plate appearance with a strikeout flag, which both the
batter and pitcher feature builders rely on.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlencode
from urllib.request import urlopen

import polars as pl

from .config import SAVANT_DATA_DIR

# Events that terminate a plate appearance with a strikeout.
STRIKEOUT_EVENTS: frozenset[str] = frozenset({"strikeout", "strikeout_double_play"})

# Non-batting terminal events (baserunning, etc.) that are NOT plate appearances.
NON_PA_EVENTS: frozenset[str] = frozenset(
    {
        "caught_stealing_2b", "caught_stealing_3b", "caught_stealing_home",
        "pickoff_1b", "pickoff_2b", "pickoff_3b",
        "pickoff_caught_stealing_2b", "pickoff_caught_stealing_3b",
        "pickoff_caught_stealing_home",
        "stolen_base_2b", "stolen_base_3b", "stolen_base_home",
        "wild_pitch", "passed_ball", "other_out", "runner_double_play",
    }
)

# Swinging-strike (whiff) pitch descriptions and batting-hit events.
# ``foul_tip`` is a swing-and-tick caught by the catcher: intentionally counted
# as a whiff here (and therefore folded into CSW).
WHIFF_DESCRIPTIONS: frozenset[str] = frozenset(
    {"swinging_strike", "swinging_strike_blocked", "foul_tip"}
)
HIT_EVENTS: frozenset[str] = frozenset({"single", "double", "triple", "home_run"})

# Batted-ball types that count as fly balls for HR/FB: fly balls AND popups,
# matching FanGraphs' FB definition (which includes infield flies / popups).
FLY_BALL_TYPES: frozenset[str] = frozenset({"fly_ball", "popup"})

# Pitches the batter offered at (bunts excluded) and the subset that made
# contact. ``foul_tip`` is a whiff (above), so it is NOT contact here, which
# keeps the identity ``Swings = Whiffs + Contacts``.
SWING_DESCRIPTIONS: frozenset[str] = frozenset(
    {"swinging_strike", "swinging_strike_blocked", "foul_tip", "foul", "hit_into_play"}
)
CONTACT_DESCRIPTIONS: frozenset[str] = frozenset({"foul", "hit_into_play"})


def xwoba_num() -> pl.Expr:
    """Per-PA xwOBA numerator, matching Baseball Savant's own construction.

    Batted balls use the model estimate (``estimated_woba_using_speedangle``);
    non-contact terminal events (K/BB/HBP) fall back to ``woba_value``, which
    already carries the correct *season-specific* linear weight. Non-terminal
    pitches are null on both columns and contribute nothing to the sum.
    """
    return (
        pl.when(pl.col("estimated_woba_using_speedangle").is_not_null())
        .then(pl.col("estimated_woba_using_speedangle"))
        .otherwise(pl.col("woba_value"))
    )


def woba_agg() -> pl.Expr:
    """Actual wOBA from Savant's per-PA ``woba_value`` / ``woba_denom``.

    Uses the season-correct weights Savant already assigned, and the proper
    denominator (AB + BB - IBB + SF + HBP) rather than a raw PA count.
    """
    return (pl.col("woba_value").sum() / pl.col("woba_denom").sum()).alias("wOBA")


def xwoba_agg() -> pl.Expr:
    """xwOBA aggregation over plate appearances using Savant's inputs.

    See :func:`xwoba_num`. Divides by ``sum(woba_denom)`` so IBB / sacrifice
    bunts (denom = 0) are excluded exactly as Savant does.
    """
    return (xwoba_num().sum() / pl.col("woba_denom").sum()).alias("xwOBA")

# Minimal column set needed for PA/batter/context features (keeps loads light).
DEFAULT_COLUMNS: tuple[str, ...] = (
    "game_pk", "game_date", "game_year", "player_name",
    "pitcher", "batter", "stand", "p_throws",
    "home_team", "away_team", "inning_topbot",
    "at_bat_number", "pitch_number", "events",
    "n_thruorder_pitcher", "pitcher_days_since_prev_game",
    "estimated_woba_using_speedangle", "woba_value", "woba_denom",
)

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def season_path(year: int) -> Path:
    """Path to the regular-season Statcast parquet for ``year``."""
    return SAVANT_DATA_DIR / str(year) / f"statcast_{year}_regular.parquet"


def regular_season_schedule(
    year: int,
    *,
    timeout: float = 30.0,
) -> tuple[dt.date, dt.date, frozenset[int]]:
    """Return official regular-season bounds and MLB game IDs."""
    query = urlencode({"sportId": 1, "season": year, "gameType": "R"})
    with urlopen(f"{MLB_SCHEDULE_URL}?{query}", timeout=timeout) as response:
        payload = json.load(response)

    games = [
        game
        for date_entry in payload.get("dates", [])
        for game in date_entry.get("games", [])
        if game.get("gameType") == "R"
    ]
    if not games:
        raise RuntimeError(f"MLB schedule returned no regular-season games for {year}")

    dates = [dt.date.fromisoformat(game["officialDate"]) for game in games]
    game_pks = frozenset(int(game["gamePk"]) for game in games)
    return min(dates), max(dates), game_pks


def validate_statcast_season(
    frame: pl.DataFrame,
    year: int,
    *,
    official_game_pks: frozenset[int] | None = None,
) -> None:
    """Reject empty, mislabeled, or wrong-season Statcast data."""
    required = {"game_pk", "game_date", "game_year"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Statcast {year} data is missing columns: {missing}")
    if frame.is_empty():
        raise ValueError(f"Statcast {year} data is empty")

    years = set(
        frame.select(pl.col("game_year").cast(pl.Int32).unique())
        .to_series()
        .drop_nulls()
        .to_list()
    )
    date_years = set(
        frame.select(pl.col("game_date").cast(pl.Date).dt.year().unique())
        .to_series()
        .drop_nulls()
        .to_list()
    )
    if years != {year} or date_years != {year}:
        raise ValueError(
            f"Statcast file labeled {year} contains game_year={sorted(years)} "
            f"and date years={sorted(date_years)}"
        )

    if official_game_pks is not None:
        observed = frozenset(
            int(game_pk)
            for game_pk in frame["game_pk"].drop_nulls().unique().to_list()
        )
        wrong_season = observed - official_game_pks
        coverage = len(observed & official_game_pks) / len(official_game_pks)
        if wrong_season or coverage < 0.98:
            sample = sorted(wrong_season)[:5]
            raise ValueError(
                f"Statcast {year} game IDs do not match the official schedule "
                f"(coverage={coverage:.1%}, wrong-season sample={sample})"
            )


def download_statcast_season(
    year: int,
    *,
    path: Path | None = None,
    verbose: bool = True,
) -> Path:
    """Download and atomically store one verified MLB regular season."""
    try:
        from pybaseball import cache
        from pybaseball import statcast as fetch_statcast
    except ImportError as exc:
        raise RuntimeError(
            "Install the research dependencies before downloading Statcast: "
            'python -m pip install -e ".[research]"'
        ) from exc

    cache.enable()
    start_date, end_date, official_game_pks = regular_season_schedule(year)
    pandas_frame = fetch_statcast(
        start_dt=start_date.isoformat(),
        end_dt=end_date.isoformat(),
        verbose=verbose,
        parallel=True,
    )
    frame = pl.from_pandas(pandas_frame, nan_to_null=True).with_columns(
        pl.col("game_date").cast(pl.Date),
        pl.col("game_year").cast(pl.Int32),
        pl.col("game_pk").cast(pl.Int64),
    )
    if "game_type" in frame.columns:
        frame = frame.filter(pl.col("game_type") == "R")

    validate_statcast_season(
        frame,
        year,
        official_game_pks=official_game_pks,
    )

    destination = path or season_path(year)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.parquet")
    frame.write_parquet(temporary)
    temporary.replace(destination)
    return destination


def load_statcast_years(
    years: Iterable[int],
    columns: Sequence[str] | None = DEFAULT_COLUMNS,
) -> pl.DataFrame:
    """Load and concatenate regular-season Statcast for the given years.

    ``columns=None`` loads every column. Missing requested columns are ignored
    so the loader keeps working if a season predates a Statcast field.
    """
    frames: list[pl.DataFrame] = []
    for year in years:
        path = season_path(year)
        if not path.exists():
            raise FileNotFoundError(f"Statcast file not found: {path}")
        lf = pl.scan_parquet(path)
        available = set(lf.collect_schema().names())
        if columns is not None:
            requested = [column for column in columns if column in available]
            validation_columns = [
                column
                for column in ("game_pk", "game_date", "game_year")
                if column in available and column not in requested
            ]
            frame = lf.select([*requested, *validation_columns]).collect()
            validate_statcast_season(frame, int(year))
            frame = frame.select(requested)
        else:
            frame = lf.collect()
            validate_statcast_season(frame, int(year))
        frames.append(frame)
    return pl.concat(frames, how="diagonal_relaxed")


def plate_appearances(df: pl.DataFrame) -> pl.DataFrame:
    """Reduce pitch-level rows to one row per plate appearance.

    Keeps the terminal pitch of each ``(game_pk, at_bat_number)`` whose event is
    an actual batting outcome, and adds an ``is_k`` boolean. ``game_date`` is
    normalized to a date.
    """
    out = (
        df.filter(pl.col("events").is_not_null() & ~pl.col("events").is_in(NON_PA_EVENTS))
        # terminal pitch of the plate appearance
        .sort(["game_pk", "at_bat_number", "pitch_number"])
        .group_by(["game_pk", "at_bat_number"], maintain_order=True)
        .last()
        .with_columns(
            pl.col("events").is_in(STRIKEOUT_EVENTS).alias("is_k"),
            pl.col("game_date").cast(pl.Date).alias("game_date"),
        )
    )
    return out


def add_event_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Add per-pitch boolean outcome flags shared by pitcher and batter builders.

    Adds ``is_pa, is_k, is_bb, is_hbp, is_hr, is_hit, is_whiff,
    is_called_strike`` and normalizes ``game_date`` to a date. Needs only the
    ``events``, ``description``, and ``game_date`` columns.
    """
    return df.with_columns(
        pl.col("game_date").cast(pl.Date),
        (pl.col("events").is_not_null() & ~pl.col("events").is_in(NON_PA_EVENTS)).alias("is_pa"),
        pl.col("events").is_in(STRIKEOUT_EVENTS).alias("is_k"),
        pl.col("events").is_in(["walk", "intent_walk"]).alias("is_bb"),
        (pl.col("events") == "hit_by_pitch").alias("is_hbp"),
        (pl.col("events") == "home_run").alias("is_hr"),
        pl.col("events").is_in(HIT_EVENTS).alias("is_hit"),
        pl.col("description").is_in(WHIFF_DESCRIPTIONS).alias("is_whiff"),
        (pl.col("description") == "called_strike").alias("is_called_strike"),
    )


# Count columns produced by summing the flags from ``add_plate_discipline_flags``.
DISCIPLINE_COUNTS: tuple[str, ...] = (
    "InZone", "OutZone", "Swings", "Chases", "ZSwings",
    "Contacts", "ZContacts", "OContacts",
)


def add_plate_discipline_flags(df: pl.DataFrame) -> pl.DataFrame:
    """Add per-pitch swing / zone / contact flags (needs ``description``, ``zone``).

    Uses Statcast's ``zone`` grid: zones 1-9 are in the strike zone, 11-14 are
    outside it. These flags are batter-neutral primitives; summed on the pitcher
    side they describe swings *induced/allowed*, and on the batter side they
    describe the hitter's own swing decisions.

    Adds: ``is_in_zone, is_out_zone, is_swing, is_contact, is_chase (O-swing),
    is_zswing (Z-swing), is_zcontact, is_ocontact``.
    """
    z = pl.col("zone")
    in_zone = z.is_not_null() & (z <= 9)
    out_zone = z.is_not_null() & (z >= 11)
    swing = pl.col("description").is_in(SWING_DESCRIPTIONS)
    contact = pl.col("description").is_in(CONTACT_DESCRIPTIONS)
    return df.with_columns(
        in_zone.alias("is_in_zone"),
        out_zone.alias("is_out_zone"),
        swing.alias("is_swing"),
        contact.alias("is_contact"),
        (swing & out_zone).alias("is_chase"),
        (swing & in_zone).alias("is_zswing"),
        (contact & in_zone).alias("is_zcontact"),
        (contact & out_zone).alias("is_ocontact"),
    )


def discipline_count_exprs() -> list[pl.Expr]:
    """Aggregation expressions summing the plate-discipline flags into counts."""
    return [
        pl.col("is_in_zone").sum().alias("InZone"),
        pl.col("is_out_zone").sum().alias("OutZone"),
        pl.col("is_swing").sum().alias("Swings"),
        pl.col("is_chase").sum().alias("Chases"),
        pl.col("is_zswing").sum().alias("ZSwings"),
        pl.col("is_contact").sum().alias("Contacts"),
        pl.col("is_zcontact").sum().alias("ZContacts"),
        pl.col("is_ocontact").sum().alias("OContacts"),
    ]


def _rate(num: str, den: str) -> pl.Expr:
    return pl.when(pl.col(den) > 0).then(pl.col(num) / pl.col(den)).otherwise(None)


def add_plate_discipline_rates(df: pl.DataFrame) -> pl.DataFrame:
    """Derive the standard plate-discipline rates from the summed counts.

    Expects ``Pitches``, ``Whiffs`` and the :data:`DISCIPLINE_COUNTS` columns.
    Rates (all in [0, 1]):
        ``zone_rate`` (Zone%), ``swing_rate``, ``chase_rate`` (O-Swing%),
        ``zswing_rate`` (Z-Swing%), ``contact_rate``, ``zcontact_rate``,
        ``ocontact_rate``, ``swstr_rate`` (SwStr% = whiffs/pitch),
        ``whiff_rate`` (whiffs per swing).
    """
    return df.with_columns(
        _rate("InZone", "Pitches").alias("zone_rate"),
        _rate("Swings", "Pitches").alias("swing_rate"),
        _rate("Chases", "OutZone").alias("chase_rate"),
        _rate("ZSwings", "InZone").alias("zswing_rate"),
        _rate("Contacts", "Swings").alias("contact_rate"),
        _rate("ZContacts", "ZSwings").alias("zcontact_rate"),
        _rate("OContacts", "Chases").alias("ocontact_rate"),
        _rate("Whiffs", "Pitches").alias("swstr_rate"),
        _rate("Whiffs", "Swings").alias("whiff_rate"),
    )


def batter_k_rate(pa: pl.DataFrame, min_pa: int = 1) -> pl.DataFrame:
    """Overall K% per batter from a plate-appearance frame."""
    return (
        pa.group_by("batter")
        .agg(
            pl.len().alias("PA"),
            pl.col("is_k").sum().alias("K"),
        )
        .with_columns((pl.col("K") / pl.col("PA")).alias("k_rate"))
        .filter(pl.col("PA") >= min_pa)
        .sort("k_rate", descending=True)
    )
