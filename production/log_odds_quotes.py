"""Ingest manual K-prop quotes into the odds ledger (no API).

Scores each quote against ``artifacts/projection_log/projections.parquet``
and appends accept/deny + unit sizing rows to ``artifacts/odds_log/ledger.parquet``.

Examples:
    python production/log_odds_quotes.py --book novig --date 2026-07-30 ^
      --quote "Sean Burke,6.5,-150,+130" --quote "Andre Pallante,4.5,+163,-185"

    python production/log_odds_quotes.py --book novig --unit 50 --list-board
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.market import DEFAULT_EDGE_FLOOR  # noqa: E402
from Python.odds_ledger import (  # noqa: E402
    LEDGER_PATH,
    append_open_rows,
    score_quote_to_row,
)

LOG_PATH = config.OUTPUT_DIR / "projection_log" / "projections.parquet"
_LINE_COL = re.compile(r"^p_over_(\d+)_(\d+)$")


def _line_to_col(line: float) -> str:
    return f"p_over_{int(line)}_{int(round((line - int(line)) * 10))}"


def _parse_american(token: str) -> float:
    t = token.strip().replace("−", "-")
    if t[0] not in "+-" and t.lstrip("0123456789") == "" and t.isdigit():
        return float(t)
    return float(t)


def _parse_quote(raw: str) -> tuple[str, float, float, float]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"Bad --quote {raw!r}; expected Name,line,over,under")
    return parts[0], float(parts[1]), _parse_american(parts[2]), _parse_american(parts[3])


def _load_board(slate: date | None, preferred_only: bool) -> pl.DataFrame:
    if not LOG_PATH.exists():
        raise SystemExit(f"Missing {LOG_PATH}. Run production/log_projections.py first.")
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


def _match(board: pl.DataFrame, name: str) -> dict:
    key = name.strip().lower()
    hits = board.filter(pl.col("player_name").str.to_lowercase() == key)
    if hits.is_empty():
        hits = board.filter(pl.col("player_name").str.to_lowercase().str.contains(key, literal=True))
    if hits.is_empty():
        last = key.split()[-1]
        hits = board.filter(
            pl.col("player_name").str.to_lowercase().str.contains(last, literal=True)
        )
    if hits.is_empty():
        raise SystemExit(f"No board match for {name!r}")
    if hits.height > 1:
        raise SystemExit(
            f"Ambiguous {name!r}: {hits.select('player_name', 'expected_K').to_dicts()}"
        )
    return hits.to_dicts()[0]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", type=date.fromisoformat, default=None)
    p.add_argument("--book", type=str, default="novig")
    p.add_argument("--quote", action="append", default=[])
    p.add_argument("--unit", type=float, default=50.0, help="Dollar size of 1u (default 50)")
    p.add_argument("--edge-floor", type=float, default=DEFAULT_EDGE_FLOOR)
    p.add_argument("--all-starters", action="store_true")
    p.add_argument("--list-board", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Print rows; do not write ledger")
    args = p.parse_args()

    board = _load_board(args.date, preferred_only=not args.all_starters)
    slate = board["game_date"][0]
    print(f"slate={slate}  preferred_n={board.height}  book={args.book}  unit=${args.unit:.0f}")

    if args.list_board or not args.quote:
        for r in board.sort("expected_K", descending=True).to_dicts():
            print(
                f"  {r['player_name']:22} expK={float(r['expected_K']):5.2f}  "
                f"{r.get('away_team')}@{r.get('home_team')}"
            )
        if not args.quote:
            print('\nAdd quotes: --quote "Name,line,over,under"')
            return

    rows = []
    for raw in args.quote:
        name, line, over, under = _parse_quote(raw)
        row = _match(board, name)
        col = _line_to_col(line)
        if col not in row or row[col] is None:
            raise SystemExit(f"No {col} for {name}")
        ticket = score_quote_to_row(
            game_date=str(row["game_date"]),
            game_pk=row.get("game_pk"),
            pitcher=row.get("pitcher"),
            player_name=row["player_name"],
            line=line,
            over_price=over,
            under_price=under,
            p_model_over=float(row[col]),
            book=args.book,
            unit_dollars=args.unit,
            edge_floor=args.edge_floor,
            source="manual_quote",
            projected_tbf=row.get("projected_tbf"),
            days_rest=row.get("days_rest"),
            expected_K=row.get("expected_K"),
        )
        flag = "BET" if ticket["passes_floor"] else "skip"
        print(
            f"[{flag}] {ticket['player_name']} {ticket['side']} {ticket['line']} "
            f"@ {ticket['bet_price']:+.0f}  edge={ticket['edge']:+.1%}  "
            f"{ticket['units']:.2f}u (${ticket['stake']:.2f})"
        )
        rows.append(ticket)

    n_bet = sum(1 for r in rows if r["passes_floor"])
    print(f"Summary: {n_bet}/{len(rows)} BET at floor={args.edge_floor:.0%}")
    if args.dry_run:
        print("dry-run: not writing")
        return
    _, n_appended, n_skipped = append_open_rows(rows)
    print(
        f"Appended {n_appended} (skipped {n_skipped} already-open) → {LEDGER_PATH}"
    )


if __name__ == "__main__":
    main()
