"""Tests for mlb_props.statcast plate-appearance extraction."""

from __future__ import annotations

import datetime as dt

import polars as pl

from mlb_props import statcast as sc


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
