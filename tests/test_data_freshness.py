"""Freshness classification + lockstep rules (pure logic; no IO)."""

import datetime as dt

from production.ops.check_data_freshness import classify_lag, in_season, season_end_ok


def test_in_season_window():
    assert in_season(dt.date(2026, 7, 1)) is True
    assert in_season(dt.date(2026, 9, 29)) is True
    assert in_season(dt.date(2026, 10, 6)) is False
    assert in_season(dt.date(2027, 3, 1)) is False


def test_fresh_within_two_days():
    assert classify_lag(0, True) == "GREEN"
    assert classify_lag(2, True) == "GREEN"


def test_three_day_gap_is_never_green():
    # The Sep-2026 L3 gap (3d) must flag, never pass silently.
    assert classify_lag(3, True) == "YELLOW"
    assert classify_lag(6, True) == "RED"


def test_offseason_season_end_ok():
    assert season_end_ok(dt.date(2026, 9, 27)) == "GREEN"
    # Mid-September max in offseason = incomplete season pull, must be RED.
    assert season_end_ok(dt.date(2026, 9, 16)) == "RED"
    assert season_end_ok(dt.date(2026, 8, 30)) == "YELLOW"
    assert season_end_ok(dt.date(2026, 7, 1)) == "RED"
