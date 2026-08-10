"""Poll SharpAPI MLB pitcher strikeouts into the odds ledger.

Morning (open / bet-time snapshot):
    python production/odds/poll_odds.py --snapshot open --unit 50

Near first pitch (or use the tip-aware watcher):
    python production/odds/poll_odds.py --snapshot close
    python production/odds/close_watcher.py

Requires ``SHARPAPI_KEY`` in repo-root ``.env``. Free tier = DraftKings + FanDuel.
Open replaces unclosed same-day tickets by default (``--append`` to keep).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.env_load import load_project_dotenv  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_close import fill_closes  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    LEDGER_PATH,
    append_open_rows,
    replace_open_slate,
)
from Python.odds_open import poll_open_tickets  # noqa: E402

LOG_PATH = config.OUTPUT_DIR / "projection_log" / "projections.parquet"


def _load_board(slate: date | None, preferred_only: bool) -> pl.DataFrame:
    if not LOG_PATH.exists():
        raise SystemExit(
            f"Missing {LOG_PATH}. Run production/projections/log_projections.py first."
        )
    df = pl.read_parquet(LOG_PATH)
    if df["game_date"].dtype == pl.Datetime:
        df = df.with_columns(pl.col("game_date").dt.date().alias("game_date"))
    else:
        df = df.with_columns(pl.col("game_date").cast(pl.Date))
    dates = sorted(df["game_date"].unique().to_list())
    use = slate if slate is not None else dates[-1]
    board = df.filter(pl.col("game_date") == use)
    if preferred_only and "is_preferred" in board.columns:
        board = board.filter(pl.col("is_preferred"))
    if board.is_empty():
        raise SystemExit(f"No projection rows for {use}; logged={dates}")
    return board


def _poll_open(
    board: pl.DataFrame,
    *,
    unit: float,
    edge_floor: float,
    book: str | None,
    dry_run: bool,
    replace: bool,
    quality_gate: bool,
    kpi_policy: str | None,
) -> None:
    rows, unmatched, n_quotes = poll_open_tickets(
        board,
        unit=unit,
        edge_floor=edge_floor,
        book=book,
        quality_gate=quality_gate,
        kpi_policy_path=kpi_policy,
    )
    print(f"SharpAPI paired quotes: {n_quotes}")
    for ticket in rows:
        note = str(ticket.get("note") or "")
        if "quality_gate_hold=" in note:
            flag = "HOLD"
        elif ticket["passes_floor"]:
            flag = "BET"
        elif "oos=" in note:
            flag = "OOS"
        else:
            flag = "skip"
        tip_m = ticket.get("minutes_to_tip_at_open")
        tip_s = f"  tip-{tip_m:.0f}m" if tip_m is not None else ""
        print(
            f"[{flag}] {ticket['book']:10} {ticket['player_name']:20} "
            f"{ticket['side']} {ticket['line']} @ {ticket['bet_price']:+.0f}  "
            f"edge={ticket['edge']:+.1%}  {ticket['units']:.2f}u{tip_s}"
        )

    n_bet = sum(1 for r in rows if r["passes_floor"])
    n_hold = sum(1 for r in rows if "quality_gate_hold=" in str(r.get("note") or ""))
    print(f"Matched={len(rows)}  BET={n_bet}  HOLD={n_hold}  unmatched_or_bad_line={len(unmatched)}")
    if unmatched[:8]:
        print("  e.g.", ", ".join(unmatched[:8]))
    if dry_run:
        print("dry-run: not writing ledger")
        return
    if not rows:
        print("Nothing to append.")
        return
    slate = str(board["game_date"][0])
    if replace:
        _, n_written, n_removed = replace_open_slate(rows, slate=slate)
        print(
            f"Replaced slate {slate}: wrote {n_written}, removed {n_removed} "
            f"prior unclosed opens → {LEDGER_PATH}"
        )
    else:
        _, n_appended, n_skipped = append_open_rows(rows)
        print(
            f"Appended {n_appended} (skipped {n_skipped} already-open) → {LEDGER_PATH}"
        )


def _poll_close(
    board: pl.DataFrame,
    *,
    book: str | None,
    dry_run: bool,
) -> None:
    slate = str(board["game_date"][0])
    result = fill_closes(slate=slate, book=book, dry_run=dry_run)
    if result["n_need"] == 0:
        print(f"No open tickets needing close for {slate}")
        return
    print(
        f"SharpAPI paired quotes: {result['n_quotes']}"
        + (
            f" (dropped {result.get('n_dupes_dropped', 0)} dupes)"
            if result.get("n_dupes_dropped")
            else ""
        )
    )
    for miss in result.get("misses") or []:
        print(f"MISS close {miss}")
    print(
        f"Updated closes: {result['n_upd']}/{result['n_need']}  "
        f"miss={result['n_miss']}  line_fallback={result['n_line_fallback']}"
    )
    if dry_run:
        print("dry-run: not writing")
        return
    if result.get("updated"):
        print(f"Wrote {LEDGER_PATH}")
    elif result["n_upd"] == 0:
        print("Nothing written.")


def main() -> None:
    load_project_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--snapshot",
        choices=("open", "close"),
        required=True,
        help="open=bet-time quotes; close=fill CLV on today's open tickets",
    )
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--unit", type=float, default=50.0)
    p.add_argument("--edge-floor", type=float, default=DEFAULT_EDGE_FLOOR)
    p.add_argument(
        "--book",
        type=str,
        default=None,
        help="Optional sportsbook filter (draftkings|fanduel).",
    )
    p.add_argument("--all-starters", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--quality-gate",
        action="store_true",
        help="Apply diagnostics-driven HOLD gate to open-ticket sizing.",
    )
    p.add_argument(
        "--append",
        action="store_true",
        help="Open only: keep existing same-day opens (default: replace)",
    )
    p.add_argument(
        "--kpi-policy",
        type=str,
        default=None,
        help="Optional path to KPI/gate policy JSON (default: production/ops/kpi_policy.json).",
    )
    args = p.parse_args()

    board = _load_board(args.date, preferred_only=not args.all_starters)
    print(
        f"slate={board['game_date'][0]}  board_n={board.height}  "
        f"snapshot={args.snapshot}  unit=${args.unit:.0f}"
    )
    if args.snapshot == "open":
        _poll_open(
            board,
            unit=args.unit,
            edge_floor=args.edge_floor,
            book=args.book,
            dry_run=args.dry_run,
            replace=not args.append,
            quality_gate=args.quality_gate,
            kpi_policy=args.kpi_policy,
        )
    else:
        _poll_close(board, book=args.book, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
