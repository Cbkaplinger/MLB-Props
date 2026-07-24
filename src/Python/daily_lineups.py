"""Daily MLB lineup ingestion with ID-safe player matching.

RotoGrinders supplies projected/confirmed batting orders. MLB's Stats API
supplies canonical game, team, probable-pitcher, and player identifiers.
Names are used only to resolve a scraped row against an official team roster;
all returned model-facing rows retain MLB numeric IDs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Mapping
import unicodedata
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import polars as pl

from . import config


ROTOGRINDERS_LINEUPS_URL = "https://rotogrinders.com/lineups/mlb?site=draftkings"
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
MLB_TEAM_ROSTER_URL = "https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
_USER_AGENT = "MLB-Props/0.1 (daily lineup research)"

# Stable MLB Stats API team IDs. Aliases account for common DFS abbreviations.
TEAM_IDS: dict[str, int] = {
    "ARI": 109,
    "ATL": 144,
    "BAL": 110,
    "BOS": 111,
    "CHC": 112,
    "CWS": 145,
    "CIN": 113,
    "CLE": 114,
    "COL": 115,
    "DET": 116,
    "HOU": 117,
    "KC": 118,
    "LAA": 108,
    "LAD": 119,
    "MIA": 146,
    "MIL": 158,
    "MIN": 142,
    "NYM": 121,
    "NYY": 147,
    "ATH": 133,
    "PHI": 143,
    "PIT": 134,
    "SD": 135,
    "SF": 137,
    "SEA": 136,
    "STL": 138,
    "TB": 139,
    "TEX": 140,
    "TOR": 141,
    "WSH": 120,
}
TEAM_ALIASES: dict[str, str] = {
    "AZ": "ARI",
    "ARI": "ARI",
    "CHW": "CWS",
    "CWS": "CWS",
    "KAN": "KC",
    "KCR": "KC",
    "KC": "KC",
    "OAK": "ATH",
    "ATH": "ATH",
    "SDP": "SD",
    "SD": "SD",
    "SFG": "SF",
    "SF": "SF",
    "TBR": "TB",
    "TB": "TB",
    "WAS": "WSH",
    "WSN": "WSH",
    "WSH": "WSH",
}
_TEAM_CODES_BY_ID = {team_id: code for code, team_id in TEAM_IDS.items()}


@dataclass(frozen=True)
class DailySlate:
    """Resolved daily batter lineups and starting pitchers."""

    lineups: pl.DataFrame
    starters: pl.DataFrame


def canonical_team_code(value: str) -> str:
    """Normalize a DFS team abbreviation to the project convention."""
    raw = value.strip().upper()
    code = TEAM_ALIASES.get(raw, raw)
    if code not in TEAM_IDS:
        raise ValueError(f"Unknown MLB team abbreviation: {value!r}")
    return code


def _name_key(value: str) -> str:
    """Create a conservative comparison key for roster-bound name matching."""
    ascii_name = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    ascii_name = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", ascii_name)
    return re.sub(r"[^a-z0-9]+", "", ascii_name)


def _fetch_bytes(url: str, *, timeout: float) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def fetch_rotogrinders_html(*, timeout: float = 30.0) -> bytes:
    """Download the current DraftKings MLB lineup page."""
    return _fetch_bytes(ROTOGRINDERS_LINEUPS_URL, timeout=timeout)


def _lineup_schema() -> dict[str, pl.DataType]:
    return {
        "game_date": pl.Date,
        "away_team": pl.String,
        "home_team": pl.String,
        "away_team_id": pl.Int64,
        "home_team_id": pl.Int64,
        "team": pl.String,
        "team_id": pl.Int64,
        "opponent": pl.String,
        "opponent_team_id": pl.Int64,
        "is_home": pl.Boolean,
        "batting_order": pl.Int64,
        "player_name": pl.String,
        "bats": pl.String,
        "position": pl.String,
        "salary": pl.Int64,
        "lineup_status": pl.String,
        "source": pl.String,
        "source_player_path": pl.String,
        "fetched_at": pl.Datetime(time_zone="UTC"),
    }


def _starter_schema() -> dict[str, pl.DataType]:
    return {
        "game_date": pl.Date,
        "away_team": pl.String,
        "home_team": pl.String,
        "away_team_id": pl.Int64,
        "home_team_id": pl.Int64,
        "team": pl.String,
        "team_id": pl.Int64,
        "opponent": pl.String,
        "opponent_team_id": pl.Int64,
        "is_home": pl.Boolean,
        "player_name": pl.String,
        "throws": pl.String,
        "lineup_status": pl.String,
        "source": pl.String,
        "source_player_path": pl.String,
        "fetched_at": pl.Datetime(time_zone="UTC"),
    }


def _player_values(nameplate: object) -> tuple[str | None, str | None, str | None]:
    if nameplate is None:
        return None, None, None
    anchor = nameplate.select_one("a.player-nameplate-name")
    if anchor is None:
        return None, None, None
    name = anchor.get_text(" ", strip=True)
    if not name or name.upper() == "TBD":
        return None, None, None
    hand_node = nameplate.select_one(".player-nameplate-stats > span.small")
    hand = hand_node.get_text(" ", strip=True).strip("()") if hand_node else None
    return name, hand or None, anchor.get("href")


def parse_rotogrinders_html(
    html: bytes | str,
    *,
    game_date: date,
    fetched_at: datetime | None = None,
) -> DailySlate:
    """Parse RotoGrinders markup without performing identity joins."""
    fetched_at = (fetched_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    soup = BeautifulSoup(html, "html.parser")
    lineup_rows: list[dict[str, object]] = []
    starter_rows: list[dict[str, object]] = []

    for card in soup.select(".module.game-card"):
        team_nodes = card.select(".game-card-teams .team-nameplate-title")
        lineup_cards = card.select(".game-card-lineups > .lineup-card")
        if len(team_nodes) != 2 or len(lineup_cards) != 2:
            continue

        away_team = canonical_team_code(str(team_nodes[0].get("data-abbr", "")))
        home_team = canonical_team_code(str(team_nodes[1].get("data-abbr", "")))
        away_team_id = TEAM_IDS[away_team]
        home_team_id = TEAM_IDS[home_team]

        for index, lineup_card in enumerate(lineup_cards):
            is_home = index == 1
            team = home_team if is_home else away_team
            opponent = away_team if is_home else home_team
            team_id = home_team_id if is_home else away_team_id
            opponent_team_id = away_team_id if is_home else home_team_id
            body = lineup_card.select_one(".lineup-card-body")
            body_classes = set(body.get("class", [])) if body else set()
            lineup_status = "projected" if "unconfirmed" in body_classes else "confirmed"
            common = {
                "game_date": game_date,
                "away_team": away_team,
                "home_team": home_team,
                "away_team_id": away_team_id,
                "home_team_id": home_team_id,
                "team": team,
                "team_id": team_id,
                "opponent": opponent,
                "opponent_team_id": opponent_team_id,
                "is_home": is_home,
                "lineup_status": lineup_status,
                "source": "rotogrinders",
                "fetched_at": fetched_at,
            }

            pitcher_container = lineup_card.select_one(".lineup-card-pitcher")
            pitcher_plate = (
                pitcher_container.find(
                    "span", class_="player-nameplate", recursive=False
                )
                if pitcher_container
                else None
            )
            pitcher_name, pitcher_hand, pitcher_path = _player_values(pitcher_plate)
            starter_rows.append(
                {
                    **common,
                    "player_name": pitcher_name,
                    "throws": pitcher_hand,
                    "source_player_path": pitcher_path,
                }
            )

            if body is None:
                continue
            for player_row in body.select("li.lineup-card-player"):
                nameplate = player_row.select_one("span.player-nameplate")
                player_name, bats, player_path = _player_values(nameplate)
                order_node = nameplate.find("span", class_="small") if nameplate else None
                try:
                    batting_order = int(order_node.get_text(strip=True))
                except (AttributeError, TypeError, ValueError):
                    batting_order = None
                salary_raw = nameplate.get("data-salary") if nameplate else None
                try:
                    salary = int(salary_raw)
                except (TypeError, ValueError):
                    salary = None
                lineup_rows.append(
                    {
                        **common,
                        "batting_order": batting_order,
                        "player_name": player_name,
                        "bats": bats,
                        "position": (
                            str(nameplate.get("data-position"))
                            if nameplate and nameplate.get("data-position")
                            else None
                        ),
                        "salary": salary,
                        "source_player_path": player_path,
                    }
                )

    return DailySlate(
        lineups=pl.DataFrame(
            lineup_rows,
            schema=_lineup_schema(),
            orient="row",
            strict=False,
        ),
        starters=pl.DataFrame(
            starter_rows,
            schema=_starter_schema(),
            orient="row",
            strict=False,
        ),
    )


def fetch_mlb_schedule(
    game_date: date,
    *,
    timeout: float = 30.0,
) -> pl.DataFrame:
    """Fetch the official daily schedule and probable-pitcher IDs."""
    query = urlencode(
        {
            "sportId": 1,
            "date": game_date.isoformat(),
            "hydrate": "probablePitcher",
        }
    )
    payload = json.loads(
        _fetch_bytes(f"{MLB_SCHEDULE_URL}?{query}", timeout=timeout)
    )
    rows: list[dict[str, object]] = []
    for date_group in payload.get("dates", []):
        for game in date_group.get("games", []):
            away = game["teams"]["away"]
            home = game["teams"]["home"]
            away_id = int(away["team"]["id"])
            home_id = int(home["team"]["id"])
            if away_id not in _TEAM_CODES_BY_ID or home_id not in _TEAM_CODES_BY_ID:
                continue
            rows.append(
                {
                    "game_pk": int(game["gamePk"]),
                    "game_date": game_date,
                    "game_time": datetime.fromisoformat(
                        game["gameDate"].replace("Z", "+00:00")
                    ),
                    "game_status": game.get("status", {}).get("detailedState"),
                    "away_team": _TEAM_CODES_BY_ID[away_id],
                    "home_team": _TEAM_CODES_BY_ID[home_id],
                    "away_team_id": away_id,
                    "home_team_id": home_id,
                    "away_probable_pitcher_id": (
                        int(away["probablePitcher"]["id"])
                        if away.get("probablePitcher", {}).get("id") is not None
                        else None
                    ),
                    "home_probable_pitcher_id": (
                        int(home["probablePitcher"]["id"])
                        if home.get("probablePitcher", {}).get("id") is not None
                        else None
                    ),
                }
            )
    return pl.DataFrame(
        rows,
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
        orient="row",
        strict=False,
    )


def fetch_mlb_rosters(
    team_ids: tuple[int, ...],
    game_date: date,
    *,
    roster_type: str = "active",
    timeout: float = 30.0,
) -> pl.DataFrame:
    """Fetch official team rosters containing MLB person IDs."""
    rows: list[dict[str, int | str]] = []
    for team_id in sorted(set(team_ids)):
        query = urlencode(
            {"rosterType": roster_type, "date": game_date.isoformat()}
        )
        url = f"{MLB_TEAM_ROSTER_URL.format(team_id=team_id)}?{query}"
        payload = json.loads(_fetch_bytes(url, timeout=timeout))
        rows.extend(
            {
                "team_id": team_id,
                "mlb_id": int(item["person"]["id"]),
                "player_name": item["person"]["fullName"],
            }
            for item in payload.get("roster", [])
            if item.get("person", {}).get("id") is not None
            and item.get("person", {}).get("fullName")
        )
    return pl.DataFrame(
        rows,
        schema={
            "team_id": pl.Int64,
            "mlb_id": pl.Int64,
            "player_name": pl.String,
        },
        orient="row",
    ).unique(subset=["team_id", "mlb_id"])


def resolve_player_ids(
    frame: pl.DataFrame,
    rosters: pl.DataFrame,
    *,
    output_column: str,
    aliases: Mapping[tuple[int, str], int] | None = None,
    require_complete: bool = True,
) -> pl.DataFrame:
    """Resolve scraped names within an official team roster, then retain IDs."""
    if frame.is_empty():
        return frame.with_columns(pl.lit(None, dtype=pl.Int64).alias(output_column))
    roster_keys = rosters.with_columns(
        pl.col("player_name")
        .map_elements(_name_key, return_dtype=pl.String)
        .alias("_name_key")
    )
    ambiguous = (
        roster_keys.group_by(["team_id", "_name_key"])
        .agg(pl.col("mlb_id").n_unique().alias("_ids"))
        .filter(pl.col("_ids") > 1)
    )
    if not ambiguous.is_empty():
        raise ValueError(
            "Official roster contains ambiguous normalized player names: "
            f"{ambiguous.head(10).to_dicts()}"
        )

    keyed = frame.with_columns(
        pl.col("player_name")
        .fill_null("")
        .map_elements(_name_key, return_dtype=pl.String)
        .alias("_name_key")
    )
    resolved = keyed.join(
        roster_keys.select("team_id", "_name_key", "mlb_id"),
        on=["team_id", "_name_key"],
        how="left",
        validate="m:1",
    )
    if aliases:
        alias_rows = [
            {
                "team_id": team_id,
                "_name_key": _name_key(name),
                "_alias_mlb_id": mlb_id,
            }
            for (team_id, name), mlb_id in aliases.items()
        ]
        alias_frame = pl.DataFrame(alias_rows)
        resolved = (
            resolved.join(
                alias_frame,
                on=["team_id", "_name_key"],
                how="left",
                validate="m:1",
            )
            .with_columns(
                pl.coalesce("mlb_id", "_alias_mlb_id").alias("mlb_id")
            )
            .drop("_alias_mlb_id")
        )

    missing = resolved.filter(pl.col("mlb_id").is_null()).select(
        "team", "player_name"
    )
    if require_complete and not missing.is_empty():
        raise ValueError(
            f"Could not resolve {missing.height} lineup players to MLB IDs: "
            f"{missing.unique().head(20).to_dicts()}"
        )
    return resolved.rename({"mlb_id": output_column}).drop("_name_key")


def attach_schedule(slate: DailySlate, schedule: pl.DataFrame) -> DailySlate:
    """Attach official game IDs and probable pitchers to parsed source rows."""
    join_columns = [
        "game_date",
        "away_team_id",
        "home_team_id",
        "away_team",
        "home_team",
    ]
    schedule_columns = [
        *join_columns,
        "game_pk",
        "game_time",
        "game_status",
        "away_probable_pitcher_id",
        "home_probable_pitcher_id",
    ]

    def _join(frame: pl.DataFrame) -> pl.DataFrame:
        out = frame.join(
            schedule.select(schedule_columns),
            on=join_columns,
            how="left",
            validate="m:1",
        )
        missing = out.filter(pl.col("game_pk").is_null())
        if not missing.is_empty():
            games = missing.select("away_team", "home_team").unique().to_dicts()
            raise ValueError(f"RotoGrinders games missing from MLB schedule: {games}")
        return out

    starters = _join(slate.starters).with_columns(
        pl.when(pl.col("is_home"))
        .then(pl.col("home_probable_pitcher_id"))
        .otherwise(pl.col("away_probable_pitcher_id"))
        .alias("official_probable_pitcher_id")
    )
    return DailySlate(lineups=_join(slate.lineups), starters=starters)


def validate_daily_slate(
    slate: DailySlate,
    *,
    require_confirmed: bool = False,
) -> None:
    """Reject malformed, incomplete, duplicate, or unresolved daily rows."""
    if slate.lineups.is_empty():
        raise ValueError("RotoGrinders returned no MLB batting-order rows")
    if slate.starters.is_empty():
        raise ValueError("RotoGrinders returned no MLB starting pitchers")

    invalid_orders = slate.lineups.filter(
        pl.col("batting_order").is_null()
        | ~pl.col("batting_order").is_between(1, 9)
    )
    if not invalid_orders.is_empty():
        raise ValueError("Daily lineup contains a missing/invalid batting-order slot")

    coverage = slate.lineups.group_by(["game_pk", "team_id"]).agg(
        pl.len().alias("rows"),
        pl.col("batting_order").n_unique().alias("spots"),
        pl.col("batter").n_unique().alias("batters"),
    )
    invalid_coverage = coverage.filter(
        (pl.col("rows") != 9)
        | (pl.col("spots") != 9)
        | (pl.col("batters") != 9)
    )
    if not invalid_coverage.is_empty():
        raise ValueError(
            "Daily lineup must contain nine unique resolved batters per team: "
            f"{invalid_coverage.to_dicts()}"
        )
    if slate.starters.filter(pl.col("pitcher").is_null()).height:
        raise ValueError("Daily slate contains an unresolved starting pitcher")
    starter_coverage = slate.starters.group_by(["game_pk", "team_id"]).agg(
        pl.len().alias("rows"),
        pl.col("pitcher").n_unique().alias("pitchers"),
    )
    if starter_coverage.filter(
        (pl.col("rows") != 1) | (pl.col("pitchers") != 1)
    ).height:
        raise ValueError("Daily slate must contain one resolved starter per team")
    probable_mismatch = slate.starters.filter(
        pl.col("official_probable_pitcher_id").is_not_null()
        & (pl.col("pitcher") != pl.col("official_probable_pitcher_id"))
    )
    if not probable_mismatch.is_empty():
        raise ValueError(
            "RotoGrinders starter disagrees with MLB probable pitcher: "
            f"{probable_mismatch.select('team', 'player_name', 'pitcher', 'official_probable_pitcher_id').to_dicts()}"
        )
    if require_confirmed and (
        slate.lineups.filter(pl.col("lineup_status") != "confirmed").height
        or slate.starters.filter(pl.col("lineup_status") != "confirmed").height
    ):
        raise ValueError("Daily slate still contains projected lineups")


def build_daily_slate(
    *,
    game_date: date | None = None,
    timeout: float = 30.0,
    require_confirmed: bool = False,
    aliases: Mapping[tuple[int, str], int] | None = None,
) -> DailySlate:
    """Fetch, resolve, validate, and return today's daily projection inputs."""
    game_date = game_date or datetime.now(ZoneInfo("America/New_York")).date()
    parsed = parse_rotogrinders_html(
        fetch_rotogrinders_html(timeout=timeout),
        game_date=game_date,
    )
    scheduled = attach_schedule(
        parsed,
        fetch_mlb_schedule(game_date, timeout=timeout),
    )
    team_ids = tuple(
        sorted(
            set(scheduled.lineups["team_id"].to_list())
            | set(scheduled.starters["team_id"].to_list())
        )
    )
    active = fetch_mlb_rosters(
        team_ids,
        game_date,
        roster_type="active",
        timeout=timeout,
    )
    try:
        lineups = resolve_player_ids(
            scheduled.lineups,
            active,
            output_column="batter",
            aliases=aliases,
        )
        starters = resolve_player_ids(
            scheduled.starters,
            active,
            output_column="pitcher",
            aliases=aliases,
        )
    except ValueError:
        roster_40 = fetch_mlb_rosters(
            team_ids,
            game_date,
            roster_type="40Man",
            timeout=timeout,
        )
        rosters = pl.concat([active, roster_40]).unique(
            subset=["team_id", "mlb_id"]
        )
        lineups = resolve_player_ids(
            scheduled.lineups,
            rosters,
            output_column="batter",
            aliases=aliases,
        )
        starters = resolve_player_ids(
            scheduled.starters,
            rosters,
            output_column="pitcher",
            aliases=aliases,
        )

    resolved = DailySlate(lineups=lineups, starters=starters)
    validate_daily_slate(resolved, require_confirmed=require_confirmed)
    return resolved


