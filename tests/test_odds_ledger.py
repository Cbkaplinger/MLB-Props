"""Tests for odds ledger tip timestamps + idempotent open/close."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from Python.odds_ledger import (
    append_open_rows,
    apply_close,
    dedupe_ledger_props,
    minutes_to_tip,
    open_dedupe_key,
    parse_event_start_utc,
    replace_open_slate,
    score_quote_to_row,
    stable_ticket_id,
)


def _row(**kwargs):
    base = dict(
        game_date="2026-07-30",
        game_pk=1,
        pitcher=100,
        player_name="Sean Burke",
        line=6.5,
        over_price=-110,
        under_price=-110,
        p_model_over=0.58,
        book="draftkings",
        unit_dollars=50.0,
        source="test",
        event_id="evt_1",
        event_start_time="2026-07-30T23:10:00Z",
        logged_at=datetime(2026, 7, 30, 14, 0, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return score_quote_to_row(**base)


def test_parse_event_start_utc_z() -> None:
    dt = parse_event_start_utc("2026-07-30T23:10:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 23


def test_minutes_to_tip() -> None:
    tip = datetime(2026, 7, 30, 23, 10, tzinfo=timezone.utc)
    as_of = datetime(2026, 7, 30, 22, 10, tzinfo=timezone.utc)
    assert minutes_to_tip(tip, as_of=as_of) == 60.0


def test_score_quote_stores_tip_fields() -> None:
    row = _row()
    assert row["event_id"] == "evt_1"
    assert row["event_start_time_utc"] is not None
    assert row["minutes_to_tip_at_open"] == 550.0  # 14:00 → 23:10
    assert row["closed_at_utc"] is None
    assert "2026-07-30" in row["ticket_id"]
    assert "2026-07-30T14:00" not in row["ticket_id"]


def test_stable_ticket_id_deterministic() -> None:
    a = stable_ticket_id(
        game_date="2026-07-30",
        player_name="Sean Burke",
        line=6.5,
        book="DraftKings",
        side="over",
    )
    b = stable_ticket_id(
        game_date="2026-07-30",
        player_name="Sean Burke",
        line=6.5,
        book="draftkings",
        side="over",
    )
    assert a == b


def test_append_open_rows_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "ledger.parquet"
    row = _row()
    frame, n1, s1 = append_open_rows([row], path=path)
    assert n1 == 1 and s1 == 0 and frame.height == 1
    frame2, n2, s2 = append_open_rows([row], path=path)
    assert n2 == 0 and s2 == 1 and frame2.height == 1


def test_open_dedupe_key_ignores_side() -> None:
    k1 = open_dedupe_key(
        game_date="2026-07-30", player_name="Sean Burke", book="DK", line=6.5
    )
    k2 = open_dedupe_key(
        game_date="2026-07-30", player_name="sean burke", book="dk", line=6.5
    )
    assert k1 == k2


def test_replace_open_slate_drops_unclosed_same_day(tmp_path: Path) -> None:
    path = tmp_path / "ledger.parquet"
    old = _row(book="fanduel")
    append_open_rows([old], path=path)
    fresh = _row(
        book="draftkings",
        logged_at=datetime(2026, 7, 30, 15, 0, tzinfo=timezone.utc),
    )
    frame, n_written, n_removed = replace_open_slate(
        [fresh], slate="2026-07-30", path=path
    )
    assert n_removed == 1
    assert n_written == 1
    assert frame.height == 1
    assert frame["book"][0] == "draftkings"


def test_replace_open_slate_keeps_closed_rows(tmp_path: Path) -> None:
    path = tmp_path / "ledger.parquet"
    row = _row()
    append_open_rows([row], path=path)
    ledger = pl.read_parquet(path)
    closed = apply_close(
        ledger,
        ticket_id=row["ticket_id"],
        close_over=-115,
        close_under=-105,
        closed_at=datetime(2026, 7, 30, 23, 5, tzinfo=timezone.utc),
    )
    closed.write_parquet(path)
    fresh = _row(book="fanduel")
    frame, n_written, n_removed = replace_open_slate(
        [fresh], slate="2026-07-30", path=path
    )
    assert n_removed == 0
    assert n_written == 1
    assert frame.height == 2


def test_apply_close_sets_closed_at_and_is_idempotent() -> None:
    row = _row()
    ledger = pl.DataFrame([row])
    closed_at = datetime(2026, 7, 30, 23, 5, tzinfo=timezone.utc)
    once = apply_close(
        ledger,
        ticket_id=row["ticket_id"],
        close_over=-115,
        close_under=-105,
        closed_at=closed_at,
    )
    r = once.to_dicts()[0]
    assert r["clv_pp"] is not None
    assert r["closed_at_utc"].startswith("2026-07-30T23:05")
    assert r["minutes_to_tip_at_close"] == 5.0

    twice = apply_close(
        once,
        ticket_id=row["ticket_id"],
        close_over=-200,
        close_under=+150,
        closed_at=datetime(2026, 7, 30, 23, 9, tzinfo=timezone.utc),
    )
    r2 = twice.to_dicts()[0]
    assert r2["close_over"] == -115
    assert r2["closed_at_utc"].startswith("2026-07-30T23:05")


def test_dedupe_ledger_props_keeps_best_edge_book() -> None:
    dk = _row(book="draftkings", over_price=-126, under_price=104, p_model_over=0.35)
    fd = _row(book="fanduel", over_price=-130, under_price=100, p_model_over=0.35)
    # Force edges: DK higher edge on under side via p_model
    assert dk["player_name"] == fd["player_name"]
    assert dk["line"] == fd["line"]
    # Ensure DK has higher edge than FD for sort
    if float(dk["edge"]) < float(fd["edge"]):
        dk, fd = fd, dk
    led = pl.DataFrame([dk, fd])
    one = dedupe_ledger_props(led)
    assert one.height == 1
    assert float(one["edge"][0]) == max(float(dk["edge"]), float(fd["edge"]))
    assert one["book"][0] == (dk["book"] if float(dk["edge"]) >= float(fd["edge"]) else fd["book"])


def test_dedupe_ledger_props_keeps_over_and_under_separate() -> None:
    # Same player/line but opposite sides are DISTINCT bettable props: they must
    # NOT be collapsed into one row (the old key lacked ``side`` and merged them).
    over = _row(book="draftkings", over_price=-120, under_price=+105, p_model_over=0.62)
    under = _row(book="fanduel", over_price=-115, under_price=+110, p_model_over=0.38)
    assert over["side"] == "over"
    assert under["side"] == "under"
    led = pl.DataFrame([over, under])
    ded = dedupe_ledger_props(led)
    assert ded.height == 2
    assert sorted(ded["side"].to_list()) == ["over", "under"]


def test_dedupe_ledger_props_keeps_best_book_per_side() -> None:
    # Two books on the SAME side collapse to one row (best edge); a second side
    # on the same line is retained separately.
    dk_over = _row(book="draftkings", over_price=-120, under_price=104, p_model_over=0.62)
    fd_over = _row(book="fanduel", over_price=-130, under_price=100, p_model_over=0.62)
    under = _row(book="novig", over_price=-110, under_price=+100, p_model_over=0.42)
    led = pl.DataFrame([dk_over, fd_over, under])
    ded = dedupe_ledger_props(led)
    assert ded.height == 2
    assert sorted(ded["side"].to_list()) == ["over", "under"]
    over_rows = ded.filter(pl.col("side") == "over")
    assert over_rows.height == 1
    assert float(over_rows["edge"][0]) == max(float(dk_over["edge"]), float(fd_over["edge"]))
