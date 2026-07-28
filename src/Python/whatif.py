"""Counterfactual matchup helpers (playground / demos).

Freeze one pitcher's as-of form and score expected_K against proxy lineups for
every other club. Lineups prefer today's RotoGrinders card when available,
else each team's most recent batting-order 1–9 from batter_rolling.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import polars as pl

from Python import config, identity
from Python.daily_lineups import TEAM_IDS, DailySlate, build_daily_slate
from Python.live_assembly import (
    _asof_pitcher_form,
    _normalize_team_expr,
    normalize_team_code,
    score_frame,
)


def _all_statcast_teams() -> list[str]:
    """Team codes as used in Level 1–3 (ARI → AZ, etc.)."""
    return sorted({normalize_team_code(code) for code in TEAM_IDS})


def _pitcher_home_team(pitcher_id: int, *, asof: date, rolling: pl.DataFrame) -> str:
    hist = rolling.filter(
        (pl.col("pitcher") == pitcher_id) & (pl.col("game_date") < asof)
    ).sort("game_date")
    if hist.is_empty():
        raise ValueError(f"No pitcher_rolling history for {pitcher_id} before {asof}")
    last = hist.tail(1)
    # Last start: pitcher team is home if is_home else away.
    if "is_home" in last.columns and last["is_home"][0] is not None:
        if bool(last["is_home"][0]):
            return normalize_team_code(str(last["home_team"][0]))
        return normalize_team_code(str(last["away_team"][0]))
    return normalize_team_code(str(last["home_team"][0]))


def _recent_team_lineup(
    team: str,
    *,
    asof: date,
    batter_rolling: pl.DataFrame,
) -> pl.DataFrame:
    """Most recent batting-order 1–9 for ``team`` before ``asof``."""
    team = normalize_team_code(team)
    hist = batter_rolling.filter(
        (pl.col("game_date") < asof)
        & (_normalize_team_expr("bat_team") == team)
        & pl.col("lineup_slot").is_between(1, 9)
    )
    if hist.is_empty():
        return pl.DataFrame(
            schema={
                "batter": pl.Int64,
                "batting_order": pl.Int64,
                "bat_team": pl.Utf8,
            }
        )
    last_date = hist.select(pl.col("game_date").max()).item()
    return (
        hist.filter(pl.col("game_date") == last_date)
        .sort("lineup_slot")
        .unique(subset=["lineup_slot"], keep="first")
        .select(
            pl.col("batter").cast(pl.Int64),
            pl.col("lineup_slot").cast(pl.Int64).alias("batting_order"),
            pl.lit(team).alias("bat_team"),
        )
        .head(9)
    )


def _slate_lineups_by_team(slate: DailySlate | None) -> dict[str, pl.DataFrame]:
    if slate is None or slate.lineups.is_empty():
        return {}
    out: dict[str, pl.DataFrame] = {}
    lineups = slate.lineups.with_columns(_normalize_team_expr("team").alias("bat_team"))
    for team in lineups["bat_team"].unique().to_list():
        out[str(team)] = (
            lineups.filter(pl.col("bat_team") == team)
            .select(
                pl.col("batter").cast(pl.Int64),
                pl.col("batting_order").cast(pl.Int64),
                "bat_team",
            )
            .sort("batting_order")
        )
    return out


def build_whatif_slate(
    pitcher_id: int,
    *,
    asof: date | None = None,
    pitcher_is_home: bool = True,
    live_slate: DailySlate | None = None,
) -> DailySlate:
    """Build a synthetic slate: one pitcher vs every other club."""
    asof = asof or datetime.now(ZoneInfo("America/New_York")).date()
    rolling = pl.read_parquet(config.PITCHER_ROLLING_PATH).with_columns(
        pl.col("game_date").cast(pl.Date)
    )
    batter_rolling = pl.read_parquet(config.BATTER_ROLLING_PATH).with_columns(
        pl.col("game_date").cast(pl.Date)
    )
    pitch_team = _pitcher_home_team(pitcher_id, asof=asof, rolling=rolling)
    try:
        name_by_id = {
            int(r["mlb_id"]): str(r["player_name"])
            for r in identity.load_player_map().iter_rows(named=True)
        }
    except Exception:  # noqa: BLE001
        name_by_id = {}
    pitcher_name = name_by_id.get(pitcher_id, f"mlb_id:{pitcher_id}")

    form = _asof_pitcher_form([pitcher_id], asof=asof, rolling=rolling)
    throws = None
    if "p_throws" in form.columns and form["p_throws"][0] is not None:
        throws = str(form["p_throws"][0]).upper()

    live_by_team = _slate_lineups_by_team(live_slate)
    starter_rows: list[dict[str, Any]] = []
    lineup_rows: list[dict[str, Any]] = []
    fetched_at = datetime.now(timezone.utc)

    for i, opp in enumerate(_all_statcast_teams()):
        if opp == pitch_team:
            continue
        game_pk = 9_000_000 + i
        home_team = pitch_team if pitcher_is_home else opp
        away_team = opp if pitcher_is_home else pitch_team
        lineup = live_by_team.get(opp)
        lineup_source = "rotogrinders"
        if lineup is None or lineup.height < 9:
            lineup = _recent_team_lineup(opp, asof=asof, batter_rolling=batter_rolling)
            lineup_source = "recent_lineup"
        if lineup.height < 9:
            continue

        starter_rows.append(
            {
                "game_date": asof,
                "slate_game_key": game_pk,
                "rg_game_time": None,
                "rg_game_number": 1,
                "away_team": away_team,
                "home_team": home_team,
                "away_team_id": 0,
                "home_team_id": 0,
                "team": pitch_team,
                "team_id": 0,
                "opponent": opp,
                "opponent_team_id": 0,
                "is_home": pitcher_is_home,
                "player_name": pitcher_name,
                "throws": throws,
                "lineup_status": "whatif",
                "source": "whatif",
                "source_player_path": None,
                "fetched_at": fetched_at,
                "game_pk": game_pk,
                "pitcher": pitcher_id,
                "official_probable_pitcher_id": pitcher_id,
                "lineup_source": lineup_source,
            }
        )
        for bat in lineup.to_dicts():
            lineup_rows.append(
                {
                    "game_date": asof,
                    "slate_game_key": game_pk,
                    "rg_game_time": None,
                    "rg_game_number": 1,
                    "away_team": away_team,
                    "home_team": home_team,
                    "away_team_id": 0,
                    "home_team_id": 0,
                    "team": opp,
                    "team_id": 0,
                    "opponent": pitch_team,
                    "opponent_team_id": 0,
                    "is_home": not pitcher_is_home,
                    "batting_order": int(bat["batting_order"]),
                    "player_name": name_by_id.get(int(bat["batter"]), ""),
                    "bats": None,
                    "position": None,
                    "salary": None,
                    "lineup_status": "whatif",
                    "source": lineup_source,
                    "source_player_path": None,
                    "fetched_at": fetched_at,
                    "game_pk": game_pk,
                    "batter": int(bat["batter"]),
                }
            )

    if not starter_rows:
        raise ValueError("Could not build any opponent lineups for what-if slate")

    return DailySlate(
        lineups=pl.DataFrame(lineup_rows),
        starters=pl.DataFrame(starter_rows),
    )


def score_pitcher_vs_league(
    pitcher_id: int,
    *,
    asof: date | None = None,
    pitcher_is_home: bool = True,
    allow_stale: bool = True,
    use_live_lineups: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score ``pitcher_id`` against every other team; return scored frame + meta."""
    asof = asof or datetime.now(ZoneInfo("America/New_York")).date()
    live_slate = None
    if use_live_lineups:
        try:
            live_slate = build_daily_slate(game_date=asof, require_probable_match=False)
        except Exception as exc:  # noqa: BLE001
            live_slate = None
            live_err = str(exc)
        else:
            live_err = None
    else:
        live_err = "skipped"

    slate = build_whatif_slate(
        pitcher_id,
        asof=asof,
        pitcher_is_home=pitcher_is_home,
        live_slate=live_slate,
    )

    # Reuse live assembly path without dual expansion (synthetic single pitcher).
    from Python.live_assembly import build_live_feature_frame

    frame, build_meta = build_live_feature_frame(
        slate, allow_stale=allow_stale, dual_starters=False
    )
    scored, report = score_frame(frame)
    report["build"] = build_meta
    report["whatif"] = {
        "pitcher_id": pitcher_id,
        "asof": asof.isoformat(),
        "pitcher_is_home": pitcher_is_home,
        "live_lineups_error": live_err,
        "n_opponents": int(len(scored)),
    }
    return scored, report
