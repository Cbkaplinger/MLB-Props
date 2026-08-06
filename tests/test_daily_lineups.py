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


def _html(*, game2: bool = False) -> str:
    marker = " ###2" if game2 else ""
    time_label = "7:10 PM ET" if not game2 else "10:10 PM ET"
    return f"""
    <div class="module game-card">
      <div class="game-card-header"><span class="game-time">{time_label}{marker}</span></div>
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


def _html_doubleheader() -> str:
    return _html(game2=False) + _html(game2=True)

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
            enrich=False,
        ),
        starters=daily_lineups.resolve_player_ids(
            scheduled.starters,
            rosters,
            output_column="pitcher",
            enrich=False,
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


def test_attach_schedule_disambiguates_doubleheaders_by_game_number() -> None:
    parsed = daily_lineups.parse_rotogrinders_html(
        _html_doubleheader(),
        game_date=GAME_DATE,
        fetched_at=datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
    )
    schedule = pl.DataFrame(
        {
            "game_pk": [111, 222],
            "game_date": [GAME_DATE, GAME_DATE],
            "game_time": [
                datetime(2026, 7, 23, 23, 10, tzinfo=timezone.utc),
                datetime(2026, 7, 24, 2, 10, tzinfo=timezone.utc),
            ],
            "game_status": ["Scheduled", "Scheduled"],
            "game_number": [1, 2],
            "double_header": ["S", "S"],
            "away_team": ["SD", "SD"],
            "home_team": ["ATL", "ATL"],
            "away_team_id": [135, 135],
            "home_team_id": [144, 144],
            "away_probable_pitcher_id": [900, 902],
            "home_probable_pitcher_id": [901, 903],
        }
    )
    slate = daily_lineups.attach_schedule(parsed, schedule)
    keys = (
        slate.starters.select("slate_game_key", "game_pk", "rg_game_number")
        .unique()
        .sort("slate_game_key")
    )
    assert keys["game_pk"].to_list() == [111, 222]
    assert keys["rg_game_number"].to_list() == [1, 2]
    # Old team-pair m:1 join would fail; we must still have one starter per game/team.
    assert slate.starters.height == 4
    assert slate.starters["game_pk"].n_unique() == 2


def test_attach_schedule_error_mentions_overnight_lag() -> None:
    parsed = _parsed()
    wrong_day = pl.DataFrame(
        {
            "game_pk": [999],
            "game_date": [GAME_DATE],
            "game_time": [datetime(2026, 7, 23, 16, 15, tzinfo=timezone.utc)],
            "game_status": ["Scheduled"],
            "game_number": [1],
            "double_header": ["N"],
            "away_team": ["NYY"],
            "home_team": ["BOS"],
            "away_team_id": [147],
            "home_team_id": [111],
            "away_probable_pitcher_id": [1],
            "home_probable_pitcher_id": [2],
        }
    )
    with pytest.raises(ValueError, match="overnight|SLATE_DATE|yesterday"):
        daily_lineups.attach_schedule(parsed, wrong_day)


def test_rg_schedule_mismatch_message_points_at_inferred_date() -> None:
    msg = daily_lineups._rg_schedule_mismatch_message(
        requested=date(2026, 8, 3),
        unmatched=[{"away_team": "WSH", "home_team": "ATL"}],
        schedule=pl.DataFrame(
            {
                "away_team": ["LAD"],
                "home_team": ["CHC"],
                "away_team_id": [119],
                "home_team_id": [112],
            }
        ),
        inferred=date(2026, 8, 2),
        inferred_n=1,
        n_cards=1,
    )
    assert "2026-08-03" in msg
    assert "2026-08-02" in msg
    assert "SLATE_DATE" in msg
    assert "WSH@ATL" in msg

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
        enrich=False,
    )

    assert out["batter"].to_list() == [101]


def test_resolve_player_ids_fails_loudly_for_unmapped_name() -> None:
    with pytest.raises(ValueError, match="Could not resolve 1 lineup players"):
        daily_lineups.resolve_player_ids(
            _parsed().lineups.head(1),
            _rosters().filter(pl.col("mlb_id") != 101),
            output_column="batter",
            enrich=False,
        )


def test_resolve_player_ids_uses_legal_first_name_variant() -> None:
    """RotoGrinders legal name vs MLB useName (Jakob vs Jake Bauers)."""
    frame = pl.DataFrame(
        {
            "team": ["MIL"],
            "team_id": [158],
            "player_name": ["Jakob Bauers"],
        }
    )
    rosters = pl.DataFrame(
        {
            "team_id": [158],
            "mlb_id": [641343],
            "player_name": ["Jake Bauers"],
            "first_name": ["Jakob"],
            "use_name": ["Jake"],
            "nick_name": ["JB"],
            "last_name": ["Bauers"],
            "map_name": ["Jake Bauers"],
        }
    )
    out = daily_lineups.resolve_player_ids(
        frame,
        rosters,
        output_column="batter",
        enrich=False,
    )
    assert out["batter"].to_list() == [641343]


def test_resolve_player_ids_fuzzy_matches_given_name_typo_on_team() -> None:
    """Scrape typo against unique same-team last name (Hao Lee → Jung Hoo Lee)."""
    frame = pl.DataFrame(
        {
            "team": ["SF"],
            "team_id": [137],
            "player_name": ["Hao Lee"],
        }
    )
    rosters = pl.DataFrame(
        {
            "team_id": [137, 137],
            "mlb_id": [808982, 1],
            "player_name": ["Jung Hoo Lee", "Other Player"],
            "first_name": ["Jung Hoo", "Other"],
            "use_name": ["Jung Hoo", "Other"],
            "nick_name": [None, None],
            "last_name": ["Lee", "Player"],
            "map_name": ["Jung Hoo Lee", "Other Player"],
        }
    )
    out = daily_lineups.resolve_player_ids(
        frame,
        rosters,
        output_column="batter",
        enrich=False,
    )
    assert out["batter"].to_list() == [808982]


def test_resolve_player_ids_matches_nickname_mike_to_michael() -> None:
    """RotoGrinders 'Mike King' vs MLB 'Michael King' (no nickName on people API)."""
    frame = pl.DataFrame(
        {
            "team": ["SD"],
            "team_id": [135],
            "player_name": ["Mike King"],
        }
    )
    rosters = pl.DataFrame(
        {
            "team_id": [135],
            "mlb_id": [650633],
            "player_name": ["Michael King"],
            "first_name": ["Michael"],
            "use_name": ["Michael"],
            "nick_name": [None],
            "last_name": ["King"],
            "map_name": ["Michael King"],
        }
    )
    out = daily_lineups.resolve_player_ids(
        frame,
        rosters,
        output_column="pitcher",
        enrich=False,
    )
    assert out["pitcher"].to_list() == [650633]


def test_resolve_player_ids_fuzzy_given_typo_and_last_typo() -> None:
    """Common misspellings on given and last when the team roster is unique."""
    frame = pl.DataFrame(
        {
            "team": ["SD", "SD"],
            "team_id": [135, 135],
            "player_name": ["Micheal King", "Michael Kinq"],
        }
    )
    rosters = pl.DataFrame(
        {
            "team_id": [135],
            "mlb_id": [650633],
            "player_name": ["Michael King"],
            "first_name": ["Michael"],
            "use_name": ["Michael"],
            "nick_name": [None],
            "last_name": ["King"],
            "map_name": ["Michael King"],
        }
    )
    out = daily_lineups.resolve_player_ids(
        frame,
        rosters,
        output_column="pitcher",
        enrich=False,
    )
    assert out["pitcher"].to_list() == [650633, 650633]


def test_resolve_player_ids_fuzzy_rejects_wrong_last_name() -> None:
    """Full-string similarity alone must not map Kong → King."""
    frame = pl.DataFrame(
        {
            "team": ["SD"],
            "team_id": [135],
            "player_name": ["Michael Kong"],
        }
    )
    rosters = pl.DataFrame(
        {
            "team_id": [135],
            "mlb_id": [650633],
            "player_name": ["Michael King"],
            "first_name": ["Michael"],
            "use_name": ["Michael"],
            "nick_name": [None],
            "last_name": ["King"],
            "map_name": ["Michael King"],
        }
    )
    with pytest.raises(ValueError, match="Could not resolve"):
        daily_lineups.resolve_player_ids(
            frame,
            rosters,
            output_column="pitcher",
            enrich=False,
        )


def test_resolve_player_ids_fuzzy_does_not_cross_team() -> None:
    frame = pl.DataFrame(
        {
            "team": ["MIL"],
            "team_id": [158],
            "player_name": ["Hao Lee"],
        }
    )
    rosters = pl.DataFrame(
        {
            "team_id": [137],
            "mlb_id": [808982],
            "player_name": ["Jung Hoo Lee"],
            "first_name": ["Jung Hoo"],
            "use_name": ["Jung Hoo"],
            "nick_name": [None],
            "last_name": ["Lee"],
            "map_name": ["Jung Hoo Lee"],
        }
    )
    with pytest.raises(ValueError, match="Could not resolve"):
        daily_lineups.resolve_player_ids(
            frame,
            rosters,
            output_column="batter",
            enrich=False,
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
        daily_lineups.validate_daily_slate(
            mismatched, require_probable_match=True
        )


def test_validate_daily_slate_warns_on_probable_mismatch_by_default(
    capsys,
) -> None:
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
    daily_lineups.validate_daily_slate(mismatched)
    captured = capsys.readouterr()
    assert "disagrees with MLB probable pitcher" in captured.out


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
