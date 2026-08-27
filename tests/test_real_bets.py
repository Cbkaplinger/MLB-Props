"""Integration tests for the append-only real-money bet ledger.

The core contract these tests enforce: **a real ticket can never silently
drop** (the failure mode that already lost the 8/24 batch once). Every ticket
that enters ``append_real_bets`` is either appended or returned in
``skipped_ids``; nothing melts into the frame unobserved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from Python import real_bets as rb  # noqa: E402


def _row(
    player: str = "Valdez",
    game_date: str = "2026-08-24",
    line: float = 4.5,
    side: str = "under",
    book: str = "draftkings",
    **extra,
) -> dict:
    base = {
        "game_date": game_date,
        "player_name": player,
        "line": line,
        "book": book,
        "side": side,
        "bet_price": -120,
        "stake": 50.0,
        "result": "win",
        "result_source": "user",
        "pnl": 41.67,
        "placed_utc": "2026-08-24T15:00:00Z",
    }
    base.update(extra)
    return base


def _empty_ledger(tmp_path: Path) -> Path:
    p = tmp_path / "real_bets.parquet"
    if p.exists():
        p.unlink()
    return p


def test_append_two_ids_and_two_ticket_ids(tmp_path: Path) -> None:
    """New tickets append; a same-id ticket inside one batch is reported, not lost."""
    p = _empty_ledger(tmp_path)
    batch = [_row(player="Valdez"), _row(player="Suarez", book="novig")]
    frame, n_appended, skipped = rb.append_real_bets(batch, path=p)
    assert n_appended == 2
    assert skipped == []
    assert frame.height == 2
    assert frame["ticket_id"].n_unique() == 2


def test_duplicate_within_batch_is_reported(tmp_path: Path) -> None:
    """A key repeated inside a single batch is skipped AND returned."""
    p = _empty_ledger(tmp_path)
    dup = _row(player="Valdez")
    batch = [dup, dup, _row(player="Suarez", book="novig")]
    frame, n_appended, skipped = rb.append_real_bets(batch, path=p)
    assert n_appended == 2
    assert len(skipped) == 1
    assert skipped[0] == dup["game_date"] + "_valdez_4.5_draftkings_under"
    assert frame.height == 2


def test_reappend_idempotent_and_never_silent(tmp_path: Path) -> None:
    """Re-appending the same batch appends 0 and reports every id as skipped."""
    p = _empty_ledger(tmp_path)
    batch = [_row(player="Valdez"), _row(player="Suarez", book="novig"),
             _row(player="Skenes", line=6.5, book="fanduel", side="under", bet_price=-130, stake=50, pnl=38.46)]
    _, n, _ = rb.append_real_bets(batch, path=p)
    assert n == 3
    frame, n2, skipped2 = rb.append_real_bets(batch, path=p)
    assert n2 == 0
    assert frame.height == 3  # unchanged
    assert len(skipped2) == 3  # every id reported, nothing silent
    assert sorted(skipped2) == sorted(frame["ticket_id"].to_list())


def test_real_target_is_never_the_paper_ledger(tmp_path: Path) -> None:
    """Backfill must target the real-bets path, not the paper-sim ledger path."""
    from Python.odds_ledger import LEDGER_PATH

    assert rb.REAL_BETS_PATH.name == "real_bets.parquet"
    assert rb.REAL_BETS_PATH != LEDGER_PATH


def test_summary_matches_hand_wins(tmp_path: Path) -> None:
    p = _empty_ledger(tmp_path)
    rows = [
        _row(player="Valdez", pnl=41.67, result="win"),
        _row(player="Messick", line=6.5, side="over", book="draftkings", bet_price=-110, pnl=-50.0, result="loss"),
    ]
    rb.append_real_bets(rows, path=p)
    s = rb.real_bets_summary(rb.load_real_bets(p))
    assert s["n"] == 2
    assert s["wins"] == 1 and s["losses"] == 1
    assert s["pnl"] == pytest.approx(41.67 - 50.0)
    assert s["stake"] == pytest.approx(100.0)


def test_schema_columns_stable(tmp_path: Path) -> None:
    """Every appended row lands with the fixed auditable schema columns."""
    p = _empty_ledger(tmp_path)
    rb.append_real_bets([_row(player="Valdez")], path=p)
    frame = rb.load_real_bets(p)
    assert set(frame.columns) == set(rb._FINAL_KEYS)  # noqa: SLF001
    assert "bet_price" in frame.columns and "placed_utc" in frame.columns
    assert frame["status"].to_list() == ["settled"]
