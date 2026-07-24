from __future__ import annotations

from datetime import date, datetime, timezone

import polars as pl
import pytest

from Python import daily_lineups


GAME_DATE = date(2026, 7, 23)


def _lineup_card(
    *,
    prefix: str,
    pitcher: str,
    confirmed: bool,
) -> str:
    body_class = "lineup-card-body" if confirmed else "lineup-card-body unconfirmed"
    players = "".join(
        f"""
        <li class="lineup-card-player">
          <span class="player-nameplate" data-position="OF" data-salary="{3000 + spot}">
            <span class="small">{spot}</span>
            <div class="player-nameplate-info">
              <a class="player-nameplate-name" href="/players/{prefix.lower()}-{spot}">
                {prefix} Batter {spot}
              </a>
              <span class="player-nameplate-stats"><span class="small">(R)</span></span>
            </div>
          </span>
        </li>
        """
        for spot in range(1, 10)
    )
    return f"""
    <div class="lineup-card">
      <div class="lineup-card-header">
        <div class="lineup-card-pitcher">
          <span class="player-nameplate" data-position="SP">
            <div class="player-nameplate-info">
              <a class="player-nameplate-name" href="/players/{prefix.lower()}-starter">
                {pitcher}
              </a>
              <span class="player-nameplate-stats"><span class="small">(L)</span></span>
            </div>
          </span>
        </div>
      </div>
      <div class="{body_class}">
        <ul class="lineup-card-players">{players}</ul>
      </div>
    </div>
    """


def _html() -> str:
    return f"""
    <div class="module game-card">
      <div class="game-card-teams">
        <span class="team-nameplate-title" data-abbr="SDP"></span>
        <span class="team-nameplate-title" data-abbr="ATL"></span>
      </div>
      <div class="game-card-lineups">
        {_lineup_card(prefix="Away", pitcher="Away Starter", confirmed=False)}
        {_lineup_card(prefix="Home", pitcher="Home Starter", confirmed=True)}
      </div>
    </div>
    """


def _parsed() -> daily_lineups.DailySlate:
    return daily_lineups.parse_rotogrinders_html(
        _html(),
        game_date=GAME_DATE,
        fetched_at=datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
    )


def _schedule() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "game_pk": [824893],
            "game_date": [GAME_DATE],
            "game_time": [datetime(2026, 7, 23, 16, 15, tzinfo=timezone.utc)],
            "game_status": ["Scheduled"],
            "away_team": ["SD"],
            "home_team": ["ATL"],
            "away_team_id": [135],
            "home_team_id": [144],
            "away_probable_pitcher_id": [900],
            "home_probable_pitcher_id": [901],
        },
        schema={
            "game_pk": pl.Int64,
            "game_date": pl.Date,
            "game_time": pl.Datetime(time_zone="UTC"),
            "game_status": pl.String,
            "away_team": pl.String,
            "home_team": pl.String,
            "away_team_id": pl.Int64,
            "home_team_id": pl.Int64,
            "away_probable_pitcher_id": pl.Int64,
            "home_probable_pitcher_id": pl.Int64,
        },
    )


def _rosters() -> pl.DataFrame:
    rows = [
        {"team_id": 135, "mlb_id": 900, "player_name": "Away Starter"},
        {"team_id": 144, "mlb_id": 901, "player_name": "Home Starter"},
    ]
    rows.extend(
        {"team_id": 135, "mlb_id": 100 + spot, "player_name": f"Away Batter {spot}"}
        for spot in range(1, 10)
    )
    rows.extend(
        {"team_id": 144, "mlb_id": 200 + spot, "player_name": f"Home Batter {spot}"}
        for spot in range(1, 10)
    )
    return pl.DataFrame(rows)


def _resolved() -> daily_lineups.DailySlate:
    scheduled = daily_lineups.attach_schedule(_parsed(), _schedule())
    rosters = _rosters()
    return daily_lineups.DailySlate(
        lineups=daily_lineups.resolve_player_ids(
            scheduled.lineups,
            rosters,
            output_column="batter",
        ),
        starters=daily_lineups.resolve_player_ids(
            scheduled.starters,
            rosters,
            output_column="pitcher",
        ),
    )


