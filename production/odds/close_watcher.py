"""Tip-aware CLV close watcher (Free-tier SharpAPI).

Only hits SharpAPI when tickets are inside the tip window (default T−2…T+3).
Idle time sleeps until the next window — no polling every 2 minutes from morning.

Each loop tick also runs a cheap "late-open" sweep: if a board starter has no
open ticket yet for the slate (e.g. its market wasn't posted at the morning
``--snapshot open`` poll), it re-fetches quotes and appends one as soon as the
book posts it — no separate manual ``poll_odds.py --append`` needed. Disable
with ``--no-late-open``.

Examples:
    python production/odds/close_watcher.py
    python production/odds/close_watcher.py --once
    python production/odds/close_watcher.py --minutes-before 10 --minutes-after 3
    python production/odds/close_watcher.py --minutes-before 5 --minutes-after 2  # wider/tighter override
    python production/odds/close_watcher.py --no-late-open

Requires ``SHARPAPI_KEY`` in repo-root ``.env``. Keep the machine awake.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from Python import config  # noqa: E402
from Python.env_load import load_project_dotenv  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_close import (  # noqa: E402
    expire_past_window_misses,
    fill_closes,
    next_future_tip_minutes,
    open_needing_close,
    select_due_tickets,
)
from Python.odds_ledger import (  # noqa: E402
    LEDGER_PATH,
    append_open_rows,
    load_ledger,
    norm_player_name,
)
from Python.odds_open import poll_open_tickets  # noqa: E402

LOG_PATH = config.OUTPUT_DIR / "odds_log" / "close_watcher.log"
BOARD_PATH = config.OUTPUT_DIR / "projection_log" / "projections.parquet"
ET = ZoneInfo("America/New_York")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts}  {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _today_slate() -> str:
    return datetime.now(ET).date().isoformat()


def _slate_has_passed(slate: str) -> bool:
    """True once local ET date is after the target slate date."""
    try:
        slate_d = date.fromisoformat(str(slate)[:10])
    except ValueError:
        return False
    return datetime.now(ET).date() > slate_d


def _load_board(slate: str) -> pl.DataFrame | None:
    """Preferred-pitcher projection board for ``slate``, or ``None``."""
    if not BOARD_PATH.exists():
        return None
    df = pl.read_parquet(BOARD_PATH)
    if df["game_date"].dtype == pl.Datetime:
        df = df.with_columns(pl.col("game_date").dt.date().alias("game_date"))
    else:
        df = df.with_columns(pl.col("game_date").cast(pl.Date))
    board = df.filter(pl.col("game_date").cast(pl.Utf8).str.slice(0, 10) == slate)
    if "is_preferred" in board.columns:
        board = board.filter(pl.col("is_preferred"))
    return board if not board.is_empty() else None


def _late_open_sweep(
    *,
    slate: str,
    unit: float,
    edge_floor: float,
    book: str | None,
    dry_run: bool,
) -> int:
    """Pick up starters whose markets weren't posted at the morning open poll.

    Cheap: only hits SharpAPI when a board starter has no open ticket yet
    for this slate. Idempotent — appended via the same dedupe key as
    ``poll_odds.py --snapshot open --append``.
    """
    board = _load_board(slate)
    if board is None:
        return 0
    ledger = load_ledger()
    open_names: set[str] = set()
    if not ledger.is_empty() and "status" in ledger.columns and "player_name" in ledger.columns:
        opens = ledger.filter(pl.col("status") == "open")
        if "game_date" in opens.columns:
            opens = opens.filter(
                pl.col("game_date").cast(pl.Utf8).str.slice(0, 10) == slate
            )
        open_names = {
            norm_player_name(str(n)) for n in opens["player_name"].to_list()
        }
    missing = [
        n for n in board["player_name"].to_list() if norm_player_name(n) not in open_names
    ]
    if not missing:
        return 0
    rows, _unmatched, n_quotes = poll_open_tickets(
        board, unit=unit, edge_floor=edge_floor, book=book
    )
    if dry_run:
        _log(
            f"late-open dry-run: missing_starters={missing} quotes={n_quotes} "
            f"matched={len(rows)}"
        )
        return 0
    if not rows:
        return 0
    _, n_appended, _n_skipped = append_open_rows(rows)
    if n_appended:
        added = sorted({r["player_name"] for r in rows})
        _log(
            f"late-open: appended {n_appended} new ticket(s) "
            f"(missing_starters={missing}, added={added})"
        )
    return n_appended


def _sleep_seconds_until_window(
    waiting: list[dict],
    *,
    minutes_before: float,
    interval: int,
) -> int:
    """Seconds to sleep until the next ticket enters the close window."""
    nxt = next_future_tip_minutes(waiting)
    if nxt is None:
        return max(30, int(interval))
    mins_to_tip, _ = nxt
    # Wake when tip - minutes_before is reached (plus small buffer).
    secs = (mins_to_tip - minutes_before) * 60.0 - 15.0
    if secs <= interval:
        return max(30, int(interval))
    # Cap long sleeps so we still expire past-window tickets periodically.
    return int(min(secs, 30 * 60))


def _run_tick(
    *,
    slate: str,
    minutes_before: float,
    minutes_after: float,
    include_missing_tip: bool,
    book: str | None,
    dry_run: bool,
    allow_cross_book: bool,
    interval: int,
) -> dict:
    # Drop tickets stuck past T+after with no CLV (e.g. DK market gone).
    expired = expire_past_window_misses(
        slate=slate,
        minutes_after=minutes_after,
        dry_run=dry_run,
    )
    if expired.get("n_expired"):
        _log(f"expired unavailable closes: {expired['n_expired']}")

    ledger = load_ledger()
    need = open_needing_close(ledger, slate=slate)
    if need.is_empty():
        sleep_s = max(60, int(interval))
        _log(f"slate={slate} no open tickets yet; sleep {sleep_s}s (late-open active)")
        return {
            "n_need": 0,
            "n_due": 0,
            "n_waiting": 0,
            "done": False,
            "sleep_s": sleep_s,
        }

    rows = need.to_dicts()
    due, waiting, _ = select_due_tickets(
        rows,
        minutes_before=minutes_before,
        minutes_after=minutes_after,
        include_missing_tip=include_missing_tip,
    )
    _log(
        f"slate={slate} need={len(rows)} due={len(due)} waiting={len(waiting)}"
    )
    if not due:
        nxt = next_future_tip_minutes(waiting)
        if nxt:
            m, name = nxt
            sleep_s = _sleep_seconds_until_window(
                waiting, minutes_before=minutes_before, interval=interval
            )
            _log(f"next tip in {m:.0f}m ({name}); sleep {sleep_s}s (no API)")
        else:
            sleep_s = max(30, int(interval))
            _log(f"no future tips in need-set; sleep {sleep_s}s (no API)")
        return {
            "n_need": len(rows),
            "n_due": 0,
            "n_waiting": len(waiting),
            "done": False,
            "sleep_s": sleep_s,
        }

    for r in due:
        m = r.get("_minutes_to_tip")
        tip_s = f"tip={m:+.0f}m" if m is not None else "tip=?"
        _log(f"due {r.get('player_name')} {r.get('book')} {tip_s}")

    ids = {str(r["ticket_id"]) for r in due if r.get("ticket_id")}
    # Retry misses every tick while still inside the window (allow cross-book
    # fill first) — only give up once truly past T+minutes_after, which
    # expire_past_window_misses() enforces at the top of the next tick.
    result = fill_closes(
        ticket_ids=ids,
        slate=slate,
        book=book,
        dry_run=dry_run,
        allow_cross_book=allow_cross_book,
        mark_misses_unavailable=False,
    )
    _log(
        f"close tick: upd={result['n_upd']}/{result['n_need']} "
        f"miss={result['n_miss']} cross={result.get('n_cross_book', 0)} "
        f"unavail={result.get('n_unavailable', 0)} "
        f"line_fallback={result['n_line_fallback']} quotes={result['n_quotes']}"
    )

    # Post-tip pregame misses (e.g. a book pulled the market right at first
    # pitch, common after a watcher gap/restart straddles tip): one immediate
    # is_live=True retry before the next tick's expire_past_window_misses
    # would otherwise permanently mark these "unavailable" with no CLV at all.
    miss_ids_by_tip = {
        str(r["ticket_id"]): r.get("_minutes_to_tip")
        for r in due
        if r.get("ticket_id") is not None
    }
    live_retry_ids = {
        tid
        for tid in (result.get("miss_ticket_ids") or [])
        if (miss_ids_by_tip.get(tid) or 0) <= 0
    }
    if live_retry_ids:
        live_result = fill_closes(
            ticket_ids=live_retry_ids,
            slate=slate,
            book=book,
            dry_run=dry_run,
            allow_cross_book=allow_cross_book,
            mark_misses_unavailable=False,
            status_override="ok_live_fallback",
            is_live=True,
        )
        if live_result["n_upd"]:
            _log(
                f"live-odds fallback: filled {live_result['n_upd']} post-tip close(s) "
                f"(pregame market already gone; tagged close_status=ok_live_fallback)"
            )
        for miss in live_result.get("misses") or []:
            _log(f"MISS (will retry next tick) {miss}")
    for tid, miss in zip(result.get("miss_ticket_ids") or [], result.get("misses") or []):
        if tid in live_retry_ids:
            continue  # already logged above via the live-odds fallback attempt
        _log(f"MISS (will retry next tick) {miss}")

    left = open_needing_close(load_ledger(), slate=slate)
    return {
        **result,
        "n_due": len(due),
        "n_waiting": len(waiting),
        "n_left": left.height,
        "done": left.is_empty(),
        "sleep_s": max(30, int(interval)),
    }


def main() -> None:
    load_project_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Min seconds between ticks while tickets are due (default 60)",
    )
    p.add_argument("--minutes-before", type=float, default=2.0)
    p.add_argument("--minutes-after", type=float, default=3.0)
    p.add_argument("--no-missing-tip", action="store_true")
    p.add_argument(
        "--no-cross-book",
        action="store_true",
        help="Do not use another book's quote when the ticket's book is missing",
    )
    p.add_argument("--book", type=str, default=None)
    p.add_argument(
        "--no-late-open",
        action="store_true",
        help="Disable sweeping for starters missing an open ticket (late-posted markets)",
    )
    p.add_argument("--open-unit", type=float, default=50.0)
    p.add_argument("--open-edge-floor", type=float, default=DEFAULT_EDGE_FLOOR)
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    slate = args.date.isoformat() if args.date else _today_slate()
    _log(
        f"close_watcher start slate={slate} interval={args.interval}s "
        f"window=T-{args.minutes_before:g}…T+{args.minutes_after:g} "
        f"cross_book={not args.no_cross_book} late_open={not args.no_late_open} "
        f"ledger={LEDGER_PATH}"
    )
    if not LEDGER_PATH.exists():
        raise SystemExit(
            f"No ledger at {LEDGER_PATH}. Run poll_odds --snapshot open first."
        )

    while True:
        try:
            if not args.no_late_open:
                _late_open_sweep(
                    slate=slate,
                    unit=args.open_unit,
                    edge_floor=args.open_edge_floor,
                    book=args.book,
                    dry_run=args.dry_run,
                )
        except Exception as exc:  # noqa: BLE001
            _log(f"ERROR late-open sweep: {exc}")
        try:
            summary = _run_tick(
                slate=slate,
                minutes_before=args.minutes_before,
                minutes_after=args.minutes_after,
                include_missing_tip=not args.no_missing_tip,
                book=args.book,
                dry_run=args.dry_run,
                allow_cross_book=not args.no_cross_book,
                interval=args.interval,
            )
        except SystemExit as exc:
            _log(f"fatal: {exc}")
            raise
        except Exception as exc:  # noqa: BLE001
            _log(f"ERROR tick: {exc}")
            summary = {"done": False, "sleep_s": max(30, int(args.interval))}

        if args.once:
            _log("once: exiting")
            break
        if summary.get("done"):
            _log(f"all closes filled/unavailable for {slate} — exiting")
            break
        if summary.get("n_need", 0) == 0 and _slate_has_passed(slate):
            _log(f"slate {slate} has passed with no open closes pending — exiting")
            break
        time.sleep(max(15, int(summary.get("sleep_s") or args.interval)))


if __name__ == "__main__":
    main()
