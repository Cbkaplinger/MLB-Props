"""Tests for the shared SharpAPI fetch contract (#113.3)."""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from Python.sharp_odds import (  # noqa: E402
    StrikeoutQuote,
    read_quotes_parquet,
    write_quotes_parquet,
)


def _quotes() -> list[StrikeoutQuote]:
    return [
        StrikeoutQuote(player_name="Logan Gilbert", line=6.5, over_american=-142,
                       under_american=112, sportsbook="fanduel",
                       home_team="SEA", away_team="TEX", event_id="e1",
                       event_start_time="2026-09-10T20:10:00Z", is_main_line=True),
        StrikeoutQuote(player_name="Hagen Smith", line=2.5, over_american=-123,
                       under_american=-104, sportsbook="draftkings",
                       home_team="CWS", away_team="PIT", event_id=None,
                       event_start_time=None, is_main_line=False),
    ]


def test_round_trip_including_nones(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    write_quotes_parquet(_quotes(), p)
    back = read_quotes_parquet(p, max_age_min=None)
    assert back == _quotes()
    assert back[1].event_id is None
    assert back[1].is_main_line is False


def test_stale_refusal(tmp_path: Path) -> None:
    import pytest
    p = tmp_path / "q.parquet"
    write_quotes_parquet(_quotes(), p)
    try:
        read_quotes_parquet(p, max_age_min=0.0)
    except ValueError as exc:
        assert "old >" in str(exc)
    else:
        raise AssertionError("stale file accepted")
    assert read_quotes_parquet(p, max_age_min=60 * 24) == _quotes()


def test_missing_file_errors(tmp_path: Path) -> None:
    import pytest
    with pytest.raises(FileNotFoundError):
        read_quotes_parquet(tmp_path / "nope.parquet")


def test_both_consumers_see_identical_prices(tmp_path: Path) -> None:
    p = tmp_path / "q.parquet"
    write_quotes_parquet(_quotes(), p)
    a = read_quotes_parquet(p, max_age_min=None)
    b = read_quotes_parquet(p, max_age_min=None)
    assert [(q.player_name, q.line, q.over_american, q.under_american) for q in a] == \
           [(q.player_name, q.line, q.over_american, q.under_american) for q in b]
    assert pl.read_parquet(p)["fetched_at_utc"][0] is not None


def test_poll_consumes_shared_file_verbatim(tmp_path: Path) -> None:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "production" / "odds"))
    import poll_odds
    from Python.odds_open import poll_open_tickets
    p = tmp_path / "q.parquet"
    write_quotes_parquet(_quotes(), p)
    board = pl.DataFrame([{"player_name": "Logan Gilbert", "p_over_6_5": 0.64,
                              "game_date": "2026-09-10"}])
    rows, unmatched, n = poll_open_tickets(
        board, unit=50.0, edge_floor=0.01,
        quotes=read_quotes_parquet(p, max_age_min=None))
    gil = [r for r in rows if r["player_name"] == "Logan Gilbert"]
    assert gil, f"unmatched: {unmatched}"
    assert gil[0]["over_price"] == -142.0 and gil[0]["under_price"] == 112.0
    assert poll_odds is not None  # module import path exercised
