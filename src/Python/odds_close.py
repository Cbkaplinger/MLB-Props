"""Tip-aware closing-line fill for the odds ledger (Free-tier SharpAPI).

Used by ``production/poll_odds.py --snapshot close`` and
``production/close_watcher.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import polars as pl

from Python.odds_ledger import (
    LEDGER_PATH,
    apply_close,
    load_ledger,
    mark_close_unavailable,
    minutes_to_tip,
    norm_player_name,
    parse_event_start_utc,
    save_ledger,
)
from Python.sharp_odds import StrikeoutQuote, fetch_mlb_strikeout_quotes


def dedupe_quotes(quotes: list[StrikeoutQuote]) -> tuple[list[StrikeoutQuote], int]:
    seen: set[tuple[str, str, float]] = set()
    out: list[StrikeoutQuote] = []
    dupes = 0
    for q in quotes:
        key = (norm_player_name(q.player_name), q.sportsbook.lower(), float(q.line))
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        out.append(q)
    return out, dupes


def quote_maps(
    quotes: list[StrikeoutQuote],
) -> tuple[
    dict[tuple[str, str, float], StrikeoutQuote],
    dict[tuple[str, str], StrikeoutQuote],
    dict[tuple[str, str], StrikeoutQuote],
    dict[str, StrikeoutQuote],
]:
    by_line: dict[tuple[str, str, float], StrikeoutQuote] = {}
    by_event: dict[tuple[str, str], StrikeoutQuote] = {}
    by_name: dict[tuple[str, str], StrikeoutQuote] = {}
    by_player: dict[str, StrikeoutQuote] = {}
    for q in quotes:
        name = norm_player_name(q.player_name)
        book = q.sportsbook.lower()
        by_line[(name, book, float(q.line))] = q
        by_name[(name, book)] = q
        by_player[name] = q
        if q.event_id:
            by_event[(str(q.event_id), book)] = q
    return by_line, by_event, by_name, by_player


def match_close_quote(
    row: dict[str, Any],
    *,
    by_line: dict[tuple[str, str, float], StrikeoutQuote],
    by_event: dict[tuple[str, str], StrikeoutQuote],
    by_name: dict[tuple[str, str], StrikeoutQuote],
    by_player: dict[str, StrikeoutQuote] | None = None,
    allow_cross_book: bool = False,
) -> tuple[StrikeoutQuote | None, str]:
    """Return ``(quote, mode)`` where mode is ``same_book`` | ``cross_book`` | ````."""
    name = norm_player_name(str(row.get("player_name") or ""))
    book = str(row.get("book") or "").lower()
    line = float(row["line"])
    hit = by_line.get((name, book, line))
    if hit is not None:
        return hit, "same_book"
    event_id = row.get("event_id")
    if event_id:
        hit = by_event.get((str(event_id), book))
        if hit is not None:
            return hit, "same_book"
    hit = by_name.get((name, book))
    if hit is not None:
        return hit, "same_book"
    if allow_cross_book and by_player is not None:
        hit = by_player.get(name)
        if hit is not None:
            return hit, "cross_book"
    return None, ""


def open_needing_close(
    ledger: pl.DataFrame,
    *,
    slate: str | None = None,
) -> pl.DataFrame:
    if ledger.is_empty() or "status" not in ledger.columns:
        return ledger
    out = ledger.filter(pl.col("status") == "open")
    if "clv_pp" in out.columns:
        out = out.filter(pl.col("clv_pp").is_null())
    if "close_status" in out.columns:
        out = out.filter(
            pl.col("close_status").is_null()
            | (pl.col("close_status") != "unavailable")
        )
    if slate is not None and "game_date" in out.columns:
        out = out.filter(
            pl.col("game_date").cast(pl.Utf8).str.slice(0, 10) == str(slate)[:10]
        )
    return out


def row_minutes_to_tip(
    row: dict[str, Any],
    *,
    as_of: datetime | None = None,
) -> float | None:
    tip = parse_event_start_utc(row.get("event_start_time_utc"))
    if tip is None:
        note = str(row.get("note") or "")
        if "start=" in note:
            raw = note.split("start=", 1)[1].split(";", 1)[0].split("|", 1)[0].strip()
            tip = parse_event_start_utc(raw)
    return minutes_to_tip(tip, as_of=as_of)


def select_due_tickets(
    rows: list[dict[str, Any]],
    *,
    as_of: datetime | None = None,
    minutes_before: float = 15.0,
    minutes_after: float = 5.0,
    include_missing_tip: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Split rows into due / waiting (see close_watcher docs)."""
    now = as_of or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    due: list[dict[str, Any]] = []
    waiting: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    any_known_due = False

    for r in rows:
        m = row_minutes_to_tip(r, as_of=now)
        if m is None:
            missing.append(r)
            continue
        if -minutes_after <= m <= minutes_before:
            due.append({**r, "_minutes_to_tip": m})
            any_known_due = True
        else:
            waiting.append({**r, "_minutes_to_tip": m})

    if include_missing_tip and any_known_due and missing:
        due_dates = {str(r.get("game_date") or "")[:10] for r in due}
        for r in missing:
            if str(r.get("game_date") or "")[:10] in due_dates:
                due.append({**r, "_minutes_to_tip": None})
            else:
                waiting.append({**r, "_minutes_to_tip": None})
    else:
        waiting.extend(missing)

    return due, waiting, any_known_due


