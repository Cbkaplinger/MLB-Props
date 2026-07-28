"""Tests for Python.statcast loading and plate-appearance extraction."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from Python import statcast as sc


def _pitch(game_pk, ab, pitch, events, batter=1):
    return {
        "game_pk": game_pk,
        "at_bat_number": ab,
        "pitch_number": pitch,
        "events": events,
        "batter": batter,
        "game_date": dt.datetime(2024, 4, 1),
    }


def _sample() -> pl.DataFrame:
    rows = [
        # AB1: two pitches, ends in a strikeout -> 1 PA, is_k
        _pitch(1, 1, 1, None, batter=10),
        _pitch(1, 1, 2, "strikeout", batter=10),
        # AB2: single -> PA, not K
        _pitch(1, 2, 1, "single", batter=11),
        # AB3: caught stealing -> NOT a plate appearance
        _pitch(1, 3, 1, "caught_stealing_2b", batter=11),
        # AB4: three pitches ending in a walk -> PA, not K
        _pitch(1, 4, 1, None, batter=10),
        _pitch(1, 4, 2, None, batter=10),
        _pitch(1, 4, 3, "walk", batter=10),
    ]
    return pl.DataFrame(rows)


def test_plate_appearances_counts_and_k_flag():
    pa = sc.plate_appearances(_sample())
    assert pa.height == 3  # AB1, AB2, AB4 (AB3 excluded as non-PA)
    assert int(pa["is_k"].sum()) == 1
    assert pa["game_date"].dtype == pl.Date


def test_plate_appearances_keeps_terminal_pitch():
    pa = sc.plate_appearances(_sample())
    ab1 = pa.filter(pl.col("at_bat_number") == 1)
    assert ab1.height == 1
    assert ab1["events"][0] == "strikeout"  # last pitch, not the null first pitch


def test_batter_k_rate():
    pa = sc.plate_appearances(_sample())
    kr = sc.batter_k_rate(pa, min_pa=1).sort("batter")
    b10 = kr.filter(pl.col("batter") == 10)
    assert int(b10["PA"][0]) == 2  # strikeout + walk
    assert int(b10["K"][0]) == 1
    assert abs(b10["k_rate"][0] - 0.5) < 1e-9


def test_intentional_walk_and_batter_interference_are_plate_appearances():
    frame = pl.DataFrame(
        {
            "game_date": [dt.date(2024, 4, 1), dt.date(2024, 4, 1)],
            "events": ["intent_walk", "batter_interference"],
            "description": ["ball", "hit_into_play"],
        }
    )
    flagged = sc.add_event_flags(frame)
    assert flagged["is_pa"].to_list() == [True, True]
    assert flagged["is_bb"].to_list() == [True, False]


def test_validate_statcast_season_accepts_official_game_ids():
    frame = pl.DataFrame(
        {
            "game_pk": [100, 100],
            "game_date": [dt.date(2025, 4, 1), dt.date(2025, 4, 1)],
            "game_year": [2025, 2025],
        }
    )
    sc.validate_statcast_season(frame, 2025, official_game_pks=frozenset({100}))


def test_validate_statcast_season_rejects_relabelled_game_ids():
    frame = pl.DataFrame(
        {
            "game_pk": [100],
            "game_date": [dt.date(2025, 4, 1)],
            "game_year": [2025],
        }
    )
    with pytest.raises(ValueError, match="do not match the official schedule"):
        sc.validate_statcast_season(
            frame,
            2025,
            official_game_pks=frozenset({200}),
        )


def test_update_statcast_season_skips_fetch_when_current(tmp_path, monkeypatch):
    path = tmp_path / "statcast_2026_regular.parquet"
    cached = pl.DataFrame(
        {
            "game_pk": [100, 101],
            "game_date": [dt.date(2026, 7, 26), dt.date(2026, 7, 26)],
            "game_year": [2026, 2026],
            "game_type": ["R", "R"],
        }
    )
    cached.write_parquet(path)

    monkeypatch.setattr(
        sc,
        "regular_season_schedule",
        lambda year: (dt.date(2026, 3, 20), dt.date(2026, 10, 5), frozenset({100, 101})),
    )
    monkeypatch.setattr(
        sc,
        "_ytd_official_game_pks",
        lambda year, pull_end: frozenset({100, 101}),
    )
    monkeypatch.setattr(
        sc,
        "_official_game_pks_between",
        lambda year, start, end: frozenset(),
    )

    def _boom(*_args, **_kwargs):
        raise AssertionError("should not fetch when cache is current")

    monkeypatch.setattr(sc, "_fetch_statcast_range", _boom)

    report = sc.update_statcast_season(
        2026,
        path=path,
        end_dt=dt.date(2026, 7, 26),
        verbose=False,
    )
    assert report["skipped_fetch"] is True
    assert report["fetched_rows"] == 0
    assert report["total_rows"] == 2


def test_update_statcast_season_appends_only_new_days(tmp_path, monkeypatch):
    path = tmp_path / "statcast_2026_regular.parquet"
    cached = pl.DataFrame(
        {
            "game_pk": [100],
            "game_date": [dt.date(2026, 7, 25)],
            "game_year": [2026],
            "game_type": ["R"],
        }
    )
    cached.write_parquet(path)

    monkeypatch.setattr(
        sc,
        "regular_season_schedule",
        lambda year: (dt.date(2026, 3, 20), dt.date(2026, 10, 5), frozenset({100, 101})),
    )
    monkeypatch.setattr(
        sc,
        "_ytd_official_game_pks",
        lambda year, pull_end: frozenset({100, 101}),
    )
    monkeypatch.setattr(
        sc,
        "_official_game_pks_between",
        lambda year, start, end: frozenset({101}),
    )

    def _fetch(start_date, end_date, *, verbose=True):
        assert start_date == dt.date(2026, 7, 26)
        assert end_date == dt.date(2026, 7, 26)
        return pl.DataFrame(
            {
                "game_pk": [101],
                "game_date": [dt.date(2026, 7, 26)],
                "game_year": [2026],
                "game_type": ["R"],
            }
        )

    monkeypatch.setattr(sc, "_fetch_statcast_range", _fetch)

    report = sc.update_statcast_season(
        2026,
        path=path,
        end_dt=dt.date(2026, 7, 26),
        verbose=False,
    )
    assert report["skipped_fetch"] is False
    assert report["fetched_rows"] == 1
    assert report["total_rows"] == 2
    assert pl.read_parquet(path)["game_pk"].sort().to_list() == [100, 101]


def test_update_statcast_season_rejects_empty_day_when_games_scheduled(
    tmp_path, monkeypatch
):
    path = tmp_path / "statcast_2026_regular.parquet"
    cached = pl.DataFrame(
        {
            "game_pk": [100],
            "game_date": [dt.date(2026, 7, 25)],
            "game_year": [2026],
            "game_type": ["R"],
        }
    )
    cached.write_parquet(path)

    monkeypatch.setattr(
        sc,
        "regular_season_schedule",
        lambda year: (dt.date(2026, 3, 20), dt.date(2026, 10, 5), frozenset({100, 101})),
    )
    monkeypatch.setattr(
        sc,
        "_official_game_pks_between",
        lambda year, start, end: frozenset({101}),
    )
    monkeypatch.setattr(
        sc,
        "_fetch_statcast_range",
        lambda *_a, **_k: pl.DataFrame(
            schema={
                "game_pk": pl.Int64,
                "game_date": pl.Date,
                "game_year": pl.Int32,
                "game_type": pl.Utf8,
            }
        ),
    )

    with pytest.raises(ValueError, match="missing"):
        sc.update_statcast_season(
            2026,
            path=path,
            end_dt=dt.date(2026, 7, 26),
            verbose=False,
        )
