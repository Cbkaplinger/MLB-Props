"""Tip-aware CLV close watcher (Free-tier SharpAPI).

Only hits SharpAPI when tickets are inside the tip window (default T−15…T+5).
Idle time sleeps until the next window — no polling every 2 minutes from morning.

Examples:
    python production/close_watcher.py
    python production/close_watcher.py --once
    python production/close_watcher.py --minutes-before 10 --minutes-after 3

Requires ``SHARPAPI_KEY`` in repo-root ``.env``. Keep the machine awake.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.env_load import load_project_dotenv  # noqa: E402
from Python.odds_close import (  # noqa: E402
    expire_past_window_misses,
    fill_closes,
    next_future_tip_minutes,
    open_needing_close,
    select_due_tickets,
)
from Python.odds_ledger import LEDGER_PATH, load_ledger  # noqa: E402

LOG_PATH = config.OUTPUT_DIR / "odds_log" / "close_watcher.log"
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
        return {"n_need": 0, "n_due": 0, "n_waiting": 0, "done": True, "sleep_s": 0}

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
    # Inside the window: one miss with no quote → mark unavailable (don't hammer API).
    # Still allow cross-book fill first.
    result = fill_closes(
        ticket_ids=ids,
        slate=slate,
        book=book,
        dry_run=dry_run,
        allow_cross_book=allow_cross_book,
        mark_misses_unavailable=True,
    )
    _log(
        f"close tick: upd={result['n_upd']}/{result['n_need']} "
        f"miss={result['n_miss']} cross={result.get('n_cross_book', 0)} "
        f"unavail={result.get('n_unavailable', 0)} "
        f"line_fallback={result['n_line_fallback']} quotes={result['n_quotes']}"
    )
    for miss in result.get("misses") or []:
        _log(f"MISS→unavailable {miss}")

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
        default=120,
        help="Min seconds between ticks while tickets are due (default 120)",
    )
    p.add_argument("--minutes-before", type=float, default=15.0)
    p.add_argument("--minutes-after", type=float, default=5.0)
    p.add_argument("--no-missing-tip", action="store_true")
    p.add_argument(
        "--no-cross-book",
        action="store_true",
        help="Do not use another book's quote when the ticket's book is missing",
    )
    p.add_argument("--book", type=str, default=None)
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    slate = args.date.isoformat() if args.date else _today_slate()
    _log(
        f"close_watcher start slate={slate} interval={args.interval}s "
        f"window=T-{args.minutes_before:g}…T+{args.minutes_after:g} "
        f"cross_book={not args.no_cross_book} ledger={LEDGER_PATH}"
    )
    if not LEDGER_PATH.exists():
        raise SystemExit(
            f"No ledger at {LEDGER_PATH}. Run poll_odds --snapshot open first."
        )

    while True:
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
        time.sleep(max(15, int(summary.get("sleep_s") or args.interval)))


if __name__ == "__main__":
    main()
