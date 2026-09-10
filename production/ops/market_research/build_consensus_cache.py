"""Precompute devig-median consensus panels (local compute, $0 re-spend).

Per (market, snapshot, gd, key, line): fair-over median + n_books.
Markets: pitcher_strikeouts, pitcher_outs (two-way only; alts are over-only).
Snapshots: close, morning. Writes data/Odds-Historical/theoddsapi/
consensus_cache.parquet (ignored) + reuses join_keys event-date cache.

All research scripts should read this instead of re-devigging per run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.odds_ledger import atomic_write_parquet  # noqa: E402
from analyze_book_skill import _devig_pair  # noqa: E402
from join_keys import HIST, load_event_date_map, sorted_key  # noqa: E402

OUT = HIST / "consensus_cache.parquet"


def main() -> None:
    evdate = load_event_date_map()
    bk = pl.scan_parquet(HIST / "book_lines_pitcher.parquet").filter(
        pl.col("market").is_in(["pitcher_strikeouts", "pitcher_outs"])).collect()
    over = bk.filter(pl.col("side") == "over").select(
        ["event_id", "market", "snapshot", "player_norm", "line", "book", "price"])
    under = bk.filter(pl.col("side") == "under").select(
        ["event_id", "market", "snapshot", "player_norm", "line", "book", "price"])
    pairs = over.join(under, on=["event_id", "market", "snapshot", "player_norm", "line", "book"],
                      suffix="_u")
    rows = []
    for r in pairs.to_dicts():
        fo, _ = _devig_pair(r["price"], r["price_u"])
        if fo is None:
            continue
        gd = evdate.get(r["event_id"], "")
        if not gd:
            continue
        rows.append({"market": r["market"], "snapshot": r["snapshot"], "gd": gd,
                     "key": sorted_key(r["player_norm"]), "line": float(r["line"]), "fair": fo})
    pf = pl.DataFrame(rows)
    agg = pf.group_by(["market", "snapshot", "gd", "key", "line"]).agg(
        pl.col("fair").median().alias("fair"), pl.len().alias("n_books"))
    atomic_write_parquet(agg, OUT)
    print(f"consensus props: {agg.height} -> {OUT}")
    print(agg.group_by(["market", "snapshot"]).len().sort(["market", "snapshot"]).to_dicts())


if __name__ == "__main__":
    main()
