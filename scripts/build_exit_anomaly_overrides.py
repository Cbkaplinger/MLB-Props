"""Build/refresh exit anomaly overrides from official MLB feed + heuristics.

Writes/updates: production/ops/exit_anomaly_overrides.csv

Signal tiers:
- High confidence:
  - explicit ejection event from MLB game feed playEvents
  - suspended game states from MLB game status
- Medium confidence:
  - game called/completed early status (weather-tagged when rain/storm context exists)
- Low confidence:
  - starter disagreement heuristic (opener/bulk surprise candidate)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OVERRIDE_PATH = ROOT / "production" / "ops" / "exit_anomaly_overrides.csv"
GRADED_PATH = ROOT / "artifacts" / "projection_log" / "graded.parquet"
MLB_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"

KEY_COLS = ["game_pk", "pitcher", "game_date"]
OUT_COLS = KEY_COLS + [
    "exit_anomaly_flag",
    "exit_anomaly_type",
    "exit_anomaly_confidence",
    "exit_anomaly_source",
    "note",
]


def _normalize_keys(df: pl.DataFrame) -> pl.DataFrame:
    out = df
    if "game_pk" in out.columns:
        out = out.with_columns(pl.col("game_pk").cast(pl.Int64, strict=False))
    if "pitcher" in out.columns:
        out = out.with_columns(pl.col("pitcher").cast(pl.Int64, strict=False))
    if "game_date" in out.columns:
        out = out.with_columns(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10))
    return out


def _load_existing() -> pl.DataFrame:
    if not OVERRIDE_PATH.exists():
        return pl.DataFrame(schema={c: pl.Utf8 for c in OUT_COLS})
    existing = pl.read_csv(OVERRIDE_PATH)
    if existing.is_empty():
        return existing
    existing = _normalize_keys(existing)
    for col, default in (
        ("exit_anomaly_flag", True),
        ("exit_anomaly_type", "other_exogenous"),
        ("exit_anomaly_confidence", "manual"),
        ("exit_anomaly_source", "manual_override"),
        ("note", None),
    ):
        if col not in existing.columns:
            existing = existing.with_columns(pl.lit(default).alias(col))
    return existing.select([c for c in OUT_COLS if c in existing.columns]).with_columns(
        pl.col("exit_anomaly_flag").cast(pl.Boolean, strict=False)
    )


def _fetch_feed(game_pk: int, timeout: float = 20.0) -> dict:
    url = MLB_FEED_URL.format(game_pk=game_pk)
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def _status_tags(feed: dict, pitchers: list[int], game_pk: int, game_date: str) -> list[dict]:
    out: list[dict] = []
    game_data = feed.get("gameData", {})
    status = game_data.get("status", {}) or {}
    detailed = str(status.get("detailedState", "")).strip()
    lower = detailed.lower()
    weather = game_data.get("weather", {}) or {}
    weather_text = " ".join(
        str(weather.get(k, "")) for k in ("condition", "wind", "temp")
    ).lower()

    has_rain_context = bool(re.search(r"rain|storm|thunder|lightning", weather_text))
    has_rain_context = has_rain_context or bool(
        re.search(r"rain|storm|thunder|lightning", lower)
    )
    if "suspended" in lower:
        anomaly_type = "suspension_shortened"
        conf = "high"
        source = "game_status"
        note = f"MLB status detailedState={detailed}"
    elif any(tok in lower for tok in ("completed early", "called")):
        anomaly_type = "weather_shortened" if has_rain_context else "other_exogenous"
        conf = "medium"
        source = "game_status"
        note = (
            f"MLB status detailedState={detailed}; "
            f"weather_context={'rain/storm' if has_rain_context else 'none'}"
        )
    else:
        return out

    for pitcher in pitchers:
        out.append(
            {
                "game_pk": game_pk,
                "pitcher": pitcher,
                "game_date": game_date,
                "exit_anomaly_flag": True,
                "exit_anomaly_type": anomaly_type,
                "exit_anomaly_confidence": conf,
                "exit_anomaly_source": source,
                "note": note,
            }
        )
    return out


def _ejection_tags(
    feed: dict,
    game_pk: int,
    default_game_date: str,
    valid_pitchers: set[int],
) -> list[dict]:
    out: list[dict] = []
    game_date = (
        str(
            feed.get("gameData", {})
            .get("datetime", {})
            .get("officialDate", default_game_date)
        )[:10]
    )
    plays = feed.get("liveData", {}).get("plays", {}).get("allPlays", []) or []
    for play in plays:
        for pe in play.get("playEvents", []) or []:
            details = pe.get("details", {}) or {}
            event_type = str(details.get("eventType", "")).lower()
            if event_type != "ejection":
                continue
            player_id = pe.get("player", {}).get("id")
            if player_id is None:
                continue
            player_id = int(player_id)
            if player_id not in valid_pitchers:
                # Ejection can be manager/coach/position player; keep pitcher-only tags.
                continue
            desc = str(details.get("description", "")).strip()
            out.append(
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
    return out


def _opener_bulk_heuristic(graded: pl.DataFrame) -> pl.DataFrame:
    if "starter_disagreement" not in graded.columns:
        return pl.DataFrame(schema={c: pl.Utf8 for c in OUT_COLS})
    candidates = graded.filter(pl.col("starter_disagreement") == True)  # noqa: E712
    if candidates.is_empty():
        return pl.DataFrame(schema={c: pl.Utf8 for c in OUT_COLS})
    return (
        candidates.select([c for c in KEY_COLS if c in candidates.columns])
        .unique()
        .with_columns(
            pl.lit(True).alias("exit_anomaly_flag"),
            pl.lit("opener_bulk_surprise").alias("exit_anomaly_type"),
            pl.lit("low").alias("exit_anomaly_confidence"),
            pl.lit("starter_disagreement_heuristic").alias("exit_anomaly_source"),
            pl.lit(
                "Starter source disagreement heuristic; verify with official feed/game notes."
            ).alias("note"),
        )
    )


def _priority_expr() -> pl.Expr:
    return (
        pl.when(pl.col("exit_anomaly_source") == "manual_override")
        .then(pl.lit(100))
        .when(pl.col("exit_anomaly_source") == "mlb_feed_event")
        .then(pl.lit(90))
        .when(pl.col("exit_anomaly_source") == "game_status")
        .then(pl.lit(80))
        .when(pl.col("exit_anomaly_source") == "starter_disagreement_heuristic")
        .then(pl.lit(40))
        .otherwise(pl.lit(10))
        .alias("_priority")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="Optional cap for MLB feed calls (debug/smoke mode).",
    )
    args = parser.parse_args()

    if not GRADED_PATH.exists():
        raise FileNotFoundError(f"Missing {GRADED_PATH}. Run grading flow first.")

    graded = _normalize_keys(
        pl.read_parquet(GRADED_PATH).select(
            [c for c in ["game_pk", "pitcher", "game_date", "starter_disagreement"] if c in pl.read_parquet(GRADED_PATH, n_rows=1).columns]
        )
    )
    graded_keys = graded.select([c for c in KEY_COLS if c in graded.columns]).unique()
    if graded_keys.is_empty():
        raise RuntimeError("No graded keys found to build override candidates.")

    existing = _load_existing()
    by_game = (
        graded_keys.group_by(["game_pk", "game_date"])
        .agg(pl.col("pitcher").drop_nulls().unique().alias("pitchers"))
        .sort("game_date")
    )
    if args.max_games is not None:
        by_game = by_game.tail(args.max_games)

    auto_rows: list[dict] = []
    fetch_errors = 0
    for row in by_game.iter_rows(named=True):
        game_pk = int(row["game_pk"])
        game_date = str(row["game_date"])
        pitchers = [int(p) for p in (row.get("pitchers") or [])]
        try:
            feed = _fetch_feed(game_pk)
        except URLError:
            fetch_errors += 1
            continue
        except TimeoutError:
            fetch_errors += 1
            continue
        valid_pitchers = set(pitchers)
        auto_rows.extend(
            _ejection_tags(
                feed,
                game_pk=game_pk,
                default_game_date=game_date,
                valid_pitchers=valid_pitchers,
            )
        )
        auto_rows.extend(_status_tags(feed, pitchers=pitchers, game_pk=game_pk, game_date=game_date))

    auto_feed = pl.DataFrame(auto_rows) if auto_rows else pl.DataFrame(schema={c: pl.Utf8 for c in OUT_COLS})
    auto_feed = _normalize_keys(auto_feed) if not auto_feed.is_empty() else auto_feed
    if not auto_feed.is_empty():
        # Keep only starter-game keys present in graded artifacts.
        auto_feed = auto_feed.join(graded_keys, on=KEY_COLS, how="inner")
    auto_openers = _opener_bulk_heuristic(graded)

    existing_tagged = (
        existing.select([c for c in OUT_COLS if c in existing.columns]).with_columns(pl.lit(0).alias("_fresh"))
        if not existing.is_empty()
        else pl.DataFrame(schema={**{c: pl.Utf8 for c in OUT_COLS}, "_fresh": pl.Int64})
    )
    auto_feed_tagged = (
        auto_feed.select([c for c in OUT_COLS if c in auto_feed.columns]).with_columns(pl.lit(1).alias("_fresh"))
        if not auto_feed.is_empty()
        else pl.DataFrame(schema={**{c: pl.Utf8 for c in OUT_COLS}, "_fresh": pl.Int64})
    )
    auto_openers_tagged = (
        auto_openers.select([c for c in OUT_COLS if c in auto_openers.columns]).with_columns(pl.lit(1).alias("_fresh"))
        if not auto_openers.is_empty()
        else pl.DataFrame(schema={**{c: pl.Utf8 for c in OUT_COLS}, "_fresh": pl.Int64})
    )
    combined = pl.concat(
        [existing_tagged, auto_feed_tagged, auto_openers_tagged],
        how="diagonal_relaxed",
    )
    combined = _normalize_keys(combined).with_columns(
        pl.col("exit_anomaly_flag").fill_null(True).cast(pl.Boolean, strict=False),
        pl.col("exit_anomaly_type").fill_null("other_exogenous"),
        pl.col("exit_anomaly_confidence").fill_null("low"),
        pl.col("exit_anomaly_source").fill_null("manual_override"),
        pl.col("note").fill_null(""),
        _priority_expr(),
    )
    out = (
        combined.sort(["_priority", "_fresh", "game_date"], descending=[True, True, True])
        .unique(subset=KEY_COLS, keep="first")
        .drop(["_priority", "_fresh"])
        .sort(["game_date", "game_pk", "pitcher"], descending=[True, True, False])
    )
    # Persist only graded-matched auto rows; allow unmatched manual rows intentionally.
    auto_matched = (
        out.filter(pl.col("exit_anomaly_source") != "manual_override")
        .join(graded_keys, on=KEY_COLS, how="inner")
    )
    manual_all = out.filter(pl.col("exit_anomaly_source") == "manual_override")
    out = (
        pl.concat([manual_all, auto_matched], how="vertical_relaxed")
        .unique(subset=KEY_COLS, keep="first")
        .sort(["game_date", "game_pk", "pitcher"], descending=[True, True, False])
    )

    OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.write_csv(OVERRIDE_PATH)

    print(f"wrote {OVERRIDE_PATH}")
    print(f"rows={out.height} | fetch_errors={fetch_errors}")
    print(out.group_by(["exit_anomaly_type", "exit_anomaly_confidence", "exit_anomaly_source"]).agg(pl.len().alias("n")).sort("n", descending=True))
    unmatched = out.join(graded_keys, on=KEY_COLS, how="anti")
    print(f"unmatched_vs_graded={unmatched.height}")
    if unmatched.height:
        print(unmatched.head(10))


if __name__ == "__main__":
    main()
