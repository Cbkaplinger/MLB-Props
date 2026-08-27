"""Compact and retain aux quote history for non-K watcher markets."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
ODDS_DIR = ROOT / "artifacts" / "odds_log"
AUX_QUOTES_PATH = ODDS_DIR / "watcher_aux_quotes.parquet"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retention-days", type=int, default=120)
    args = p.parse_args()

    if not AUX_QUOTES_PATH.exists():
        print(f"skip: missing {AUX_QUOTES_PATH}")
        return

    df = pl.read_parquet(AUX_QUOTES_PATH)
    before = int(df.height)
    if df.is_empty() or "logged_at_utc" not in df.columns:
        print(f"skip: no rows or logged_at_utc missing ({AUX_QUOTES_PATH})")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, args.retention_days))).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    key_cols = [
        c
        for c in [
            "logged_at_utc",
            "market_stat",
            "event_id",
            "player_name",
            "sportsbook",
            "selection_type",
            "line",
            "odds_american",
        ]
        if c in df.columns
    ]
    out = (
        df.with_columns(pl.col("logged_at_utc").cast(pl.Utf8))
        .filter(pl.col("logged_at_utc") >= cutoff)
        .unique(subset=key_cols, keep="last")
        .sort("logged_at_utc")
    )
    after = int(out.height)
    out.write_parquet(AUX_QUOTES_PATH)
    print(
        f"compacted {AUX_QUOTES_PATH.name}: before={before} after={after} "
        f"retention_days={args.retention_days}"
    )


if __name__ == "__main__":
    main()

