"""Live strikeout recommendation board (model × SharpAPI odds).

Terminal prints **BET only** (≥ edge floor, in-support).
Full matched slate (BET + skip + OOS) is always written for monitoring / curves.

Examples:
    python production/odds_board.py --unit 50
    python production/odds_board.py --show-all
    python production/odds_board.py --open-html

Writes (full slate every run — single file, overwritten):
  artifacts/odds_log/recommendations.parquet
  artifacts/odds_log/recommendations.html
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python.env_load import load_project_dotenv  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_board import (  # noqa: E402
    build_recommendations,
    write_recommendations,
)


def _print_table(frame: pl.DataFrame, *, bets_only: bool) -> None:
    if frame.is_empty():
        print("No matched rows.")
        return
    view = frame
    if bets_only:
        if "recommendation" in view.columns:
            view = view.filter(pl.col("recommendation") == "BET")
        elif "passes_floor" in view.columns:
            view = view.filter(pl.col("passes_floor") == True)  # noqa: E712
        if view.is_empty():
            print("No BET rows at current floor (full slate still written to parquet/HTML).")
            return
    cols = [
        c
        for c in (
            "recommendation",
            "pitcher_team",
            "player_name",
            "expected_K",
            "book",
            "line",
            "best_side",
            "best_price",
            "edge",
            "units",
            "stake",
            "oos_reason",
        )
        if c in view.columns
    ]
    rows = view.select(cols).to_dicts()
    hdr = (
        f"{'rec':4} {'tm':3} {'pitcher':18} {'expK':>5} {'book':10} "
        f"{'line':>4} {'side':5} {'price':>5} {'edge':>7} {'u':>5} {'$':>6}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        price = int(r["best_price"])
        print(
            f"{r['recommendation']:4} {str(r.get('pitcher_team') or '?'):3} "
            f"{str(r['player_name'])[:18]:18} {float(r['expected_K']):5.2f} "
            f"{str(r['book']):10} {float(r['line']):4.1f} {r['best_side']:5} "
            f"{price:+5d} {float(r['edge'])*100:+6.1f}% "
            f"{float(r['units']):5.2f} {float(r['stake']):6.2f}"
            + (f"  [{r['oos_reason']}]" if r.get("oos_reason") else "")
        )


def main() -> None:
    load_project_dotenv()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--unit", type=float, default=50.0)
    p.add_argument("--edge-floor", type=float, default=DEFAULT_EDGE_FLOOR)
    p.add_argument("--book", type=str, default=None, help="draftkings|fanduel")
    p.add_argument("--all-starters", action="store_true")
    p.add_argument(
        "--all-books",
        action="store_true",
        help="Keep DK and FD per pitcher (default: best book only)",
    )
    p.add_argument(
        "--show-all",
        action="store_true",
        help="Print BET+skip+OOS (default: BET only)",
    )
    p.add_argument("--open-html", action="store_true")
    p.add_argument("--no-write", action="store_true")
    args = p.parse_args()

    frame, meta = build_recommendations(
        slate=args.date,
        preferred_only=not args.all_starters,
        unit_dollars=args.unit,
        edge_floor=args.edge_floor,
        sportsbook=args.book,
        best_book_only=not args.all_books,
    )
    print(
        f"slate={meta['slate_date']}  board={meta['n_board']}  "
        f"quotes={meta['n_quotes']}  matched={meta['n_matched']}"
        f"/{meta.get('n_matched_raw', meta['n_matched'])}  "
        f"BET={meta['n_bet']}  unmatched={meta['n_unmatched']}"
        + ("  (best book/pitcher)" if meta.get("best_book_only") else "  (all books)")
    )
    if meta.get("unmatched_sample"):
        print("unmatched e.g.", ", ".join(meta["unmatched_sample"][:8]))
    if meta.get("preferred_missing_quote"):
        print(
            f"preferred with no scored quote ({meta.get('n_preferred_missing_quote')}):",
            ", ".join(meta["preferred_missing_quote"][:8]),
        )
    print()
    _print_table(frame, bets_only=not args.show_all)

    if not args.no_write:
        pq, html = write_recommendations(frame, meta)
        print()
        print(f"Wrote {pq}  (full slate n={0 if frame.is_empty() else frame.height})")
        print(f"Wrote {html}")
        if args.open_html:
            webbrowser.open(html.resolve().as_uri())


if __name__ == "__main__":
    main()
