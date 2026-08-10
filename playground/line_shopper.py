"""Dry-run line shopper: paste book K props against logged projections.

No API calls. Loads ``artifacts/projection_log/projections.parquet``, matches
pitchers by name, scores edge / quarter-Kelly / pass-floor via ``Python.market``.

Examples:
    # Show preferred board for the latest logged slate
    python playground/line_shopper.py

    # Score one or more pasted quotes (name, line, over_amer, under_amer)
    python playground/line_shopper.py --quote "Shane Bieber,4.5,+115,-145"
    python playground/line_shopper.py --quote "Bieber,4.5,115,-145" --quote "Cavalli,5.5,-110,-110"

    # Persist scored quotes under artifacts/odds_log/
    python playground/line_shopper.py --quote "Bieber,4.5,115,-145" --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from Python import config  # noqa: E402
from Python.market import (  # noqa: E402
    DEFAULT_EDGE_FLOOR,
    DEFAULT_KELLY_FRACTION,
    evaluate_side,
)

LOG_PATH = config.OUTPUT_DIR / "projection_log" / "projections.parquet"
ODDS_DIR = config.OUTPUT_DIR / "odds_log"
PAPER_PATH = ODDS_DIR / "paper_dry_run.parquet"

_LINE_COL = re.compile(r"^p_over_(\d+)_(\d+)$")


def _line_to_col(line: float) -> str:
    whole = int(line)
    frac = int(round((line - whole) * 10))
    return f"p_over_{whole}_{frac}"


def _parse_american(token: str) -> float:
    t = token.strip().replace("−", "-")  # unicode minus
    if not t:
        raise ValueError("empty American odds")
    if t[0] not in "+-" and t.isdigit():
        # Bare "115" means +115 (books often omit the plus)
        return float(t)
    return float(t)


def _parse_quote(raw: str) -> tuple[str, float, float, float]:
    """``Name, line, over, under`` → parts."""
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise SystemExit(
            f"Bad --quote {raw!r}; expected 'Name,line,over,under' "
            "(e.g. 'Shane Bieber,4.5,+115,-145')"
        )
    name, line_s, over_s, under_s = parts
    try:
        line = float(line_s)
        over = _parse_american(over_s)
        under = _parse_american(under_s)
    except ValueError as exc:
        raise SystemExit(f"Bad --quote {raw!r}: {exc}") from exc
    return name, line, over, under


def _load_board(*, slate: date | None, preferred_only: bool) -> pl.DataFrame:
    if not LOG_PATH.exists():
        raise SystemExit(
            f"Missing {LOG_PATH}. Run:\n"
            "  python production/projections/log_projections.py --allow-stale"
        )
    df = pl.read_parquet(LOG_PATH)
    if "game_date" not in df.columns:
        raise SystemExit("projection log missing game_date")

    # Normalize date column for filtering
    g = df["game_date"]
    if g.dtype == pl.Datetime:
        df = df.with_columns(pl.col("game_date").dt.date().alias("game_date"))

    dates = sorted(df["game_date"].unique().to_list())
    if not dates:
        raise SystemExit("projection log is empty")
    use = slate if slate is not None else dates[-1]
    board = df.filter(pl.col("game_date") == use)
    if board.is_empty():
        raise SystemExit(f"No rows for {use}; logged dates={dates}")
    if preferred_only and "is_preferred" in board.columns:
        board = board.filter(pl.col("is_preferred"))
    return board.sort("expected_K", descending=True)


def _match_pitcher(board: pl.DataFrame, name: str) -> dict:
    key = name.strip().lower()
    names = board.with_columns(pl.col("player_name").str.to_lowercase().alias("_n"))
    hits = names.filter(pl.col("_n") == key)
    if hits.is_empty():
        hits = names.filter(pl.col("_n").str.contains(key, literal=True))
    if hits.is_empty():
        raise SystemExit(
            f"No board match for {name!r}. Try --list to see names on this slate."
        )
    if hits.height > 1:
        preview = hits.select("player_name", "pitcher", "expected_K").to_dicts()
        raise SystemExit(f"Ambiguous {name!r}; matches={preview}")
    return hits.drop("_n").to_dicts()[0]


def _print_board(board: pl.DataFrame) -> None:
    slate = board["game_date"][0]
    print(f"Preferred board  slate={slate}  n={board.height}  source={LOG_PATH}")
    print()
    show_cols = [
        c
        for c in (
            "player_name",
            "pitcher",
            "away_team",
            "home_team",
            "expected_K",
            "fair_amer_4_5",
            "fair_amer_5_5",
            "fair_amer_6_5",
            "p_over_4_5",
            "p_over_5_5",
            "p_over_6_5",
        )
        if c in board.columns
    ]
    # Compact text table
    rows = board.select(show_cols).head(20).to_dicts()
    hdr = (
        f"{'pitcher':22} {'expK':>5} {'fair4.5':>8} {'fair5.5':>8} "
        f"{'p4.5':>6} {'p5.5':>6} {'matchup':12}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        matchup = f"{r.get('away_team', '?')}@{r.get('home_team', '?')}"
        print(
            f"{str(r['player_name'])[:22]:22} "
            f"{r['expected_K']:5.2f} "
            f"{_fmt_amer(r.get('fair_amer_4_5')):>8} "
            f"{_fmt_amer(r.get('fair_amer_5_5')):>8} "
            f"{_fmt_p(r.get('p_over_4_5')):>6} "
            f"{_fmt_p(r.get('p_over_5_5')):>6} "
            f"{matchup:12}"
        )
    if board.height > 20:
        print(f"... ({board.height - 20} more; full list uses --list)")
    print()
    print("Paste a quote:")
    print('  python playground/line_shopper.py --quote "Lastname,5.5,+120,-140"')


def _fmt_amer(v: object) -> str:
    if v is None:
        return "—"
    try:
        x = int(v)
    except (TypeError, ValueError):
        return "—"
    return f"+{x}" if x > 0 else str(x)


def _fmt_p(v: object) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.0%}"
    except (TypeError, ValueError):
        return "—"


def _score_quote(
    board: pl.DataFrame,
    *,
    name: str,
    line: float,
    over: float,
    under: float,
    bankroll: float,
    edge_floor: float,
) -> dict:
    row = _match_pitcher(board, name)
    col = _line_to_col(line)
    if col not in row or row[col] is None:
        avail = sorted(
            f"{m.group(1)}.{m.group(2)}"
            for c in row
            if (m := _LINE_COL.match(str(c)))
        )
        raise SystemExit(
            f"No model p for line {line} on {row['player_name']}; "
            f"available={avail}"
        )
    p_over = float(row[col])
    over_ev = evaluate_side(
        p_over,
        over,
        under,
        "over",
        edge_floor=edge_floor,
        kelly_frac=DEFAULT_KELLY_FRACTION,
        bankroll=bankroll,
    )
    under_ev = evaluate_side(
        1.0 - p_over,
        over,
        under,
        "under",
        edge_floor=edge_floor,
        kelly_frac=DEFAULT_KELLY_FRACTION,
        bankroll=bankroll,
    )
    best = over_ev if over_ev["edge"] >= under_ev["edge"] else under_ev
    return {
        "game_date": str(row["game_date"]),
        "game_pk": row.get("game_pk"),
        "pitcher": row["pitcher"],
        "player_name": row["player_name"],
        "expected_K": float(row["expected_K"]),
        "line": line,
        "open_over_price": over,
        "open_under_price": under,
        "p_model_over": p_over,
        "best_side": best["side"],
        "best_edge": float(best["edge"]),
        "best_p_market": float(best["p_market"]),
        "best_price": float(best["price_american"]),
        "passes_floor": bool(best["passes_floor"]),
        "kelly_frac": float(best["kelly_frac"]),
        "stake": float(best["stake"]),
        "bankroll": bankroll,
        "edge_floor": edge_floor,
        "over_edge": float(over_ev["edge"]),
        "under_edge": float(under_ev["edge"]),
        "fair_amer_model": row.get(col.replace("p_over_", "fair_amer_", 1)),
    }


def _print_score(s: dict) -> None:
    flag = "PASS" if s["passes_floor"] else "skip"
    print(
        f"[{flag}] {s['player_name']}  K {s['line']}  "
        f"expK={s['expected_K']:.2f}  model_p_over={s['p_model_over']:.1%}"
    )
    print(
        f"       book { _fmt_amer(s['open_over_price']) } / "
        f"{ _fmt_amer(s['open_under_price']) }  "
        f"→ best={s['best_side']} @ {_fmt_amer(s['best_price'])}  "
        f"edge={s['best_edge']:+.1%}  mkt_p={s['best_p_market']:.1%}"
    )
    print(
        f"       over_edge={s['over_edge']:+.1%}  under_edge={s['under_edge']:+.1%}  "
        f"¼Kelly stake=${s['stake']:.2f} on ${s['bankroll']:.0f} bankroll "
        f"(floor={s['edge_floor']:.0%})"
    )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Slate date YYYY-MM-DD (default: latest in projection log).",
    )
    parser.add_argument(
        "--quote",
        action="append",
        default=[],
        help='Name,line,over,under  (repeatable). Example: "Bieber,4.5,+115,-145"',
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print full preferred name list for the slate.",
    )
    parser.add_argument(
        "--all-starters",
        action="store_true",
        help="Include non-preferred dual-starter rows.",
    )
    parser.add_argument(
        "--bankroll",
        type=float,
        default=1000.0,
        help="Paper bankroll for stake display (default 1000).",
    )
    parser.add_argument(
        "--edge-floor",
        type=float,
        default=DEFAULT_EDGE_FLOOR,
        help=f"Pass threshold (default {DEFAULT_EDGE_FLOOR} from gates doc).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"Append scored quotes to {PAPER_PATH}.",
    )
    args = parser.parse_args()

    board = _load_board(slate=args.date, preferred_only=not args.all_starters)

    if args.list or not args.quote:
        _print_board(board)
        if args.list:
            print("All preferred names on slate:")
            for r in board.select("player_name", "pitcher", "expected_K").to_dicts():
                print(f"  {r['player_name']:25} id={r['pitcher']}  expK={r['expected_K']:.2f}")
        if not args.quote:
            return

    scored: list[dict] = []
    for raw in args.quote:
        name, line, over, under = _parse_quote(raw)
        s = _score_quote(
            board,
            name=name,
            line=line,
            over=over,
            under=under,
            bankroll=args.bankroll,
            edge_floor=args.edge_floor,
        )
        _print_score(s)
        scored.append(s)

    n_pass = sum(1 for s in scored if s["passes_floor"])
    print(f"Summary: {n_pass}/{len(scored)} pass ≥{args.edge_floor:.0%} edge floor.")

    if args.write and scored:
        ODDS_DIR.mkdir(parents=True, exist_ok=True)
        frame = pl.DataFrame(scored).with_columns(
            pl.lit(datetime.now(timezone.utc).isoformat()).alias("scored_at_utc"),
            pl.lit("manual_dry_run").alias("source"),
        )
        if PAPER_PATH.exists():
            prev = pl.read_parquet(PAPER_PATH)
            # Align schemas loosely
            frame = pl.concat([prev, frame], how="diagonal_relaxed")
        frame.write_parquet(PAPER_PATH)
        meta = {
            "path": str(PAPER_PATH),
            "n_rows": frame.height,
            "last_batch": len(scored),
            "n_pass_last_batch": n_pass,
        }
        (ODDS_DIR / "last_dry_run.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        print(f"Wrote {len(scored)} quote(s) → {PAPER_PATH}")


if __name__ == "__main__":
    main()
