"""Backfill historical exit anomaly overrides from MLB status + feed events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
PITCHER_GAMES_PATH = ROOT / "data" / "processed" / "pitcher_games.parquet"
DEFAULT_OUT = ROOT / "artifacts" / "projection_log" / "exit_anomaly_overrides_hist_2023_2024.csv"
MLB_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"


def _schedule_games(season: int) -> list[dict]:
    query = urlencode({"sportId": 1, "season": season, "gameType": "R"})
    with urlopen(f"https://statsapi.mlb.com/api/v1/schedule?{query}", timeout=30.0) as r:
        payload = json.load(r)
    return [
        g
        for d in payload.get("dates", [])
        for g in d.get("games", [])
        if g.get("gameType") == "R"
    ]


def _fetch_feed(game_pk: int, timeout: float = 20.0) -> dict:
    with urlopen(MLB_FEED_URL.format(game_pk=game_pk), timeout=timeout) as r:
        return json.load(r)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-season", type=int, default=2023)
    parser.add_argument("--end-season", type=int, default=2024)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--include-ejections",
        action="store_true",
        default=False,
        help="Also scan MLB feed playEvents for pitcher ejections (slow).",
    )
    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="Optional cap on game_pk feed scans (debug/smoke mode).",
    )
    args = parser.parse_args()

    pg = pl.read_parquet(PITCHER_GAMES_PATH).with_columns(
        pl.col("game_pk").cast(pl.Int64, strict=False),
        pl.col("pitcher").cast(pl.Int64, strict=False),
        pl.col("game_date").cast(pl.Utf8).str.slice(0, 10),
    )
    pg = pg.filter(
        (pl.col("season") >= args.start_season) & (pl.col("season") <= args.end_season)
    )
    keys = pg.select(["game_pk", "pitcher", "game_date"]).unique()
    pitchers_by_game = (
        keys.group_by("game_pk")
        .agg(pl.col("pitcher").drop_nulls().unique().alias("pitchers"))
    )
    game_pitcher_map = {
        int(r["game_pk"]): {int(p) for p in r["pitchers"]}
        for r in pitchers_by_game.iter_rows(named=True)
    }

    status_rows: list[dict] = []
    for season in range(args.start_season, args.end_season + 1):
        for game in _schedule_games(season):
            game_pk = int(game.get("gamePk"))
            detailed = str((game.get("status") or {}).get("detailedState", "")).strip()
            lower = detailed.lower()
            if "suspended" in lower:
                an_type = "suspension_shortened"
                conf = "high"
            elif any(tok in lower for tok in ("completed early", "called")):
                an_type = "weather_shortened" if "rain" in lower else "other_exogenous"
                conf = "medium"
            else:
                continue
            status_rows.append(
                {
                    "game_pk": game_pk,
                    "game_date": str(game.get("officialDate", ""))[:10],
                    "exit_anomaly_type": an_type,
                    "exit_anomaly_confidence": conf,
                    "exit_anomaly_source": "game_status",
                    "note": f"MLB schedule detailedState={detailed}",
                }
            )

    ejection_rows: list[dict] = []
    feed_calls = 0
    feed_errors = 0
    if args.include_ejections:
        game_pks = sorted(game_pitcher_map.keys())
        if args.max_games is not None:
            game_pks = game_pks[: args.max_games]
        for game_pk in game_pks:
            try:
                feed = _fetch_feed(game_pk)
                feed_calls += 1
            except (URLError, TimeoutError):
                feed_errors += 1
                continue
            game_date = str(
                (feed.get("gameData", {}).get("datetime", {}) or {}).get("officialDate", "")
            )[:10]
            plays = (feed.get("liveData", {}).get("plays", {}) or {}).get("allPlays", []) or []
            valid_pitchers = game_pitcher_map.get(game_pk, set())
            for play in plays:
                for pe in play.get("playEvents", []) or []:
                    details = pe.get("details", {}) or {}
                    if str(details.get("eventType", "")).lower() != "ejection":
                        continue
                    player_id = pe.get("player", {}).get("id")
                    if player_id is None:
                        continue
                    player_id = int(player_id)
                    if player_id not in valid_pitchers:
                        continue
                    desc = str(details.get("description", "")).strip()
                    ejection_rows.append(
                        {
                            "game_pk": game_pk,
                            "pitcher": player_id,
                            "game_date": game_date,
                            "exit_anomaly_flag": True,
                            "exit_anomaly_type": "ejection",
                            "exit_anomaly_confidence": "high",
                            "exit_anomaly_source": "mlb_feed_event",
                            "note": f"MLB playEvents ejection: {desc}"[:500],
                        }
                    )

    if not status_rows and not ejection_rows:
        out = pl.DataFrame(
            schema={
                "game_pk": pl.Int64,
                "pitcher": pl.Int64,
                "game_date": pl.Utf8,
                "exit_anomaly_flag": pl.Boolean,
                "exit_anomaly_type": pl.Utf8,
                "exit_anomaly_confidence": pl.Utf8,
                "exit_anomaly_source": pl.Utf8,
                "note": pl.Utf8,
            }
        )
    else:
        status = (
            pl.DataFrame(status_rows).with_columns(
                pl.col("game_pk").cast(pl.Int64, strict=False),
                pl.col("game_date").cast(pl.Utf8).str.slice(0, 10),
            )
            if status_rows
            else pl.DataFrame()
        )
        status_for_starters = (
            keys.join(status, on=["game_pk", "game_date"], how="inner")
            .with_columns(pl.lit(True).alias("exit_anomaly_flag"))
            .select(
                [
                    "game_pk",
                    "pitcher",
                    "game_date",
                    "exit_anomaly_flag",
                    "exit_anomaly_type",
                    "exit_anomaly_confidence",
                    "exit_anomaly_source",
                    "note",
                ]
            )
            if status_rows
            else pl.DataFrame()
        )
        ejections = (
            pl.DataFrame(ejection_rows).with_columns(
                pl.col("game_pk").cast(pl.Int64, strict=False),
                pl.col("pitcher").cast(pl.Int64, strict=False),
                pl.col("game_date").cast(pl.Utf8).str.slice(0, 10),
                pl.col("exit_anomaly_flag").cast(pl.Boolean, strict=False),
            )
            if ejection_rows
            else pl.DataFrame()
        )
        combined = (
            pl.concat([status_for_starters, ejections], how="vertical_relaxed")
            if not status_for_starters.is_empty() and not ejections.is_empty()
            else (status_for_starters if not status_for_starters.is_empty() else ejections)
        )
        out = (
            combined
            .unique(subset=["game_pk", "pitcher", "game_date"], keep="first")
            .sort(["game_date", "game_pk", "pitcher"], descending=[True, True, False])
        )

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    out.write_csv(args.output_path)
    print(f"wrote {args.output_path}")
    print(f"rows={out.height}")
    if args.include_ejections:
        print(f"feed_calls={feed_calls} feed_errors={feed_errors} ejection_rows={len(ejection_rows)}")
    if out.height:
        print(
            out.group_by(
                ["exit_anomaly_type", "exit_anomaly_confidence", "exit_anomaly_source"]
            )
            .agg(pl.len().alias("n"))
            .sort("n", descending=True)
        )


if __name__ == "__main__":
    main()
