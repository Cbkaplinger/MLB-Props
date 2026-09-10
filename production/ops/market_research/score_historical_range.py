"""Batch-score frozen bundle over a historical date range (post hoc, research).

Loops predict_slate --historical-date logic per date (L3 rows, no scrape),
appends to ONE consolidated parquet so the model is never re-spun:
  artifacts/live_scores/historical_scores_2025_2026.parquet (ignored)

Resume: dates already in the parquet are skipped. Lineage columns
(bundle stems/sha, calibration version, scored_utc) ride on every row.
Writes NOTHING live. Full 2025-2026 run takes a while; sample first:
  python production/ops/market_research/score_historical_range.py --sample 3
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from Python.live_assembly import historical_training_rows, score_frame  # noqa: E402
from Python.count_layer import PROJECTION_K_LINES  # noqa: E402
from join_keys import sorted_key  # noqa: E402

OUT = ROOT / "artifacts" / "live_scores" / "historical_scores_2025_2026.parquet"


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2025-03-27")
    ap.add_argument("--end", default="2026-09-09")
    ap.add_argument("--sample", type=int, default=0,
                    help="score only every Nth date with rows (timing probe)")
    args = ap.parse_args()

    done: set[str] = set()
    if OUT.exists():
        try:
            done = set(pl.scan_parquet(OUT).select("gd").collect()["gd"].unique().to_list())
        except Exception:
            pass
    print(f"resume: {len(done)} dates already scored; output {OUT}")

    import pandas as pd  # noqa: E402
    from datetime import datetime, timezone  # noqa: E402

    stamp = datetime.now(timezone.utc).isoformat()
    n_new, n_skip = 0, 0
    frames: list[pl.DataFrame] = []
    for i, d in enumerate(daterange(date.fromisoformat(args.start), date.fromisoformat(args.end))):
        s = d.isoformat()
        if s in done:
            n_skip += 1
            continue
        try:
            frame = historical_training_rows(d)
        except Exception as e:
            print(f"{s}: no L3 rows ({str(e)[:80]})")
            continue
        if len(frame) == 0:
            continue
        if args.sample and (i % args.sample != 0):
            continue
        scored, report = score_frame(frame, lines=PROJECTION_K_LINES)
        pdf = scored.copy()
        pdf["gd"] = s
        pdf["key_sorted"] = [sorted_key(x) for x in pdf["player_name"].astype(str)]
        pdf["scored_utc"] = stamp
        pdf["calibration_version"] = report.get("calibration_version", "")
        frames.append(pl.from_pandas(pdf))
        n_new += len(pdf)
        print(f"{s}: scored {len(pdf)} rows")
        if len(frames) >= 10:  # checkpoint every 10 dates
            out = pl.concat(frames, how="diagonal_relaxed")
            if OUT.exists():
                out = pl.concat([pl.read_parquet(OUT), out], how="diagonal_relaxed")
            out.write_parquet(OUT)
            frames = []
    if frames:
        out = pl.concat(frames, how="diagonal_relaxed")
        if OUT.exists():
            out = pl.concat([pl.read_parquet(OUT), out], how="diagonal_relaxed")
        out.write_parquet(OUT)
    print(f"done: +{n_new} rows, {n_skip} dates skipped, output {OUT}")


if __name__ == "__main__":
    main()