def write_daily_slate(
    slate: DailySlate,
    *,
    output_dir: Path = config.PROCESSED_DATA_DIR,
) -> tuple[Path, Path]:
    """Persist ID-resolved daily inputs as separate batter/pitcher parquets."""
    game_dates = slate.lineups["game_date"].unique().to_list()
    if len(game_dates) != 1:
        raise ValueError(f"Expected one slate date, found {game_dates}")
    stamp = game_dates[0].isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    lineup_path = output_dir / f"daily_lineups_{stamp}.parquet"
    starter_path = output_dir / f"daily_starters_{stamp}.parquet"
    slate.lineups.write_parquet(lineup_path)
    slate.starters.write_parquet(starter_path)
    return lineup_path, starter_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-confirmed",
        action="store_true",
        help="Fail until every RotoGrinders lineup is marked confirmed.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=config.PROCESSED_DATA_DIR,
    )
    args = parser.parse_args()
    slate = build_daily_slate(require_confirmed=args.require_confirmed)
    lineup_path, starter_path = write_daily_slate(
        slate,
        output_dir=args.output_dir,
    )
    print(f"Wrote {slate.lineups.height} lineup rows to {lineup_path}")
    print(f"Wrote {slate.starters.height} starter rows to {starter_path}")


if __name__ == "__main__":
    main()
