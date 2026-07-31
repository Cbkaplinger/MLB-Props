"""Poll SharpAPI MLB pitcher strikeouts into the odds ledger.

Morning (open / bet-time snapshot):
    python production/poll_odds.py --snapshot open --unit 50

Near first pitch (or use the tip-aware watcher):
    python production/poll_odds.py --snapshot close
    python production/close_watcher.py

Requires ``SHARPAPI_KEY`` in repo-root ``.env``. Free tier = DraftKings + FanDuel.
Open replaces unclosed same-day tickets by default (``--append`` to keep).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.env_load import load_project_dotenv  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_board import p_model_over_for_line  # noqa: E402
from Python.odds_close import dedupe_quotes, fill_closes  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    LEDGER_PATH,
    append_open_rows,
    norm_player_name,
    replace_open_slate,
    score_quote_to_row,
)
from Python.sharp_odds import fetch_mlb_strikeout_quotes  # noqa: E402

LOG_PATH = config.OUTPUT_DIR / "projection_log" / "projections.parquet"


def _load_board(slate: date | None, preferred_only: bool) -> pl.DataFrame:
    if not LOG_PATH.exists():
        raise SystemExit(
            f"Missing {LOG_PATH}. Run production/log_projections.py first."
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


def _match_board_row(board: pl.DataFrame, player_name: str) -> dict | None:
    key = norm_player_name(player_name)
    hits = board.filter(
        pl.col("player_name").map_elements(norm_player_name, return_dtype=pl.Utf8) == key
    )
    if hits.is_empty():
        last = key.split()[-1] if key else ""
        if last:
            hits = board.filter(
                pl.col("player_name")
                .map_elements(norm_player_name, return_dtype=pl.Utf8)
                .str.contains(last, literal=True)
            )
    if hits.is_empty() or hits.height > 1:
        return None
    return hits.to_dicts()[0]


def _poll_open(
    board: pl.DataFrame,
    *,
    unit: float,
    edge_floor: float,
    book: str | None,
    dry_run: bool,
    replace: bool,
) -> None:
    quotes, n_dupes = dedupe_quotes(
        fetch_mlb_strikeout_quotes(sportsbook=book, main_only=True, is_live=False)
    )
    print(
        f"SharpAPI paired quotes: {len(quotes)}"
        + (f" (dropped {n_dupes} dupes)" if n_dupes else "")
    )
    rows = []
    unmatched = []
    for q in quotes:
        brow = _match_board_row(board, q.player_name)
        if brow is None:
            unmatched.append(q.player_name)
            continue
        col_p = p_model_over_for_line(brow, q.line)
        if col_p is None:
            unmatched.append(f"{q.player_name} line={q.line}")
            continue
        ticket = score_quote_to_row(
            game_date=str(brow["game_date"]),
            game_pk=brow.get("game_pk"),
            pitcher=brow.get("pitcher"),
            player_name=brow["player_name"],
            line=q.line,
            over_price=q.over_american,
            under_price=q.under_american,
            p_model_over=col_p,
            book=q.sportsbook,
            unit_dollars=unit,
            edge_floor=edge_floor,
            source="sharpapi",
            event_id=q.event_id,
            event_start_time=q.event_start_time,
            projected_tbf=brow.get("projected_tbf"),
            days_rest=brow.get("days_rest"),
            expected_K=brow.get("expected_K"),
            note="",
        )
        if ticket["passes_floor"]:
            flag = "BET"
        elif "oos=" in str(ticket.get("note") or ""):
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
        rows.append(ticket)

    n_bet = sum(1 for r in rows if r["passes_floor"])
    print(f"Matched={len(rows)}  BET={n_bet}  unmatched_or_bad_line={len(unmatched)}")
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
        "--append",
        action="store_true",
        help="Open only: keep existing same-day opens (default: replace)",
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
        )
    else:
        _poll_close(board, book=args.book, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