def next_future_tip_minutes(waiting: list[dict[str, Any]]) -> tuple[float, str] | None:
    """Soonest *future* tip among waiting rows (positive minutes only)."""
    upcoming = [
        (float(r["_minutes_to_tip"]), str(r.get("player_name") or "?"))
        for r in waiting
        if r.get("_minutes_to_tip") is not None and float(r["_minutes_to_tip"]) > 0
    ]
    if not upcoming:
        return None
    upcoming.sort(key=lambda x: x[0])
    return upcoming[0]


def expire_past_window_misses(
    *,
    slate: str | None = None,
    minutes_after: float = 5.0,
    as_of: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mark tickets past T+minutes_after with no CLV as ``close_status=unavailable``."""
    now = as_of or datetime.now(timezone.utc)
    ledger = load_ledger()
    need = open_needing_close(ledger, slate=slate)
    if need.is_empty():
        return {"n_expired": 0, "updated": False}

    updated = ledger
    n_exp = 0
    for r in need.to_dicts():
        m = row_minutes_to_tip(r, as_of=now)
        if m is None:
            continue
        if m < -minutes_after:
            n_exp += 1
            if not dry_run:
                updated = mark_close_unavailable(
                    updated,
                    ticket_id=str(r["ticket_id"]),
                    reason=f"past_window_tip{m:+.0f}m",
                )
    if dry_run or n_exp == 0:
        return {"n_expired": n_exp, "updated": False}
    save_ledger(updated)
    return {"n_expired": n_exp, "updated": True}


def fill_closes(
    *,
    ticket_ids: set[str] | None = None,
    slate: str | None = None,
    book: str | None = None,
    dry_run: bool = False,
    quotes: list[StrikeoutQuote] | None = None,
    allow_cross_book: bool = True,
    mark_misses_unavailable: bool = False,
) -> dict[str, Any]:
    """Fetch SharpAPI (unless quotes given) and fill CLV on matching open tickets."""
    ledger = load_ledger()
    need = open_needing_close(ledger, slate=slate)
    empty = {
        "n_need": 0,
        "n_upd": 0,
        "n_miss": 0,
        "n_line_fallback": 0,
        "n_cross_book": 0,
        "n_unavailable": 0,
        "n_quotes": 0,
        "misses": [],
        "updated": False,
    }
    if need.is_empty():
        return empty

    rows = need.to_dicts()
    if ticket_ids is not None:
        rows = [r for r in rows if r.get("ticket_id") in ticket_ids]
    if not rows:
        return empty

    if quotes is None:
        quotes, n_dupes = dedupe_quotes(
            fetch_mlb_strikeout_quotes(sportsbook=book, main_only=True, is_live=False)
        )
    else:
        quotes, n_dupes = dedupe_quotes(quotes)
    by_line, by_event, by_name, by_player = quote_maps(quotes)

    updated = ledger
    n_upd = 0
    n_miss = 0
    n_line_fallback = 0
    n_cross = 0
    n_unavail = 0
    misses: list[str] = []
    closed_at = datetime.now(timezone.utc)

    for r in rows:
        q, mode = match_close_quote(
            r,
            by_line=by_line,
            by_event=by_event,
            by_name=by_name,
            by_player=by_player,
            allow_cross_book=allow_cross_book,
        )
        if q is None:
            n_miss += 1
            label = f"{r.get('player_name')} {r.get('book')} line={r.get('line')}"
            misses.append(label)
            if mark_misses_unavailable and not dry_run:
                updated = mark_close_unavailable(
                    updated,
                    ticket_id=str(r["ticket_id"]),
                    reason="market_missing",
                )
                n_unavail += 1
            continue
        if abs(float(q.line) - float(r["line"])) > 1e-9:
            n_line_fallback += 1
        status = "ok_cross_book" if mode == "cross_book" else "ok"
        if mode == "cross_book":
            n_cross += 1
        updated = apply_close(
            updated,
            ticket_id=str(r["ticket_id"]),
            close_over=float(q.over_american),
            close_under=float(q.under_american),
            closed_at=closed_at,
            close_status=status,
        )
        after = updated.filter(pl.col("ticket_id") == r["ticket_id"]).to_dicts()[0]
        if after.get("clv_pp") is not None:
            n_upd += 1

    meta = {
        "n_need": len(rows),
        "n_upd": n_upd,
        "n_miss": n_miss,
        "n_line_fallback": n_line_fallback,
        "n_cross_book": n_cross,
        "n_unavailable": n_unavail,
        "n_quotes": len(quotes),
        "n_dupes_dropped": n_dupes,
        "misses": misses,
        "updated": (n_upd > 0 or n_unavail > 0) and not dry_run,
        "path": str(LEDGER_PATH),
    }
    if dry_run or not meta["updated"]:
        return meta
    save_ledger(updated)
    return meta
