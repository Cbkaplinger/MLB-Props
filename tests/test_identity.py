from __future__ import annotations

import polars as pl
import pytest

from Python import identity


def _players() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "mlb_id": [10, 20],
            "player_name": ["Jane Ace", "John Hitter"],
        },
        schema={"mlb_id": pl.Int64, "player_name": pl.String},
    )


def test_pitcher_name_prefers_id_map_and_keeps_id() -> None:
    starts = pl.DataFrame(
        {"pitcher": [10, 11], "player_name": ["Ace, Jane", "Fallback, Pat"]}
    )

    out = identity.enrich_pitcher_names(starts, _players())

    assert out["pitcher"].to_list() == [10, 11]
    assert out["pitcher_name"].to_list() == ["Jane Ace", "Pat Fallback"]


def test_batter_name_join_keeps_unmatched_players() -> None:
    games = pl.DataFrame({"game_pk": [1, 1], "batter": [20, 21]})

    out = identity.attach_player_name(
        games,
        _players(),
        id_column="batter",
        output_column="batter_name",
    )

    assert out["batter"].to_list() == [20, 21]
    assert out["batter_name"].to_list() == ["John Hitter", None]


def test_enrich_batter_names_reports_unmapped_ids() -> None:
    games = pl.DataFrame({"game_pk": [1, 1], "batter": [20, 21]})
    out = identity.enrich_batter_names(games, _players())

    assert identity.unmapped_player_ids(
        out,
        id_column="batter",
        name_column="batter_name",
    ) == (21,)


def test_enrich_batter_names_can_require_complete_map() -> None:
    games = pl.DataFrame({"game_pk": [1], "batter": [21]})
    with pytest.raises(ValueError, match="Could not map 1 batter IDs"):
        identity.enrich_batter_names(games, _players(), require_complete=True)


def test_player_map_csv_uses_mlb_name() -> None:
    csv = b"MLBID,MLBNAME,PLAYERNAME\n10,Jane Ace,Jane Alternate\n"
    out = identity.player_map_from_csv(csv)
    assert out.row(0, named=True) == {"mlb_id": 10, "player_name": "Jane Ace"}
