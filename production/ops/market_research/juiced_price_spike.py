"""Juiced-price spike: attach real morning prices to universe rows (read-only).

October v2 must speak JUICED edges (live floors are juiced; the harness
speaks fair). This proves the join and measures the translation:
DK else FD else book-median morning price per (gd, key, line) on 2026
close-matched universe rows; edge_juiced - edge_fair distribution.

Writes artifacts/odds_log/juiced_price_spike.json. No live change.
Success (#98): >= 70% DK/FD coverage.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.market import american_to_implied_prob  # noqa: E402
from Python.odds_ledger import atomic_write_text  # noqa: E402
from join_keys import HIST, ODDS_DIR, load_event_date_map, sorted_key  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()
    evdate = load_event_date_map()
    uni = pl.read_parquet(ODDS_DIR / "universe_panel_live.parquet").filter(
        pl.col("p_book_close").is_not_null()
        & pl.col("p_ours_cal").is_not_null()
        & pl.col("p_book_morning").is_not_null()
        & (pl.col("gd").str.slice(0, 4) == "2026"))
    print(f"2026 universe rows: {uni.height}")
    bk = pl.scan_parquet(HIST / "book_lines_pitcher.parquet").filter(
        (pl.col("market") == "pitcher_strikeouts")
        & (pl.col("snapshot") == "morning")
        & (pl.col("side") == "over")).collect().with_columns(
        pl.col("event_id").map_elements(lambda e: evdate.get(e, ""),
                                        return_dtype=pl.Utf8).alias("gd"),
        pl.col("player_norm").map_elements(sorted_key,
                                           return_dtype=pl.Utf8).alias("key"))
    bk = bk.filter(pl.col("gd") != "")
    print(f"morning over rows: {bk.height}")
    dk = bk.filter(pl.col("book") == "draftkings").select(
        ["gd", "key", "line", "price"]).rename({"price": "dk"})
    fd = bk.filter(pl.col("book") == "fanduel").select(
        ["gd", "key", "line", "price"]).rename({"price": "fd"})
    med = bk.group_by(["gd", "key", "line"]).agg(
        pl.col("price").median().alias("med"))
    j = uni.join(dk, on=["gd", "key", "line"], how="left").join(
        fd, on=["gd", "key", "line"], how="left").join(
        med, on=["gd", "key", "line"], how="left")
    price = j["dk"].fill_null(j["fd"]).fill_null(j["med"])
    src = (pl.when(j["dk"].is_not_null()).then(pl.lit("DK"))
           .when(j["fd"].is_not_null()).then(pl.lit("FD"))
           .otherwise(pl.lit("median"))).alias("src")
    j = j.with_columns(price.alias("dec_price"), src)
    cov = j.filter(pl.col("dec_price").is_not_null())
    print(f"coverage: {cov.height}/{j.height} = {cov.height / j.height:.3f}")
    print("by source:", cov.group_by("src").len().to_dicts())
    pm = cov["p_ours_cal"].to_numpy().astype(float)
    pd = cov["p_book_morning"].to_numpy().astype(float)
    pr = cov["dec_price"].to_numpy().astype(float)
    pj = np.array([float(american_to_implied_prob(x)) for x in pr])
    edge_fair = pm - pd
    edge_juiced = pm - pj
    trans = edge_juiced - edge_fair
    rep = {"generated_utc": datetime.now(timezone.utc).isoformat(),
           "n": int(j.height), "n_priced": int(cov.height),
           "coverage": float(cov.height / j.height),
           "by_source": {r["src"]: r["len"] for r in
                         cov.group_by("src").len().to_dicts()},
           "edge_fair_mean": float(np.mean(edge_fair)),
           "edge_juiced_mean": float(np.mean(edge_juiced)),
           "translation_mean": float(np.mean(trans)),
           "translation_median": float(np.median(trans)),
           "translation_p10": float(np.quantile(trans, 0.10)),
           "translation_p90": float(np.quantile(trans, 0.90))}
    out = ODDS_DIR / "juiced_price_spike.json"
    atomic_write_text(out, json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
