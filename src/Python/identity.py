"""Canonical MLB player identities and display-name enrichment.

Statcast's numeric ``pitcher`` and ``batter`` fields remain the durable keys
used for grouping and joins. Human-readable names are attached as metadata and
are never used to identify a player.
"""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import polars as pl

from . import config


PLAYER_ID_MAP_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1JgczhD5VDQ1EiXqVG-blttZcVwbZd5_Ne_mefUGwJnk/pub?output=csv"
)
MLB_PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people"


def normalized_name_expr(column: str) -> pl.Expr:
    """Convert ``Last, First`` to ``First Last``, preserving other formats."""
    name = pl.col(column).cast(pl.String).str.strip_chars()
    parts = name.str.split_exact(",", 1)
    last = parts.struct.field("field_0").str.strip_chars()
    first = parts.struct.field("field_1").str.strip_chars()
    return (
        pl.when(first.is_not_null() & (first != ""))
        .then(pl.concat_str([first, last], separator=" "))
        .otherwise(name)
    )


def player_map_from_csv(data: bytes) -> pl.DataFrame:
    """Parse MLB IDs and display names from the player register."""
    return (
        pl.read_csv(BytesIO(data), infer_schema_length=10_000)
        .select(
            pl.col("MLBID").cast(pl.Int64, strict=False).alias("mlb_id"),
            pl.coalesce(
                pl.col("MLBNAME").cast(pl.String),
                pl.col("PLAYERNAME").cast(pl.String),
            )
            .str.strip_chars()
            .alias("player_name"),
        )
        .filter(
            pl.col("mlb_id").is_not_null()
            & pl.col("player_name").is_not_null()
            & (pl.col("player_name") != "")
        )
        .unique(subset=["mlb_id"], keep="first")
        .sort("mlb_id")
    )


def load_player_map(
    path: Path = config.PLAYER_ID_MAP_PATH,
    *,
    refresh: bool = False,
    url: str = PLAYER_ID_MAP_URL,
    timeout: float = 30.0,
) -> pl.DataFrame:
    """Load the cached player map, downloading it only when necessary."""
    if path.exists() and not refresh:
        return pl.read_parquet(path)

    with urlopen(url, timeout=timeout) as response:  # noqa: S310
        players = player_map_from_csv(response.read())

    path.parent.mkdir(parents=True, exist_ok=True)
    players.write_parquet(path)
    return players


def fetch_mlb_player_names(
    player_ids: tuple[int, ...],
    *,
    timeout: float = 30.0,
) -> pl.DataFrame:
    """Resolve player IDs through MLB's official people endpoint."""
    rows: list[dict[str, int | str]] = []
    for start in range(0, len(player_ids), 100):
        chunk = player_ids[start : start + 100]
        query = urlencode({"personIds": ",".join(map(str, chunk))})
        with urlopen(f"{MLB_PEOPLE_URL}?{query}", timeout=timeout) as response:
            payload = json.load(response)
        rows.extend(
            {"mlb_id": int(person["id"]), "player_name": person["fullName"]}
            for person in payload.get("people", [])
            if person.get("id") is not None and person.get("fullName")
        )
    return pl.DataFrame(
        rows,
        schema={"mlb_id": pl.Int64, "player_name": pl.String},
    )


def complete_player_map(
    players: pl.DataFrame,
    player_ids: tuple[int, ...],
    *,
    cache_path: Path | None = config.PLAYER_ID_MAP_PATH,
) -> pl.DataFrame:
    """Fetch IDs absent from the register and optionally update the cache."""
    known = frozenset(int(value) for value in players["mlb_id"].to_list())
    missing = tuple(sorted(set(player_ids) - known))
    if not missing:
        return players

    fetched = fetch_mlb_player_names(missing)
    if fetched.is_empty():
        return players

    completed = (
        pl.concat([players, fetched], how="vertical_relaxed")
        .unique(subset=["mlb_id"], keep="last")
        .sort("mlb_id")
    )
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        completed.write_parquet(cache_path)
    return completed


def attach_player_name(
    frame: pl.DataFrame,
    players: pl.DataFrame,
    *,
    id_column: str,
    output_column: str,
) -> pl.DataFrame:
    """Left-join a display name while retaining the numeric player key."""
    names = players.select(
        pl.col("mlb_id").cast(frame.schema[id_column]).alias(id_column),
        pl.col("player_name").alias(output_column),
    )
    return frame.join(names, on=id_column, how="left", validate="m:1")


def unmapped_player_ids(
    frame: pl.DataFrame,
    *,
    id_column: str,
    name_column: str,
) -> tuple[int, ...]:
    """Return unique player IDs whose display name could not be resolved."""
    return tuple(
        int(player_id)
        for player_id in (
            frame.filter(pl.col(name_column).is_null())
            .select(id_column)
            .unique()
            .sort(id_column)
            .to_series()
            .drop_nulls()
            .to_list()
        )
    )


def enrich_batter_names(
    frame: pl.DataFrame,
    players: pl.DataFrame | None = None,
    *,
    resolve_missing: bool | None = None,
    require_complete: bool = False,
) -> pl.DataFrame:
    """Add ``batter_name`` from the ID map; Statcast has no batter-name fallback."""
    use_cached_map = players is None
    players = load_player_map() if use_cached_map else players
    resolve_missing = use_cached_map if resolve_missing is None else resolve_missing
    if resolve_missing:
        player_ids = tuple(
            int(player_id)
            for player_id in frame["batter"].drop_nulls().unique().to_list()
        )
        players = complete_player_map(players, player_ids)
    out = attach_player_name(
        frame,
        players,
        id_column="batter",
        output_column="batter_name",
    )
    missing = unmapped_player_ids(
        out,
        id_column="batter",
        name_column="batter_name",
    )
    if require_complete and missing:
        sample = list(missing[:10])
        raise ValueError(
            f"Could not map {len(missing)} batter IDs to names; sample={sample}"
        )
    return out


def enrich_pitcher_names(
    frame: pl.DataFrame,
    players: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Add normalized ``pitcher_name``, preferring the ID-map spelling."""
    out = frame.with_columns(
        normalized_name_expr("player_name").alias("pitcher_name")
    )
    if players is None:
        return out

    out = attach_player_name(
        out,
        players,
        id_column="pitcher",
        output_column="_mapped_pitcher_name",
    )
    return (
        out.with_columns(
            pl.coalesce("_mapped_pitcher_name", "pitcher_name").alias("pitcher_name")
        )
        .drop("_mapped_pitcher_name")
    )
