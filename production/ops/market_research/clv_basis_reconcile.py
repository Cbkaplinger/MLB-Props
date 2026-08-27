"""Build CLV basis reconciliation artifacts from the settled ledger.

Reconciles the authoritative ledger ``clv_pp`` (de-vigged probability-point
CLV) against alternative "beat the close" bases and against pikkit-style tiny
trailing windows, so short-window external numbers are explained rather than
misread as cohort skill.

Reads:
  - artifacts/odds_log/ledger.parquet       (gitignored; read-only)

Writes:
  - artifacts/odds_log/clv_basis_reconcile.json
  - artifacts/odds_log/clv_basis_reconcile.parquet

Run (from repo root):
  .\\.venv\\Scripts\\python.exe production/ops/market_research/clv_basis_reconcile.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from Python.odds_ledger import dedupe_ledger_props  # noqa: E402

ODDS_DIR = ROOT / "artifacts" / "odds_log"
LEDGER_PATH = ODDS_DIR / "ledger.parquet"

JSON_OUT = ODDS_DIR / "clv_basis_reconcile.json"
PARQUET_OUT = ODDS_DIR / "clv_basis_reconcile.parquet"

# Windows reported: all-time, last 14 days, and the trailing-cap that external
# trackers use (we default to the trailing-10 pikkit basis).
RECENT_DAYS = 14
TRAILING_WINDOW = 10


def _load_ledger() -> pl.DataFrame:
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"ledger not found: {LEDGER_PATH}")
    df = pl.read_parquet(LEDGER_PATH)
    if df["game_date"].dtype == pl.String:
        df = df.with_columns(
            pl.col("game_date").str.to_date("%Y-%m-%d").alias("game_date")
        )
    return df


def _as_rows(summary: dict[str, float], scope: str) -> list[dict]:
    return [
        {
            "scope": scope,
            "metric": k,
            "value": round(v, 6),
        }
        for k, v in summary.items()
    ]


def main() -> None:
    from Python.clv_basis import trailing_window_beat_rates, window_beat_rates

    ledger = _load_ledger()
    closed = ledger.filter(pl.col("clv_pp").is_not_null())
    # One row per (date, player, line, side): keep best-edge book so DK+FD
    # pairs are not double-counted in CLV/beat-rate summary statistics.
    closed = dedupe_ledger_props(closed) if not closed.is_empty() else closed

    all_rows = _as_rows(window_beat_rates(closed), "all")
    # Recent window by game_date (e.g. last 14 calendar days).
    recent_cut = date.today().fromordinal(date.today().toordinal() - RECENT_DAYS)
    if "game_date" in closed.columns:
        recent = closed.filter(pl.col("game_date") >= recent_cut)
        if recent.height:
            all_rows += _as_rows(window_beat_rates(recent), f"last_{RECENT_DAYS}d")

    full_rate = window_beat_rates(closed)
    trailing = trailing_window_beat_rates(
        closed,
        window=TRAILING_WINDOW,
        order_col="closed_at_utc",
        clv_col="clv_pp",
    )

    # A durable JSON with both full-cohort and trailing-window views plus a
    # human-readable reconciliation note so the interpretation survives.
    reconciliation = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "n_closed": int(closed.height),
        "full_cohort": full_rate,
        "trailing_window": trailing,
        "note": (
            "The authoritative ledger clv_pp (de-vigged probability-point CLV) "
            "has a strict >0 beat-close rate near 50% because most strikeout "
            "prop closing lines do not move (|clv| <= 1pp on a large share). "
            "External trackers often report a small trailing window (e.g. the "
            "last 10 bets) or a lenient >=0 'didn't get worse' basis, both of "
            "which read much higher and are not comparable to full-cohort skill. "
            "Pre-registered skill gates should use the full-cohort price basis."
        ),
    }

    JSON_OUT.write_text(
        json.dumps(reconciliation, indent=2, default=str), encoding="utf-8"
    )
    out_rows = all_rows + [{"scope": "trailing_window", **trailing}]
    pl.DataFrame(out_rows).write_parquet(PARQUET_OUT)

    # Console summary
    def pct(x: float) -> str:
        return f"{100 * x:.1f}%"

    print(f"ledger closed n={closed.height}")
    print("full cohort (price de-vig basis):")
    print(f"  beat >0:  {pct(full_rate['price_devig_gt0'])}")
    print(f"  beat >=0: {pct(full_rate['price_devig_ge0'])}")
    print(
        f"  n moved <=1pp: {int(full_rate['n_no_move_pt1pp'])} "
        f"({pct(full_rate['frac_no_move_pt1pp'])})"
    )
    print(f"trailing {TRAILING_WINDOW} (external-tracker style):")
    print(
        f"  {trailing['beat_n']}/{trailing['n']} beating CLV "
        f"({pct(trailing['beat_rate'])})"
    )
    print(f"wrote {JSON_OUT.name} / {PARQUET_OUT.name}")


if __name__ == "__main__":
    main()