def test_parse_rotogrinders_preserves_lineups_spots_and_status() -> None:
    slate = _parsed()

    assert slate.lineups.height == 18
    assert slate.starters.height == 2
    assert slate.lineups["batting_order"].unique().sort().to_list() == list(
        range(1, 10)
    )
    assert (
        slate.lineups.filter(pl.col("team") == "SD")["lineup_status"].unique().item()
        == "projected"
    )
    assert (
        slate.lineups.filter(pl.col("team") == "ATL")["lineup_status"].unique().item()
        == "confirmed"
    )
    first = slate.lineups.sort("is_home", "batting_order").row(0, named=True)
    assert first["player_name"] == "Away Batter 1"
    assert first["salary"] == 3001
    assert first["source_player_path"] == "/players/away-1"


def test_attach_schedule_adds_game_and_official_probable_pitchers() -> None:
    slate = daily_lineups.attach_schedule(_parsed(), _schedule())

    assert slate.lineups["game_pk"].unique().to_list() == [824893]
    assert slate.starters.sort("is_home")[
        "official_probable_pitcher_id"
    ].to_list() == [900, 901]


def test_resolve_player_ids_is_scoped_to_official_team_roster() -> None:
    frame = _parsed().lineups.head(1)
    rosters = pl.DataFrame(
        {
            "team_id": [135, 144],
            "mlb_id": [101, 999],
            "player_name": ["Away Batter 1", "Away Batter 1"],
        }
    )

    out = daily_lineups.resolve_player_ids(
        frame,
        rosters,
        output_column="batter",
    )

    assert out["batter"].to_list() == [101]


def test_resolve_player_ids_fails_loudly_for_unmapped_name() -> None:
    with pytest.raises(ValueError, match="Could not resolve 1 lineup players"):
        daily_lineups.resolve_player_ids(
            _parsed().lineups.head(1),
            _rosters().filter(pl.col("mlb_id") != 101),
            output_column="batter",
        )


def test_validate_daily_slate_requires_unique_nine_player_lineups() -> None:
    slate = _resolved()
    daily_lineups.validate_daily_slate(slate)

    incomplete = daily_lineups.DailySlate(
        lineups=slate.lineups.head(17),
        starters=slate.starters,
    )
    with pytest.raises(ValueError, match="nine unique resolved batters"):
        daily_lineups.validate_daily_slate(incomplete)


def test_validate_daily_slate_can_require_confirmed_source() -> None:
    with pytest.raises(ValueError, match="still contains projected"):
        daily_lineups.validate_daily_slate(_resolved(), require_confirmed=True)


def test_validate_daily_slate_rejects_probable_pitcher_disagreement() -> None:
    slate = _resolved()
    mismatched = daily_lineups.DailySlate(
        lineups=slate.lineups,
        starters=slate.starters.with_columns(
            pl.when(pl.col("team") == "SD")
            .then(pl.lit(999))
            .otherwise(pl.col("official_probable_pitcher_id"))
            .alias("official_probable_pitcher_id")
        ),
    )

    with pytest.raises(ValueError, match="disagrees with MLB probable pitcher"):
        daily_lineups.validate_daily_slate(mismatched)


def test_write_daily_slate_keeps_batter_and_pitcher_ids(tmp_path) -> None:
    slate = _resolved()

    lineup_path, starter_path = daily_lineups.write_daily_slate(
        slate,
        output_dir=tmp_path,
    )

    assert lineup_path.name == "daily_lineups_2026-07-23.parquet"
    assert starter_path.name == "daily_starters_2026-07-23.parquet"
    assert pl.read_parquet(lineup_path)["batter"].null_count() == 0
    assert pl.read_parquet(starter_path)["pitcher"].null_count() == 0
